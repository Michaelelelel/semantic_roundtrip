# One-shot conversion of completed jobs

`migrate_current_runs.py` converts **copies**, not the original runs. It accepts
two explicitly checked source formats; both use job YAML and database 4:

- experiment schema 10 / run database 11 for completed reconstruction jobs;
- experiment schema 8 / run database 10 only for complete, local rating-only
  jobs such as the archived 900-candidate illustratability job.

Other formats and mixed-version source jobs are refused. The application itself
reads only the new current format: experiment 11, run database 12, job YAML 5
and job database 4. No runtime compatibility path or model inference is added.

Wait until each selected job and every child run is **completed**. Terminal
failed observation tasks in schema-10 jobs are preserved; running/paused jobs, unfinished tasks,
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

Keep original archives and conversion evidence. Bind the SQ1 job explicitly
to the converted **chosen-style** job. Do not expose original and converted
copies with identical IDs simultaneously under one website/report input root.
The converter remains available until the real completed jobs have been
converted and independently verified; do not remove it merely after mock checks.

## Older candidate-rating archive

The original candidate job uses experiment schema 8 and run database 10.
This special conversion path is limited to a single configured local
`illustratability_rating` stage per run, no inherited work, and exactly one
complete rating and completed task per planned title. Every score must be an
integer from 0 through 100 matching its saved complete OpenAI-compatible answer.
Other stage configurations, tasks, runtime events, outputs, verification records,
lineage, incomplete ratings or unexpected versions are refused. This does not
enable conversion of older reconstruction experiments.

```bash
uv run python scripts/migrate_current_runs.py \
  --source-job artifacts/candidate_illustratability/20260902T162529Z_candidate-illustratability_a1cfe5f2 \
  --destination-root artifacts/candidate_illustratability/current/jobs \
  --dry-run
```

Only if the destination does not already exist and the preflight is correct,
replace `--dry-run` with `--apply`. A published converted copy is reused, never
overwritten or migrated again.

The conversion removes the obsolete **empty** `verifications` table and its
indexes, adds the current **empty** prompt/image-check and prompt-prediction
tables, and updates format versions. All populated tables remain exactly equal,
including all ratings, raw answers, timestamps, task attempts and runtime events.
Rating configurations change only their schema version; prompt profiles, model
settings, seeds, titles and manifest-6 artifacts are preserved. The conversion
report records the actual 8→11 / 10→12 source transition, per-domain counts and
score sums, original file hashes and independent copies of the original schemas.

The existing selected datasets and archived figures/CSVs remain usable without
conversion or rerating. Use the converted copy when loading the archived job in
the current application or rerunning its current distribution notebook; retain
the original job and archived report as historical evidence.
