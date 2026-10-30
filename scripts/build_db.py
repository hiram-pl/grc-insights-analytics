"""
build_db.py
Builds the DuckDB database from the processed (email-free) CSVs.
Safe to re-run: every table is rebuilt from scratch.

Usage (from the repo root):
    python scripts/build_db.py                 # real data: data/processed/ -> data/grc.duckdb
    python scripts/build_db.py --sample        # fake data: sample_data/   -> sample_data/sample.duckdb
"""

import argparse
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("--sample", action="store_true", help="use the fake data in sample_data/")
args = parser.parse_args()

if args.sample:
    data_dir, db_path = REPO / "sample_data", REPO / "sample_data" / "sample.duckdb"
else:
    data_dir, db_path = REPO / "data" / "processed", REPO / "data" / "grc.duckdb"

posts_csv = (data_dir / "posts.csv").as_posix()
opens_csv = (data_dir / "per_post_opens.csv").as_posix()

con = duckdb.connect(str(db_path))

con.sql(f"""
-- One row per Substack post. post_number = numeric part of post_id, used for joins.
CREATE OR REPLACE TABLE posts AS
SELECT
    split_part(post_id, '.', 1)::BIGINT          AS post_number,
    post_id,
    title,
    subtitle,
    try_cast(post_date AS TIMESTAMPTZ)            AS published_at,
    try_cast(email_sent_at AS TIMESTAMPTZ)        AS emailed_at,
    is_published
FROM read_csv_auto('{posts_csv}');

-- Per-post email stats (no email addresses).
CREATE OR REPLACE TABLE opens AS
SELECT * FROM read_csv_auto('{opens_csv}');

-- Analysis table: every emailed post with its stats and how crowded its send day was.
CREATE OR REPLACE TABLE email_posts AS
SELECT
    p.post_number,
    p.title,
    p.subtitle,
    p.emailed_at,
    CAST(p.emailed_at AS DATE)                                        AS send_day,
    o.recipients,
    o.unique_openers,
    o.total_opens,
    o.open_rate,
    COUNT(*)     OVER (PARTITION BY CAST(p.emailed_at AS DATE))       AS batch_size,
    ROW_NUMBER() OVER (PARTITION BY CAST(p.emailed_at AS DATE)
                       ORDER BY p.emailed_at)                         AS position_in_batch
FROM posts p
JOIN opens o USING (post_number);
""")

# Sanity check: every opens row should match a post (anti-join).
unmatched = con.sql("""
    SELECT COUNT(*) FROM opens o LEFT JOIN posts p USING (post_number)
    WHERE p.post_number IS NULL
""").fetchall()[0][0]
print(f"Built {db_path.relative_to(REPO)}")
print(f"Opens rows with no matching post: {unmatched} (should be 0)")
con.close()
