# Final study protocol

This file records the exact executable protocol. Scientific justification and
interpretation belong in the thesis.

The model roles are Prompt generation (PG), Image generation (IG), Image
description (ID) and Title guessing (TG). The analysis columns `pg`, `bb` and
`bi` identify PG, ID and TG respectively. Job and run identifiers use these
same technical keys. Figure labels use the reader-facing role names.

## Study revision and scope (`final_v7`)

The study compares direct image, description-mediated and prompt-based title
reconstruction. Prompt and image verification are independently executable and
importable stages. The software supports configurable models and predefined
reconstruction routes, not arbitrary workflow composition. Run snapshots record
the settings actually used, and reused outputs retain their source identity.

Revision `final_v7` retains the completed fixed 360-pair manual audit (90 titles
from each of four PG roots), with prompt-use labels `0/n/e` and no separate
`prompt_requests_text` field. The unperformed manual style-adherence and
development prompt-prefix assessments are excluded from the final scope.
The four-style reconstruction comparison remains. It compares the specified
style instructions, without claiming independently verified visual adherence.
Experiment configurations, inference settings, matrices, automated
verification policies, reconstruction metrics and main-study analysis methods
remain unchanged. In particular, the saved literal prompt-title check continues
to gate the primary outcome. Existing snapshots and reports retain their original
revision identifiers. This assessment-scope revision was made after the style
report and does not change its recorded results.

Unrestricted generation is the common reference. It adds no rendering-style
instruction, leaving the choice of visual clues within the end-to-end task.
The choice is not based on the highest or lowest observed accuracy, and
unrestricted does not mean style-neutral. The complete style report supported
retaining this reference on 2026-09-10. Some dependent jobs had already started
with unrestricted before that report. Existing artifacts provide a practical
reuse advantage, not the scientific selection criterion. Descriptive centrality
is not an automatic selection rule. All reused inputs must match the reference
style. The operational 8+12 Aqueduct alternative below preserves the same
experimental conditions.

## Four-style comparison

The unrestricted `direct_core` job and the `direct_photorealistic`,
`direct_comic` and `direct_sketch` jobs form the style comparison. Every job
uses `final_titles_v1` (30 titles per domain), the complete 4 x 4 PG/TG matrix,
prompt seeds `1000` and `1001`, and image seeds `8566257` and `2875613`.
Each style therefore has 1,440 generated images and 5,760 direct predictions.
The unrestricted diagonal entries also create the ratings, descriptions and
paired indirect baselines required by the main study; those extra outputs do
not change the direct observations used here.

The four prompt profiles share the same task wording and differ only in the
style instruction. The prompt verifier, both Q38 image-verification policies,
28-step SD profile and all other inference settings remain fixed. The report
shows blind-strict and title-aware image verification, each crossed with Strict
and Normalized Exact Match. Every outcome also requires the prompt verifier to
pass and uses the same complete planned denominator. Blind-strict image
verification with Strict Exact Match is primary. This complete direct
comparison supports a documented style choice but does not establish a
universal optimum or an indirect-route style effect.

The complete report `style_report_20260910_082753` uses these source jobs:

| Style | Source Job ID |
| --- | --- |
| Unrestricted | `20260903T230744Z_final-direct-core_faa7afcb` |
| Photorealistic | `20260903T230758Z_final-direct-photorealistic_0488e791` |
| Sketch | `20260906T115545Z_final-direct-sketch_d64119f3` |
| Comic | `20260908T101720Z_final-direct-comic_9e7afc81` |

All four contain 5,760 direct predictions and complete persisted check decisions.
Primary overall accuracy is 11.39%, 11.35%, 11.74% and 12.08%, respectively.
Title-aware/Strict Exact sensitivity, also including the prompt check, is
13.45%, 13.16%, 12.93% and 13.85%. Paired primary differences from unrestricted
are -0.03 pp [-0.90, +0.85], +0.35 pp [-1.56, +2.41] and
+0.69 pp [-1.18, +2.43], with pointwise 95% intervals.
These intervals do not establish equivalence. All metrics, including the
prompt gate, remain unchanged. Completeness of stored decisions does not
establish the correctness of those decisions or adherence to the requested style.

For the candidate-distribution figure, `RATING_JOB` identifies the complete
four-model candidate-rating job. Each candidate contributes its equally weighted
Q25/G3/Q38/G4 mean only when all four ratings are available. Histograms use a
fixed 0--100 scale with 20 five-point bins in separate domain panels and report
incomplete ratings.
The 900-candidate pool must not be confused with either 90-title final set.

