# STATUS: grc-insights-analytics

Project log for the GRC Insights analytics pipeline: what has been built, what we've learned, and what's next.
Last updated **Nov 14, 2026**. Conventions, data quirks and privacy rules are in `CLAUDE.md`; the public-facing summary is in `README.md`.

## Where things stand

**Step 1 (instrument everything) is complete.** All four data sources (Substack, Mailchimp, LinkedIn, GA4) feed one DuckDB database (20 tables). Metrics and a UTM convention are defined, and a standalone dashboard is generated from the database. The main open question from Step 1 is answered: the open-rate decline is **subscriber fatigue, not list composition**.

**Step 2 (experiments and new projects) is next**, starting with the weekly-cadence relaunch.

| Source | How it gets in | Data covers | Freshness |
|---|---|---|---|
| Substack account export | `aggregate_opens.py`, `hash_subscribers.py` | emails Sept 2024 - June 1, 2026 (102 emailed posts) | export of Oct 30, 2026 |
| Substack Stats page | CSVs into `data/processed/substack_stats/` | followers daily, views monthly, per-post stats | export of Oct 31, 2026 |
| Mailchimp account export | `aggregate_mailchimp.py` | 220 campaigns since 2020 | export of Oct 30, 2026 |
| LinkedIn page analytics | `process_linkedin.py` | Oct 29, 2025 - Oct 28, 2026 | export of Oct 30, 2026 |
| GA4 (Data API) | `pull_ga4.py` (live) | Oct 30, 2026 onward | pulled Nov 14, 2026 (through Nov 13) |

All real data stays local and git-ignored. Only fictional `sample_data/` is committed.

## Timeline

### Oct 30-31, 2026: Step 1 build-out
- **Substack pipeline** (`4cb5c40`): aggregate per-post open/delivery files (which contain emails) into email-free per-post counts; build DuckDB.
- **Mailchimp** (`e432ed5`, `095c0cc`): turn the 2,283-file account export into 5 email-free tables with a built-in no-email check. Load into DuckDB, matching export file ids to campaigns via Mailchimp's slug rule. Add Substack-vs-Mailchimp open rate comparison.
- **Exploration environment** (`3dc1569`): Jupyter notebook with a read-only DB connection and SQL practice questions.
- **LinkedIn** (`6f165af`): process page analytics exports (daily metrics, posts, demographics, peer benchmark); overlapping exports de-duplicated, newest wins. Add `inventory_files.py` to inspect new exports without exposing values.
- **Substack Stats exports**: per-post views, daily followers, monthly views, audience location; matched to posts on title + publish time.
- **Dashboard** (`5fe0465`, `88acb9b`): `export_dashboard_data.py` (aggregated CSVs) and `build_dashboard_html.py` (standalone Plotly page). A Claude-hosted version, "GRC Insights Growth Dashboard", was also published.
- **Outside the repo**: GA4 connected to Substack under a GRC-owned account; `GRC_UTM_Builder` sheet created with an approved source/medium list.
- **Findings**: batch sending costs followers, views and opens; Substack's decline is Substack-specific; Mailchimp is the biggest untapped lever; LinkedIn posts never promote Insights; the audience is waiting despite no posts since June; Mailchimp lists are rosters, not opt-in.

### Nov 13, 2026: Subscriber cohort analysis
- **`hash_subscribers.py`** (`d5ba18a`): per-subscriber delivery and open history with emails replaced by keyed HMAC-SHA256 hashes. Emails never touch disk. New tables `subscribers`, `sub_email_history`; queries `cohort_open_rates.sql`, `open_rate_by_emails_received.sql`.
- **Result**: the open-rate decline is fatigue. See finding 7 below.
- **Dashboard + sample data** (`020ee02`): "Subscriber fatigue" section (open rate by cohort). New `make_sample_data.py` generates every fake input. Fixed a `.gitignore` rule that had silently kept sample CSVs in subfolders out of git, which broke the README quick start. The quick start was verified end to end from a fresh clone.

