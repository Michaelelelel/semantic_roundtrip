"""Versioned strict and supplementary title-comparison rules."""

import unicodedata

EXACT_MATCH_METHOD = "strict_trimmed_exact_v1"
NORMALIZED_EXACT_METHOD = "casefold_whitespace_exact_v1"


def title_exact_match(expected_title: str, predicted_title: str) -> bool:
    """Compare titles case-sensitively after trimming outer whitespace."""
    return expected_title.strip() == predicted_title.strip()


def title_normalized_exact_match(
    expected_title: str,
    predicted_title: str,
) -> bool:
    """Compare titles after conservative case and whitespace normalization."""

    def normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value)
        return " ".join(normalized.casefold().split())

    return normalize(expected_title) == normalize(predicted_title)
