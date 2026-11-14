"""
pull_mailchimp.py
Pulls GRC's Mailchimp campaign reports through the Marketing API into the SAME CSVs
aggregate_mailchimp.py makes from the account export, so build_db.py needs no changes.

Privacy by design: every request names the exact `fields` it needs. Email addresses are
never requested, so they never reach this machine's memory, let alone disk. The final
no-email check still runs (belt and braces).

Setup (once):
    1. Mailchimp > Profile > Extras > API keys > Create A Key (name: grc-insights-pipeline)
    2. Save it:  pbpaste > data/mailchimp-key && chmod 600 data/mailchimp-key   (git-ignored)

Outputs (data/processed/mailchimp/, rebuilt from scratch on every run):
    campaigns.csv      one row per sent campaign (export column names)
    link_clicks.csv    clicks per campaign per link (domain + path only)
    unsub_reasons.csv  unsubscribe reason counts per campaign
    list_growth.csv    contacts per audience x status x source x month

Usage (from the repo root):
    python scripts/pull_mailchimp.py
"""

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from mc_common import assert_no_emails, clean_url, redact, slugify

REPO = Path(__file__).resolve().parents[1]
KEY = REPO / "data" / "mailchimp-key"
OUT = REPO / "data" / "processed" / "mailchimp"

if not KEY.exists():
    sys.exit(f"No API key at {KEY.relative_to(REPO)}. See the setup notes at the top of this script.")
api_key = KEY.read_text().strip()

# A key looks like 'abc123...-us21'. The part after the dash is the data center,
# and every request for this account goes to that data center's server.
dc = api_key.rsplit("-", 1)[-1]
BASE = f"https://{dc}.api.mailchimp.com/3.0"

session = requests.Session()
session.auth = ("anystring", api_key)  # Mailchimp uses basic auth: any username, key as password
PAGE = 1000                            # Mailchimp's maximum page size