The completed rating job `20260902T162529Z_candidate-illustratability_a1cfe5f2`
is preserved in [`../../../artifacts/candidate_illustratability/`](../../../artifacts/candidate_illustratability/README.md),
with all 3,600 valid ratings, no missing ratings, raw responses, snapshots and
the executed distribution report. Its README reproduces the figure using the
dedicated distribution notebook without model calls. The notebook defaults to
the supplied job in its Job-ID directory; `report/` contains the executed
analysis, tables, figures and manifest. The documented source identifiers and
raw responses accompany the stored ratings and selected title sets.

This profile is a dataset-design diagnostic: inspect low/high-score
concentrations, asymmetry, sparse tails, domain differences and missing ratings.
The protocol retains the unfiltered random main dataset. Skewness alone is not
a defect, and no balanced/normal score distribution or automatic
filtering threshold is required. A strong concentration near low scores prompts
discussion of how informative the planned comparisons can be, not automatic
title exclusion. Ratings are model judgements, not reconstruction probabilities.
The observed candidate distributions supported retaining the random sample,
not replacing it with a visually promising subset. The review informed that
retention, without claiming a preregistered threshold or that the sample had
never existed before the rating analysis. Any change needs an explicit
protocol revision before new main runs: filtering changes the target population
and must not serve merely to increase accuracy.
The high-illustratability supplement remains distinct from the random main study.

`notebooks/style_decision.ipynb` takes the four complete 4 x 4 style jobs.
`notebooks/illustratability_distribution.ipynb` takes only the candidate-rating
job and defaults to the archived input. Neither needs indirect or Aqueduct jobs.
Commands are in [`../../../EXPERIMENTS.md`](../../../EXPERIMENTS.md).

## Roles and routes

- PG (Prompt generation): title and domain to visual prompt.
- IG (Image generation): visual prompt to image.
- Prompt verifier: deterministic normalized search for the reference title in
  the generated prompt.
- Strict image verifier: blind Q38 check rejecting any unambiguously readable
  meaningful writing.
- Title-aware image verifier: Q38 receives the reference title and rejects only
  readable writing that communicates that title; unrelated text is allowed.
- TG (Title guessing): image plus domain to title on the direct route.
- ID (Image description): image to neutral description; TG reconstructs the title from that
  description on the indirect route.
- Prompt-based TG: original generated prompt plus domain to title, without
  an image, reference title, candidate list or verification metadata.

## Shared protocol

- Dataset: `final_titles_v1`, 30 songs, 30 movie titles and 30 band names.
- Selection: fixed-seed random sample from each eligible top-300 popularity
  pool; seed `20260811`; no title-length quota.
- Cutoff: entries released by 2018; documented filters, six development-title
  exclusions and at most one song per primary artist.
- Prompt seeds: `1000`, `1001`.
- Image seeds: `8566257`, `2875613`.
- Observations: four per title and image-dependent condition; two per title for
  prompt reconstruction, without multiplication by image seeds.
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

| Model label | Model | Deployment | Roles |
| --- | --- | --- | --- |
| Q25 | Qwen2.5-VL-32B-Instruct F16 | local | PG, ID, TG |
| G3 | Gemma 3 27B IT F16 | local | PG, ID, TG |
| Q38 | Qwen3.8-27B BF16 | local | PG, ID, TG, verifier |
| G4 | Gemma 4 31B IT BF16 | local | PG, ID, TG |
| D32 | DeepSeek-R1-Distill-Qwen-32B F16 | local | PG, TG |
| O120 | GPT-OSS 120B MXFP4 | local | PG, TG |
| V4 | DeepSeek-V4-Flash 284B | Aqueduct | PG, TG |
| IG | Stable Diffusion 3.5 Large BF16 | local | image generation |

V4 is an externally hosted larger configuration, not an equal-size or
equal-compute comparison.

## Jobs

