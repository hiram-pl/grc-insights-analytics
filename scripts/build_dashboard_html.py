"""
build_dashboard_html.py
Builds a standalone HTML dashboard you can open in any browser, email, or host.
Reads the CSVs written by export_dashboard_data.py.

Usage (from the repo root):
    python scripts/export_dashboard_data.py && python scripts/build_dashboard_html.py
        -> data/processed/dashboard/dashboard.html   (real data; git-ignored, keep it private)
    python scripts/export_dashboard_data.py --sample && python scripts/build_dashboard_html.py --sample
        -> sample_data/dashboard/dashboard.html      (fake data; safe to publish, e.g. GitHub Pages)

The page loads Plotly from its CDN, so it needs an internet connection to draw the charts.
"""

import argparse
import html
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

REPO = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--sample", action="store_true")
args = parser.parse_args()
src = REPO / ("sample_data/dashboard" if args.sample else "data/processed/dashboard")

needed = ["views_monthly", "followers_daily", "send_day_followers", "views_by_batch",
          "channel_open_rates", "email_posts", "linkedin_monthly", "mailchimp_insights_clicks"]
missing = [n for n in needed if not (src / f"{n}.csv").exists()]
if missing:
    raise SystemExit(f"Missing {', '.join(missing)} in {src}. Run scripts/export_dashboard_data.py"
                     f"{' --sample' if args.sample else ''} first.")
d = {n: pd.read_csv(src / f"{n}.csv") for n in needed}

BLUE, ORANGE, GREEN, RED, GREY = "#2f6fb2", "#d9822b", "#3a8f5c", "#c0392b", "#b8bec6"
LAYOUT = dict(template="simple_white", height=300, margin=dict(l=50, r=20, t=10, b=40),
              font=dict(family="Inter, Helvetica, Arial, sans-serif", size=12), hoverlabel=dict(bgcolor="white"))

# --- headline figures (same definitions as the Claude dashboard) ---------------------------
fol = d["followers_daily"].assign(date=lambda x: pd.to_datetime(x["date"])).sort_values("date")
last = fol.iloc[-1]
before = fol[fol["date"] <= last["date"] - timedelta(days=30)].iloc[-1]
followers, followers_30d = int(last["followers"]), int(last["followers"] - before["followers"])

vm = d["views_monthly"].assign(month=lambda x: pd.to_datetime(x["month"])).sort_values("month")
views_last, views_prev = int(vm.iloc[-1]["views"]), int(vm.iloc[-2]["views"])
views_month = vm.iloc[-1]["month"].strftime("%B %Y")

opens = d["channel_open_rates"].dropna(subset=["substack_open_rate"]).sort_values("quarter").iloc[-1]
li = d["linkedin_monthly"]
sdf = d["send_day_followers"].set_index("bucket")
vbb = d["views_by_batch"].assign(bucket=lambda x: x["bucket"].astype(str)).set_index("bucket")
lost_per_day = -sdf.loc["5plus", "avg_follower_change"]
batch_views, solo_views = round(vbb.loc["5plus", "median_views"]), round(vbb.loc["1", "median_views"])


def signed(v):
    cls = "good" if v > 0 else "bad" if v < 0 else ""
    return f'<span class="{cls}">{v:+,}</span>' if v else "0"


# --- charts ---------------------------------------------------------------------------------
def fig_html(fig, first=False):
    fig.update_layout(**LAYOUT)
    return fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False,
                       config={"displayModeBar": False, "responsive": True})


charts = {}

f = go.Figure(go.Bar(x=vm["month"], y=vm["views"], marker_color=BLUE,
                     hovertemplate="%{x|%B %Y}<br>%{y:,} views<extra></extra>"))
f.update_xaxes(tickformat="%b %y")
charts["views"] = fig_html(f, first=True)

f = go.Figure(go.Scatter(x=fol["date"], y=fol["followers"], mode="lines", line=dict(color=BLUE, width=2),
                         hovertemplate="%{x|%b %-d, %Y}<br>%{y:,} followers<extra></extra>"))
f.update_yaxes(rangemode="tozero")
charts["followers"] = fig_html(f)

s = d["send_day_followers"]
f = go.Figure(go.Bar(x=s["label"], y=s["avg_follower_change"],
                     marker_color=[RED if v < 0 else GREY for v in s["avg_follower_change"]],
                     customdata=s[["days", "total_losses"]],
                     hovertemplate="%{x}<br>%{y:+.2f} followers/day<br>%{customdata[0]} days, "
                                   "%{customdata[1]} lost in total<extra></extra>"))
