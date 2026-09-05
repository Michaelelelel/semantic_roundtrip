# One-shot conversion of completed jobs

`migrate_current_runs.py` converts **copies**, not the original runs. It accepts
only experiment schema 10 / run database 11 / job YAML and database 4. Other
formats are refused. The application itself reads only the new current format.

Wait until each selected job and every child run is **completed**. Terminal
failed observation tasks are preserved; running/paused jobs, unfinished tasks,
active runtime events and ambiguous provenance are refused. Never run this
against either active DGX job or change its runner while it is running.

From the repository directory, first inspect the read-only plan:

```bash
uv run python scripts/migrate_current_runs.py \
  --source-job /archive/20260903T230744Z_final-direct-core_faa7afcb \
  --source-job /archive/20260903T230758Z_final-direct-photorealistic_0488e791 \
  --destination-root /converted-study-runs \
  --dry-run
```

Replace the example parent directories with the actual completed archives.
After inspecting the reported identities, versions, counts and destination,
run the same command with `--apply` instead of `--dry-run`. Omitting both flags
is also read-only. Existing destinations are never overwritten. Each job is
published only after its complete copy passes validation. An error retains a
uniquely named, visibly incomplete `.migrating-…` directory for diagnosis; do
not use that directory for analysis or inheritance.

Conversion adds an **empty** prompt-prediction table; separates the persisted
prompt/image verification stage names; and translates active configuration and
bundled provenance snapshots. Existing predictions, checks, models, seeds,
profiles, titles, images, task states, timestamps and origin IDs do not change.
The converter checks all four image/description endpoint numerators, old-table
contents, artifact hashes, dataset/seed alignment and SQLite integrity/FKs.
Grouped verifier model lifecycle events map once to image verification; no
prompt runtime or new inference is invented.

Each copy contains `migration/report.json`, exact converter source, originals of
changed YAMLs and original-schema SQLite backups. Per-run
`migration_record.json` accompanies future inherited provenance. Historical
absolute source locations remain recorded; operational reads resolve the
bundled translated snapshots without requiring those original locations.

Keep original archives and conversion evidence. Bind the new SQ5 job explicitly
to the converted **chosen-style** job. Do not expose original and converted
copies with identical IDs simultaneously under one website/report input root.
The converter remains available until the real completed jobs have been
converted and independently verified; do not remove it merely after mock checks.
