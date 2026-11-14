"""
make_sample_data.py
Generates FAKE data in sample_data/, in the same formats the pipeline reads from
data/processed/, so anyone can run the whole pipeline without real exports.

Everything here is invented: subscribers, titles, campaigns, counts. The simulation is
loosely shaped like the real publication (batch send days, open rates that fade as
subscribers receive more emails) so the dashboard and queries have something to show,
but no number in it is real. Seeded, so re-running gives identical files.

Usage (from the repo root):
    python scripts/make_sample_data.py
"""

import csv
import math
import random
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "sample_data"
EXPORT_DAY = "2026-10-31"
rng = random.Random(42)

START, END = date(2024, 9, 1), date(2026, 10, 31)
DAYS = [START + timedelta(days=i) for i in range((END - START).days + 1)]


def write(path, header, rows):
    path = OUT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        w.writerows(rows)
    print(f"  {path.relative_to(REPO)}: {len(rows)} rows")


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S+00")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower())


# ---------------------------------------------------------------------------
# Send schedule: (day, number of Insights emails that day)
# ---------------------------------------------------------------------------
sends = {}
d = date(2024, 9, 17)
while d < date(2025, 6, 15):                       # early era: mostly one a week
    sends[d] = rng.choice([1, 1, 1, 1, 2, 3])
    d += timedelta(days=rng.choice([6, 7, 8, 10, 14]))
d = date(2025, 10, 6)                              # relaunch era: frequent, often batched
while d < date(2026, 6, 10):
    sends[d] = rng.choice([1, 1, 1, 1, 2, 3, 4])
    d += timedelta(days=rng.choice([5, 7, 8, 10]))
for day, n in [(date(2025, 11, 20), 6), (date(2026, 1, 15), 9), (date(2026, 2, 12), 12),
               (date(2026, 3, 19), 7), (date(2026, 4, 23), 11), (date(2026, 5, 28), 5)]:
    sends[day] = n                                 # the crowded days

# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
ADJ = ["Rethinking", "Inside", "The Economics of", "Why", "Mapping", "Scaling", "The Future of",
       "Reassessing", "Beyond", "Funding", "Measuring", "The Politics of"]
TOPIC = ["Urban Water Systems", "Microfinance", "Battery Supply Chains", "Rural Broadband",
         "Coffee Cooperatives", "Carbon Markets", "Student Housing", "Telehealth", "Port Logistics",
         "Vertical Farming", "Esports Sponsorship", "Fintech Lending", "Wind Energy", "Fast Fashion",
         "Cold Chain Vaccines", "Semiconductor Policy", "Language-Learning Apps", "Ocean Shipping"]
PLACE = ["", " in Lagos", " in Lima", " in Jakarta", " in Lisbon", " in Nairobi", " in Hanoi", " in Ohio"]
used = set()


def title():
    while True:  # 12 x 18 x 8 = 1,728 possible titles
        t = f"{rng.choice(ADJ)} {rng.choice(TOPIC)}{rng.choice(PLACE)}"
        if t not in used:
            used.add(t)
            return t


posts = []  # dicts
num = 150_000_000
for day in sorted(sends):
    for k in range(sends[day]):
        num += rng.randint(50_000, 400_000)
        sent = datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc) + timedelta(minutes=7 * k)
        posts.append(dict(num=num, title=title(), published=sent - timedelta(minutes=2), emailed=sent,
                          batch=sends[day]))
web_only = []
for _ in range(45):                                # posts never emailed
    day = rng.choice(DAYS[:-30])
    num_w = 150_000_000 + rng.randint(1, 900) * 1_000_003
    web_only.append(dict(num=num_w, title=title(),
                         published=datetime(day.year, day.month, day.day, 18, 0, tzinfo=timezone.utc),
                         emailed=None, batch=0))

