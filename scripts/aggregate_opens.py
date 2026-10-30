"""
aggregate_opens.py
Turns Substack's per-post open/delivery files (which contain email addresses)
into one per-post summary table with NO email addresses, and copies posts.csv
(post metadata, no emails) into data/processed/.

Usage (from the repo root):
    python scripts/aggregate_opens.py                      # reads data/raw/substack/
    python scripts/aggregate_opens.py path/to/unzipped_export
"""

import shutil
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
export_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "raw" / "substack"
out_dir = REPO / "data" / "processed"
out_dir.mkdir(parents=True, exist_ok=True)


def find_col(df, keywords):
    """Return the first column whose name contains any of the keywords."""
    for col in df.columns:
        if any(k in col.lower() for k in keywords):
            return col
    return None


def post_number(path):
    """'200141804.opens.csv' -> '200141804' (the numeric part of post_id)."""
    return path.name.split(".")[0]


open_files = sorted(export_dir.rglob("*.opens.csv"))
deliver_files = {post_number(f): f for f in export_dir.rglob("*.delivers.csv")}

if not open_files:
    sys.exit(f"No *.opens.csv files found under {export_dir.resolve()}. Check the path.")

# Show column names (never row contents) so you can confirm the format.
sample = pd.read_csv(open_files[0], nrows=0)
print(f"Found {len(open_files)} opens files. Columns in the first one: {list(sample.columns)}")

rows = []
for f in open_files:
    df = pd.read_csv(f)
    email_col = find_col(df, ["email"])
    time_col = find_col(df, ["timestamp", "opened", "date", "time"])

    row = {
        "post_number": post_number(f),
        "total_opens": len(df),  # includes repeat opens by the same person
        "unique_openers": df[email_col].nunique() if email_col else None,
    }
    if time_col:
        times = pd.to_datetime(df[time_col], errors="coerce", utc=True)
        row["first_open_at"] = times.min()
        row["last_open_at"] = times.max()

    d = deliver_files.get(row["post_number"])
    if d is not None:
        deliveries = pd.read_csv(d)
        d_email = find_col(deliveries, ["email"])
        row["recipients"] = deliveries[d_email].nunique() if d_email else len(deliveries)

    rows.append(row)

summary = pd.DataFrame(rows)
if "recipients" in summary:
    summary["open_rate"] = (summary["unique_openers"] / summary["recipients"]).round(4)

summary.to_csv(out_dir / "per_post_opens.csv", index=False)
print(f"Wrote data/processed/per_post_opens.csv ({len(summary)} posts). No email addresses included.")

posts = list(export_dir.rglob("posts.csv"))
if posts:
    shutil.copy(posts[0], out_dir / "posts.csv")
    print("Copied posts.csv to data/processed/")
else:
    print("posts.csv not found in the export; copy it into data/processed/ yourself.")
