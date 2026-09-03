# Final study protocol

This file records the exact executable protocol. Scientific justification and
interpretation belong in the thesis.

## Four-style selection pilot (revision `final_v2`)

`configs/jobs/style_pilot/free.yaml`, `sketch.yaml`, `comic.yaml` and
`photorealistic.yaml` are separate pilot jobs. Each uses the same 90 held-out
titles (30 per domain), only Q25/Q25, G3/G3, Q38/Q38 and G4/G4 PG/BI pairs,
prompt seed `1000` and image seed `8566257`. There are 360 planned images and
direct predictions per job. No rating, description or indirect guessing stages
are executed. The blind strict Q38 verifier, 28-step SD profile and non-style
inference settings remain fixed; only the explicit style instruction differs.

`scripts/datasets/build_style_pilot.py` samples from the saved eligible top-300
CSV after excluding the existing random and high-illustratability final sets.
It shuffles each domain with seed `20260903`, enforces one song per primary
artist and writes dataset YAML, source CSV and a JSON provenance manifest.
There are no length or rating quotas. This held-out selection is not the full
candidate population and is not a replacement for either final dataset.

The pilot reports strict and normalized end-to-end accuracy, both with the same
complete planned denominator, plus per-model/per-domain and technical tables.
It uses one seed pair and cannot establish seed robustness, crossed PG/BI style
interactions or superiority on the indirect route. The shared main-study style
is selected separately after reviewing this evidence. Existing main job
definitions below are retained; the pilot does not silently replace SQ1.

For the supervisor's rating figure, `RATING_JOB` identifies the complete
four-model candidate-rating job. Each candidate contributes its equally weighted
Q25/G3/Q38/G4 mean only when all four ratings are available. Histograms use a
fixed 0--100 scale in separate domain panels and report incomplete ratings.
The 900-candidate pool must not be confused with either 90-title final set.

The existing notebook's `ANALYSIS_MODE=style_pilot` requires no indirect or
Aqueduct jobs. Commands are in [`../../../RUNNING.md`](../../../RUNNING.md).

## Roles and routes

- PG: title and domain to visual prompt.
- BG: visual prompt to image.
- Verifier: rejects images with unambiguously readable meaningful writing.
- BI: image to title on the direct route.
- BB: image to neutral description; BI reconstructs the title from that
  description on the indirect route.

## Shared protocol

- Dataset: `final_titles_v1`, 30 songs, 30 movie titles and 30 band names.
- Selection: fixed-seed random sample from each eligible top-300 popularity
  pool; seed `20260811`; no title-length quota.
- Cutoff: entries released by 2018; documented filters, six development-title
  exclusions and at most one song per primary artist.
- Prompt seeds: `1000`, `1001`.
- Image seeds: `8566257`, `2875613`.
- Observations: four per title and condition.
- Retry: one technical retry with identical settings.
- No retry because a reconstruction is wrong.
- Run artifacts are never edited manually.

The supplementary high-illustratability dataset is selected independently of
reconstruction accuracy. Q25, G3, Q38 and G4 each rate all 900 eligible
candidates once with `rating_v2`, temperature 0 and thinking off. A candidate
must have all four ratings. Their equally weighted mean is sorted descending
within domain, followed by popularity rank and stable source ID; songs are
deduplicated by primary artist. The first 30 per domain form
`illustratable_titles_v1`; the next two form the disjoint six-title development
set. Selection aborts if a domain has fewer than 32 complete selectable ratings.
There is no absolute score cutoff. The selected final and development splits
are disjoint, but they need not be disjoint from the random main sample.

Dataset sources and limitations are in
[`../../datasets/final_titles_v1.md`](../../datasets/final_titles_v1.md).

## Models

