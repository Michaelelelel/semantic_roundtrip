# Final study protocol

This file records the exact executable protocol. Scientific justification and
interpretation belong in the thesis.

## Study revision and scope (`final_v3`)

The SQ5 extension adds prompt-based reconstruction and separates prompt and image
verification into independently executable/importable stages. The original
`final_v2` image/description conditions, model requests, seeds and decisions are
unchanged. Original run snapshots keep their historical identity; a logged
format conversion on copies does not retrospectively relabel their protocol.
The software supports configurable models and predefined reconstruction routes,
not arbitrary workflow composition.

The preferred common-style recommendation is unrestricted generation: no added
explicit rendering-style instruction, rather than the highest or lowest
observed accuracy. It is not style-neutral. Complete the full four-style report,
report contrary evidence and obtain supervisor confirmation before affected
main jobs or SQ5 start. Existing direct/indirect artifacts are a practical reuse
advantage. Descriptive style centrality is not an automatic selection rule.

## Four-style comparison (revision `final_v2`)

The unrestricted `direct_core` job and the `direct_photorealistic`,
`direct_comic` and `direct_sketch` jobs form the style comparison. Every job
uses `final_titles_v1` (30 titles per domain), the complete 4 x 4 PG/BI matrix,
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
dedicated distribution notebook without model calls. Archiving changes no selection rule.

This profile is a dataset-design diagnostic: inspect low/high-score
concentrations, asymmetry, sparse tails, domain differences and missing ratings.
The protocol retains the unfiltered random main dataset. Skewness alone is not
a defect, and no balanced/normal score distribution or automatic
filtering threshold is required. A strong concentration near low scores prompts
discussion of how informative the planned comparisons can be, not automatic
title exclusion. Ratings are model judgements, not reconstruction probabilities.
Record the dataset rationale with the report. Any change needs an explicit
protocol revision before new main runs: filtering changes the target population
and must not serve merely to increase accuracy.
The high-illustratability supplement remains distinct from the random main study.

`notebooks/style_decision.ipynb` takes the four complete 4 x 4 style jobs.
`notebooks/illustratability_distribution.ipynb` takes only the candidate-rating
job and defaults to the archived input. Neither needs indirect or Aqueduct jobs.
Commands are in [`../../../EXPERIMENTS.md`](../../../EXPERIMENTS.md).

## Roles and routes

- PG: title and domain to visual prompt.
- BG: visual prompt to image.
- Prompt verifier: deterministic normalized search for the reference title in
  the generated prompt.
- Strict image verifier: blind Q38 check rejecting any unambiguously readable
  meaningful writing.
- Title-aware image verifier: Q38 receives the reference title and rejects only
  readable writing that communicates that title; unrelated text is allowed.
- BI: image to title on the direct route.
- BB: image to neutral description; BI reconstructs the title from that
  description on the indirect route.
- Prompt reconstruction: original generated prompt plus domain to title, without
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
| `direct_photorealistic.yaml` | 16 | 1,440 | paired photorealistic condition |
| `direct_thinking.yaml` | 12 additions | 720 | native-thinking direct supplement |
| `direct_illustratable.yaml` | 16 | 1,440 | high-illustratability direct supplement |
| `direct_prompt_only.yaml` | 16 | 0 | SQ5 prompt reconstruction and four diagonal three-way comparisons |

`candidate_illustratability.yaml` is a four-model rating prerequisite, not an
additional reconstruction job. It must complete before the illustratability datasets
and jobs can be generated.

The Aqueduct job imports the exact completed `indirect_local` job. It must be
bound explicitly with `--source-job local_indirect=runs/JOB_DIRECTORY` when
started. If the optional plan view is used, it needs the same binding. No
automatic newest-job or dataset-fingerprint check is used.

The thinking job imports the exact completed `direct_core` job with
`--source-job direct_base=runs/JOB_DIRECTORY`. It computes only the 12 cells in
which Q38 or G4 occupies PG or BI; the four Q25/G3-only cells come from the
thinking-off direct job during analysis.

The prompt job imports the exact completed unrestricted `direct_core` job via
`--source-job direct_base=runs/JOB_DIRECTORY`, after style confirmation. Every
cell imports prompt/image verification and direct predictions. The four diagonal
cells additionally import `title_guessing_from_description` and its descriptions.
No new image, description or indirect calls are made. If a different style is
confirmed, revise this binding/design explicitly before starting SQ5; do not
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
- BB: `prompts/image_description/plain_v1.yaml`.
- Direct BI: `prompts/title_guessing/plain_v3.yaml`.
- Indirect BI: `prompts/title_guessing/description_plain_v3.yaml`.
- Prompt BI: `prompts/title_guessing/prompt_plain_v1.yaml`.
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

| Scope | Reasoning | Output ceiling | Timeout |
| --- | --- | ---: | ---: |
| Q25/G3/Q38/G4 PG, rating and BB | none; explicitly off for Q38/G4 | 512 | backend profile |
| Q25/G3/Q38/G4 direct/indirect/prompt BI | none; explicitly off for Q38/G4 | 128 | backend profile |
| D32 PG and BI | native DeepSeek | 16,384 | 7,200 s |
| O120 PG and BI | Harmony medium | 16,384 | 7,200 s |
| V4 PG and BI | Aqueduct high | 32,000 | 3,600 s |
| both fixed Q38 image verifiers | off; temperature 0, top-p 1 | 512 | 1,800 s |

