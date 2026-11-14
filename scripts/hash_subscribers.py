"""
hash_subscribers.py
Builds subscriber-level tables for cohort analysis WITHOUT email addresses.
Each email is replaced by a keyed hash (HMAC-SHA256, truncated), so the same person
gets the same sub_id across posts but the id can't be turned back into an email
without the secret key.

The key lives in data/.subscriber_hash_key (git-ignored, created on first run).
Keep it on the data owner's machine: anyone with the key and a list of emails could
re-link ids to people. Re-use the same key on later exports so ids stay stable.

Outputs (data/processed/, git-ignored):
    subscribers.csv      sub_id, signed_up_at, active_subscription, email_disabled, on_list
                         one row per address in the email list or any delivery file
    sub_deliveries.csv   sub_id, post_number, opened, first_open_at
                         one row per email delivered (opened = at least one open)

Usage (from the repo root):
    python scripts/hash_subscribers.py                       # reads data/raw/substack/
    python scripts/hash_subscribers.py path/to/unzipped_export
"""

import hashlib
import hmac
import secrets
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
export_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "raw" / "substack"
out_dir = REPO / "data" / "processed"
out_dir.mkdir(parents=True, exist_ok=True)

key_file = REPO / "data" / ".subscriber_hash_key"
if not key_file.exists():
    key_file.write_text(secrets.token_hex(32))
    key_file.chmod(0o600)
    print(f"Created a new hash key at {key_file.relative_to(REPO)} (keep it private, don't delete it)")
KEY = bytes.fromhex(key_file.read_text().strip())


def sub_id(email: str) -> str:
    return hmac.new(KEY, email.strip().lower().encode(), hashlib.sha256).hexdigest()[:16]


opens = sorted(export_dir.rglob("*.opens.csv"))
delivers = sorted(export_dir.rglob("*.delivers.csv"))
email_list = next(iter(export_dir.rglob("email_list*.csv")), None)
if not delivers:
    sys.exit(f"No *.delivers.csv files under {export_dir.resolve()}.")

con = duckdb.connect()  # in-memory: emails never touch disk
con.create_function("sub_id", sub_id, ["VARCHAR"], "VARCHAR")


def files(paths):
    return "[" + ", ".join(f"'{p.as_posix()}'" for p in paths) + "]"


# post_number comes from the file name ('200141804.delivers.csv'), same as aggregate_opens.py.
con.sql(f"""
CREATE TABLE d AS
SELECT DISTINCT sub_id(email) AS sub_id,
       split_part(parse_filename(filename), '.', 1)::BIGINT AS post_number
FROM read_csv({files(delivers)}, filename = true, all_varchar = true, union_by_name = true)
WHERE email IS NOT NULL
""")
con.sql(f"""
CREATE TABLE o AS
SELECT sub_id(email) AS sub_id,
       split_part(parse_filename(filename), '.', 1)::BIGINT AS post_number,
       MIN(try_cast(timestamp AS TIMESTAMPTZ)) AS first_open_at
FROM read_csv({files(opens)}, filename = true, all_varchar = true, union_by_name = true)
WHERE email IS NOT NULL
GROUP BY ALL
""")

con.sql(f"""
COPY (
    SELECT d.sub_id, d.post_number, o.sub_id IS NOT NULL AS opened, o.first_open_at
    FROM d LEFT JOIN o USING (sub_id, post_number)
    ORDER BY post_number, sub_id
) TO '{(out_dir / "sub_deliveries.csv").as_posix()}' (HEADER)
""")

orphan_opens = con.sql("SELECT COUNT(*) FROM o ANTI JOIN d USING (sub_id, post_number)").fetchall()[0][0]

if email_list:
    con.sql(f"""
    CREATE TABLE l AS
    SELECT sub_id(email) AS sub_id,
           MIN(try_cast(created_at AS TIMESTAMPTZ)) AS signed_up_at,
           bool_or(active_subscription::BOOLEAN) AS active_subscription,
           bool_or(email_disabled::BOOLEAN) AS email_disabled
    FROM read_csv('{email_list.as_posix()}', all_varchar = true)
    WHERE email IS NOT NULL
    GROUP BY 1
    """)
else:
    print("No email_list*.csv found: signup dates will be missing for everyone.")
    con.sql("CREATE TABLE l (sub_id VARCHAR, signed_up_at TIMESTAMPTZ, "
            "active_subscription BOOLEAN, email_disabled BOOLEAN)")

# Everyone who is on the list or ever got an email. on_list = false means they have
# left the list since (unsubscribed or deleted), so their signup date is unknown.
con.sql(f"""
COPY (
    SELECT sub_id, l.signed_up_at, l.active_subscription, l.email_disabled,
           l.sub_id IS NOT NULL AS on_list
    FROM (SELECT sub_id FROM l UNION SELECT sub_id FROM d) ids
    LEFT JOIN l USING (sub_id)
    ORDER BY sub_id
) TO '{(out_dir / "subscribers.csv").as_posix()}' (HEADER)
""")

n_subs, n_list = con.sql("SELECT (SELECT COUNT(DISTINCT sub_id) FROM d), (SELECT COUNT(*) FROM l)").fetchall()[0]
n_del = con.sql("SELECT COUNT(*) FROM d").fetchall()[0][0]
print(f"{len(delivers)} posts, {n_del:,} deliveries to {n_subs} addresses; {n_list} addresses on the current list")
if orphan_opens:
    print(f"  {orphan_opens} opens had no matching delivery (dropped)")
print("Wrote data/processed/subscribers.csv and sub_deliveries.csv. No email addresses included.")

con.close()  # explicit close: DuckDB 2.0 prints nanobind "leaked" warnings if left open at exit
