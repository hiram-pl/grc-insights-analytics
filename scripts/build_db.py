"""
build_db.py
Builds the DuckDB database from the processed (email-free) CSVs.
Safe to re-run: every table is rebuilt from scratch.

Usage (from the repo root):
    python scripts/build_db.py                 # real data: data/processed/ -> data/grc.duckdb
    python scripts/build_db.py --sample        # fake data: sample_data/   -> sample_data/sample.duckdb

Tables
    Substack:  posts, opens, email_posts
               post_stats, sub_followers_daily, sub_views_monthly, sub_audience_location
               (stats tables built only if <data dir>/substack_stats/ has Stats-page exports)
               subscribers, sub_email_history  (hashed ids; built only if sub_deliveries.csv exists)
    GA4:       ga4_traffic_daily, ga4_pages_daily  (built only if <data dir>/ga4/ has pull_ga4.py output)
    Mailchimp: mc_campaigns, mc_link_clicks, mc_list_growth, mc_unsub_reasons
               (built only if <data dir>/mailchimp/campaigns.csv exists)
    LinkedIn:  li_daily, li_posts, li_demographics, li_competitors
               (built only if <data dir>/linkedin/daily.csv exists)
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


def csv(name):
    """Path string DuckDB can read, e.g. csv('mailchimp/campaigns.csv')."""
    return (data_dir / name).as_posix()


def latest(folder, pattern):
    """Newest export matching pattern (file names end in _YYYY-MM-DD.csv), or None."""
    files = sorted((data_dir / folder).glob(pattern))
    return files[-1].as_posix() if files else None


con = duckdb.connect(str(db_path))

# ---------------------------------------------------------------------------
# Substack
# ---------------------------------------------------------------------------
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
FROM read_csv_auto('{csv("posts.csv")}');

-- Per-post email stats (no email addresses).
CREATE OR REPLACE TABLE opens AS
SELECT * FROM read_csv_auto('{csv("per_post_opens.csv")}');

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

unmatched = con.sql("""
    SELECT COUNT(*) FROM opens o LEFT JOIN posts p USING (post_number)
    WHERE p.post_number IS NULL