f.add_hline(y=0, line_color="#888", line_width=1)
charts["batch_followers"] = fig_html(f)

v = d["views_by_batch"].assign(bucket=lambda x: x["bucket"].astype(str))
f = go.Figure(go.Bar(x=v["label"], y=v["median_views"],
                     marker_color=[BLUE if b == "1" else GREY for b in v["bucket"]],
                     customdata=v[["posts", "views_per_recipient"]],
                     hovertemplate="%{x}<br>%{y:,.0f} median views<br>%{customdata[0]} posts, "
                                   "%{customdata[1]:.2f} views/recipient<extra></extra>"))
charts["batch_views"] = fig_html(f)

o = d["channel_open_rates"].assign(quarter=lambda x: pd.to_datetime(x["quarter"]))
f = go.Figure()
for col, name, color in [("mailchimp_open_rate", "Mailchimp", ORANGE), ("substack_open_rate", "Substack", BLUE)]:
    f.add_trace(go.Scatter(x=o["quarter"], y=o[col], name=name, mode="lines+markers", connectgaps=False,
                           line=dict(color=color, width=2), hovertemplate=f"{name}: %{{y:.1%}}<extra></extra>"))
f.update_yaxes(tickformat=".0%", rangemode="tozero")
f.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
charts["open"] = fig_html(f)

m = d["mailchimp_insights_clicks"].assign(sent_on=lambda x: pd.to_datetime(x["sent_on"]))
f = go.Figure(go.Scatter(x=m["sent_on"], y=m["insights_clicks"], mode="markers", marker=dict(color=BLUE, size=8),
                         customdata=m[["campaign", "delivered"]],
                         hovertemplate="%{x|%b %-d, %Y}<br>%{customdata[0]}<br>%{y:,} clicks, "
                                       "%{customdata[1]:,} delivered<extra></extra>"))
f.update_xaxes(range=[m["sent_on"].min() - timedelta(days=60), vm["month"].max() + timedelta(days=31)])
f.update_yaxes(rangemode="tozero")
charts["mailchimp"] = fig_html(f)

li_m = li.assign(month=lambda x: pd.to_datetime(x["month"]))
f = go.Figure(go.Bar(x=li_m["month"], y=li_m["impressions"], marker_color=GREEN,
                     customdata=li_m[["posts", "insights_posts"]],
                     hovertemplate="%{x|%B %Y}<br>%{y:,} impressions<br>%{customdata[0]} posts, "
                                   "%{customdata[1]} linking to Insights<extra></extra>"))
f.update_xaxes(tickformat="%b %y")
charts["linkedin"] = fig_html(f)

# --- posts table ----------------------------------------------------------------------------
rows = []
for r in d["email_posts"].itertuples():
    hi = ' class="hi"' if r.batch_size >= 5 else ""
    open_rate = "" if pd.isna(r.open_rate) else f"{r.open_rate:.1%}"
    views = "" if pd.isna(r.views) else f"{int(r.views):,}"
    rows.append(f"<tr><td>{html.escape(str(r.title))}</td><td>{r.sent_on}</td><td class='n'{hi}>{r.batch_size}</td>"
                f"<td class='n'>{int(r.recipients):,}</td><td class='n'>{open_rate}</td><td class='n'>{views}</td></tr>")


def card(title, note, chart):
    return f'<div class="card"><h3>{title}</h3><p class="note">{note}</p>{charts[chart]}</div>'