| Config | Conditions | New images | Purpose |
| --- | ---: | ---: | --- |
| `direct_core.yaml` | 16 | 1,440 | direct Qwen/Gemma 4 x 4 |
| `indirect_local.yaml` | 16 | 720 | local indirect 2 x 4 x 2 |
| `aqueduct_v4_extension.yaml` | 20 additions | 360 | complete indirect 3 x 4 x 3 |
| `aqueduct_v4_independent.yaml` | 8 additions | 360 | alternative part 1: V4 PG, four ID models, D32/O120 TG |
| `aqueduct_v4_completion.yaml` | 12 additions | 0 | alternative part 2: V4 TG on descriptions from both sources |
| `direct_sketch.yaml` | 16 | 1,440 | paired direct style supplement |
| `direct_comic.yaml` | 16 | 1,440 | paired broad comic-style supplement |
| `direct_photorealistic.yaml` | 16 | 1,440 | paired photorealistic condition |
| `direct_thinking.yaml` | 12 additions | 720 | native-thinking direct supplement |
| `direct_illustratable.yaml` | 16 | 1,440 | high-illustratability direct supplement |
| `direct_prompt_only.yaml` | 16 | 0 | SQ1 prompt reconstruction and four diagonal three-way comparisons |

`candidate_illustratability.yaml` is a four-model rating prerequisite, not an
additional reconstruction job. It must complete before the illustratability datasets
and jobs can be generated.

Choose either the single Aqueduct extension or the two split jobs, never both
as additive study conditions. The split runs ten reconstruction jobs rather
than nine, but still contributes exactly 20 conditions to the local matrix of
16. It preserves existing experiment configurations and upstream artifact reuse.
The independent eight-condition job can run on a separate model deployment
while Local Indirect runs on another. It still needs local image generation,
image verification, description and D32/O120 guessing, not only Aqueduct.
The completion job executes only V4 guessing. It imports `image_description`,
`verification_prompt` and `verification_image`, with required prompts and images,
from both completed sources via `local_indirect` and `v4_independent`.
Source directories on the execution host must include their image files.

The single Aqueduct job imports the exact completed `indirect_local` job. It must be
bound explicitly with `--source-job local_indirect=runs/JOB_DIRECTORY` when
started. If the optional plan view is used, it needs the same binding. No
automatic newest-job or dataset-fingerprint check is used.

The thinking job imports the exact completed `direct_core` job with
`--source-job direct_base=runs/JOB_DIRECTORY`. It computes only the 12 cells in
which Q38 or G4 occupies PG or TG; the four Q25/G3-only cells come from the
thinking-off direct job during analysis.

The prompt job imports the exact completed unrestricted `direct_core` job via
`--source-job direct_base=runs/JOB_DIRECTORY`, under the unrestricted reference. Every
cell imports prompt/image verification and direct predictions. The four diagonal
cells additionally import `title_guessing_from_description` and its descriptions.
No new image, description or indirect calls are made. If a different style is
subsequently selected, revisit this binding/design explicitly before final inclusion; do not
combine different-style direct and indirect inputs.

## Prompts

All model instructions are versioned YAML chat profiles containing an explicit
output format and ordered `system`, `user` or `assistant` messages. Vision stages
attach the image to the profile's single user message. A profile may
intentionally contain only that user message; no empty or synthetic system
message is required.

- PG: `prompts/prompt_generation/visual_single_v5.yaml`.
- Sketch PG: `prompts/prompt_generation/visual_single_sketch_v2.yaml`.
- Comic PG: `prompts/prompt_generation/visual_single_comic_v1.yaml`.
- Photorealistic PG:
  `prompts/prompt_generation/visual_single_photorealistic_v1.yaml`.
- Strict image verifier: `prompts/verification/json_v3.yaml`.
- Title-aware image verifier:
  `prompts/verification/title_aware_json_v1.yaml`.
- ID: `prompts/image_description/plain_v1.yaml`.
- Direct TG: `prompts/title_guessing/plain_v3.yaml`.
- Description-based TG: `prompts/title_guessing/description_plain_v3.yaml`.
- Prompt-based TG: `prompts/title_guessing/prompt_plain_v1.yaml`.
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

The photorealistic condition requires this exact prefix:

```text
A photorealistic image depicting
```

All remaining content constraints match the unrestricted prompt.

## Text inference

Common sampled profile: temperature 1, top-p 0.95, top-k 0, min-p 0,
repeat penalty 1, presence penalty 0 and frequency penalty 0.

