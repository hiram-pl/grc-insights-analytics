"""
process_linkedin.py
Converts LinkedIn Page analytics exports (.xls/.xlsx) into clean CSVs for build_db.py.
LinkedIn exports contain no subscriber emails, but they stay in data/ (git-ignored) anyway.

Drop every export you download into data/raw/linkedin/ (old ones too). Overlapping
exports are fine: for daily data, the newest export wins for each date (Problem C).

Usage (from the repo root):
    python scripts/process_linkedin.py                     # reads data/raw/linkedin/
    python scripts/process_linkedin.py path/to/folder

Writes to data/processed/linkedin/:
    daily.csv           one row per date: impressions, clicks, reactions, page views, new followers ...
    posts.csv           one row per post (latest export wins)
    demographics.csv    follower and visitor breakdowns (location, industry, ...) per export
    competitors.csv     LinkedIn's peer benchmark per export period
"""

import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "raw" / "linkedin"
out = REPO / "data" / "processed" / "linkedin"
out.mkdir(parents=True, exist_ok=True)


def snake(name):
    """'Impressions (organic)' -> 'impressions_organic'"""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def export_time(path):
    """File names end in a millisecond timestamp, e.g. ..._1793384694620.xls"""
    m = re.search(r"_(\d{13})\.", path.name)
    return pd.to_datetime(int(m.group(1)), unit="ms") if m else pd.Timestamp(path.stat().st_mtime, unit="s")


def read_sheet(path, sheet):
    """LinkedIn sometimes puts a description sentence above the header row; skip it if so."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_row = 1 if raw.iloc[0].notna().sum() == 1 else 0
    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    df.columns = [snake(c) for c in df.columns]
    return df


def latest_per_key(frames, key):
    """Stack exports, then keep the row from the newest export for each key."""
    df = pd.concat(frames, ignore_index=True).sort_values("exported_at")
    return df.drop_duplicates(subset=key, keep="last").sort_values(key)


content_daily, followers_daily, visitors_daily, posts, demo, comp = [], [], [], [], [], []

for f in sorted(src.glob("*.xls*")):
    exported = export_time(f)
    name = f.name.lower()
    sheets = pd.ExcelFile(f).sheet_names

    if "_content_" in name:
        d = read_sheet(f, "Metrics")
        d["date"] = pd.to_datetime(d["date"], format="%m/%d/%Y")
        content_daily.append(d.assign(exported_at=exported))
        p = read_sheet(f, "All posts")
        p["created_date"] = pd.to_datetime(p["created_date"], errors="coerce")
        posts.append(p.assign(exported_at=exported))

    elif "_followers_" in name or "_visitors_" in name:
        kind = "followers" if "_followers_" in name else "visitors"
        daily_sheet = sheets[0]                       # "New followers" / "Visitor metrics"
        d = read_sheet(f, daily_sheet)
        d["date"] = pd.to_datetime(d["date"], format="%m/%d/%Y")
        if kind == "followers":
            # LinkedIn calls this column "Total followers", but it is NEW followers that day.
            d = d.rename(columns={"total_followers": "new_followers_total"})
            followers_daily.append(d.assign(exported_at=exported))
        else:
            visitors_daily.append(d.assign(exported_at=exported))
        for s in sheets[1:]:                          # Location, Job function, Seniority, ...
            b = read_sheet(f, s)
            demo.append(pd.DataFrame({
                "audience": kind, "dimension": snake(s),
                "value": b.iloc[:, 0], "count": b.iloc[:, 1], "exported_at": exported,
            }))

    elif "competitor" in name:
        raw = pd.read_excel(f, header=None)
        start, end = pd.to_datetime(raw.iloc[0, 0]), pd.to_datetime(raw.iloc[0, 1])
        c = pd.read_excel(f, header=1)
        c.columns = [snake(x) for x in c.columns]
        comp.append(c.assign(period_start=start, period_end=end, exported_at=exported))

if content_daily:
    daily = latest_per_key(content_daily, "date")
    for extra in (followers_daily, visitors_daily):
        if extra:
            daily = daily.merge(latest_per_key(extra, "date").drop(columns="exported_at"),
                                on="date", how="outer")
    daily.to_csv(out / "daily.csv", index=False)
    print(f"daily.csv: {len(daily)} days, {daily['date'].min().date()} to {daily['date'].max().date()}")
if posts:
    p = latest_per_key(posts, "post_link")
    p.to_csv(out / "posts.csv", index=False)
    print(f"posts.csv: {len(p)} posts")
if demo:
    pd.concat(demo).to_csv(out / "demographics.csv", index=False)
    print("demographics.csv written")
if comp:
    pd.concat(comp).to_csv(out / "competitors.csv", index=False)
    print("competitors.csv written")
if not any([content_daily, posts, demo, comp]):
    print(f"No LinkedIn exports found in {src}")