# ---------------------------------------------------------------------------
# Subscribers: sign up, get emails, open (less and less), sometimes leave
# ---------------------------------------------------------------------------
subs = []
for day in DAYS:
    rate = 0.55 if day.month in (9, 10, 11) else 0.18
    while rng.random() < rate:
        rate *= 0.5
        subs.append(dict(id=f"{rng.getrandbits(64):016x}", joined=day, left=None,
                         engagement=rng.betavariate(5, 3), received=0, paid=rng.random() < 0.15,
                         disabled=rng.random() < 0.03))

by_day = {}
for p in posts:
    by_day.setdefault(p["emailed"].date(), []).append(p)

deliveries = []
for day in DAYS:
    active = [s for s in subs if s["joined"] < day and s["left"] is None]
    todays = by_day.get(day, [])
    batch = len(todays)
    batch_factor = 1.0 if batch <= 1 else 0.86 if batch <= 4 else 0.74
    for p in todays:
        p.update(recipients=0, openers=0, first=None, last=None)
        for s in active:
            if s["disabled"]:
                continue
            prob = min(0.95, 1.1 * s["engagement"] * math.exp(-s["received"] / 110) * batch_factor)
            s["received"] += 1
            opened = rng.random() < prob
            first = p["emailed"] + timedelta(minutes=rng.randint(5, 2880)) if opened else None
            deliveries.append((s["id"], p["num"], str(opened).lower(), ts(first) if first else ""))
            p["recipients"] += 1
            if opened:
                p["openers"] += 1
                p["first"] = min(p["first"] or first, first)
                p["last"] = max(p["last"] or first, first)
    leave_p = 0.0004 + 0.0022 * batch ** 1.25
    for s in active:
        if rng.random() < leave_p * (0.6 + s["engagement"]):
            s["left"] = day

# Daily followers: everyone subscribed plus web/app followers who don't get email.
followers, extra = [], 0
for day in DAYS:
    extra += rng.random() < 0.12
    n = sum(1 for s in subs if s["joined"] <= day and (s["left"] is None or s["left"] > day))
    followers.append((day.strftime("%Y/%m/%d"), n + extra))

# ---------------------------------------------------------------------------
# Substack files
# ---------------------------------------------------------------------------
print("Writing fake sample data:")
all_posts = sorted(posts + web_only, key=lambda p: p["published"])
write("posts.csv",
      ["post_id", "post_date", "is_published", "email_sent_at", "inbox_sent_at", "type", "audience",
       "title", "subtitle", "podcast_url"],
      [(f"{p['num']}.{slug(p['title']).strip('-')}", ts(p["published"]), "true",
        ts(p["emailed"]) if p["emailed"] else "", ts(p["emailed"]) if p["emailed"] else "",
        "newsletter", "everyone", p["title"], "A fictional GRC Insights article", "") for p in all_posts])

write("per_post_opens.csv",
      ["post_number", "total_opens", "unique_openers", "first_open_at", "last_open_at", "recipients", "open_rate"],
      [(p["num"], round(p["openers"] * rng.uniform(1.2, 1.7)), p["openers"],
        ts(p["first"]) if p["first"] else "", ts(p["last"]) if p["last"] else "", p["recipients"],
        round(p["openers"] / p["recipients"], 4) if p["recipients"] else "") for p in posts])

views_rows, monthly = [], {}
for p in all_posts:
    web = rng.randint(25, 160)
    views = web + (round(p["openers"] * rng.uniform(1.1, 1.5)) if p["emailed"] else 0)
    p["views"] = views
    m = p["published"].strftime("%Y/%m/01")
    monthly[m] = monthly.get(m, 0) + views
    views_rows.append((p["title"], p["published"].strftime("%Y-%m-%dT%H:%M:%S.000Z"), "everyone", views,
                       round(rng.uniform(0.05, 0.25), 3), rng.randint(0, 4), 0, 0,
                       round(p["openers"] / p["recipients"], 3) if p.get("recipients") else ""))
write(f"substack_stats/sample_email_stats_{EXPORT_DAY}.csv",
      ["title", "post_date", "audience", "views", "engagement_rate", "signups", "subscribes",
       "estimated_value", "open_rate"], views_rows)
