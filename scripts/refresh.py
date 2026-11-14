"""
refresh.py
One command for the whole weekly refresh. launchd runs it every Monday; you can run it any time.

    1. ingest_inbox     file any exports dropped into data/inbox/ (Substack, LinkedIn)
    2. pull_ga4         GA4 Data API
    3. pull_mailchimp   Mailchimp Marketing API
    4. freshness        how old each source is -> data/processed/freshness.csv
    5. build_db         processed CSVs -> data/grc.duckdb
    6. export           DB -> dashboard CSVs
    7. dashboard_html   CSVs -> standalone dashboard.html
    8. dashboard_queue  list dashboard CSVs that changed since the hosted dashboard was last
                        published; you then say "publish the dashboard" in Claude Code

Failure policy:
    - Source steps (1-3) may fail: the source keeps last run's data (the pull's output
      folder is restored from a snapshot, so a half-finished pull never mixes old and new
      files), it's marked "failed" in freshness.csv, and the run carries on.
    - Build steps (5-7) must succeed: if one fails the run stops and nothing is published,
      so the dashboard never shows a half-built database.

Every run writes data/logs/refresh_<timestamp>.log, appends one row per step to
data/processed/pipeline_runs.csv, and ends with a macOS notification.
Exit code: 0 all good, 2 finished but a source failed or is stale, 1 a build step failed.

Usage (from the repo root):
    python scripts/refresh.py               # everything
    python scripts/refresh.py --no-pulls    # skip the API pulls (offline / quick rebuild)
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
PROCESSED = DATA / "processed"
LOGS = DATA / "logs"
LOCK = DATA / ".refresh.lock"
RUNS = PROCESSED / "pipeline_runs.csv"
FRESHNESS = PROCESSED / "freshness.csv"
EMAIL = re.compile(r"[^@\s,;:<>\"']+@[^@\s,;:<>\"']+\.[a-z]{2,}", re.I)

parser = argparse.ArgumentParser()
parser.add_argument("--no-pulls", action="store_true", help="skip the GA4 and Mailchimp pulls")
args = parser.parse_args()

run_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
LOGS.mkdir(parents=True, exist_ok=True)
log = (LOGS / f"refresh_{datetime.now():%Y-%m-%d_%H%M}.log").open("w")


def say(line=""):
    """Print to the terminal and the log."""
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()


# --- Lock: never let two refreshes run at once (e.g. launchd + you by hand) ---------------
def take_lock():
    if LOCK.exists():
        pid = int(LOCK.read_text().strip() or 0)
        try:
            os.kill(pid, 0)            # signal 0 = "are you alive?", doesn't touch the process
            sys.exit(f"Another refresh is running (pid {pid}). If it isn't, delete {LOCK.relative_to(REPO)}.")
        except (ProcessLookupError, ValueError):
            pass                       # stale lock from a crashed run: take it over
    LOCK.write_text(str(os.getpid()))


# --- Running one step ---------------------------------------------------------------------
def run_script(script, *script_args):
    """Run scripts/<script>, streaming its output to terminal + log. Returns (ok, last_line)."""
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "scripts" / script), *script_args], cwd=REPO,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"})
    last = ""
    for line in proc.stdout:
        say("   " + line.rstrip())
        if line.strip():
            last = line.strip()
    return proc.wait() == 0, last


def snapshot(folder):
    """Copy a folder aside so a failed pull can be undone. Returns the copy's path (or None)."""
    if not folder.exists():
        return None
    tmp = Path(tempfile.mkdtemp(prefix="grc-refresh-")) / folder.name
    shutil.copytree(folder, tmp)
    return tmp


def restore(folder, copy):
    if copy is None:
        return
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(copy, folder)


# --- Freshness: how old is each source? ----------------------------------------------------
STALE_AFTER = {"api": 8, "manual": 35}  # days; APIs should be at most a week old


def mtime_date(path):
    return date.fromtimestamp(path.stat().st_mtime) if path.exists() else None


def build_freshness(status_by_step):
    """One row per source: when the data was last updated, what date it runs through, and
    whether it's ok / stale / failed / missing. Written to data/processed/freshness.csv."""
    today, rows = date.today(), []

    def add(source, kind, updated, through, todo, step=None):
        age = (today - updated).days if updated else None
        if updated is None:
            status = "missing"
        elif step and status_by_step.get(step) == "failed":
            status = "failed"
        elif age > STALE_AFTER[kind]:
            status = "stale"
        else:
            status = "ok"
        rows.append({"source": source, "kind": kind, "status": status,
                     "updated_on": updated, "data_through": through, "age_days": age,
                     "action": "" if status == "ok" else todo})

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    ga4 = PROCESSED / "ga4" / "traffic_daily.csv"
    add("GA4", "api", mtime_date(ga4),
        safe(lambda: pd.read_csv(ga4, usecols=["date"])["date"].max()),
        "check data/logs for the pull_ga4 error", "pull_ga4")

    mc = PROCESSED / "mailchimp" / "campaigns.csv"
    add("Mailchimp", "api", mtime_date(mc), mtime_date(mc),
        "check data/logs for the pull_mailchimp error", "pull_mailchimp")

    # Substack account export: the email list's date inside the export zip.
    lst = next(iter(sorted((DATA / "raw" / "substack").rglob("email_list*.csv"))), None)
    add("Substack export", "manual", mtime_date(lst) if lst else None,
        safe(lambda: pd.read_csv(PROCESSED / "posts.csv", usecols=["email_sent_at"])["email_sent_at"].dropna().max()[:10]),
        "Substack > Settings > Exports > New export, then drop the zip in data/inbox/", "ingest_inbox")

    # Substack Stats page: the date in the newest file name, and its last day of data.
    stats = sorted((PROCESSED / "substack_stats").glob("*_followers_*.csv"))
    add("Substack Stats", "manual",
        safe(lambda: date.fromisoformat(stats[-1].stem[-10:])),
        safe(lambda: pd.read_csv(stats[-1], header=None)[0].iloc[-1].replace("/", "-")),
        "download the Stats page CSVs and drop them in data/inbox/", "ingest_inbox")

    li = PROCESSED / "linkedin" / "daily.csv"
    li_df = safe(lambda: pd.read_csv(li, usecols=["date", "exported_at"]))
    add("LinkedIn", "manual",
        safe(lambda: pd.to_datetime(li_df["exported_at"]).max().date()),
        safe(lambda: li_df["date"].max()),
        "LinkedIn page > Analytics > Export (content, followers, visitors), drop in data/inbox/", "ingest_inbox")

    pd.DataFrame(rows).to_csv(FRESHNESS, index=False)
    return rows


