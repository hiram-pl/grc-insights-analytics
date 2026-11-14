"""
ingest_inbox.py
The drop folder for sources without an API (Substack, LinkedIn). Download an export, drop
it in data/inbox/ as-is (zip or file), and this script works out what it is, files it in
the right place, runs the processing script for it, and moves it to data/inbox/_done/<date>/.

refresh.py runs this first, so dropping a file is all a manual refresh needs.

Usage (from the repo root):
    python scripts/ingest_inbox.py            # process everything in data/inbox/
    python scripts/ingest_inbox.py --dry-run  # only say what would happen

Exit code 0 = nothing to do or all good; 1 = something failed (that file stays in the
inbox so the next run retries it).
Prints no cell values: unknown files are described by name, size and an email flag only.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

from mc_common import EMAIL

REPO = Path(__file__).resolve().parents[1]
INBOX = REPO / "data" / "inbox"
DONE = INBOX / "_done" / date.today().isoformat()
RAW = REPO / "data" / "raw"
PROCESSED = REPO / "data" / "processed"

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()
# Print each line as it happens, so our lines and the follow-up scripts' output stay in
# order when this runs inside refresh.py (piped output is otherwise buffered in blocks).
sys.stdout.reconfigure(line_buffering=True)


# --- What a dropped file looks like: small "matcher" helpers ------------------------------
# Each takes the dropped path and returns True/False. Routes below combine them.

def zip_names(path):
    """File names inside a zip (empty list if it isn't one)."""
    if path.suffix.lower() != ".zip":
        return []
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def zip_has(*patterns):
    """Matcher: a zip containing a file matching EVERY regex, e.g. zip_has(r'posts\\.csv$')."""
    return lambda p: all(any(re.search(pat, n) for n in zip_names(p)) for pat in patterns)


def name_matches(pattern):
    """Matcher: the file name matches a regex, e.g. name_matches(r'\\.xlsx?$')."""
    return lambda p: re.search(pattern, p.name, re.I) is not None


# --- What to do with it: small "action" helpers -------------------------------------------

def safe_extract(zip_path, dest):
    """Unzip into dest, refusing entries that would land outside it (a "zip slip":
    names like ../../.zshrc). Exports are downloaded files, so treat them as untrusted."""
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not (dest / name).resolve().is_relative_to(dest):
                raise ValueError(f"unsafe path in zip: {name}")
        z.extractall(dest)
        # extractall stamps every file with "now"; restore the dates stored in the zip so
        # refresh.py can tell how old an export really is.
        for info in z.infolist():
            ts = datetime(*info.date_time).timestamp()
            os.utime(dest / info.filename, (ts, ts))


def replace_folder_with_zip(dest):
    """Action: full exports (Substack, Mailchimp) REPLACE the previous one.
    The old copy is kept once as <dest>.prev until the next drop, in case the new one is bad."""
    def action(path):
        prev = dest.with_name(dest.name + ".prev")
        if prev.exists():
            shutil.rmtree(prev)
        if dest.exists():
            dest.rename(prev)
        dest.mkdir(parents=True)
        safe_extract(path, dest)
    return action


def copy_into(dest, require_no_emails=False):
    """Action: copy the file into dest, keeping its name (LinkedIn keeps every export;
    Substack Stats files are told apart by the date in their names).
    require_no_emails: refuse files with an email address. Use it whenever dest is under
    data/processed/, which by rule holds only email-free files."""
    def action(path):
        if require_no_emails and EMAIL.search(path.read_text(errors="ignore")):
            raise ValueError("contains an email address; not copying it into data/processed/")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest / path.name)
    return action


# --- Routes: (label, matcher, action, follow-up scripts) ----------------------------------
# The first route whose matcher returns True wins, so put more specific routes first.
# Follow-up scripts run once per inbox run (not once per file), after all files are filed.
#
# Full exports replace the previous copy; per-file exports (LinkedIn, Stats) accumulate.
ROUTES = [
    # Substack account export: the only zip with posts.csv AND an email list in it.
    ("Substack account export",
     zip_has(r"(^|/)posts\.csv$", r"(^|/)email_list\.[^/]+\.csv$"),
     replace_folder_with_zip(RAW / "substack"),
     ["aggregate_opens.py", "hash_subscribers.py"]),

    # Mailchimp account export: campaigns.csv plus per-audience lists/ files.
    # No follow-up on purpose: aggregate_mailchimp.py writes data/processed/mailchimp/, which
    # would overwrite pull_mailchimp.py's fresher API data. The raw export is kept for backfill.
    ("Mailchimp account export",
     zip_has(r"(^|/)campaigns\.csv$", r"(^|/)lists/"),
     replace_folder_with_zip(RAW / "mailchimp"),
     []),

    # Substack Stats-page CSVs: <pub>_<kind>_YYYY-MM-DD.csv. Aggregates, so they may go
    # straight into data/processed/, but only after the no-email check.
    ("Substack Stats export",
     name_matches(r"_(email_stats|followers|traffic|audience_location)_\d{4}-\d{2}-\d{2}\.csv$"),
     copy_into(PROCESSED / "substack_stats", require_no_emails=True),
     []),

    ("LinkedIn export",
     name_matches(r"\.xlsx?$"),
     copy_into(RAW / "linkedin"),
     ["process_linkedin.py"]),
]


# --- Main loop ----------------------------------------------------------------------------

def describe(path):
    """Safe one-line description of a file we don't recognize: no values printed."""
    flag = ""
    if path.suffix.lower() in {".csv", ".txt"} and EMAIL.search(path.read_text(errors="ignore")):
        flag = "  [CONTAINS EMAILS]"
    elif path.suffix.lower() == ".zip":
        flag = f"  [zip, {len(zip_names(path))} files]"
    return f"{path.name} ({path.stat().st_size:,} bytes){flag}"


INBOX.mkdir(parents=True, exist_ok=True)
dropped = sorted(p for p in INBOX.iterdir() if p.is_file() and not p.name.startswith("."))
if not dropped:
    print("Inbox empty: nothing to ingest.")
    sys.exit(0)

followups, failed, updated = [], False, []
for path in dropped:
    route = next((r for r in ROUTES if r[1](path)), None)
    if route is None:
        print(f"?  Unrecognized, left in inbox: {describe(path)}")
        continue
    label, _, action, scripts = route
    print(f"-> {path.name}: {label}")
    if args.dry_run:
        continue
    try:
        action(path)
    except Exception as e:  # keep going with other files; this one stays for a retry
        print(f"   FAILED: {e}")
        failed = True
        continue
    DONE.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), DONE / path.name)
    updated.append(label)
    followups += [s for s in scripts if s not in followups]

for script in followups:
    print(f"\n== {script}")
    result = subprocess.run([sys.executable, str(REPO / "scripts" / script)], cwd=REPO)
    if result.returncode != 0:
        print(f"   FAILED: {script} exited with {result.returncode}")
        failed = True

# One machine-readable summary line for refresh.py to pick up.
print(f"\nINGESTED: {', '.join(sorted(set(updated))) or 'nothing'}")
sys.exit(1 if failed else 0)