label = "SAMPLE DATA (fictional)" if args.sample else "Internal: GRC data, do not share publicly"
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GRC Insights growth dashboard</title>
<style>
 body {{ font-family: Inter, Helvetica, Arial, sans-serif; color: #1d2329; background: #f6f7f9; margin: 0; }}
 .wrap {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px 60px; }}
 h1 {{ font-family: Georgia, serif; font-weight: 400; font-size: 32px; margin: 0 0 6px; }}
 .tag {{ display: inline-block; font-size: 11px; color: #6b7480; border: 1px solid #d6dbe1; border-radius: 4px; padding: 2px 6px; margin-bottom: 10px; }}
 .take {{ font-size: 16px; line-height: 1.5; max-width: 900px; margin: 0 0 24px; }}
 .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 28px; }}
 .card {{ background: #fff; border: 1px solid #e3e7ec; border-radius: 8px; padding: 18px; min-width: 0; }}
 .kl {{ font-size: 12px; color: #6b7480; margin: 0 0 4px; }}
 .kv {{ font-family: Georgia, serif; font-size: 32px; margin: 0 0 4px; }}
 .ks {{ font-size: 12px; color: #6b7480; margin: 0; }}
 .good {{ color: #2e7d4f; }} .bad {{ color: #c0392b; }}
 h2 {{ font-size: 18px; margin: 28px 0 10px; }}
 h3 {{ font-size: 15px; margin: 0 0 4px; }}
 .note {{ font-size: 12px; color: #6b7480; margin: 0 0 8px; line-height: 1.4; }}
 .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 14px; }}
 .tbl {{ max-height: 460px; overflow: auto; }}
 table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
 th {{ position: sticky; top: 0; background: #fff; text-align: left; border-bottom: 1px solid #d6dbe1; padding: 6px 8px; color: #6b7480; }}
 td {{ border-bottom: 1px solid #eef1f4; padding: 6px 8px; vertical-align: top; }}
 .n {{ text-align: right; font-variant-numeric: tabular-nums; }} td.hi {{ color: #c0392b; font-weight: 600; }}
 .defs {{ font-size: 12px; color: #6b7480; line-height: 1.5; }}
</style></head><body><div class="wrap">
<span class="tag">{label} · built {datetime.now():%b %d, %Y}</span>
<h1>GRC Insights growth dashboard</h1>
<p class="take">Relaunch at one email a week. On days with 5+ emails, Insights lost <b>{lost_per_day:.1f}</b> followers on average,
and those posts drew a median of <b>{batch_views:,}</b> views, against <b>{solo_views:,}</b> for posts sent alone.</p>

<div class="kpis">
 <div class="card"><p class="kl">Substack followers</p><p class="kv">{followers:,}</p><p class="ks">{signed(followers_30d)} in the last 30 days</p></div>
 <div class="card"><p class="kl">Views, {views_month}</p><p class="kv">{views_last:,}</p><p class="ks">{signed(views_last - views_prev)} vs the month before</p></div>
 <div class="card"><p class="kl">Substack open rate, latest quarter</p><p class="kv">{opens.substack_open_rate:.1%}</p><p class="ks">Mailchimp, same quarter: {opens.mailchimp_open_rate:.1%}</p></div>
 <div class="card"><p class="kl">LinkedIn posts linking to Insights, past year</p><p class="kv{' bad' if li.insights_posts.sum() == 0 else ''}">{int(li.insights_posts.sum())}</p><p class="ks">out of {int(li.posts.sum())} company page posts</p></div>
</div>

<h2>Reach</h2><div class="grid">
{card("Views per month", "Total Substack post views per month, web and email combined.", "views")}
{card("Followers over time", "Daily Substack follower total. Most growth arrives in the fall.", "followers")}
</div>
<h2>Sending pattern</h2><div class="grid">
{card("Follower change by emails sent that day", "Average daily follower change. Below zero means more people left than joined.", "batch_followers")}
{card("Views per post by emails sent that day", "Median views per post, posts emailed from Oct 2025 on.", "batch_views")}
</div>
<h2>Channels</h2><div class="grid">
{card("Open rate by quarter", "Unique opens divided by delivered. Gaps mean no sends that quarter.", "open")}
{card("Mailchimp clicks to Insights", "Each dot is a campaign that linked to Insights. Total clicks, can include security scanners.", "mailchimp")}
{card("LinkedIn impressions per month", "Impressions of all GRC company page posts.", "linkedin")}
</div>
<h2>Every emailed post</h2>
<div class="card"><div class="tbl"><table>
<thead><tr><th>Title</th><th>Sent</th><th class="n">Same-day emails</th><th class="n">Recipients</th><th class="n">Open rate</th><th class="n">Views</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></div>
<h2>Definitions</h2>
<div class="defs"><p><b>Views:</b> Substack's server-side count of post views, web and email together.
<b>Open rate:</b> unique opens divided by delivered emails (inflated somewhat by privacy features that pre-load emails).
<b>Same-day emails:</b> Insights emails sent the same calendar day (UTC).
<b>Sources:</b> Substack, Mailchimp and LinkedIn exports, processed by the grc-insights-analytics pipeline.</p></div>
</div></body></html>"""

out = src / "dashboard.html"
out.write_text(page, encoding="utf-8")
print(f"Wrote {out.relative_to(REPO)} ({out.stat().st_size / 1024:.0f} KB). Open it in any browser.")