""").fetchall()[0][0]
print(f"Substack: opens rows with no matching post: {unmatched} (should be 0)")

# Substack Stats-page exports (optional). These are counts only: no emails.
stats_email = latest("substack_stats", "*_email_stats_*.csv")
if stats_email:
    con.sql(f"""
    -- Per-post stats. The export has no post_id, so match on title + publish time
    -- (titles alone are not unique: some articles were published twice).
    CREATE OR REPLACE TABLE post_stats AS
    SELECT
        p.post_number,
        s.views,
        s.signups,
        s.engagement_rate,
        s.open_rate                          AS substack_open_rate
    FROM read_csv_auto('{stats_email}') s
    JOIN posts p
      ON p.title = s.title
     AND abs(epoch(p.published_at) - epoch(s.post_date::TIMESTAMPTZ)) < 120;

    -- Add views and signups to the email analysis table.
    CREATE OR REPLACE TABLE email_posts AS
    SELECT e.*, s.views, s.signups
    FROM email_posts e
    LEFT JOIN post_stats s USING (post_number);
    """)
    n_rows = con.sql(f"SELECT COUNT(*) FROM read_csv_auto('{stats_email}')").fetchall()[0][0]
    n_matched = con.sql("SELECT COUNT(*) FROM post_stats").fetchall()[0][0]
    print(f"Substack stats: {n_matched} of {n_rows} posts matched (should be equal)")

stats_followers = latest("substack_stats", "*_followers_*.csv")
if stats_followers:
    con.sql(f"""
    -- Daily follower total (the export has no header row). change = vs. previous day.
    CREATE OR REPLACE TABLE sub_followers_daily AS
    SELECT
        date,
        followers,
        followers - LAG(followers) OVER (ORDER BY date) AS change
    FROM (
        SELECT strptime(column0, '%Y/%m/%d')::DATE AS date, try_cast(column1 AS INTEGER) AS followers
        FROM read_csv('{stats_followers}', header = false, columns = {{'column0': 'VARCHAR', 'column1': 'VARCHAR'}})
    )
    WHERE followers IS NOT NULL;
    """)

stats_traffic = latest("substack_stats", "*_traffic_*.csv")
if stats_traffic:
    con.sql(f"""
    CREATE OR REPLACE TABLE sub_views_monthly AS
    SELECT strptime(Date, '%Y/%m/%d')::DATE AS month, Views AS views
    FROM read_csv_auto('{stats_traffic}', all_varchar = true)
    """)
    con.sql("ALTER TABLE sub_views_monthly ALTER views TYPE INTEGER")

stats_location = latest("substack_stats", "*_audience_location_*.csv")
if stats_location:
    con.sql(f"""
    CREATE OR REPLACE TABLE sub_audience_location AS
    SELECT location, "free signups" AS free_signups FROM read_csv_auto('{stats_location}')
    """)

# Subscriber-level history, hashed ids only (optional: run scripts/hash_subscribers.py).
if (data_dir / "sub_deliveries.csv").exists():
    con.sql(f"""
    CREATE OR REPLACE TABLE subscribers AS
    SELECT * FROM read_csv_auto('{csv("subscribers.csv")}');

    -- One row per email delivered to a subscriber, with the context cohort analysis needs:
    -- cohort        = quarter of the subscriber's first Insights email (known for everyone,
    --                 including people who have since left the list)
    -- prior_emails  = Insights emails this subscriber had already received
    CREATE OR REPLACE TABLE sub_email_history AS
    SELECT
        d.sub_id,
        d.post_number,
        p.emailed_at,
        date_trunc('quarter', p.emailed_at)::DATE                              AS send_quarter,
        date_trunc('quarter', MIN(p.emailed_at) OVER (PARTITION BY d.sub_id))::DATE AS cohort,
        ROW_NUMBER() OVER (PARTITION BY d.sub_id ORDER BY p.emailed_at) - 1    AS prior_emails,
        d.opened,
        s.on_list
    FROM read_csv_auto('{csv("sub_deliveries.csv")}') d
    JOIN posts p USING (post_number)
    LEFT JOIN subscribers s USING (sub_id);
    """)
    n_subs, n_rows = con.sql("SELECT COUNT(DISTINCT sub_id), COUNT(*) FROM sub_email_history").fetchall()[0]
    print(f"Subscribers: {n_rows:,} deliveries to {n_subs} hashed ids")

# GA4 web traffic (optional: run scripts/pull_ga4.py). Counts only.
if (data_dir / "ga4" / "traffic_daily.csv").exists():
    con.sql(f"""
    -- Sessions by day, traffic source and landing page. Campaign = utm_campaign when tagged.
    CREATE OR REPLACE TABLE ga4_traffic_daily AS
    SELECT date::DATE AS date, source, medium, campaign, landing_page,
           sessions::INTEGER AS sessions, engaged_sessions::INTEGER AS engaged_sessions,
           new_users::INTEGER AS new_users, views::INTEGER AS views,
           engagement_seconds::INTEGER AS engagement_seconds
    FROM read_csv('{csv("ga4/traffic_daily.csv")}', all_varchar = true);

    -- Page views by day, matched to Substack posts where the path is /p/<slug>.
    -- active_users can't be summed across days (the same person counts once per day).
    CREATE OR REPLACE TABLE ga4_pages_daily AS
    SELECT g.date::DATE AS date, g.page, p.post_number,
           g.views::INTEGER AS views, g.active_users::INTEGER AS active_users
    FROM read_csv('{csv("ga4/pages_daily.csv")}', all_varchar = true) g
    LEFT JOIN posts p
      ON regexp_extract(g.page, '^/p/([^/?#]+)', 1) = split_part(p.post_id, '.', 2);
    """)
    first, last, sessions = con.sql("SELECT MIN(date), MAX(date), SUM(sessions) FROM ga4_traffic_daily").fetchall()[0]
    post_views, all_views = con.sql("""SELECT SUM(views) FILTER (WHERE post_number IS NOT NULL), SUM(views)
                                       FROM ga4_pages_daily""").fetchall()[0]
    print(f"GA4: {first} to {last}, {sessions:,} sessions; {post_views or 0:,} of {all_views:,} page views matched to a post")
else:
    print("GA4: no ga4/traffic_daily.csv found, skipped")

# ---------------------------------------------------------------------------
# Mailchimp (optional)
# ---------------------------------------------------------------------------
if (data_dir / "mailchimp" / "campaigns.csv").exists():
    con.sql(f"""
    -- One row per campaign, with clean column names and rates recomputed from counts.
    -- slug = the title the way Mailchimp names its export files: lowercase,
    -- every run of non-alphanumeric characters replaced by '-'.
    CREATE OR REPLACE TABLE mc_campaigns AS
    SELECT
        "Unique Id"                                                   AS campaign_uid,
        Title                                                         AS title,
        Subject                                                       AS subject,
        Audience                                                      AS audience,
        try_strptime("Send Date", '%b %d, %Y %I:%M %p')               AS sent_at,   -- account time zone
        regexp_replace(lower(Title), '[^a-z0-9]+', '-', 'g')          AS slug,
        "Total Recipients"                                            AS recipients,
        "Successful Deliveries"                                       AS delivered,
        "Hard Bounces"                                                AS hard_bounces,
        "Soft Bounces"                                                AS soft_bounces,
        "Unique Opens"                                                AS unique_opens,
        "Unique Clicks"                                               AS unique_clicks,
        "Total Clicks"                                                AS total_clicks,
        Unsubscribes                                                  AS unsubscribes,
        "Unique Opens" / NULLIF("Successful Deliveries", 0)           AS open_rate,
        "Unique Clicks" / NULLIF("Successful Deliveries", 0)          AS click_rate
    FROM read_csv_auto('{csv("mailchimp/campaigns.csv")}');

    -- Link clicks per campaign, with a flag for links that point to Insights.
    CREATE OR REPLACE TABLE mc_link_clicks AS
    SELECT
        campaign_num,
        campaign_slug,
        domain,
        path,
        clicks::INTEGER                                                    AS clicks,
        domain IN ('grcglobalgroup.substack.com', 'insights.grcglobalgroup.com')
            OR (domain = 'grcglobalgroup.com' AND path LIKE '/insights%')    AS is_insights
    FROM read_csv_auto('{csv("mailchimp/link_clicks.csv")}');

    CREATE OR REPLACE TABLE mc_unsub_reasons AS
    SELECT * FROM read_csv_auto('{csv("mailchimp/unsub_reasons.csv")}');

    -- Contacts per audience / status / source / signup month. Months become real dates.
    CREATE OR REPLACE TABLE mc_list_growth AS
    SELECT
        audience,
        status,
        source,
        try_cast(joined_month || '-01' AS DATE)        AS joined_month,
        try_cast(last_changed_month || '-01' AS DATE)  AS last_changed_month,
        contacts::INTEGER                              AS contacts
    -- all_varchar keeps months like '2024-03' as text so they can be turned into dates
    FROM read_csv_auto('{csv("mailchimp/list_growth.csv")}', all_varchar = true);

    -- Map the numeric ids in the export's file names to rows in mc_campaigns.
    -- Match on slug; when several campaigns share a title, pair them up in order
    -- (lowest id <-> earliest send), which follows Mailchimp's creation order.
    CREATE OR REPLACE TABLE mc_campaign_ids AS
    WITH ids AS (
        SELECT DISTINCT campaign_num, campaign_slug AS slug FROM mc_link_clicks
        UNION
        SELECT DISTINCT campaign_num, campaign_slug FROM mc_unsub_reasons
    ),
    ids_ranked AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY slug ORDER BY campaign_num) AS rk FROM ids
    ),
    camps_ranked AS (
        SELECT campaign_uid, slug, ROW_NUMBER() OVER (PARTITION BY slug ORDER BY sent_at) AS rk
        FROM mc_campaigns
    )
    SELECT i.campaign_num, i.slug, c.campaign_uid      -- campaign_uid is NULL when unmatched
    FROM ids_ranked i
    LEFT JOIN camps_ranked c USING (slug, rk);
    """)

    # The API pull (pull_mailchimp.py) also writes each campaign's web_id, the number Mailchimp
    # uses in file names. Where we have it, match on it directly: exact, no title guessing.
    # Ids still unmatched after this are campaigns deleted from Mailchimp (kept from the archive).
    if "Web Id" in con.sql(f"DESCRIBE SELECT * FROM read_csv_auto('{csv("mailchimp/campaigns.csv")}')").df()["column_name"].values:
        con.sql(f"""
        CREATE OR REPLACE TABLE mc_campaign_ids AS
        SELECT i.campaign_num, i.slug, w."Unique Id" AS campaign_uid
        FROM (SELECT DISTINCT campaign_num::BIGINT AS campaign_num, slug FROM mc_campaign_ids) i
        LEFT JOIN read_csv_auto('{csv("mailchimp/campaigns.csv")}') w ON w."Web Id" = i.campaign_num;
        """)

    total, missing = con.sql("""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE campaign_uid IS NULL) FROM mc_campaign_ids
    """).fetchall()[0]
    print(f"Mailchimp: {total - missing} of {total} export ids matched to a campaign")
    if missing:
        print("  Unmatched ids (their clicks are kept but have no send date):")
        for num, slug in con.sql(
            "SELECT campaign_num, slug FROM mc_campaign_ids WHERE campaign_uid IS NULL"
        ).fetchall():
            print(f"    {num}  {slug}")
else:
    print("Mailchimp: no mailchimp/campaigns.csv found, skipped")

# ---------------------------------------------------------------------------
# LinkedIn (optional)
# ---------------------------------------------------------------------------
if (data_dir / "linkedin" / "daily.csv").exists():
    con.sql(f"""
    -- One row per day. engagements uses LinkedIn's definition (clicks + reactions +
    -- comments + reposts); rates are left out on purpose: compute them as SUM/SUM.
    CREATE OR REPLACE TABLE li_daily AS
    SELECT
        date::DATE                                                     AS date,
        impressions_total                                              AS impressions,
        unique_impressions_organic                                     AS unique_impressions,
        clicks_total                                                   AS clicks,
        reactions_total                                                AS reactions,
        comments_total                                                 AS comments,
        reposts_total                                                  AS reposts,
        clicks_total + reactions_total + comments_total + reposts_total AS engagements,
        new_followers_total                                            AS new_followers,
        total_page_views_total                                         AS page_views,
        total_unique_visitors_total                                    AS unique_visitors
    FROM read_csv_auto('{csv("linkedin/daily.csv")}');

    -- One row per company-page post, flagged if it links to or mentions Insights.
    CREATE OR REPLACE TABLE li_posts AS
    SELECT
        post_link,
        created_date::TIMESTAMP                                        AS created_at,
        post_title,
        post_type,
        content_type,
        impressions,
        clicks,
        likes,
        comments,
        reposts,
        follows,
        regexp_matches(lower(post_title), 'substack|grc insights|insights\\.grcglobalgroup') AS promotes_insights
    FROM read_csv_auto('{csv("linkedin/posts.csv")}');
    """)
    if (data_dir / "linkedin" / "demographics.csv").exists():
        con.sql(f"""CREATE OR REPLACE TABLE li_demographics AS
                    SELECT * FROM read_csv_auto('{csv("linkedin/demographics.csv")}')""")
    if (data_dir / "linkedin" / "competitors.csv").exists():
        con.sql(f"""CREATE OR REPLACE TABLE li_competitors AS
                    SELECT * FROM read_csv_auto('{csv("linkedin/competitors.csv")}')""")
    days, first, last = con.sql("SELECT COUNT(*), MIN(date), MAX(date) FROM li_daily").fetchall()[0]
    n_posts, promo = con.sql("SELECT COUNT(*), COUNT(*) FILTER (WHERE promotes_insights) FROM li_posts").fetchall()[0]
    print(f"LinkedIn: {days} days ({first} to {last}), {n_posts} posts, {promo} promoting Insights")
else:
    print("LinkedIn: no linkedin/daily.csv found, skipped")

# ---------------------------------------------------------------------------
# Pipeline bookkeeping (optional: written by refresh.py)
# ---------------------------------------------------------------------------
if (data_dir / "freshness.csv").exists():
    con.sql(f"""CREATE OR REPLACE TABLE freshness AS
                SELECT * FROM read_csv_auto('{csv("freshness.csv")}')""")
    n_ok, n = con.sql("SELECT COUNT(*) FILTER (WHERE status = 'ok'), COUNT(*) FROM freshness").fetchall()[0]
    print(f"Freshness: {n_ok} of {n} sources up to date")
if (data_dir / "pipeline_runs.csv").exists():
    con.sql(f"""CREATE OR REPLACE TABLE pipeline_runs AS
                SELECT * FROM read_csv_auto('{csv("pipeline_runs.csv")}')""")

print(f"Built {db_path.relative_to(REPO)}")
con.close()