### Nov 14, 2026: GA4, fixes, upkeep
- **Environment**: upgraded pandas 3.1.1, numexpr 2.14.2, bottleneck 1.6.1 (old conda builds caused NumPy 1.x errors) and streamlit 1.67.0 (cleared its version conflicts).
- **GA4 Data API pull** (`a839ce1`): service account `grc-ga4-reader` with Viewer access to the property; `pull_ga4.py` pulls daily traffic by source/medium/campaign/landing page and daily page views. New tables `ga4_traffic_daily`, `ga4_pages_daily` (pages matched to posts by slug); query `ga4_traffic_sources.sql`. The test request matched the GA4 UI exactly (100 users, 201 views, 533 events).
- **Dashboard** (`d82398c`): "Web traffic (GA4)" section (sessions per day, sessions by channel). The sample generator also makes fake GA4 data.
- **Privacy fix** (`9bf882f`): the full refresh tripped `aggregate_mailchimp.py`'s no-email check. Five newsletter links were malformed as `http://name@domain`, putting addresses in the domain column. Such links are now recorded as `email link`. Nothing left the machine.
- **LinkedIn reader** (`0b4709e`): switched from deprecated `xlrd` to `calamine`; outputs byte-identical.
- **Full refresh** run with all sources; `CLAUDE.md` updated and this file added.
- **Hosted dashboard**: added the Subscriber fatigue and Web traffic (GA4) sections and three datasets to the Claude-hosted dashboard. No Google Analytics connector exists in Claude.ai, so GA4 there is refreshed on request rather than live.

## Findings to date

1. **Batch sending costs subscribers and views.** The 6 days with 5+ emails averaged -7 followers/day (42 lost, ~45% of all losses since Sept 2024). Median views per post: 351 solo, 250 on 2-4 email days, 204 on 5+ days. Open rate: 49% / 38.5% / 33%.
2. **Substack's decline is Substack-specific.** Open rate ~61% -> ~27-31% while Mailchimp held ~53-68%.
3. **Mailchimp is the biggest untapped lever.** Lists of ~1,360-3,470 vs ~320 Substack recipients; Insights links drove hundreds of clicks per send, but none since Apr 2025.
4. **LinkedIn: 0 of 23 company posts in the past year promoted Insights.** GA4 confirms it: 3 LinkedIn sessions in 15 days.
5. **The audience is waiting.** +97 followers with no posts since June 1, 2026; the archive still draws ~1,500-2,100 views a month.
6. **Mailchimp lists are imported rosters**, not opt-in. Don't use them for cold outreach.
7. **The open-rate decline is fatigue, not list composition.** Every cohort declined (fall-2024 cohort: 61% -> 25%); newer cohorts open more, so list mix softened the drop. Opens fall with emails already received, even in the same quarter (40% under 25 emails vs 27% at 50+). The Q4 2025 cohort slid 58% -> 32% in two quarters of heavy sending. People who left were among the most engaged readers (45% vs 29-41%). 107 subscribers have never been emailed.
8. **GA4, first 15 days:** 287 sessions: search 114, direct 94, GRC websites 37, Substack 31, LinkedIn 3. No UTM-tagged traffic yet.

**Recommendation driving Step 2:** relaunch at one email a week.

## Open items

- [ ] **Weekly-cadence experiment**: compare views per post, send-day follower change and per-cohort open rate against the batch-era baseline; watch whether the 107 never-emailed subscribers hold their open rate.
- [ ] **UTM-tagged promotion** on LinkedIn and in the member Mailchimp newsletter; read results in `ga4_traffic_sources.sql` and the dashboard (needs the newsletter owner for Mailchimp).
- [ ] **Refresh the hosted dashboard** periodically (weekly or monthly): GA4 can't be live there, so its files are refreshed on request (steps in `CLAUDE.md` > Dashboards).
- [ ] **Fresh exports** for Substack, Mailchimp and LinkedIn before the next analysis (current ones are from Oct 30-31).
- [ ] **Further projects** for target roles, as chosen by the repo owner.

## Known caveats

- Open rates are inflated by Apple Mail Privacy Protection and scanners; Mailchimp clicks can include scanners. Treat them as directional.
- GA4 undercounts (ad blockers, inbox reads) and starts Oct 30, 2026. Use it for proportions by source, and Substack for totals.
- The batch-size findings are correlational, though consistent across three metrics.
- Small samples: most A/B-style comparisons won't reach significance, so test for big effects and make directional calls.
- 2 Mailchimp export ids remain unmatched to a campaign (duplicate titles); their clicks have no send date.
