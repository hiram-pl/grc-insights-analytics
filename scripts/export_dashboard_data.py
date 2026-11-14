"""
export_dashboard_data.py
Writes the small, aggregated CSVs the GRC Insights Growth Dashboard reads.
Run after build_db.py; re-upload the CSVs to the dashboard whenever you refresh.

Usage (from the repo root):
    python scripts/export_dashboard_data.py            # -> data/processed/dashboard/
    python scripts/export_dashboard_data.py --sample   # -> sample_data/dashboard/
"""

import argparse
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--sample", action="store_true")
args = parser.parse_args()

db = REPO / ("sample_data/sample.duckdb" if args.sample else "data/grc.duckdb")
out = REPO / ("sample_data/dashboard" if args.sample else "data/processed/dashboard")
out.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(db), read_only=True)

# Fail early, with the fix, if build_db.py hasn't created a table the dashboard needs.
NEEDS = {
    "posts": "Substack posts: put posts.csv in data/processed/ (aggregate_opens.py copies it)",
    "email_posts": "Substack opens: run scripts/aggregate_opens.py",
    "sub_views_monthly": "Substack Stats exports: put the *_traffic_*.csv file in data/processed/substack_stats/",
    "sub_followers_daily": "Substack Stats exports: put the *_followers_*.csv file in data/processed/substack_stats/",
    "mc_campaigns": "Mailchimp: run scripts/aggregate_mailchimp.py",
    "li_daily": "LinkedIn: run scripts/process_linkedin.py",
}
have = {r[0] for r in con.sql("SELECT table_name FROM duckdb_tables()").fetchall()}
missing = [t for t in NEEDS if t not in have]
if missing:
    print("The database is missing tables the dashboard needs:")
    for t in missing:
        print(f"  - {t}: {NEEDS[t]}")
    print("Then run `python scripts/build_db.py` again (make sure it's the latest version) and re-run this script.")
    raise SystemExit(1)

BUCKET = """CASE WHEN {n} = 0 THEN 'none' WHEN {n} = 1 THEN '1'
                 WHEN {n} <= 4 THEN '2-4' ELSE '5plus' END"""
LABEL = """CASE WHEN {n} = 0 THEN 'No send' WHEN {n} = 1 THEN '1 email'
                WHEN {n} <= 4 THEN '2–4 emails' ELSE '5+ emails' END"""

queries = {
    # Total Substack views per month (web + email), from the Stats page.
    "views_monthly": "SELECT strftime(month, '%Y-%m-%d') AS month, views FROM sub_views_monthly ORDER BY month",

    # Daily follower total.
    "followers_daily": "SELECT strftime(date, '%Y-%m-%d') AS date, followers FROM sub_followers_daily ORDER BY date",

    # Follower change on days with 0 / 1 / 2-4 / 5+ Insights emails.
    "send_day_followers": f"""
        WITH sends AS (SELECT send_day, COUNT(*) AS emails FROM email_posts GROUP BY 1),
        days AS (
            SELECT d.change, COALESCE(s.emails, 0) AS emails
            FROM sub_followers_daily d LEFT JOIN sends s ON s.send_day = d.date
            WHERE d.date >= (SELECT MIN(send_day) FROM email_posts) AND d.change IS NOT NULL)
        SELECT {BUCKET.format(n='emails')} AS bucket, {LABEL.format(n='emails')} AS label,
               COUNT(*) AS days, ROUND(AVG(change), 2) AS avg_follower_change,
               SUM(CASE WHEN change < 0 THEN change ELSE 0 END)::INTEGER AS total_losses,
               MIN(emails) AS sort_order
        FROM days GROUP BY 1, 2 ORDER BY sort_order""",

    # Views per post by how crowded the send day was (Oct 2025 onward).
    "views_by_batch": f"""
        SELECT {BUCKET.format(n='batch_size')} AS bucket, {LABEL.format(n='batch_size')} AS label,
               COUNT(*) AS posts, MEDIAN(views) AS median_views,
               ROUND(SUM(views) / SUM(recipients), 2) AS views_per_recipient,
               MIN(batch_size) AS sort_order
        FROM email_posts WHERE emailed_at >= TIMESTAMPTZ '2025-10-01'
        GROUP BY 1, 2 ORDER BY sort_order""",

    # Quarterly open rate, Mailchimp vs Substack (blank where a channel sent nothing).
    "channel_open_rates": (REPO / "sql" / "channel_open_rates.sql").read_text().rstrip().rstrip(";").replace(
        "SELECT\n    quarter,", "SELECT\n    strftime(quarter, '%Y-%m-%d') AS quarter,", 1),

    # Every emailed Insights post with its send pattern and results.
    "email_posts": """
        SELECT post_number, title, strftime(emailed_at, '%Y-%m-%d') AS sent_on, batch_size,
               recipients, ROUND(open_rate, 4) AS open_rate, views
        FROM email_posts ORDER BY emailed_at DESC""",

    # LinkedIn company page by month.
    "linkedin_monthly": (REPO / "sql" / "linkedin_monthly.sql").read_text().rstrip().rstrip(";").replace(
        "SELECT\n    m.month,", "SELECT\n    strftime(m.month, '%Y-%m-%d') AS month,", 1),

    # Mailchimp campaigns that sent clicks to Insights articles (matched campaigns only).
    "mailchimp_insights_clicks": """
        SELECT l.campaign_num, strftime(c.sent_at, '%Y-%m-%d') AS sent_on, c.title AS campaign,
               c.delivered, SUM(l.clicks)::INTEGER AS insights_clicks
        FROM mc_link_clicks l
        JOIN mc_campaign_ids i ON i.campaign_num = l.campaign_num
        JOIN mc_campaigns c ON c.campaign_uid = i.campaign_uid
        WHERE l.is_insights
        GROUP BY ALL ORDER BY sent_on""",
}