def get(path, **params):
    """One GET request -> parsed JSON. Raises on HTTP errors (bad key, rate limit, ...)."""
    r = session.get(f"{BASE}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def get_all(path, list_key, fields):
    """Every item from a paginated endpoint.

    path      e.g. "/reports"
    list_key  name of the list in the response, e.g. "reports"
    fields    comma-separated fields to return, e.g. "reports.id,reports.campaign_title"

    Mailchimp pages with `count` (items per page) and `offset` (items to skip), and each
    response says how many items exist in `total_items`.
    """
    items, offset = [], 0
    while True:
        resp = get(path, count=PAGE, offset=offset, fields=f"{fields},total_items")
        items += resp[list_key]
        offset += PAGE
        # `fields` is a whitelist: without naming total_items we wouldn't know when to stop.
        if offset >= resp["total_items"]:
            break
    return items


# Account time zone: the export shows send dates in it, and build_db.py expects that.
tz = ZoneInfo(get("/", fields="account_timezone")["account_timezone"])


def send_date(iso):
    """'2025-01-19T15:03:00+00:00' (UTC) -> 'Jan 19, 2025 10:03 AM' in the account time zone."""
    return datetime.fromisoformat(iso).astimezone(tz).strftime("%b %d, %Y %I:%M %p")


# 1. Campaign reports ---------------------------------------------------------
# Only what campaigns.csv below reads. Nested fields use dots.
REPORT_FIELDS = ",".join(f"reports.{f}" for f in [
    "id", "campaign_title", "subject_line", "list_name", "send_time", "emails_sent",
    "bounces.hard_bounces", "bounces.soft_bounces",
    "opens.unique_opens", "opens.opens_total",
    "clicks.unique_subscriber_clicks", "clicks.clicks_total",
    "unsubscribed",
])
reports = get_all("/reports", "reports", REPORT_FIELDS)

# web_id is the number Mailchimp puts in export file names (e.g. 12816693_november-newsletter.csv).
# It lives on the campaign, not the report, so fetch it separately and join on id.
web_ids = {c["id"]: c["web_id"] for c in get_all("/campaigns", "campaigns", "campaigns.id,campaigns.web_id")}

camp = pd.DataFrame([{
    # Export column names, so build_db.py's mc_campaigns query works unchanged.
    "Title": r["campaign_title"],
    "Subject": r["subject_line"],
    "Audience": r["list_name"],
    "Send Date": send_date(r["send_time"]),
    "Total Recipients": r["emails_sent"],
    "Successful Deliveries": r["emails_sent"] - r["bounces"]["hard_bounces"] - r["bounces"]["soft_bounces"],
    "Soft Bounces": r["bounces"]["soft_bounces"],
    "Hard Bounces": r["bounces"]["hard_bounces"],
    "Unique Opens": r["opens"]["unique_opens"],
    "Total Opens": r["opens"]["opens_total"],
    # unique_subscriber_clicks = people who clicked (what the export calls Unique Clicks);
    # unique_clicks counts unique (person, link) pairs and is ~2.6x larger here.
    "Unique Clicks": r["clicks"]["unique_subscriber_clicks"],
    "Total Clicks": r["clicks"]["clicks_total"],
    "Unsubscribes": r["unsubscribed"],
    "Unique Id": r["id"],
    "Web Id": web_ids.get(r["id"]),
} for r in reports if r.get("send_time")])
for col in ["Title", "Subject"]:
    camp[col] = camp[col].map(redact)
OUT.mkdir(parents=True, exist_ok=True)
camp.to_csv(OUT / "campaigns.csv", index=False)
print(f"campaigns.csv: {len(camp)} campaigns")

# 2 + 3. Per-campaign link clicks and unsubscribe reasons ---------------------
click_rows, unsub_rows = [], []
for r in reports:
    num, slug = web_ids.get(r["id"]), slugify(r["campaign_title"])

    for u in get_all(f"/reports/{r['id']}/click-details", "urls_clicked",
                     "urls_clicked.url,urls_clicked.total_clicks"):
        domain, path = clean_url(u["url"])
        click_rows.append({"domain": domain, "path": path, "clicks": u["total_clicks"],
                           "campaign_num": num, "campaign_slug": slug})

    # Only the reason is requested; the endpoint would otherwise return each person's email.
    reasons = Counter(u.get("reason") or "none given" for u in
                      get_all(f"/reports/{r['id']}/unsubscribed", "unsubscribes", "unsubscribes.reason"))
    unsub_rows += [{"reason": k, "unsubscribes": v, "campaign_num": num, "campaign_slug": slug}
                   for k, v in reasons.items()]

# Deleted campaigns vanish from the API, but the Oct 30, 2026 account export still had their
# clicks and unsubscribes (3 campaigns, incl. a Jan 2025 newsletter with 345 Insights clicks).
# Keep those rows from the frozen archive, for campaign ids the API no longer knows.
ARCHIVE = REPO / "data" / "processed" / "mailchimp_archive"
live_ids = {str(n) for n in web_ids.values()}


def archived(name, columns):
    f = ARCHIVE / name
    if not f.exists():
        return pd.DataFrame(columns=columns)
    old = pd.read_csv(f, dtype={"campaign_num": str})
    return old[~old["campaign_num"].isin(live_ids)][columns]


CLICK_COLS = ["domain", "path", "clicks", "campaign_num", "campaign_slug"]
UNSUB_COLS = ["reason", "unsubscribes", "campaign_num", "campaign_slug"]
old_clicks, old_unsubs = archived("link_clicks.csv", CLICK_COLS), archived("unsub_reasons.csv", UNSUB_COLS)
print(f"Archive: kept {old_clicks['campaign_num'].nunique()} deleted campaigns "
      f"({int(old_clicks['clicks'].sum()):,} clicks, {int(old_unsubs['unsubscribes'].sum())} unsubscribes)")

clicks = pd.DataFrame(click_rows, columns=CLICK_COLS).astype({"campaign_num": str})
clicks = clicks.groupby(["domain", "path", "campaign_num", "campaign_slug"], as_index=False)["clicks"].sum()
pd.concat([clicks[CLICK_COLS], old_clicks]).to_csv(OUT / "link_clicks.csv", index=False)
pd.concat([pd.DataFrame(unsub_rows, columns=UNSUB_COLS), old_unsubs]).to_csv(OUT / "unsub_reasons.csv", index=False)
print(f"link_clicks.csv: {int(clicks['clicks'].sum()):,} clicks; unsub_reasons.csv written")

# 4. Audience growth (counts only) --------------------------------------------
growth = []
for lst in get_all("/lists", "lists", "lists.id,lists.name"):
    # Status, source and two timestamps; nothing that identifies a person.
    MEMBER_FIELDS = "members.status,members.source,members.timestamp_opt,members.last_changed"
    members = pd.DataFrame(get_all(f"/lists/{lst['id']}/members", "members", MEMBER_FIELDS))
    if members.empty:
        continue
    month = lambda col: pd.to_datetime(members.get(col), errors="coerce", utc=True) \
        .dt.tz_localize(None).dt.to_period("M").astype(str)
    g = pd.DataFrame({
        "audience": slugify(lst["name"]),  # same as the export file names
        # The export names its folders "members", the API says "subscribed"; keep the export's word.
        "status": members["status"].replace({"subscribed": "members"}),
        "source": members.get("source", pd.Series(index=members.index, dtype=str)).fillna("unknown").replace("", "unknown"),
        "joined_month": month("timestamp_opt"),
        "last_changed_month": month("last_changed"),
    })
    growth.append(g.value_counts().rename("contacts").reset_index())

pd.concat(growth).to_csv(OUT / "list_growth.csv", index=False)
print("list_growth.csv written")

# Final safety check, same as aggregate_mailchimp.py. Never weaken or skip it.
assert_no_emails(OUT)
assert_no_emails(ARCHIVE)
print(f"\nAll outputs in {OUT.relative_to(REPO)} passed the no-email check. Next: python scripts/build_db.py")