| ID | Model | Deployment | Roles |
| --- | --- | --- | --- |
| Q25 | Qwen2.5-VL-32B-Instruct F16 | local | PG, BB, BI |
| G3 | Gemma 3 27B IT F16 | local | PG, BB, BI |
| Q38 | Qwen3.8-27B BF16 | local | PG, BB, BI, verifier |
| G4 | Gemma 4 31B IT BF16 | local | PG, BB, BI |
| D32 | DeepSeek-R1-Distill-Qwen-32B F16 | local | PG, BI |
| O120 | GPT-OSS 120B MXFP4 | local | PG, BI |
| V4 | DeepSeek-V4-Flash 284B | Aqueduct | PG, BI |
| BG | Stable Diffusion 3.5 Large BF16 | local | image generation |

V4 is an externally hosted larger configuration, not an equal-size or
equal-compute comparison.

## Jobs

| Config | Conditions | New images | Purpose |
| --- | ---: | ---: | --- |
| `direct_core.yaml` | 16 | 1,440 | direct Qwen/Gemma 4 x 4 |
| `indirect_local.yaml` | 16 | 720 | local indirect 2 x 4 x 2 |
| `aqueduct_v4_extension.yaml` | 20 additions | 360 | complete indirect 3 x 4 x 3 |
| `direct_sketch.yaml` | 16 | 1,440 | paired direct style supplement |
| `direct_comic.yaml` | 16 | 1,440 | paired broad comic-style supplement |
| `direct_thinking.yaml` | 12 additions | 720 | native-thinking direct supplement |
| `direct_illustratable.yaml` | 16 | 1,440 | high-illustratability direct supplement |

`candidate_illustratability.yaml` is a four-model rating prerequisite, not an
eighth reconstruction job. It must complete before the illustratability datasets
and jobs can be generated.

The Aqueduct job imports the exact completed `indirect_local` job. It must be
bound explicitly with `--source-job local_indirect=runs/JOB_DIRECTORY` when
started. If the optional plan view is used, it needs the same binding. No
automatic newest-job or dataset-fingerprint check is used.

The thinking job imports the exact completed `direct_core` job with
`--source-job direct_base=runs/JOB_DIRECTORY`. It computes only the 12 cells in
which Q38 or G4 occupies PG or BI; the four Q25/G3-only cells come from the
thinking-off direct job during analysis.

## Prompts

- PG: `prompts/prompt_generation/visual_single_v5.yaml`.
- Sketch PG: `prompts/prompt_generation/visual_single_sketch_v2.yaml`.
- Comic PG: `prompts/prompt_generation/visual_single_comic_v1.yaml`.
- Verifier: `prompts/verification/json_v3.txt`.
- BB: `prompts/image_description/plain_v1.txt`.
- Direct BI: `prompts/title_guessing/plain_v3.txt`.
- Indirect BI: `prompts/title_guessing/description_plain_v3.txt`.
- Illustratability: `prompts/illustratability/rating_v2.yaml`.

The unrestricted PG prompt requests one concise concrete scene and prohibits
the target string, readable text, logos and existing cover/poster art. It does
not prescribe a style. The sketch supplement changes only the PG style
instruction in the scientific path and requires this exact prefix:

```text
A simple sparse black-ink freehand outline sketch on a plain white background, using only hand-drawn contour lines, depicting
```

The comic supplement instead requires this broader exact prefix:

```text
A stylized comic or cartoon illustration depicting
```

Colour, line work and concrete comic execution remain free. Readable text,
speech bubbles, logos and the target title remain prohibited.

## Text inference

Common sampled profile: temperature 1, top-p 0.95, top-k 0, min-p 0,
repeat penalty 1, presence penalty 0 and frequency penalty 0.

