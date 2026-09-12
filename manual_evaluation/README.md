# Manual verifier assessment

[`verifier_assessment.csv`](verifier_assessment.csv) was manually assessed by
Michael Hagmann on 11 September 2026. It covers 360 prompt/image pairs from
`final_direct_core`, job `20260903T230744Z_final-direct-core_faa7afcb`:
90 titles from each of four PG models, at prompt/image seeds `1000/8566257`.
`run_id` + `image_id` identifies each source image. Public job download: not yet published.
Saved model decisions were visible, and selected cases were discussed with AI assistance.

| Label | Meaning |
| --- | --- |
| `prompt_title_use` | `0`: complete title absent, `n`: normal descriptive use, `e`: explicit reference or instruction to write the complete title. |
| `flag_strict` | `1`: readable meaningful writing, `0`: allowed. |
| `flag_title_aware` | `1`: complete title readable as writing, `0`: allowed. Partial titles alone do not qualify. |

Blank means unreviewed, not `0`. Keep IDs, titles and prompt texts unchanged.
The [study protocol](../configs/jobs/final_study/STUDY_DESIGN.md#protocol-validation-and-stability)
defines the full rubric and scope.

[`evaluate_verifier.py`](../scripts/evaluate_verifier.py) compares these labels
with the job's saved decisions. Agreement is `(both accept + both reject) / 360`.
Prompt categories are counted separately. Run from the repository root:

```bash
python scripts/evaluate_verifier.py --job <completed-Core-job-directory>
```

The script only prints results. It does not change labels, jobs or scoring rules.