| Scope | Reasoning | Output ceiling | Client timeout |
| --- | --- | ---: | ---: |
| Q25/G3/Q38/G4 PG, rating and ID | none; explicitly off for Q38/G4 | 512 | backend profile |
| Q25/G3/Q38/G4 direct/description/prompt TG | none; explicitly off for Q38/G4 | 128 | backend profile |
| D32 PG and TG | native DeepSeek | 16,384 | 7,200 s |
| O120 PG and TG | Harmony medium | 16,384 | 7,200 s |
| V4 PG and TG | Aqueduct high | 32,000 | 3,600 s |
| both fixed Q38 image verifiers | off; temperature 0, top-p 1 | 512 | 1,800 s |

The primary, style and illustratability matrices keep Q38/G4 thinking off. In
the separate thinking supplement, Q38 and G4 use native thinking whenever they
occupy PG or TG; Q25 and G3 are unchanged and both Q38 image verifiers remain
thinking-off.
Q38 uses the `deepseek` reasoning format and G4 uses `auto`, with no explicit
thinking budget, a 16,384-token output ceiling and a 7,200-second timeout.

These are client connection/read timeouts, not hard request or job-duration
limits. The local Docker deployment sets the llama.cpp router and worker
transport timeouts to 9,000 seconds, above the longest client timeout of 7,200.
This does not extend token budgets or control the external Aqueduct gateway.
Changes to effective transport limits can affect failure rates; retain existing
errors and record the deployed settings. Aqueduct requests are non-streaming;
existing runs retain their saved configurations.

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
optimum. Each run stores the workflow actually used.

## Outcomes and analysis

Primary image/description outcome: title-level end-to-end Strict Exact Match
under the prompt and blind-strict image policies. Prompt reconstruction uses
the prompt policy only, with its own full planned prompt denominator.

Every generated prompt is checked deterministically for a normalized literal
occurrence of the reference title. Every generated image is independently
checked twice by Q38: the blind-strict policy looks for any meaningful readable
writing, while the title-aware policy looks only for readable writing that
communicates the supplied reference title. Verification never prevents image
generation, description or title reconstruction.

The primary observation scores 1 only when the prompt check passes, the strict
image check passes, a prediction exists and Strict Exact Match is true. Three
sensitivity outcomes combine the same prompt gate with title-aware image
verification and/or Normalized Exact Match. All four use the identical complete
planned denominator. Rejections, missing decisions, missing predictions,
invalid responses, timeouts and exhausted retries score 0 and remain in that
denominator. Each cause is also reported separately.

The supporting `prediction_only_strict_accuracy` is exact matches divided by
available predictions, regardless of verification. The existing count-based
`verifier_accepted_strict_accuracy` divides primary successes by blind-strict
image passes on image-dependent routes, not by the intersection of prompt and
image passes. The prompt gate remains required in its numerator. For the prompt
route, the denominator instead counts prompt-check passes. This diagnostic is
distinct from the common-valid-input comparison below, which requires both
gates on the shared image inputs. Neither replaces the primary denominator.
An empty denominator is reported as `n/a`. Count-based tables cover
all configured main and supplementary matrices, overall, by condition and by
domain, with planned, produced and accepted counts. Prediction coverage,
policy-specific acceptance, explicit rejections, missing verifier decisions,
missing predictions and errors are reported separately.

For example, four planned observations, three predictions, two exact titles,
four passed prompt checks and two passed strict image checks yield 25.0% primary
end-to-end accuracy when only one exact title belongs to a strictly accepted
image. Prediction-only accuracy is 66.7%, prediction coverage is 75.0% and
strict-image acceptance is 50.0%. Conditional accuracy changes the evaluated
subset; it is not an improvement of the model.

Strict Exact Match is case-sensitive after trimming outer whitespace
(`strict_trimmed_exact_v1`). Normalized Exact Match uses Unicode NFC, casefold,
collapsed whitespace and an explicit punctuation mapping: U+00B7 (middle dot)
and U+2010--U+2015 (typographic hyphens/dashes) become ASCII hyphen-minus.
If necessary, it tolerates exactly one additional
matching quote pair around the prediction: straight single/double quotes or
English/German curly single/double quotes. It never removes reference-title
punctuation apart from that mapping, internal quotes, Markdown or explanatory
text. The method ID is
`nfc_casefold_whitespace_middot_dashes_outer_quotes_exact_v3`, printed in the
analysis report. Main-study normalized values remain supporting tables. The
style report plots all four image-policy/title-matching combinations.
Analysis reads raw outputs and persisted decisions without modifying them.

