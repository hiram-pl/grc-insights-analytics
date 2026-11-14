# Publish the hosted dashboard

What Claude does when the owner says "publish the dashboard" (or "refresh the hosted dashboard")
in an interactive Claude Code session. The Artifact tools this needs don't exist in headless
`claude -p`, which is why this step isn't in the scheduled job.

Dashboard: "GRC Insights Growth Dashboard", https://claude.ai/artifact/58LF778yncSfUDhxBcGH9U
Each dataset id = a CSV's name without `.csv` in `data/processed/dashboard/`.

1. Run `python scripts/publish_dashboard.py`. It lists the changed CSVs and writes them to
   `data/processed/dashboard/.pending_publish.json`. If nothing changed, stop.
   (If the data itself is old, run `python scripts/refresh.py` first.)
2. For each listed file, read `datasets/<id>` with ArtifactData `get`. Note its `version` and
   current `source.url` (the old blob, `/_blob/<old id>`). A file with no dataset (a new CSV)
   needs a page change: skip it and tell the owner.
   Then list the artifact's assets (Artifact `list`, `scope: "assets"`); it shows each blob's
   sha256. Skip any file whose local `shasum -a 256` equals its current blob's: it's already there.
3. Upload each file: Artifact `publish` with `url`, `asset: true`, `file_path` (one per call).
   Note the returned `/_blob/<id>`.
4. One ArtifactData `batch` with an `update` per dataset, each pinned with `if_version`:
   `source.url` = new blob, `updated: {at: <UTC now>, by: "grc-insights-analytics refresh.py"}`,
   `edit: {via: "claude", at: <UTC now>}`.
5. Only after the batch succeeds, delete each replaced blob (Artifact `delete`, `url`, `path` =
   old asset id), so outdated rows don't stay downloadable. Never delete a blob a dataset still
   points to.
6. Run `python scripts/publish_dashboard.py --mark-published`.
7. Read `data/users/me/check` and `runs` via ArtifactData for errors (absent = nobody has the
   page open, which is fine).

Don't touch `files/index.html` or `dash/*` for a data publish: charts, sentences and KPIs
recompute from the datasets. Page changes are separate work (re-read the page first; follow
the type's one-writer rules).
