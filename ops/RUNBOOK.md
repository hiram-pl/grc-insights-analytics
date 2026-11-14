# Runbook: the weekly refresh

What runs on its own, what you do, and what to do when something goes wrong.

## TL;DR

You don't need to do anything at 8am Monday. Read the notification when you're next at your Mac.
- **Most weeks:** maybe say "publish the dashboard" in Claude Code (about a minute).
- **About monthly:** drop fresh Substack and LinkedIn exports into `data/inbox/` when the run says they're stale.

## What happens every Monday at 08:00

launchd (`com.grc.insights.refresh`, installed by `ops/install_schedule.sh`) starts `scripts/refresh.py` in the background, with no window. It takes about 4–5 minutes:

1. **Inbox:** files anything dropped into `data/inbox/` during the week and runs its processor.
2. **GA4:** pulls web traffic through yesterday (seconds).
3. **Mailchimp:** pulls every campaign report (about 4 minutes, the slow part).
4. **Freshness:** records how old each source is (`data/processed/freshness.csv`).
5. **Rebuild:** `data/grc.duckdb`, the dashboard CSVs, and the local `data/processed/dashboard/dashboard.html`.
6. **Queue:** lists hosted-dashboard CSVs that changed since the last publish.
7. **Notification:** a macOS banner titled "GRC Insights refresh".

## What the notification means

| Notification says | Meaning | What you do |
|---|---|---|
| "Done: all sources fresh. GA4, Mailchimp up to date" | Everything worked; the hosted dashboard is already current | Nothing |
| "… Hosted dashboard: N files to publish" | New numbers are ready for the shared dashboard link | When convenient, open Claude Code in this repo and say **"publish the dashboard"** (steps in `ops/publish_dashboard_prompt.md`) |
| "Done, with warnings. LinkedIn stale" (or Substack Export / Substack Stats) | A manual export is more than 35 days old | Download it (see below) and drop it into `data/inbox/`. The next run picks it up, or run `python scripts/refresh.py` now |
| "Done, with warnings. Mailchimp failed" (or GA4) | The API pull failed (offline, expired key, API outage). Last week's data was restored and everything else updated | Usually nothing: it retries next Monday. If it repeats, read the newest log in `data/logs/` |
| "FAILED at build_db: dashboard not updated" (or export / dashboard_html) | A build step broke and the run stopped before publishing anything. The most common cause is a notebook or `duckdb` session holding `data/grc.duckdb` open | Close it, then run `python scripts/refresh.py`. If it fails again, read the log |

## When it doesn't run at 08:00

- **Mac asleep or lid closed:** it runs once as soon as the Mac wakes.
- **Mac shut down all Monday, or you're logged out:** that week is skipped. Catch up with `python scripts/refresh.py`, or `launchctl kickstart gui/$(id -u)/com.grc.insights.refresh`.
- **Offline:** the GA4 and Mailchimp pulls fail and keep last week's data. The rest still runs, and you get the "failed" warning.

## Manual exports (when flagged as stale)

Drop each file into `data/inbox/` exactly as downloaded. Don't unzip or rename it.

| Source | Where to get it | File |
|---|---|---|
| Substack account export | Substack > Settings > Exports > New export | `.zip` |
| Substack Stats | Substack > Stats: download the CSVs (email stats, followers, traffic, audience location) | `<pub>_<kind>_YYYY-MM-DD.csv` |
| LinkedIn | Company page > Analytics > Export (content, followers, visitors, competitors) | `.xls` / `.xlsx` |
| Mailchimp export (rarely needed; the API is primary) | Mailchimp > Account > Settings > Manage my data > Export | `.zip` (kept for backfill only) |

Recognized files move to `data/inbox/_done/<date>/`. An unrecognized file stays in the inbox with a warning in the log. A file that fails, for example a Stats CSV containing an email address, also stays there, so the next run retries it.

## Checking on it

```bash
launchctl print gui/$(id -u)/com.grc.insights.refresh | grep "last exit"   # 0 ok, 2 warnings, 1 failed
ls -t data/logs | head -1                                                   # newest run's log (data/logs/)
cat data/processed/freshness.csv                                            # status of each source
tail -30 ~/Library/Logs/grc-insights-refresh.log                            # launchd-level output
duckdb -readonly data/grc.duckdb "FROM pipeline_runs ORDER BY run_id DESC LIMIT 10"
```

## Changing the setup

- **Moved the repo or changed Python:** re-run `zsh ops/install_schedule.sh` (`PYTHON=/path/to/python3` to override).
- **Change the day or time:** edit `StartCalendarInterval` in `ops/com.grc.insights.refresh.plist`, then re-run the install script.
- **Turn it off:** `zsh ops/install_schedule.sh --remove`.
- **New Mailchimp key:** `pbpaste > data/mailchimp-key && chmod 600 data/mailchimp-key`.
- **"Operation not permitted" in the launchd log:** macOS blocked folder access. Give the Python binary Full Disk Access (System Settings > Privacy & Security), or move the repo out of `~/Desktop`, then re-run the install script.