Both Normalized Exact Match and the prompt verifier use
`normalize_title_text()` in `src/semantic_roundtrip/evaluation.py`. Exact Match
compares complete strings; `title_occurs_in_text()` searches a literal phrase
with Unicode word guards on both ends. Its method is
`nfc_casefold_whitespace_middot_dashes_word_boundaries_v1`. `WALL·E` and `WALL-E`
match, but `Wally` and `WALLE` do not; `Up` does not match `group`. Ordinary full
stops are not converted to hyphens. The deterministic decision and method ID are
persisted per prompt. A title occurrence fails the prompt policy and therefore
scores 0 in every end-to-end outcome, but it never triggers regeneration or
prevents downstream work. The status website reports persisted prompt, strict
image and title-aware image decisions separately. Current code reads and writes
only experiment schema 11 and run-database schema 12. Job YAML/snapshots use 5;
Job DB uses 4 and manifest format uses 6.

Four seed observations are averaged per title before comparisons. Confidence
intervals use 10,000 paired bootstrap resamples of complete titles, stratified
only by domain, with seed `20260829`; reported 95% percentile intervals are
pointwise. Title length remains descriptive only.

Supporting outputs are the three verifier decisions, Normalized Exact Match,
the title-aware sensitivity outcome, technical failures, runtime provenance and
visible-answer likelihood when token alignment is valid. Answer likelihood is
diagnostic, not calibrated confidence and not a cross-model ranking.

`notebooks/final_study.ipynb` takes `DIRECT_JOB`, `INDIRECT_JOB`, `AQUEDUCT_JOB`,
`THINKING_JOB`, `ILLUSTRATABLE_JOB`, `PROMPT_BASELINE_JOB` and `STYLE_REPORT_DIR`.
Use either `AQUEDUCT_JOB` or both `AQUEDUCT_INDEPENDENT_JOB` and
`AQUEDUCT_COMPLETION_JOB`, leaving the unused alternative unset.
Six completed reconstruction jobs, or seven with the split, and the validated
style export are required. The analysis checks exact condition coverage,
compatible settings and matching source artifacts before joining the indirect
inputs. It reports:

- direct 4 x 4 accuracy and predeclared PG, TG and same-minus-mixed contrasts;
- complete indirect 3 x 4 x 3 accuracy and local/hosted role contrasts;
- paired direct versus description-mediated routes on the four diagonal direct
  conditions;
- SQ1 prompt/direct matrices and the four-diagonal three-way comparison below;
- a compact imported four-style overview and descriptive centrality summary;
  complete matrices and effects remain in the sole full style report;
- native-minus-off matrices and paired effects for all 16 cells, the 12 changed
  cells and the PG-only, TG-only and both-role groups (four cells each);
- domain subgroups for songs, movies and bands;
- title-length distributions, domain-wise distributions of the four-model mean
  illustratability rating, and exploratory model-specific PG associations;
- descriptive random-versus-high-illustratability differences without causal
  or population-level interpretation;
- technical validity and coverage.

Each title contributes one equally weighted Q25/G3/Q38/G4 mean to its domain's
rating histogram. All four Direct-job ratings are required; missing means are
reported separately. Model-specific correlations and candidate selection are
unchanged.

Thinking role groups contain different model pairs and do not identify a
within-pair PG-by-TG thinking interaction. Accuracy heatmaps share a 0--100%
scale; difference heatmaps share a symmetric -100 to +100 pp scale. Effect plots
display estimates and the calculated pointwise intervals. Each figure is
displayed inline and exported as a 300-dpi PNG and vector PDF, with fixed
scientific titles independent of the input job's development/final designation.
Supporting CSV tables and input/code/software provenance are saved quietly to
the notebook's output directory. The three notebooks have no analysis-mode
switches or embedded helper definitions. Shared table assembly and plotting are
in `analysis/reporting.py` and `analysis/plotting.py`; the existing statistical
estimators are implemented in `analysis/statistics.py`.

RQ1 compares selected direct Qwen/Gemma configurations through three
aspects: earlier/later configurations within each family, families within each
release cohort, and same-model versus crossed PG/TG assignments within the four
planned model-pair comparisons. PG and TG differences are reported separately.
The pairing contrasts describe interaction on end-to-end accuracy, not a
mechanism of semantic preservation. Full-matrix relation-group means remain
descriptive. The analysis does not include a pooled same-family contrast.
RQ2 compares PG, ID and TG choices on the indirect route. RQ3 compares both
routes on identical images. These three primary research questions address
model configuration and reconstruction route.

