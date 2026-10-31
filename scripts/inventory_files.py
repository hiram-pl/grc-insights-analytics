"""
inventory_files.py
Lists every CSV in an export folder with its row count and column names.
Prints NO cell values, so the output is safe to share even when files contain emails.

Usage (from the repo root):
    python scripts/inventory_files.py data/raw/mailchimp
"""

import re
import sys
from pathlib import Path

import pandas as pd

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)
folder = Path(sys.argv[1])
files = sorted(folder.rglob("*.csv"))
print(f"{len(files)} CSV files under {folder}\n")

for f in files:
    try:
        cols = list(pd.read_csv(f, nrows=0).columns)
        with open(f, encoding="utf-8", errors="ignore") as fh:
            n_rows = sum(1 for _ in fh) - 1
        head = pd.read_csv(f, nrows=200, dtype=str)
        has_emails = head.apply(lambda col: col.str.contains(EMAIL, na=False)).any().any()
        flag = "  [CONTAINS EMAILS - aggregate locally, don't share]" if has_emails else ""
        print(f"{f.relative_to(folder)}  |  {n_rows} rows{flag}\n    columns: {cols}\n")
    except Exception as e:
        print(f"{f.relative_to(folder)}  |  could not read ({e})\n")
