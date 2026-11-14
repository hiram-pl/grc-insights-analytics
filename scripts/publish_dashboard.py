"""
publish_dashboard.py
Tracks which dashboard CSVs changed since they were last published to the Claude-hosted
dashboard, so a publish uploads only those.

Why not fully automatic: uploading to a Claude artifact needs Claude Code's Artifact tools,
which exist only in interactive sessions (not in headless `claude -p`; checked with Claude Code
2.1.325). So the weekly refresh queues the changes and notifies you, and you say
"publish the dashboard" in Claude Code, which follows ops/publish_dashboard_prompt.md.

Usage (from the repo root):
    python scripts/publish_dashboard.py                    # list changed CSVs -> .pending_publish.json
    python scripts/publish_dashboard.py --mark-published   # after a successful publish: save their hashes

Only aggregated, email-free CSVs in data/processed/dashboard/ are ever listed.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DASH = REPO / "data" / "processed" / "dashboard"
HASHES = DASH / ".published_hashes.json"   # what the hosted dashboard has now
PENDING = DASH / ".pending_publish.json"   # what changed and still needs publishing

parser = argparse.ArgumentParser()
parser.add_argument("--mark-published", action="store_true",
                    help="record the pending files as published (run after the upload succeeded)")
args = parser.parse_args()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


published = json.loads(HASHES.read_text()) if HASHES.exists() else {}

if args.mark_published:
    if not PENDING.exists():
        sys.exit("Nothing pending: run publish_dashboard.py first.")
    pending = json.loads(PENDING.read_text())
    # Save the hashes recorded when the list was made. If a file changed again since, its
    # new hash won't match and it simply shows up as changed next time.
    published.update(pending["files"])
    HASHES.write_text(json.dumps(published, indent=2, sort_keys=True))
    PENDING.unlink()
    print(f"Marked {len(pending['files'])} files as published.")
    sys.exit(0)

current = {f.name: sha256(f) for f in sorted(DASH.glob("*.csv"))}
changed = {name: h for name, h in current.items() if published.get(name) != h}
if not changed:
    PENDING.unlink(missing_ok=True)
    print("Hosted dashboard up to date: no CSV changed since the last publish.")
    sys.exit(0)

PENDING.write_text(json.dumps({"listed_at": datetime.now().isoformat(timespec="seconds"),
                               "files": changed}, indent=2))
print(f"{len(changed)} dashboard files waiting to publish: {', '.join(changed)}")
print('To publish: open Claude Code in this repo and say "publish the dashboard".')