The five secondary research questions contextualise these comparisons.
SQ1 compares prompt-based reconstruction with the image and description routes.
SQ2 compares unrestricted, photorealistic, Sketch and Comic direct
reconstruction. SQ3 compares the thinking-off and native-thinking direct
matrices. SQ4 reports domain subgroups for songs, movie titles and band names.
SQ5 reports the association with model-rated illustratability and the
descriptive random-versus-high-illustratability comparison.
SQ means secondary research question. The distinction between main and
supplementary jobs describes experimental conditions, not question priority.

## SQ1: prompt reconstruction and three-way comparison

SQ1 is an explicitly added secondary comparison, not a retrospectively
predeclared original experiment. It uses Q25/Q38/G3/G4 in all 4x4 PG/TG cells,
the same 90 titles, prompt seeds `1000`, `1001`, thinking off and the matching
direct TG parameters (including seed `3003`). Its 180 prompt predictions per
cell total 2,880 new model calls. Prompt generation and all image-related work
are inherited. The 720 prompt predictions in the four diagonals are a subset
of these 2,880, compared with 1,440 existing direct and 1,440 existing indirect
predictions on those four same conditions.

`verification_prompt` depends only on prompts; `verification_image` depends on
images and retains both policies. `title_guessing_from_prompt` depends only on
prompts. All are independently optional/importable, and prompt-only execution
requires no image seeds or verifier model. Local and imported execution of the
same stage is disallowed. Selected inherited work must be terminal and inactive;
the parent source may still run unrelated stages.

The Prompt endpoint is passed prompt verification AND Strict Exact Match over
every planned prompt. Missing decisions, predictions and terminal failures are
zero. Normalized Exact Match is sensitivity only; there is no image-policy
variant of prompt accuracy. The image/description endpoints do not change.
Pairing averages both image seeds per prompt and both prompt seeds per title,
then equally weights the matched cells. Confidence intervals use 10,000 paired,
domain-stratified whole-title bootstrap draws with seed `20260829`.

Report the complete 16-cell prompt/direct comparison separately from the
four-diagonal prompt/direct/indirect comparison. The new contrasts are
Prompt-minus-Direct and Prompt-minus-Indirect. The Direct/Indirect contrast
references RQ3 and is not independent new evidence. A descriptive common-valid
input table retains only passed prompt and Strict-image checks, uses the same
accepted images across routes and still scores missing predictions as zero.
It reports subset denominators and does not replace the primary estimate.
Modality, representation and policy differences preclude interpreting SQ1 as
an exact stage-wise semantic-loss decomposition or a guaranteed upper bound.

The style report preserves domain strata in overall bootstrap intervals and
deduplicates prompt checks by original Run/Prompt ID (local IDs when generated
locally), never by text. A complete style has 720 logical prompts. It exports
the complete four-style evidence, method IDs, file hashes and provenance;
`STYLE_REPORT_DIR` imports only a validated compact summary into the final report.
Missing or inconsistent exports fail explicitly.

For the style notebook only, `ANALYSIS_METADATA_ONLY=1` permits an analysis copy
without local image files. It still requires complete job/run databases and
snapshots, including WAL contents when present, and retains all saved predictions
and decisions. The manifest records the omitted local image-file check.
The default `0` checks image-file existence. This option does not rerun verification,
remove its gates or provide manual image assessment. Final-study analysis and
execution-time inheritance retain their normal image-file requirements.

An interim thesis analysis may run the existing independent Core and SQ1
functions on complete metadata copies with `require_image_files=False`,
recording that choice and the exact source jobs. This skips only local pixel-file
existence checks, not saved decisions, coverage or paired-source checks. It is
not a complete execution of the final notebook and does not establish visual
inspection of omitted images. Outstanding experiment groups remain unreported.

## Protocol validation and stability

The completed single-assessor audit describes prompt-title usage and tests
application of the two existing image policies. Its CSV contains 360 prompt/image pairs
from unrestricted Direct Core job
`20260903T230744Z_final-direct-core_faa7afcb`: all 90 main-study titles
(30 per domain) from each of the four PG roots Q25/Q38/G3/G4, using prompt seed
`1000` and image seed `8566257`. These are the first configured seeds, not a
numerical-minimum rule. Each source image appears once, without TG-condition
duplicates. The mechanical selection is fixed before human labels and is
independent of stored verifier decisions and reconstruction outcomes. This
assessment protocol was defined after generation and the style report, not
preregistered as part of their execution.