for day in DAYS:  # back-catalogue views in months with no new posts
    m = day.strftime("%Y/%m/01")
    monthly[m] = monthly.get(m, 0) + rng.randint(8, 25)
write(f"substack_stats/sample_traffic_{EXPORT_DAY}.csv", ["Date", "Views"], sorted(monthly.items()))
write(f"substack_stats/sample_followers_{EXPORT_DAY}.csv", None, followers)
write(f"substack_stats/sample_audience_location_{EXPORT_DAY}.csv", ["location", "free signups"],
      [("United States", 210), ("United Kingdom", 31), ("India", 24), ("Canada", 18), ("Hong Kong", 12)])

write("subscribers.csv", ["sub_id", "signed_up_at", "active_subscription", "email_disabled", "on_list"],
      [(s["id"], "" if s["left"] else f"{s['joined']} 12:00:00+00",
        "" if s["left"] else str(s["paid"]).lower(), "" if s["left"] else str(s["disabled"]).lower(),
        str(s["left"] is None).lower()) for s in sorted(subs, key=lambda s: s["id"])])
write("sub_deliveries.csv", ["sub_id", "post_number", "opened", "first_open_at"],
      sorted(deliveries, key=lambda r: (r[1], r[0])))

# ---------------------------------------------------------------------------
# Mailchimp (member newsletter, separate list)
# ---------------------------------------------------------------------------
camps, clicks, unsubs = [], [], []
d, i = datetime(2024, 1, 10, 17, 0), 0
while d < datetime(2026, 10, 20):
    i += 1
    name = (f"{d:%B} Newsletter" if d.day <= 10 else f"Weekly Spotlight {d:%b %d}")
    delivered = 820 + i * 3 + rng.randint(-20, 20)
    rate = max(0.22, 0.46 - i * 0.0018 + rng.uniform(-0.04, 0.04))
    opens, uclicks = round(delivered * rate), round(delivered * rng.uniform(0.01, 0.04))
    num_c = 13_000_000 + i * 977
    camps.append((name, f"GRC | {name}", "GRC Members", d.strftime("%b %d, %Y %I:%M %p"), d.strftime("%A"),
                  delivered + 6, delivered, 4, 2, 6, 0, 0, opens, f"{rate:.2%}", round(opens * 1.6), uclicks,
                  f"{uclicks / delivered:.2%}", round(uclicks * 1.4), rng.randint(0, 4), 0, 0, 1,
                  f"{rng.getrandbits(40):010x}", 0, 0, 0))
    links = [("grcglobalgroup.com", "/"), ("linkedin.com", "/company/grc")]
    if rng.random() < 0.5:
        links.append(("grcglobalgroup.substack.com", f"/p/{slug(rng.choice(sorted(used)))}"))
    for dom, path in links:
        clicks.append((dom, path, rng.randint(2, 30), num_c, slug(name)))
    if rng.random() < 0.3:
        unsubs.append((rng.choice(["No longer interested", "Too many emails", "Other"]), 1, num_c, slug(name)))
    d += timedelta(days=rng.choice([7, 14, 21]))
write("mailchimp/campaigns.csv",
      ["Title", "Subject", "Audience", "Send Date", "Send Weekday", "Total Recipients", "Successful Deliveries",
       "Soft Bounces", "Hard Bounces", "Total Bounces", "Times Forwarded", "Forwarded Opens", "Unique Opens",
       "Open Rate", "Total Opens", "Unique Clicks", "Click Rate", "Total Clicks", "Unsubscribes",
       "Abuse Complaints", "Times Liked on Facebook", "Folder Id", "Unique Id", "Total Orders",
       "Total Gross Sales", "Total Revenue"], camps)
