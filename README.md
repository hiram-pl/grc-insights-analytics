# GRC Insights Analytics

An analytics pipeline for **GRC Insights**, the Substack publication of Global Research and Consulting Group (GRC), a student-run nonprofit consulting organization. It combines Substack and LinkedIn exports into a single DuckDB database so the team can measure what drives readership and make publishing decisions with data instead of instinct.

<!-- Before making this repo public: confirm with GRC leadership that the findings below are OK to share. -->

## The problem

GRC Insights had published 570+ articles, but performance data lived in separate tools (Substack, LinkedIn, Mailchimp) with no shared view. Substack's dashboard shows numbers one post at a time and has no API for publication stats, so questions like "does sending several emails in one day hurt open rates?" couldn't be answered.

## Pipeline

```
Raw exports (contain subscriber emails; never leave the owner's machine)
        │
        ▼
scripts/aggregate_opens.py      → Substack: strips emails, produces per-post counts
scripts/aggregate_mailchimp.py  → Mailchimp: campaign, link-click and list-growth tables, no emails
        │
        ▼
data/processed/*.csv          (email-free)
        │
        ▼
scripts/build_db.py           → data/grc.duckdb  (Substack + Mailchimp tables)
        │
        ▼
sql/*.sql  via  scripts/run_query.py   → analysis
```

The build is idempotent: every table is rebuilt from scratch on each run, so new exports can be dropped in without creating duplicates. A built-in anti-join check flags any stats rows that don't match a post.

## Data privacy

Raw exports contain subscriber email addresses. They are processed only on the data owner's machine, and only aggregate counts enter the pipeline. `.gitignore` blocks all real data (`data/`, `*.csv`, `*.duckdb`) from being committed. `sample_data/` contains **fake, generated data** so the pipeline can be run by anyone.

## Quick start (with fake sample data)

```bash
pip install -r requirements.txt
python scripts/build_db.py --sample
python scripts/run_query.py sql/open_rate_by_batch_size.sql --sample
```

## Running on real data

1. Unzip the Substack export into `data/raw/substack/`.
2. `python scripts/aggregate_opens.py` → writes email-free CSVs to `data/processed/`
   Optional: unzip the Mailchimp export into `data/raw/mailchimp/` and run `python scripts/aggregate_mailchimp.py`
3. `python scripts/build_db.py`
4. `python scripts/run_query.py sql/<query>.sql`

To inspect a new export without exposing its contents, `python scripts/inventory_files.py <folder>` lists each CSV's columns and row count and flags files that contain email addresses.

## Findings so far

- **Open rates roughly halved**, from ~60% of recipients in early 2025 to ~27–31% in spring 2026.
- **Subscriber growth stalled.** The list grew from 165 to ~330 between January and October 2025, then stayed flat (~320–350) for the following year.
- **Crowded send days had lower open rates.** Since October 2025: 49% on single-email days, 38.5% on days with 2–4 emails, 33% on days with 5+ (up to 13 emails in one day). Position within a batch didn't matter, so the effect looks cumulative rather than within-day.
- **Open question:** is the decline subscriber fatigue, or a change in list composition (~76 subscribers added during a period with no sends)? Next step is a subscriber-cohort analysis using hashed IDs.

## Roadmap

- [ ] Add per-post web views (Substack Stats export), the publication's north-star metric
- [ ] Subscriber cohort analysis (hashed IDs) to separate fatigue from list composition
- [x] Load Mailchimp campaign, link-click and list-growth data
- [ ] Load LinkedIn page analytics
- [ ] UTM tagging convention for cross-channel attribution
- [ ] Dashboard
- [ ] Weekly-cadence experiment: one email per week vs. historical batch sends

## Tech

Python, pandas, DuckDB, SQL (window functions, anti-joins)