# --- The run --------------------------------------------------------------------------------
STEPS = [
    # (name, script, must_succeed, folder to snapshot and restore if it fails)
    ("ingest_inbox", "ingest_inbox.py", False, None),
    ("pull_ga4", "pull_ga4.py", False, PROCESSED / "ga4"),
    ("pull_mailchimp", "pull_mailchimp.py", False, PROCESSED / "mailchimp"),
    ("freshness", None, True, None),
    ("build_db", "build_db.py", True, None),
    ("export", "export_dashboard_data.py", True, None),
    ("dashboard_html", "build_dashboard_html.py", True, None),
]
# Queue changed CSVs for the hosted dashboard (uploading needs an interactive Claude session).
STEPS.append(("dashboard_queue", "publish_dashboard.py", False, None))


def notify(title, message):
    """macOS notification banner (silently skipped if osascript isn't available)."""
    message = message.replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                   capture_output=True)


take_lock()
status_by_step, results, stopped = {}, [], False
try:
    say(f"GRC Insights refresh {run_id}")
    for name, script, must_succeed, protect in STEPS:
        if args.no_pulls and name.startswith("pull_"):
            status_by_step[name] = "skipped"
            results.append((name, "skipped", 0.0, "--no-pulls"))
            continue
        say(f"\n== {name}")
        start = time.time()
        backup = snapshot(protect) if protect else None
        try:
            if name == "freshness":
                rows = build_freshness(status_by_step)
                for r in rows:
                    say(f"   {r['source']:16} {r['status']:8} updated {r['updated_on']}, data through {r['data_through']}")
                ok, note = True, f"{sum(r['status'] == 'ok' for r in rows)} of {len(rows)} sources ok"
            else:
                ok, note = run_script(script)
        except Exception as e:      # a crash inside refresh.py itself counts as a failed step
            ok, note = False, f"{type(e).__name__}: {e}"
            say("   " + note)
        if backup is not None:
            if not ok:
                restore(protect, backup)
                say(f"   restored last run's {protect.relative_to(REPO)}/")
            shutil.rmtree(backup.parent, ignore_errors=True)
        seconds = round(time.time() - start, 1)
        status = "ok" if ok else "failed"
        status_by_step[name] = status
        results.append((name, status, seconds, EMAIL.sub("[email]", note)[:200]))
        say(f"   -> {status} in {seconds}s")
        if not ok and must_succeed:
            if "lock" in note.lower():
                say("   Hint: close notebooks / duckdb sessions that have data/grc.duckdb open, then re-run.")
            stopped = True
            break
finally:
    # Always record what happened, even if the run stopped or crashed.
    new = not RUNS.exists()
    with RUNS.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_id", "step", "status", "seconds", "note"])
        w.writerows([run_id, *r] for r in results)
    LOCK.unlink(missing_ok=True)

# --- Summary -------------------------------------------------------------------------------
fresh = pd.read_csv(FRESHNESS) if FRESHNESS.exists() else pd.DataFrame(columns=["source", "status", "age_days", "action"])
problems = fresh[fresh["status"] != "ok"]
failed_steps = [n for n, s, *_ in results if s == "failed"]
say("\n== summary")
if stopped:
    headline = f"FAILED at {failed_steps[-1]}: dashboard not updated"
elif failed_steps or not problems.empty:
    headline = "Done, with warnings"
else:
    headline = "Done: all sources fresh"
say(headline)
for _, p in problems.iterrows():
    say(f"   {p['source']}: {p['status']} ({p['age_days']} days old). {p['action']}")
pending_file = PROCESSED / "dashboard" / ".pending_publish.json"
n_pending = 0
if not stopped and pending_file.exists():
    n_pending = len(json.loads(pending_file.read_text())["files"])
    say(f"Hosted dashboard: {n_pending} files changed. In Claude Code, say \"publish the dashboard\".")
say(f"Log: {Path(log.name).relative_to(REPO)}")
log.close()

detail = "; ".join(f"{p['source']} {p['status']}" for _, p in problems.iterrows()) or "GA4, Mailchimp up to date"
if n_pending:
    detail += f". Hosted dashboard: {n_pending} files to publish"
notify("GRC Insights refresh", f"{headline}. {detail}")
sys.exit(1 if stopped else 2 if (failed_steps or not problems.empty) else 0)
