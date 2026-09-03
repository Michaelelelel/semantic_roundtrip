"""Versioned title comparisons and deterministic prompt verification."""

import json
import re
import unicodedata

from semantic_roundtrip.domain import VerificationDecision

EXACT_MATCH_METHOD = "strict_trimmed_exact_v1"
NORMALIZED_EXACT_METHOD = "nfc_casefold_whitespace_middot_dashes_outer_quotes_exact_v3"
PROMPT_TITLE_MATCH_METHOD = "nfc_casefold_whitespace_middot_dashes_word_boundaries_v1"
STRICT_IMAGE_VERIFICATION_METHOD = "visible_meaningful_text_json_v3"
TITLE_AWARE_IMAGE_VERIFICATION_METHOD = "visible_reference_title_json_v1"

# Exact translation set: MIDDLE DOT (U+00B7), HYPHEN (U+2010), NON-BREAKING
# HYPHEN (U+2011), FIGURE DASH (U+2012), EN DASH (U+2013), EM DASH (U+2014),
# HORIZONTAL BAR (U+2015). All map to ASCII HYPHEN-MINUS (U+002D).
_TITLE_PUNCTUATION = str.maketrans({char: "-" for char in "·‐‑‒–—―"})


def normalize_title_text(value: str) -> str:
    """Apply NFC, casefold, whitespace collapse and the explicit dash mapping.

    Only U+00B7 and U+2010--U+2015 are translated to ASCII hyphens. Quotes and
    all other punctuation remain intact; no aliases or semantic matching apply.
    """
    normalized = unicodedata.normalize("NFC", value).casefold()
    return " ".join(normalized.translate(_TITLE_PUNCTUATION).split())


def title_exact_match(expected_title: str, predicted_title: str) -> bool:
    """Compare titles case-sensitively after trimming outer whitespace."""
    return expected_title.strip() == predicted_title.strip()


def title_normalized_exact_match(
    expected_title: str,
    predicted_title: str,
) -> bool:
    """Normalize title text and allow one extra matching prediction quote pair."""
    expected = normalize_title_text(expected_title)
    predicted = normalize_title_text(predicted_title)
    if expected == predicted:
        return True
    # Strip only an extra wrapper on the prediction, never reference punctuation.
    return (
        len(predicted) >= 2
        and (predicted[0], predicted[-1])
        in {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("„", "“"), ("‚", "‘")}
        and predicted[1:-1].strip() == expected
    )


def title_occurs_in_text(title: str, text: str) -> bool:
    r"""Find a normalized literal phrase, guarded at both edges by Unicode \w.

    Unicode alphanumerics and underscores cannot touch either edge, even when
    the title starts or ends with punctuation. Empty inputs never match. Unlike
    normalized Exact Match, this check does not remove any outer quote pair.

    A lexical occurrence is deliberately narrower than semantic equivalence.
    The same normalization is used by normalized title matching, including the
    explicit middle-dot and dash mapping used for titles such as ``WALL·E``.
    """
    normalized_title = normalize_title_text(title)
    normalized_text = normalize_title_text(text)
    if not normalized_title or not normalized_text:
        return False
    return (
        re.search(rf"(?<!\w){re.escape(normalized_title)}(?!\w)", normalized_text)
        is not None
    )


def verify_prompt_title_absence(title: str, prompt: str) -> VerificationDecision:
    """Pass when the normalized reference title does not occur in the prompt."""
    matched = title_occurs_in_text(title, prompt)
    reason = (
        "Normalized reference title occurs in the generated prompt."
        if matched
        else None
    )
    raw_response = json.dumps(
        {
            "passed": not matched,
            "reason": reason,
            "normalized_title": normalize_title_text(title),
        },
        ensure_ascii=False,
    )
    return VerificationDecision(
        passed=not matched,
        reason=reason,
        raw_response=raw_response,
        method=PROMPT_TITLE_MATCH_METHOD,
    )