The primary, style and illustratability matrices keep Q38/G4 thinking off. In
the separate thinking supplement, Q38 and G4 use native thinking whenever they
occupy PG or BI; Q25 and G3 are unchanged and both Q38 image verifiers remain
thinking-off.
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
available predictions, regardless of verification. Conditional accepted-subset
tables are labelled by image-verification policy and never replace the primary
denominator. An empty denominator is reported as `n/a`. Count-based tables cover
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
analysis report. Main-study normalized values remain supporting tables. The
style report plots all four image-policy/title-matching combinations.
Existing raw outputs and historical run decisions remain unchanged.

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
Job DB remains 4 and manifest format remains 6. Completed experiment-10/DB-11
job-4 sources have a one-time, copy-only conversion script; earlier archives
retain their original checkout.

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
All six completed jobs and the validated style export are required. It reports:

- direct 4 x 4 accuracy and predeclared PG, BI and same-minus-mixed contrasts;
- complete indirect 3 x 4 x 3 accuracy and local/hosted role contrasts;
- paired direct versus description-mediated routes on the four diagonal direct
  conditions;
- domain subgroups for songs, movies and bands;
- title-length distributions, domain-wise distributions of the four-model mean
  illustratability rating, and exploratory model-specific PG associations;
- a compact imported four-style overview and descriptive centrality summary;
  complete matrices and effects remain in the sole full style report;
- native-minus-off matrices and paired effects for all 16 cells, the 12 changed
  cells and the PG-only, BI-only and both-role groups (four cells each);
- descriptive random-versus-high-illustratability differences without causal
  or population-level interpretation;
- technical validity and coverage.
- SQ5 prompt/direct matrices and the four-diagonal three-way comparison below.

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
Supporting CSV tables and input/code/software provenance are saved quietly to
the notebook's output directory. The three notebooks have no analysis-mode
switches or embedded helper definitions. Shared table assembly and plotting are
in `analysis/reporting.py` and `analysis/plotting.py`; the existing statistical
calculations in `analysis/statistics.py` are unchanged.

RQ1 compares selected direct Qwen/Gemma configurations through three
aspects: earlier/later configurations within each family, families within each
release cohort, and same-model versus crossed PG/BI assignments within the four
planned model-pair comparisons. PG and BI differences are reported separately.
The pairing contrasts describe interaction on end-to-end accuracy, not a
mechanism of semantic preservation. Full-matrix relation-group means remain
descriptive. The analysis does not include a pooled same-family contrast.
RQ2 compares PG, BB and BI choices on the indirect route. RQ3 compares both
routes on identical images. These three primary research questions address
model configuration and reconstruction route.

The five secondary research questions contextualise these comparisons.
SQ1 compares unrestricted, photorealistic, Sketch
and Comic direct reconstruction. SQ2 compares the thinking-off and
native-thinking direct matrices. SQ3 reports the association with model-rated
illustratability and the descriptive random-versus-high-illustratability
comparison. SQ4 reports domain subgroups for songs, movie titles and band names.
SQ5 compares prompt-based reconstruction with the image and description routes.
SQ means secondary research question. The distinction between main and
supplementary jobs describes experimental conditions, not question priority.

## SQ5: prompt reconstruction and three-way comparison

SQ5 is an explicitly added secondary comparison, not a retrospectively
predeclared original experiment. It uses Q25/Q38/G3/G4 in all 4x4 PG/BI cells,
the same 90 titles, prompt seeds `1000`, `1001`, thinking off and the matching
direct BI parameters (including seed `3003`). Its 180 prompt predictions per
cell total 2,880 new model calls. Prompt generation and all image-related work
are inherited. The 720 prompt predictions in the four diagonals are a subset
of these 2,880, compared with 1,440 existing direct and 1,440 existing indirect
predictions on those four same conditions.

`verification_prompt` depends only on prompts; `verification_image` depends on
images and retains both policies. `title_guessing_from_prompt` depends only on
prompts. All are independently optional/importable, and prompt-only execution
requires no image seeds or verifier model. Local and imported execution of the
same stage is disallowed. Selected inherited work must be terminal and inactive;
the parent source may still run unrelated stages in the new format. This is
not permission to migrate active old-format jobs.

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
Modality, representation and policy differences preclude interpreting SQ5 as
an exact stage-wise semantic-loss decomposition or a guaranteed upper bound.

The style report preserves domain strata in overall bootstrap intervals and
deduplicates prompt checks by original Run/Prompt ID (local IDs when generated
locally), never by text. A complete style has 720 logical prompts. It exports
the complete four-style evidence, method IDs, file hashes and provenance;
`STYLE_REPORT_DIR` imports only a validated compact summary into the final report.
Missing or inconsistent exports fail explicitly.

The copy-only migration preserves IDs, values, decisions, seeds, task attempts
and provenance. It adds an empty prompt-prediction table and translates the
verification stage labels/configuration. Only finished supported source jobs
are accepted; ambiguous mappings fail. Preserve originals, exact converter and
migration records outside the current website discovery root.

## Protocol validation and stability

The two image-verification policies are assessed on the same complete 168-image
development census; prompt decisions are deterministic and require no model.
Sketch and comic manipulations are each checked in all 48 generated prompt
prefixes and a fixed 24-image sample. The procedure is recorded in
[`../../../manual_evaluation/README.md`](../../../manual_evaluation/README.md).
Development accuracy is not a study result and does not tune this protocol.

In a fixed-protocol study job, isolated terminal model failures remain
zero-valued observations and do not trigger parameter changes. A method change
requires a new study revision; existing run snapshots remain unchanged.

Main and supplementary execution: [`../../../EXPERIMENTS.md`](../../../EXPERIMENTS.md).
Shared installation and operation: [`../../../RUNNING.md`](../../../RUNNING.md).
