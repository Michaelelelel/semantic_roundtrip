# Manual verifier assessment

[`verifier_assessment.csv`](verifier_assessment.csv) covers 360 prompt/image pairs
from Core job `20260903T230744Z_final-direct-core_faa7afcb`, with 90 titles per PG
model and prompt/image seeds `1000/8566257`. `run_id` + `image_id` identifies the image.

| Label | Meaning |
| --- | --- |
| `prompt_title_use` | `0`: complete title absent, `n`: normal descriptive use, `e`: explicit reference or instruction to write the complete title. |
| `flag_strict` | `1`: readable meaningful writing, `0`: allowed. |
| `flag_title_aware` | `1`: complete title readable as writing, `0`: allowed. Partial titles alone do not qualify. |

Blank means unreviewed, not `0`. Keep IDs, titles and prompt texts unchanged.
The [evaluation command](../EXPERIMENTS.md#3-manual-verifier-assessment) compares
labels with saved decisions without modifying either. Use the original Core job.
