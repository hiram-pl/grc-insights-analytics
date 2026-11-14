# CLAUDE.md: grc-insights-analytics

Context for Claude (and any collaborator) working in this repo. Read this first.

## What this project is

An analytics pipeline for **GRC Insights**, the Substack publication (grcglobalgroup.substack.com) of Global Research and Consulting Group (GRC), a student-run nonprofit consulting organization with 1,000+ members across university branches.

The repo owner is GRC's **Global Director of Insights** (Marketing Pod). The role started as reviewing, editing and publishing articles; this project uses the role's independence to build experience for internships in GTM engineering, product management, growth engineering, data science, data/product analytics, marketing ops, RevOps, growth analytics and product marketing.

The framing: treat Insights as a small **growth product** with users, data and a funnel, not just a publication. Every target role is a version of "understand a funnel, measure it, move it."

- **Step 1 (done):** instrument everything. Get all sources into one database, define metrics, set up attribution, build a dashboard.
- **Automation (done Nov 14, 2026):** weekly unattended refresh (launchd + `refresh.py`), Mailchimp via API, drop folder for Substack/LinkedIn, freshness tracking, hosted dashboard publish queue.
- **Step 2 (next):** create more projects for target roles and run experiments against the Step 1 baseline.

## Working with the owner (learning preferences)

The owner is learning while building. Guide them through the projects rather than doing it all. For example, have them attempt a problem before showing the answer, have them write code and you review it back and forth, or write initial code and have them fill in the gaps, or have them explain the approach and you refine it back and forth.

- When owner says to just do it, go ahead and just do it yourself.

Skill level: comfortable reading SQL (about a third of LeetCode SQL 50), though they've forgotten the syntax. Knows Python, Jupyter, pandas and ML concepts but forgets exact syntax, so scaffold the Python and SQL. Has taken Data C88C at UC Berkeley (c88c.org).

## Privacy rules (non-negotiable)

- Raw exports contain **subscriber email addresses**; the Mailchimp high school competition audience contains **minors' names, schools, cities, gender**. Raw files never leave the owner's machine and never go into git, Claude chats, or third-party tools.
- Aggregate locally first (`aggregate_opens.py`, `aggregate_mailchimp.py`); only email-free outputs in `data/processed/` are shared or analyzed.
- Before sharing any new export, run `python scripts/inventory_files.py <folder>`: it prints columns and row counts and flags files containing emails, without showing values.
- For the competition audience: counts by month/source/rating only. No school- or city-level breakdowns.
- Subscriber-level analysis uses **hashed IDs**, never emails. `hash_subscribers.py` replaces each email with an HMAC-SHA256 hash keyed by `data/.subscriber_hash_key` (git-ignored, created on first run). Anyone with the key plus a list of emails could re-link IDs to people, so the key never leaves the owner's machine; reuse it on later exports so IDs stay stable.
- The GA4 service account key (`data/ga4-key.json`) and the Mailchimp API key (`data/mailchimp-key`) are credentials: git-ignored, `chmod 600`, never pasted into chats or tools.
- API pulls request only the fields they need (`fields=` whitelist), so personal data never reaches the machine. Keep it that way when adding endpoints.
- `ingest_inbox.py` refuses to copy any file containing an email into `data/processed/`, and extracts zips safely (no paths outside the target).
- Privacy checks are a feature: if `aggregate_mailchimp.py` (or any script) stops on its no-email check, find and fix the cause; never weaken or skip the check.
- The **code is the owner's; the data is GRC's.** Commit and publish only `sample_data/` (fictional), never real data.
- Clear notebook outputs before committing (`jupyter nbconvert --clear-output --inplace notebooks/explore.ipynb`).
- Never put names, emails or anything private in a UTM.

## Repo layout

