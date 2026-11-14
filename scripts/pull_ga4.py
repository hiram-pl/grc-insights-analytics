"""
pull_ga4.py
Pulls GRC Insights traffic from the GA4 Data API into CSVs that build_db.py loads.
Counts only: GA4 never returns personal data through these reports.

Setup (once):
    1. Service account key (JSON) saved as data/ga4-key.json  (git-ignored; keep it private)
    2. That service account added as a Viewer in GA4 > Admin > Property access management
    3. "Google Analytics Data API" enabled in the service account's Google Cloud project
    4. The numeric GA4 property ID saved in data/ga4_property_id (or pass --property)

Outputs (data/processed/ga4/, rebuilt from scratch on every run):
    traffic_daily.csv  one row per day x source x medium x campaign x landing page
                       sessions, engaged_sessions, new_users, views, engagement_seconds
    pages_daily.csv    one row per day x page: views, active_users

Usage (from the repo root):
    python scripts/pull_ga4.py                    # everything since --start (default 2024-01-01)
    python scripts/pull_ga4.py --start 2026-01-01
"""

import argparse
import csv
import sys
from pathlib import Path

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

REPO = Path(__file__).resolve().parents[1]
KEY = REPO / "data" / "ga4-key.json"
PROPERTY_FILE = REPO / "data" / "ga4_property_id"
OUT = REPO / "data" / "processed" / "ga4"

parser = argparse.ArgumentParser()
parser.add_argument("--property", help="numeric GA4 property ID (default: read data/ga4_property_id)")
parser.add_argument("--start", default="2024-01-01", help="first day to pull, YYYY-MM-DD")
args = parser.parse_args()

if not KEY.exists():
    sys.exit(f"No service account key at {KEY.relative_to(REPO)}. See the setup notes at the top of this script.")
prop = args.property or (PROPERTY_FILE.read_text().strip() if PROPERTY_FILE.exists() else None)
if not prop:
    sys.exit(f"No property ID. Pass --property 123456789 or save it in {PROPERTY_FILE.relative_to(REPO)}.")

client = BetaAnalyticsDataClient.from_service_account_file(str(KEY))
PAGE = 100_000


def pull(name, dims, metrics):
    """Run one report (paging through all rows) and write it to OUT/<name>.csv.
    dims / metrics map GA4 API names to our column names."""
    rows, offset = [], 0
    while True:
        resp = client.run_report(RunReportRequest(
            property=f"properties/{prop}",
            date_ranges=[DateRange(start_date=args.start, end_date="yesterday")],
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in metrics],
            limit=PAGE, offset=offset, keep_empty_rows=False))
        for r in resp.rows:
            dvals = [v.value for v in r.dimension_values]
            dvals[0] = f"{dvals[0][:4]}-{dvals[0][4:6]}-{dvals[0][6:]}"  # 20261113 -> 2026-11-13
            rows.append(dvals + [v.value for v in r.metric_values])
        offset += PAGE
        if offset >= resp.row_count:
            break
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / f"{name}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(dims.values()) + list(metrics.values()))
        w.writerows(sorted(rows))
    print(f"{name}.csv: {len(rows):,} rows")


pull("traffic_daily",
     {"date": "date", "sessionSource": "source", "sessionMedium": "medium",
      "sessionCampaignName": "campaign", "landingPage": "landing_page"},
     {"sessions": "sessions", "engagedSessions": "engaged_sessions", "newUsers": "new_users",
      "screenPageViews": "views", "userEngagementDuration": "engagement_seconds"})

pull("pages_daily",
     {"date": "date", "pagePath": "page"},
     {"screenPageViews": "views", "activeUsers": "active_users"})

print(f"Wrote {OUT.relative_to(REPO)}/. Next: python scripts/build_db.py")