# Open rate by subscriber cohort (half-year of first Insights email). Optional: needs the
# hashed subscriber tables from hash_subscribers.py. Cohort-quarters with under 50
# deliveries are dropped as too noisy to plot.
if "sub_email_history" in have:
    queries["cohort_open_rates"] = """
        SELECT strftime(send_quarter, '%Y-%m-%d') AS send_quarter,
               year(cohort) || CASE WHEN month(cohort) <= 6 THEN ' H1' ELSE ' H2' END AS cohort,
               COUNT(DISTINCT sub_id) AS subscribers, COUNT(*) AS deliveries,
               ROUND(AVG(opened::INTEGER), 4) AS open_rate
        FROM sub_email_history
        GROUP BY ALL HAVING COUNT(*) >= 50
        ORDER BY cohort, send_quarter"""
else:
    print("No sub_email_history table: skipping cohort_open_rates.csv (run scripts/hash_subscribers.py)")
    (out / "cohort_open_rates.csv").unlink(missing_ok=True)

# GA4 web traffic (optional: run scripts/pull_ga4.py). Sources are grouped into a few
# readable channels; the raw source/medium detail is in sql/ga4_traffic_sources.sql.
CHANNEL = """CASE
    WHEN source = '(direct)'                                                    THEN 'Direct'
    WHEN medium = 'organic' AND source IN ('google', 'bing', 'duckduckgo', 'yahoo', 'ecosia') THEN 'Search engines'
    WHEN source LIKE '%linkedin%' OR source = 'lnkd.in'                          THEN 'LinkedIn'
    WHEN medium = 'email' OR source LIKE '%mailchimp%' OR source LIKE '%mail.%'  THEN 'Email'
    WHEN source LIKE '%substack%' OR source = 'publication-search'               THEN 'Substack'
    WHEN source LIKE '%grc%'                                                     THEN 'GRC websites'
    ELSE 'Other' END"""
GA4_FILES = ("ga4_daily", "ga4_channels")
if "ga4_traffic_daily" in have:
    queries["ga4_daily"] = """
        SELECT strftime(date, '%Y-%m-%d') AS date, SUM(sessions)::INTEGER AS sessions,
               SUM(views)::INTEGER AS views
        FROM ga4_traffic_daily GROUP BY date ORDER BY date"""
    queries["ga4_channels"] = f"""
        SELECT {CHANNEL} AS channel, SUM(sessions)::INTEGER AS sessions,
               ROUND(SUM(engaged_sessions) / SUM(sessions), 3) AS engaged_rate
        FROM ga4_traffic_daily GROUP BY 1 ORDER BY sessions DESC"""
else:
    print("No ga4_traffic_daily table: skipping GA4 files (run scripts/pull_ga4.py)")
    for f in GA4_FILES:
        (out / f"{f}.csv").unlink(missing_ok=True)

for name, sql in queries.items():
    df = con.sql(sql).df()
    df = df.drop(columns=[c for c in ("sort_order",) if c in df.columns])
    df.to_csv(out / f"{name}.csv", index=False)
    print(f"{name}.csv: {len(df)} rows")