```
grc-insights-analytics/
├── CLAUDE.md
├── README.md                 # recruiter-facing: problem, pipeline, privacy, findings, roadmap
├── STATUS.md                 # project log: everything done so far, current state, open items
├── requirements.txt          # duckdb, pandas, matplotlib, plotly, jupyterlab, google-analytics-data, python-calamine, requests
├── .gitignore                # blocks data/, *.csv, *.xls*, *.zip, *.duckdb; allows sample_data/**/*.csv
├── ops/
│   ├── com.grc.insights.refresh.plist  # launchd template (no user paths): refresh.py every Monday 08:00
│   ├── install_schedule.sh             # fills in the template and loads it (--remove to uninstall)
│   ├── publish_dashboard_prompt.md     # the "publish the dashboard" procedure
│   └── RUNBOOK.md                      # what happens each Monday, what each notification means, what to do
├── scripts/
│   ├── refresh.py                # ONE COMMAND for the whole refresh (what launchd runs); see Commands
│   ├── ingest_inbox.py           # drop folder: routes exports in data/inbox/ and runs their processor
│   ├── pull_mailchimp.py         # Mailchimp Marketing API -> same 4 CSVs as the export path (fields= whitelist)
│   ├── mc_common.py              # shared: URL cleaning, slug rule, no-email check (both Mailchimp paths)
│   ├── publish_dashboard.py      # lists dashboard CSVs changed since the last hosted publish
│   ├── inventory_files.py        # list CSVs: columns, row counts, email flag (no values printed)
│   ├── aggregate_opens.py        # Substack per-post open/deliver files -> per_post_opens.csv (+ copies posts.csv)
│   ├── hash_subscribers.py       # Substack email list + deliveries/opens -> subscribers.csv, sub_deliveries.csv (hashed ids)
│   ├── aggregate_mailchimp.py    # Mailchimp export -> 5 email-free tables (fallback/backfill; the API pull is primary)
│   ├── process_linkedin.py       # LinkedIn .xls/.xlsx exports -> daily/posts/demographics/competitors CSVs (calamine reader)
│   ├── pull_ga4.py               # GA4 Data API -> processed/ga4/traffic_daily.csv, pages_daily.csv
│   ├── build_db.py               # processed CSVs -> data/grc.duckdb (22 tables)
│   ├── run_query.py              # run a sql/*.sql file against the DB
│   ├── export_dashboard_data.py  # DB -> 8 required + 4 optional CSVs for the dashboards (deterministic row order)
│   ├── build_dashboard_html.py   # those CSVs -> standalone Plotly dashboard.html
│   └── make_sample_data.py       # seeded generator for every fake input in sample_data/
├── sql/                      # saved analysis queries (see below)
├── notebooks/explore.ipynb   # read-only DB connection, q("SQL") helper, practice questions Q1-Q5
├── sample_data/              # FICTIONAL data mirroring every real input (incl. hashed subscribers, GA4); safe to commit/publish
└── data/                     # REAL data, git-ignored
    ├── inbox/                # DROP EXPORTS HERE; processed ones move to inbox/_done/<date>/
    ├── raw/{substack,mailchimp,linkedin}/   # full exports keep one <folder>.prev copy
    ├── processed/            # posts.csv, per_post_opens.csv, subscribers.csv, sub_deliveries.csv,
    │                         # mailchimp/, mailchimp_archive/, linkedin/, substack_stats/, ga4/, dashboard/,
    │                         # freshness.csv, pipeline_runs.csv
    ├── logs/                 # one refresh_<timestamp>.log per run
    ├── ga4-key.json          # GA4 service account key (credential)
    ├── mailchimp-key         # Mailchimp API key (credential, chmod 600)
    ├── ga4_property_id       # numeric GA4 property ID, read by pull_ga4.py
    ├── .subscriber_hash_key  # HMAC key for hashed subscriber ids
    └── grc.duckdb
```

`build_db.py`, `run_query.py`, `export_dashboard_data.py` and `build_dashboard_html.py` take `--sample` to run against `sample_data/`. The processing scripts take an optional path to the raw export instead. `pull_ga4.py` takes `--property` and `--start`.

## Commands

