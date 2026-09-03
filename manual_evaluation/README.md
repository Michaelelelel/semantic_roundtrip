# Manual validation protocol

Use [`manual_checks_template.xlsx`](manual_checks_template.xlsx) with the
completed development-validation jobs. Work on a copy and keep the blank
template in Git.

## Image verifiers: 168 images

This is the complete unrestricted development-image census: seven PG models,
six titles and four seed combinations.

1. Open each image listed in `Verifier_168`.
2. Without seeing either stored verifier decision, enter
   `manual_strict_accept` using the exact rule in
   `prompts/verification/json_v3.txt` and `manual_title_aware_accept` using
   `prompts/verification/title_aware_json_v1.txt`.
3. Classify text as `none`, `ambiguous_or_pseudo` or `clear_meaningful`.
4. Finish both manual labels before entering `strict_verifier_accept` and
   `title_aware_verifier_accept` as `yes`, `no` or `invalid`.
5. Review agreement, false accepts, false rejects and invalid decisions for
   each policy in `Summary`.

The strict policy rejects any unambiguously readable meaningful writing. The
title-aware policy rejects only readable writing that communicates the supplied
reference title; unrelated writing is allowed. Invalid verifier responses are
incorrect decisions and are also counted separately. Reconstruction accuracy
must not influence these labels.

## Sketch: prompt and image checks

First inspect all 48 root PG outputs from the Sketch development-validation
job. Every prompt must start with the literal prefix in
`prompts/prompt_generation/visual_single_sketch_v2.yaml`. Record any exception
in the archived evaluation notes.

Then complete `Style_24`: two deterministic images per PG model/domain cell.
Enter:

- `style_adherent`: follows the sparse black-on-white freehand-outline rule;
- `manual_accept`: passes the independent text verifier rule;
- a note only when useful.

Style adherence is separate from title correctness. The sketch condition is
interpretable as fixed-style only when this manipulation check supports
adherence.

## Comic: prompt and image checks

Inspect all 48 root PG outputs from the Comic development-validation job. Every
prompt must start with the literal prefix in
`prompts/prompt_generation/visual_single_comic_v1.yaml`. Record any exception
in the archived evaluation notes.

Then complete `Comic_24`: two deterministic images per PG model/domain cell.
Enter:

- `style_adherent`: recognizably follows the broad comic-or-cartoon rule;
- `manual_accept`: passes the independent text verifier rule;
- a note only when useful.

The concrete comic execution is intentionally unrestricted. The check concerns
the requested comic/cartoon style and readable-text leakage, not title accuracy.

## Archive

Keep the filled workbook, both prefix-check notes, relevant development job
directories, executed notebook HTML/PNGs and code revision together. No Python
summarization script is required; the workbook contains fixed rows, dropdowns
and formulas.
