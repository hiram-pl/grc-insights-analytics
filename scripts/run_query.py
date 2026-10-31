"""
run_query.py
Runs a saved .sql file against the database and prints the result.

Usage (from the repo root):
    python scripts/run_query.py sql/open_rate_by_send_day.sql
    python scripts/run_query.py sql/open_rate_by_batch_size.sql --sample
"""

import argparse
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("sql_file")
parser.add_argument("--sample", action="store_true", help="query the fake sample database")
args = parser.parse_args()

db_path = REPO / ("sample_data/sample.duckdb" if args.sample else "data/grc.duckdb")
con = duckdb.connect(str(db_path), read_only=True)
print(con.sql(Path(args.sql_file).read_text()).df().to_string(index=False))