```bash
pip install -r requirements.txt

# Weekly refresh (automatic: launchd runs this every Monday 08:00; operations guide: ops/RUNBOOK.md)
python scripts/refresh.py                  # inbox -> GA4 -> Mailchimp -> freshness -> build -> export -> HTML -> queue
python scripts/refresh.py --no-pulls       # quick rebuild without the API pulls
#   Manual sources: drop the export (zip or file, as downloaded) into data/inbox/; the next run files it.
#     Substack account export (.zip), Substack Stats-page CSVs, LinkedIn .xls/.xlsx, Mailchimp export (.zip, backfill only)
#   Hosted dashboard: when the run says "N files to publish", say "publish the dashboard" in Claude Code.
#   Exit codes: 0 ok, 2 finished with a failed/stale source, 1 a build step failed (nothing published).

# Pieces, if you need them one at a time
python scripts/ingest_inbox.py [--dry-run]
python scripts/pull_ga4.py                 # live API pull through yesterday
python scripts/pull_mailchimp.py           # ~4 min (2 requests per campaign)
python scripts/build_db.py && python scripts/export_dashboard_data.py && python scripts/build_dashboard_html.py
python scripts/publish_dashboard.py [--mark-published]

# Schedule
zsh ops/install_schedule.sh                # install/update the launchd job (PYTHON=... to override)
launchctl kickstart gui/$(id -u)/com.grc.insights.refresh   # run it now
launchctl print gui/$(id -u)/com.grc.insights.refresh       # last exit code, run count
tail ~/Library/Logs/grc-insights-refresh.log                # launchd-level output

# Sample data (README quick start; verified from a fresh clone)
python scripts/make_sample_data.py         # only if the generator changed; outputs are committed
python scripts/build_db.py --sample
python scripts/run_query.py sql/cohort_open_rates.sql --sample
python scripts/export_dashboard_data.py --sample && python scripts/build_dashboard_html.py --sample

# Explore
python scripts/run_query.py sql/<query>.sql [--sample]
duckdb -readonly data/grc.duckdb           # SHOW TABLES; DESCRIBE t; SUMMARIZE t;
duckdb -ui -readonly data/grc.duckdb       # browser UI
jupyter lab                                # notebooks/explore.ipynb
```

Expected `build_db.py` output on real data includes:
`opens rows with no matching post: 0`, `Substack stats: 581 of 581 posts matched`, `Subscribers: 30,363 deliveries to 474 hashed ids`, `GA4: <first> to <yesterday>, ... page views matched to a post`, `Mailchimp: 219 of 222 export ids matched` (the 3 unmatched are deleted campaigns kept from the archive), `Freshness: 5 of 5 sources up to date`, `LinkedIn: 365 days (2025-10-29 to 2026-10-28), 23 posts, 0 promoting Insights`.

Always open DuckDB **read-only** when exploring; a writable session locks the file and `build_db.py` fails.

### Environment notes
- Python is Anaconda's (`/Applications/anaconda3/bin/python3`). NumPy and pandas were installed with pip, so install or upgrade packages with `python3 -m pip`, not conda, to keep compiled packages matched to NumPy 2.x. (Old conda builds of numexpr/bottleneck caused NumPy-1.x errors until they were upgraded on Nov 14, 2026.)
- DuckDB is 2.0: relations no longer have `fetchone()`. Use `.fetchall()[0]`.
- Window functions over aggregates need an explicit `GROUP BY col, col` (not `GROUP BY ALL`) or DuckDB raises "Cannot mix aggregates".
- macOS has no `timeout` command.
- launchd runs fine from `~/Desktop` here (no folder-access prompt needed; checked Nov 14, 2026). If a scheduled run ever fails with "Operation not permitted", grant the Python binary Full Disk Access or move the repo, then re-run `ops/install_schedule.sh`.
- Headless `claude -p` has no Artifact tools (Claude Code 2.1.325), which is why hosted publishing is a weekly one-liner.

## Data sources and their quirks

**Substack (account export)**
- `posts.csv`: 655 rows, 572 published posts back to 2018. **No performance numbers.** Join key `post_number` = numeric part of `post_id` (`200141804.slug` -> `200141804`).
- Older posts are an imported archive; **email history only starts Sept 2024** (98 emailed posts, then more; opens files exist only for those).
- `<post_id>.opens.csv` / `.delivers.csv` list individual emails -> aggregated locally into `per_post_opens.csv`, and hashed into per-subscriber history by `hash_subscribers.py`. 102 emailed posts, 30,363 deliveries to 474 addresses.
- `email_list.<pub>.csv`: current list only (460 addresses, `created_at` = signup). The 121 addresses that received emails but have since left are **not** in it, so their signup date is unknown; cohorts therefore use the **quarter of first Insights email**, which is known for everyone. 107 people on the list have never been emailed (joined after the last send, June 2026).
- Subtitles often follow `By Name, University` (author + branch), messy in places.

**Substack (Stats page exports, `*_YYYY-MM-DD.csv`)**
- `email_stats`: per-post views, signups, open rate. **No post_id**, and 22 titles repeat, so match on **title + publish time within 120 s**.
- `followers`: daily totals, **no header row**, dates `YYYY/MM/DD`.
- `traffic`: monthly views. `audience_location`: free signups by country.
- `build_db.py` uses the newest file for each pattern.