The single portable CSV contains these columns, in order:

```text
run_id,image_id,title,prompt_text,prompt_title_use,flag_strict,flag_title_aware,notes
```

The exact source job above and its run-local image IDs identify the original
images and stored prompts without depending on a localhost URL. The full stored
prompt is included for contextual review. Human fields were prepared blank.
Stored verifier decisions are
excluded from the CSV and read directly from the source job's SQLite databases.

`prompt_title_use` concerns the complete reference-title expression, ignoring
case, spacing and typography but not inferring it from partial words, synonyms
or symbols. Use `0` when that expression is absent, `n` when every
occurrence is normal descriptive language, and `e` when any occurrence
names the title, entity or answer, or specifies it as writing to display.
An explicit occurrence takes precedence when both uses appear. This contextual
judgement describes lexical matches, not the technical reliability of phrase
detection or which rule should be preferred. A separate label for requests to render any readable writing
is not collected. This does not imply that such requests are absent or correct.
These contextual labels do not change the literal-title gate.

`flag_strict` and `flag_title_aware` use `1` for rejection and `0` for allowance
under the existing image policies. Strict includes readable words, brands,
captions, watermarks and meaningful numbers. A single character counts only as
a clear label, logo or identifier. Illegible marks and pseudo-text do not qualify.
Title-aware rejection requires the complete
reference title as readable writing. Individual title words or a partial title
alone do not qualify, and depicted objects cannot supply missing written words.
Ambiguous readability follows their existing
pass rule and receives `0`. Blank human fields mean unreviewed or otherwise
unresolved, not a negative label. Other unresolved cases retain a blank and a
note until clarified. Each of the three human fields requires an explicit label
before final summarization (1,080 labels). Michael Hagmann completed the audit
on 2026-09-11. He viewed images alongside saved verifier decisions and title
predictions on the website and discussed selected cases with AI assistance.
The assessment was neither blinded nor wholly unassisted. The Mastodon prompt
category was corrected from `0` to `n` with his explicit confirmation before
aggregation. The single assessor's labels are a descriptive reference, not
infallible ground truth or inter-rater agreement.

The analysis separates contextual prompt categories from image-policy agreement.
For each image policy, it reports agreement, false accepts, false rejections,
and missing or invalid decisions. Missing and invalid decisions never count
as agreement and remain separately visible in the full denominator.
The audit does not replace persisted decisions, relabel generated outputs
or alter reconstruction scores.

This is a bounded audit of the unrestricted four-PG baseline at one seed pair,
not validation of other styles, indirect-only PG models or remaining seeds.
All 1,080 labels and all saved decisions are complete and valid. Strict agrees
in 343/360 cases (95.3%), with five false accepts and twelve false rejections.
Title-aware agrees in 355/360 cases (98.6%), with no observed false accepts and
five false rejections. The assessor rejects 56 Strict images but only six
Title-aware images. The different criteria and low Title-aware rejection count
must accompany interpretation of overall agreement. No inter-rater reliability
or general text-recognition performance is claimed.

Prompt categories are 344 absent, eleven normal descriptive uses and five
explicit references. The saved lexical check passes all absent cases and flags
all sixteen occurrences. These context counts are not a prompt-verifier
confusion matrix and do not define a new gate or a policy preference.
The labels are in
[`verifier_assessment.csv`](../../../manual_evaluation/verifier_assessment.csv).
[`evaluate_verifier.py`](../../../scripts/evaluate_verifier.py) reproduces the
counts directly from those labels and the source job, without image files or
model calls. Agreement is `(both accept + both reject) / 360`.
The [assessment README](../../../manual_evaluation/README.md) provides the
source-job identity, label key and calculation command.

The operational prompt check remains deterministic and requires no model.
Contextual human judgement does not replace that check. The style comparison
does not include a separate manual visual-adherence score or an assessment of
development prompt prefixes. Consequently it measures reconstruction under
the requested style instructions, not an effect conditional on verified
compliance with a rendered style. Development accuracy is not a study result
and does not tune this protocol.

In a fixed-protocol study job, isolated terminal model failures remain
zero-valued observations and do not trigger parameter changes. A method change
requires a new study revision; existing run snapshots remain unchanged.

Main and supplementary execution: [`../../../EXPERIMENTS.md`](../../../EXPERIMENTS.md).
Shared installation and operation: [`../../../RUNNING.md`](../../../RUNNING.md).