| Scope | Reasoning | Output ceiling | Timeout |
| --- | --- | ---: | ---: |
| Q25/G3/Q38/G4 PG, rating and BB | none; explicitly off for Q38/G4 | 512 | backend profile |
| Q25/G3/Q38/G4 direct/indirect BI | none; explicitly off for Q38/G4 | 128 | backend profile |
| D32 PG and BI | native DeepSeek | 16,384 | 7,200 s |
| O120 PG and BI | Harmony medium | 16,384 | 7,200 s |
| V4 PG and BI | Aqueduct high | 32,000 | 3,600 s |
| fixed Q38 verifier | off; temperature 0, top-p 1 | 512 | 1,800 s |

The primary, style and illustratability matrices keep Q38/G4 thinking off. In
the separate thinking supplement, Q38 and G4 use native thinking whenever they
occupy PG or BI; Q25 and G3 are unchanged and the Q38 verifier remains off.
Q38 uses the `deepseek` reasoning format and G4 uses `auto`, with no explicit
thinking budget, a 16,384-token output ceiling and a 7,200-second timeout.

Local reasoning models use a 32,768-token context with context shifting off.
Reasoning is model-specific; the study does not claim equal test-time compute.
A completion stopped by the token ceiling is a technical failure, even if hidden
reasoning exists.

## Image generation

All conditions use `workflows/sd3_5_large_api.json`:

- 1024 x 1024;
- 28 steps;
- CFG 4.5;
- DPM++ 2M;
- SGM Uniform;
- SD3 shift 3;
- denoise 1 and batch size 1;
- negative prompt: `text, letters, words, logos, watermarks`.

This is the fixed study deployment profile, not a claimed universal or official
optimum. Historical runs keep their own saved workflow.

## Outcomes and analysis

Primary outcome: title-level end-to-end Strict Exact Match.

An observation scores 1 only when verification passes, a prediction exists and
Strict Exact Match is true. Rejections, missing predictions, invalid responses,
timeouts and exhausted retries score 0 and remain in the full planned
denominator. They are also reported as technical counts.

The supporting `prediction_only_strict_accuracy` is exact matches divided by
available predictions, regardless of verification. The supplementary
`verifier_accepted_strict_accuracy` divides correct, accepted observations by
all accepted observations, including those with missing predictions. Neither
replaces the primary denominator. An empty denominator is reported as `n/a`.
Count-based tables cover all configured main and supplementary matrices, overall,
by condition and by domain, with planned, produced and accepted counts. Prediction
coverage, acceptance rate, explicit rejections, missing verifier decisions,
missing predictions and missing predictions linked to an error are separate. The error
table additionally reports terminal and recovered attempts at every stage.

For example, four planned observations, three predictions, two exact titles and
two accepted images yield 25.0% end-to-end, 66.7% prediction-only and 50.0%
verifier-accepted accuracy if only one exact title belongs to an accepted image.
Prediction coverage is 75.0% and the acceptance rate is 50.0%. Conditional
accuracy changes the evaluated subset; it is not an improvement of the model.

Strict Exact Match remains case-sensitive after trimming outer whitespace
(`strict_trimmed_exact_v1`). Normalized Exact Match uses Unicode NFC, casefold,
collapsed whitespace and an explicit punctuation mapping: U+00B7 (middle dot)
and U+2010--U+2015 (typographic hyphens/dashes) become ASCII hyphen-minus.
If necessary, it tolerates exactly one additional
matching quote pair around the prediction: straight single/double quotes or
English/German curly single/double quotes. It never removes reference-title
punctuation apart from that mapping, internal quotes, Markdown or explanatory
text. The method ID is
`nfc_casefold_whitespace_middot_dashes_outer_quotes_exact_v3`, printed in the
analysis report. Main-study normalized values remain supporting tables; the
style-selection pilot additionally plots both metrics. Existing raw outputs,
historical reports and strict website scoring remain unchanged.