**Mailchimp (account export, 2,283 files)**
- Keep: `campaigns.csv` (220 campaigns since 2020), `lists/*` (counts only), `geo_data/clicks/*` (clicks per URL), `aggregate_activity/unsub-reasons/*` (category only, free text dropped).
- Click URLs can contain email addresses: `mailto:` links, and five 2025 newsletter links malformed as `http://name@domain` (the address lands in the URL's host). Both are recorded as domain `email link` with no path.
- Skip for now: `aggregate_activity/{opened,not_opened,click_activity,...}` and `granular_activity/*` (per-person; raw material for the hashed cohort analysis).
- Click/unsub files are named `<num>_<slug>.csv`; `campaigns.csv` never uses `<num>`. Join by recreating Mailchimp's slug rule `regexp_replace(lower(Title), '[^a-z0-9]+', '-', 'g')`; for duplicate titles pair lowest num with earliest send (`ROW_NUMBER() OVER (PARTITION BY slug ...)`). `<num>` is Mailchimp's `web_id`, so when the API pull provides `Web Id` the build matches on it exactly instead (219 of 222). The 3 left are campaigns deleted from Mailchimp (a second "January Newsletter", an Imperial welcome email, a "BCG Mentorship" duplicate); the build prints them.
- Send dates look like `May 08, 2020 10:03 am`; rates in the export are text (`"75.00%"`), so recompute from counts.
- `MEMBER_RATING` is useless here (almost everyone has the default 2): excluded.
- Audiences are **imported rosters**: exactly one contact ever came via a signup form.

**Mailchimp (Marketing API, `pull_mailchimp.py`, primary since Nov 14, 2026)**
- Key in `data/mailchimp-key` (owner role, data center `us18`, account time zone America/New_York). Basic auth, any username.
- Every request names its `fields`, so emails are never requested (members: only status/source/timestamps; unsubscribes: only reason). The no-email check still runs on the outputs.
- Writes the same 4 CSVs and columns as the export path (`campaigns.csv` gets an extra `Web Id`). `build_db.py` then matches export ids on `web_id` exactly instead of by title.
- Field traps found by reconciling with the export: export "Unique Clicks" = API `unique_subscriber_clicks` (API `unique_clicks` counts person x link, ~2.6x larger); API status `subscribed` = export folder `members`.
- **Deleted campaigns vanish from the API.** Their clicks/unsubscribes (3 campaigns, incl. a Feb 2025 "January Newsletter" with 345 Insights clicks) are kept from the frozen, email-free `data/processed/mailchimp_archive/` (from the Oct 30, 2026 export).
- API clicks are more complete than the export's geo files (~3k clicks had no location). Apr 2025 Insights clicks: 405 (export said 389).
- `/campaigns` also lists drafts; draft titles can contain email addresses, so never write draft titles anywhere.
- `aggregate_mailchimp.py` would overwrite the API outputs, so the inbox files a Mailchimp export zip without running it.

**LinkedIn (page analytics .xls/.xlsx)**
- Read with `engine="calamine"` (pandas deprecated xlrd). Switching produced byte-identical outputs.
- Some sheets have a description sentence above the header (auto-detected).
- "Total followers" in the daily sheet actually means **new followers that day** -> renamed `new_followers`.
- Overlapping exports: newest export wins per date.
- `promotes_insights` = post text matches `substack|grc insights|insights.grcglobalgroup` (keyword match; misses links without those words).

**GA4**
- Property under a **GRC-owned** Google account; Measurement ID pasted into Substack Settings > Analytics (Substack inserts the Google tag; leave the GTM field empty). Enhanced measurement off; data retention 14 months; Marketing Pod lead added as admin.
- Test in incognito: ad blockers (e.g. uBlock Origin Lite) replace the GA script with a `chrome-extension://` stand-in, so nothing is sent.
- **GA4 undercounts** (blockers, inbox reads). Use Substack views for totals, GA4 for proportions by source/medium.
- **Data starts Oct 30, 2026** (when GA4 was connected); nothing earlier exists.
- **Data API pull:** `pull_ga4.py` authenticates as the service account `grc-ga4-reader` (key in `data/ga4-key.json`), which has **Viewer** access on the property (GA4 Admin > Property access management) and the Google Analytics Data API enabled in its Cloud project. No Cloud IAM roles needed. Property ID lives in `data/ga4_property_id`. Pulls through *yesterday*; GA4 needs about a day to finalize.
- Two reports, rebuilt in full each run: `traffic_daily` (date x source x medium x campaign x landing page: sessions, engaged_sessions, new_users, views, engagement_seconds) and `pages_daily` (date x page: views, active_users). `active_users` is not summable across days.
- Pages match to posts on `/p/<slug>` = second part of `post_id`. Unmatched views are site pages (`/`, `/archive`, `/t/...`), not errors.
- Source quirks: Substack's own search shows as `publication-search`; AI tools as medium `ai-assistant`; Substack share links add campaigns like `post-expanded-share`.

## Database tables (`data/grc.duckdb`)

| Table | One row = | Notes |
|---|---|---|
| `posts` | Substack post | `post_number`, `published_at`, `emailed_at` |
| `opens` | emailed post | recipients, unique_openers, total_opens, open_rate |
| `email_posts` | emailed post | + `batch_size` (Insights emails that UTC day), `position_in_batch`, `views`, `signups` |
| `post_stats` | post | views, signups, engagement_rate |
| `sub_followers_daily` | day | followers, `change` vs prior day (LAG) |
| `sub_views_monthly` | month | total views (web + email) |
| `sub_audience_location` | country | free signups |
| `mc_campaigns` | Mailchimp campaign | sent_at, delivered, unique_opens/clicks, unsubscribes, open/click rate, slug |
| `mc_link_clicks` | link x campaign | clicks, `is_insights` flag |
| `mc_list_growth` | audience x status x source x month | contacts |
| `mc_unsub_reasons` | reason x campaign | unsubscribes |
| `mc_campaign_ids` | export file id | maps `campaign_num` -> `campaign_uid` (NULL if unmatched) |
| `li_daily` | day | impressions, clicks, reactions, comments, reposts, engagements, new_followers, page_views |
| `li_posts` | company page post | impressions, clicks, likes, comments, reposts, follows, `promotes_insights` |
| `li_demographics` | breakdown value x export | followers/visitors by location, industry, etc. |
| `li_competitors` | peer page x export | LinkedIn's benchmark |
| `subscribers` | hashed subscriber | `sub_id`, `signed_up_at` (NULL if left), `active_subscription`, `email_disabled`, `on_list` |
| `sub_email_history` | email delivered to a subscriber | `cohort` (quarter of first Insights email), `send_quarter`, `prior_emails`, `opened` |
| `ga4_traffic_daily` | day x source x medium x campaign x landing page | sessions, engaged_sessions, new_users, views, engagement_seconds |
| `ga4_pages_daily` | day x page | views, active_users, `post_number` (NULL for non-post pages) |
| `freshness` | data source | status ok/stale/failed/missing, updated_on, data_through, age_days, action (written by `refresh.py`) |
| `pipeline_runs` | refresh step x run | status, seconds, note: run history for debugging |

Saved queries in `sql/`: `channel_open_rates`, `insights_clicks_from_mailchimp`, `linkedin_monthly`, `cohort_open_rates`, `open_rate_by_emails_received`, `ga4_traffic_sources`. (The batch-size and send-day analyses now live as queries inside `export_dashboard_data.py`.)

## Metric definitions and conventions

- **North star: views** (Substack's count, web + email). Chosen because at this size visibility beats engagement.
- **Guardrail: unsubscribes / follower losses.**
- **Inputs:** posting volume (Substack), quality (restacks/shares; non-subscriber views), outreach (LinkedIn/IG/Mailchimp posts linking to Insights; logged by the UTM sheet), discoverability (search traffic, GA4).
- **Rates are always SUM(numerator)/SUM(denominator).** Never average or sum rates (summing LinkedIn daily engagement rate gave 40.68; the real yearly rate was 18.7%).
- Know the **grain** of a table before any SUM/COUNT.
- Open rate is inflated by Apple Mail Privacy Protection and security scanners; Mailchimp click totals can include scanner clicks. Treat as directional.
- `batch_size` uses UTC days; Substack follower days use Substack's boundary, so some drops land a day early.
- Small lists: most A/B tests won't reach significance. Say so; test for big effects, pool across sends, make directional calls.
- Every build step must be **idempotent** (`CREATE OR REPLACE`), and include a sanity check (anti-join or match count) for every join.

## UTM convention

Use the **GRC_UTM_Builder** sheet (Google Sheet, shared with the Marketing Pod) for every Insights link shared **outside** Substack: LinkedIn, Instagram (incl. bio), Mailchimp, group chats/Slack, QR codes.

- Approved sources -> mediums: `linkedin/social`, `instagram/social`, `facebook/social`, `mailchimp/email`, `whatsapp/messaging`, `slack/messaging`, `grc-website/referral`, `partner/referral`, `poster/qr`. Add new ones to the Sources tab first.
- Lowercase, hyphens. Campaign = article slug (`esg-reporting`) or `initiative-yyyy-mm` (`gmt-newsletter-2026-11`). Content optional (`author-tag`, `member-repost`, `reminder`).
- The sheet's Check column must say OK (case-sensitive source check, source/medium match).
- **Never** tag links inside Substack (post-to-post, Notes, Substack emails): it overwrites the real source.
- Strip Substack's own `?utm_...` from share-button links before building.
- A link's tags must describe where *that* link is posted.
- Read results in GA4: Reports > Acquisition > Traffic acquisition, dimension Session source / medium, secondary Session campaign.

## Findings so far (Oct 31, 2026 exports; GA4 through Nov 13, 2026)

1. **Batch sending costs subscribers and views.** Since Sept 2024, Insights emails went out on only 39 days (13 emails on Jan 19, 2026; 11 on May 9).
   - Followers: 6 days with 5+ emails averaged **-7/day**, 42 lost in total, more than across all 733 no-send days. That's 42 of 93 total losses since Sept 16, 2024 (**~45%**). Worst two days ever (-14 each) = Jan 19 and May 9.
   - Views per post (Oct 2025+): median **351** solo, **250** on 2-4 days, **204** on 5+ days (~42% lower).
   - Open rate (Oct 2025+): 49% solo, 38.5% on 2-4, 33% on 5+. Position within a batch doesn't matter.
   - Correlational, but consistent across three metrics.
2. **Substack's decline is Substack-specific.** Open rate ~61% (late 2024) -> ~27-31% (spring 2026) while Mailchimp held ~53-68%. Rules out channel-wide causes.
3. **Mailchimp is the biggest untapped lever.** ~2,530 main list, ~1,360 current members, ~3,470 HS competition vs ~320 Substack recipients. Insights links drove ~250 clicks (Nov 2024), ~680 (two Jan 2025 sends), 405 (Apr 2025; 389 in the export's geo files, which miss clicks without a location), then **nothing since Apr 2025**. A broken Nov 2024 link (two URLs pasted together) got 129 clicks.
4. **LinkedIn: 0 of 23 company posts in the past year promoted Insights.** July engagement rate (53%) is inflated by "Meet the Pod" posts with tagged people (clicks on names). GRC 7,042 followers; peers TAMID 22,812 (254 posts/yr), 180 Degrees 95,697 (28 posts/yr).
5. **Audience is waiting.** No posts since June 1, 2026, yet +97 followers (465 total). Archive still drew 2,118 views (Sept) and 1,491 (Oct). Views run ~2x email opens.
6. **Mailchimp lists are rosters, not opt-in.** 1 form signup ever; of 706 unsubscribes, 22 chose "I never signed up", 9 spam reports; a 2023 cold "Sample of 1,000 teacher emails" got 121 bounces. Don't use GRC's Mailchimp for cold outreach; use an outbound tool and check Mailchimp's acceptable use policy.
7. **The open-rate decline is fatigue, not list composition** (`cohort_open_rates.sql`). Every cohort (by quarter of first email) declined: the fall-2024 cohort went 61% (Q4 2024) -> 25% (Q2 2026). Newer cohorts open *more* than older ones, so list mix softened the drop (at the Q4 2024 mix, Q2 2026 would be ~25% vs actual 29%).
   - Heavy sending burns new subscribers fast: the Q4 2025 cohort went 58% -> 42% (next quarter, 32 emails) -> 32%.
   - Within the same quarter, open rate falls with emails already received (`open_rate_by_emails_received.sql`): Q2 2026: 40% (<25 emails), 31% (25-49), 27% (50+).
   - The 121 who left the list were engaged: 45% open rate in Q1 2026 vs 29-41% for cohorts that stayed.
   - 107 subscribers have never received an email, so the relaunch reaches a fresh group.
8. **GA4, first 15 days (Oct 30 - Nov 13, 2026):** 287 sessions. Search engines 114 (42% engaged), direct 94 (22%), GRC websites 37 (49%), Substack 31, LinkedIn 3. No UTM-tagged campaigns yet. Early and small: directional only.
- **Discarded hypothesis:** the 2025 subscriber jump was *not* a bulk import; daily data shows gradual fall-recruiting growth.
- **Answered:** "fatigue or list composition?" -> fatigue (finding 7).

## Dashboards

- **Claude-hosted:** "GRC Insights Growth Dashboard", https://claude.ai/artifact/58LF778yncSfUDhxBcGH9U. Private until shared; anyone shared with can download its data files. Built from the Claude "Dashboard" artifact type: its page (`files/index.html`) and its 12 datasets live in the artifact's store, and each dataset is an attached CSV with the **same id as the CSV name** in `data/processed/dashboard/` (8 originals + `cohort_open_rates`, `ga4_daily`, `ga4_channels`, `freshness`, added Nov 14, 2026).
- **No live GA4:** Claude.ai has no Google Analytics connector (checked Nov 14, 2026), so the hosted dashboard can't query GA4 live. It's refreshed on request instead. A self-hosted GA4 MCP server was judged not worth the upkeep; Looker Studio is the option if the team needs live GA4 between refreshes.
- **"Publish the dashboard"** (or "refresh the hosted dashboard") means: follow `ops/publish_dashboard_prompt.md`. In short:
  1. Data should already be fresh from the weekly `refresh.py`; if not, run `python scripts/refresh.py` first.
  2. `python scripts/publish_dashboard.py` lists CSVs changed since the last publish (by SHA-256 against `data/processed/dashboard/.published_hashes.json`).
  3. Upload only those whose sha256 differs from the attached blob (Artifact `list` `scope: "assets"` shows blob hashes), batch-update the `datasets/<id>` pinned to their versions, then delete the replaced blobs.
  4. `python scripts/publish_dashboard.py --mark-published`, then read `data/users/me/check` and `runs`.
  5. Don't touch `files/index.html` for a data publish. For page changes, re-read it first (the owner may have edited it by hand) and follow the type's `one-writer` rules.
- **Why not fully automatic:** the Artifact tools exist only in interactive Claude Code sessions, not headless `claude -p` (tested Nov 14, 2026 with Claude Code 2.1.325, also with `--tools`). So the weekly job queues changes and notifies; the owner says "publish the dashboard". Re-test `claude -p` after Claude Code updates; if the tools appear, `publish_dashboard.py` can call it directly.
- The hosted page shows a **"Data as of"** line from the `freshness` dataset (added Nov 14, 2026).
- **Standalone:** `build_dashboard_html.py` -> `data/processed/dashboard/dashboard.html` (real, internal) and `sample_data/dashboard/dashboard.html` (fictional, publishable via GitHub Pages once the repo is public). Loads Plotly from CDN.
- Headline: "Relaunch at one email a week." KPIs: followers + 30-day change, latest-month views, Substack vs Mailchimp open rate, LinkedIn posts linking to Insights.
- Sections: Reach, Sending pattern, **Subscriber fatigue** (open rate by cohort; optional, needs hashed subscriber data), **Web traffic (GA4)** (sessions per day, sessions by channel; optional, needs GA4 pull), Channels, every emailed post, definitions. Optional sections are skipped cleanly when their data is missing.
- GA4 channel grouping (in `export_dashboard_data.py`): Direct, Search engines, LinkedIn, Email, Substack (incl. `publication-search`), GRC websites, Other.
- Possible later: Looker Studio (connects to GA4 directly).

## Step 2: next experiments and projects

- **Other projects**: repo owner may specify what other projects they want to work on.
- **Weekly cadence** for the relaunch: one email at a time; bundle backlogs into one digest. Compare views/post, send-day follower change and **per-cohort open rate** against the batch-era baseline. First relaunch sends matter: the fall 2026 cohort (107 never-emailed subscribers) is subscribed and waiting. Track whether its open rate holds near its starting level instead of the 58% -> 32% slide the Q4 2025 cohort showed.
- **UTM results in GA4:** once tagged links go out, they appear by campaign in `sql/ga4_traffic_sources.sql` and in the dashboard's GA4 section.
- **Insights section in the member/GMT Mailchimp newsletter** with tagged links (`mailchimp/email/gmt-newsletter-yyyy-mm`); read sessions in GA4. Needs the newsletter owner.
- **LinkedIn promotion** of every article with a tagged link; tag the author and branch.