write("mailchimp/link_clicks.csv", ["domain", "path", "clicks", "campaign_num", "campaign_slug"], clicks)
write("mailchimp/unsub_reasons.csv", ["reason", "unsubscribes", "campaign_num", "campaign_slug"], unsubs)
write("mailchimp/list_growth.csv",
      ["audience", "status", "source", "joined_month", "last_changed_month", "contacts"],
      [("GRC Members", st, "Hosted Signup Form", f"{y}-{m:02d}", f"{y}-{m:02d}", rng.randint(2, 30))
       for y in (2024, 2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 10)
       for st in ("subscribed", "unsubscribed")])

# ---------------------------------------------------------------------------
# LinkedIn company page
# ---------------------------------------------------------------------------
li_days = [date(2025, 10, 29) + timedelta(days=i) for i in range(365)]
write("linkedin/daily.csv",
      ["date", "impressions_total", "unique_impressions_organic", "clicks_total", "reactions_total",
       "comments_total", "reposts_total", "new_followers_total", "total_page_views_total",
       "total_unique_visitors_total"],
      [(day.isoformat(), imp := rng.randint(40, 600), round(imp * 0.7), rng.randint(0, 25),
        rng.randint(0, 20), rng.randint(0, 3), rng.randint(0, 2), rng.randint(0, 6),
        rng.randint(2, 40), rng.randint(1, 25)) for day in li_days])
li_posts = []
for k in range(24):
    day = rng.choice(li_days)
    t = ("New on our Substack: " + rng.choice(sorted(used))) if k < 2 else \
        rng.choice(["Meet our new analysts", "Recruiting is open", "Client spotlight", "Thank you to our partners"])
    li_posts.append((f"https://www.linkedin.com/feed/update/urn:li:activity:{7_200_000_000 + k}", f"{day} 16:00:00",
                     t, "Organic", "Image", rng.randint(200, 4000), rng.randint(5, 120), rng.randint(10, 150),
                     rng.randint(0, 10), rng.randint(0, 6), rng.randint(0, 8)))
write("linkedin/posts.csv", ["post_link", "created_date", "post_title", "post_type", "content_type", "impressions",
                             "clicks", "likes", "comments", "reposts", "follows"], li_posts)

# ---------------------------------------------------------------------------
# GA4 web traffic (tracking "starts" Oct 1, 2026 in the sample)
# ---------------------------------------------------------------------------
SOURCES = [("google", "organic", "(organic)", 4.0, 0.45), ("(direct)", "(none)", "(direct)", 3.0, 0.25),
           ("grcglobalgroup.com", "referral", "(referral)", 1.0, 0.5),
           ("publication-search", "referral", "(referral)", 0.8, 0.4),
           ("linkedin", "social", "insights-relaunch", 0.4, 0.55),
           ("mailchimp", "email", "monthly-newsletter", 0.3, 0.6), ("chatgpt.com", "referral", "(referral)", 0.2, 0.7)]
pages = [f"/p/{slug(t).strip('-')}" for t in sorted(used)[:40]] + ["/", "/archive"]
traffic, page_views = [], {}
for i in range(31):
    day = date(2026, 10, 1) + timedelta(days=i)
    for src, med, camp, rate, engaged in SOURCES:
        for _ in range(sum(rng.random() < rate / 4 for _ in range(4)) * rng.randint(1, 3)):
            page = rng.choice(pages)
            n_views = rng.randint(1, 3)
            traffic.append((day.isoformat(), src, med, camp, page, 1, int(rng.random() < engaged),
                            int(rng.random() < 0.7), n_views, rng.randint(0, 240)))
            page_views[(day.isoformat(), page)] = page_views.get((day.isoformat(), page), 0) + n_views
write("ga4/traffic_daily.csv", ["date", "source", "medium", "campaign", "landing_page", "sessions",
                                "engaged_sessions", "new_users", "views", "engagement_seconds"], traffic)
write("ga4/pages_daily.csv", ["date", "page", "views", "active_users"],
      [(d_, p_, v, max(1, v - rng.randint(0, 1))) for (d_, p_), v in sorted(page_views.items())])
print("Done. All of it is fictional.")
