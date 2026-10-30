"""
aggregate_mailchimp.py
Turns the Mailchimp account export into a few small, email-free tables.
Run it on your own machine; only the outputs are safe to share.

Usage (from the repo root):
    python scripts/aggregate_mailchimp.py                        # reads data/raw/mailchimp/
    python scripts/aggregate_mailchimp.py path/to/unzipped_export

Writes to data/processed/mailchimp/:
    campaigns.csv           one row per campaign (email addresses redacted from text)
    list_growth.csv         contacts per audience, status, source and month (counts only)
    member_ratings.csv      engagement-rating distribution per audience (counts only)
    link_clicks.csv         clicks per campaign per link (emails/query strings stripped)
    unsub_reasons.csv       unsubscribe reason counts per campaign (free-text dropped)
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "raw" / "mailchimp"
out = REPO / "data" / "processed" / "mailchimp"
out.mkdir(parents=True, exist_ok=True)

EMAIL = re.compile(r"[^@\s,;:<>\"']+@[^@\s,;:<>\"']+\.[a-z]{2,}", re.I)


def redact(value):
    return EMAIL.sub("[email]", value) if isinstance(value, str) else value


def campaign_key(path):
    """'12816693_november-newsletter.csv' -> ('12816693', 'november-newsletter')"""
    num, _, slug = path.stem.partition("_")
    return num, slug


def find(pattern):
    return sorted(src.rglob(pattern))


# 1. Campaign summary ---------------------------------------------------------
camp_files = find("campaigns.csv")
if camp_files:
    camp = pd.read_csv(camp_files[0])
    for col in camp.columns:  # redact() leaves non-text values unchanged
        camp[col] = camp[col].map(redact)
    camp.to_csv(out / "campaigns.csv", index=False)
    print(f"campaigns.csv: {len(camp)} campaigns")
else:
    print("campaigns.csv not found")

# 2 + 3. Audience lists: growth over time and member ratings ------------------
growth_rows, rating_rows = [], []
for f in find("lists/*/*.csv"):
    status = f.parent.name                       # members, unsubscribed, cleaned, ...
    audience = f.stem.split("_", 2)[-1]          # e.g. global-research-and-consulting
    df = pd.read_csv(f, dtype=str)
    if df.empty:
        continue
    joined = pd.to_datetime(df.get("OPTIN_TIME"), errors="coerce")
    joined = joined.fillna(pd.to_datetime(df.get("CONFIRM_TIME"), errors="coerce"))
    changed = pd.to_datetime(df.get("LAST_CHANGED"), errors="coerce")
    g = pd.DataFrame({
        "audience": audience,
        "status": status,
        "source": df.get("SOURCE", pd.Series("unknown", index=df.index)).fillna("unknown"),
        "joined_month": joined.dt.to_period("M").astype(str),
        "last_changed_month": changed.dt.to_period("M").astype(str),
    })
    growth_rows.append(g.value_counts().rename("contacts").reset_index())
    if "MEMBER_RATING" in df:
        r = df["MEMBER_RATING"].value_counts().rename_axis("member_rating")
        rating_rows.append(r.rename("contacts").reset_index().assign(audience=audience, status=status))

if growth_rows:
    pd.concat(growth_rows).to_csv(out / "list_growth.csv", index=False)
    pd.concat(rating_rows).to_csv(out / "member_ratings.csv", index=False)
    print("list_growth.csv, member_ratings.csv written")

# 4. Link clicks (geo files already aggregate clicks per URL; no emails) ------
click_rows = []
for f in find("geo_data/clicks/*.csv"):
    df = pd.read_csv(f, dtype={"Url": str})
    if df.empty or "Url" not in df:
        continue
    num, slug = campaign_key(f)
    parts = df["Url"].fillna("").map(urlsplit)
    df["domain"] = parts.map(lambda p: p.netloc.lower().removeprefix("www.") or p.scheme)
    df["path"] = parts.map(lambda p: "" if p.scheme == "mailto" else p.path)  # drop mailto addresses
    df["clicks"] = pd.to_numeric(df["Clicks"], errors="coerce").fillna(0)
    agg = df.groupby(["domain", "path"], as_index=False)["clicks"].sum()
    click_rows.append(agg.assign(campaign_num=num, campaign_slug=slug))

if click_rows:
    clicks = pd.concat(click_rows)
    clicks.to_csv(out / "link_clicks.csv", index=False)
    by_domain = clicks.groupby("domain")["clicks"].sum().sort_values(ascending=False)
    print("link_clicks.csv written. Top clicked domains:")
    print(by_domain.head(10).to_string())
    print(f"Clicks to substack.com domains: {int(by_domain[by_domain.index.str.contains('substack')].sum())}")

# 5. Unsubscribe reasons (category only; free-text descriptions are dropped) --
unsub_rows = []
for f in find("aggregate_activity/unsub-reasons/*.csv"):
    df = pd.read_csv(f, dtype=str)
    if df.empty or "reason" not in df:
        continue
    num, slug = campaign_key(f)
    r = df["reason"].fillna("none given").value_counts().rename_axis("reason")
    unsub_rows.append(r.rename("unsubscribes").reset_index().assign(campaign_num=num, campaign_slug=slug))

if unsub_rows:
    pd.concat(unsub_rows).to_csv(out / "unsub_reasons.csv", index=False)
    print("unsub_reasons.csv written")

# Final safety check: no output file may contain an email address.
for f in out.glob("*.csv"):
    text = f.read_text(errors="ignore")
    assert not EMAIL.search(text), f"Email address found in {f.name}; do not share it."
print(f"\nAll outputs in {out.relative_to(REPO)} passed the no-email check.")