Both normalized Exact Match and the optional prompt-title search use
`normalize_title_text()` in `src/semantic_roundtrip/evaluation.py`. Exact Match
compares complete strings; `title_occurs_in_text()` searches a literal phrase
with Unicode word guards on both ends. Its method is
`nfc_casefold_whitespace_middot_dashes_word_boundaries_v1`. `WALL·E` and `WALL-E`
match, but `Wally` and `WALLE` do not; `Up` does not match `group`. Ordinary full
stops are not converted to hyphens. PG `title_check_report: true` writes a
`prompt_title_check.json` sidecar from persisted prompts after that stage, also
on resume. A hit flags a lexical occurrence, not a request to render writing.
It never excludes work, triggers regeneration, or changes accuracy. The notebook
can also recompute flags from historical raw prompts without modifying runs.

Four seed observations are averaged per title before comparisons. Confidence
intervals use 10,000 paired bootstrap resamples of complete titles, stratified
only by domain, with seed `20260829`; reported 95% percentile intervals are
pointwise. Title length remains descriptive only.

Supporting outputs are Normalized Exact Match, verifier decisions, technical
failures, runtime provenance and visible-answer likelihood when token alignment
is valid. Answer likelihood is diagnostic, not calibrated confidence and not a
cross-model ranking.

The analysis notebook takes `DIRECT_JOB`, `INDIRECT_JOB`, `AQUEDUCT_JOB`,
`SKETCH_JOB`, `COMIC_JOB`, `THINKING_JOB` and `ILLUSTRATABLE_JOB`. It reports:

- direct 4 x 4 accuracy and predeclared PG, BI and same-minus-mixed contrasts;
- complete indirect 3 x 4 x 3 accuracy and local/hosted role contrasts;
- paired direct versus description-mediated routes on the four diagonal direct
  conditions;
- domain subgroups for songs, movies and bands;
- title-length distributions, domain-wise distributions of the four-model mean
  illustratability rating, and exploratory model-specific PG associations;
- paired Sketch-minus-unrestricted, Comic-minus-unrestricted and
  Sketch-minus-Comic matrices and effects, overall and by PG/BI model;
- native-minus-off matrices and paired effects for all 16 cells, the 12 changed
  cells and the PG-only, BI-only and both-role groups (four cells each);
- descriptive random-versus-high-illustratability differences without causal
  or population-level interpretation;
- technical validity and coverage.

Each title contributes one equally weighted Q25/G3/Q38/G4 mean to its domain's
rating histogram. All four Direct-job ratings are required; missing means are
reported separately. Model-specific correlations and candidate selection are
unchanged.

Thinking role groups contain different model pairs and do not identify a
within-pair PG-by-BI thinking interaction. Accuracy heatmaps share a 0--100%
scale; difference heatmaps share a symmetric -100 to +100 pp scale. Effect plots
display estimates and the calculated pointwise intervals. Each figure is
displayed inline and exported as a 300-dpi PNG and vector PDF, with fixed
scientific titles independent of the input job's development/final designation.

RQ1 compares selected direct Qwen/Gemma configurations. RQ2 compares PG, BB and
BI choices on the indirect route. RQ3 compares both routes on identical images.
RQ4 reports domain subgroups. SQ1 compares unrestricted direct reconstruction
with the paired Sketch and Comic conditions. SQ2 compares the thinking-off and
native-thinking direct matrices. SQ3 reports the association with model-rated
illustratability and the descriptive random-versus-high-illustratability
comparison. SQ1--SQ3 are supplementary, not additional primary research
questions.

## Protocol validation and stability

The fixed verifier is assessed on the complete 168-image development census.
Sketch and comic manipulations are each checked in all 48 generated prompt
prefixes and a fixed 24-image sample. The procedure is recorded in
[`../../../manual_evaluation/README.md`](../../../manual_evaluation/README.md).
Development accuracy is not a study result and does not tune this protocol.

In a fixed-protocol study job, isolated terminal model failures remain
zero-valued observations and do not trigger parameter changes. A method change
requires a new study revision; existing run snapshots remain unchanged.

Execution commands: [`../../../RUNNING.md`](../../../RUNNING.md).
