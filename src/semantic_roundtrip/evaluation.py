"""Versioned strict and supplementary title-comparison rules."""

import unicodedata

EXACT_MATCH_METHOD = "strict_trimmed_exact_v1"
NORMALIZED_EXACT_METHOD = "casefold_whitespace_outer_quotes_exact_v2"


def title_exact_match(expected_title: str, predicted_title: str) -> bool:
    """Compare titles case-sensitively after trimming outer whitespace."""
    return expected_title.strip() == predicted_title.strip()


def title_normalized_exact_match(
    expected_title: str,
    predicted_title: str,
) -> bool:
    """Normalize case/whitespace and allow one extra prediction quote pair."""

    def normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value)
        return " ".join(normalized.casefold().split())

    expected, predicted = normalize(expected_title), normalize(predicted_title)
    if expected == predicted:
        return True
    # Strip only an extra wrapper on the prediction, never reference punctuation.
    return (
        len(predicted) >= 2
        and (predicted[0], predicted[-1])
        in {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("„", "“"), ("‚", "‘")}
        and predicted[1:-1].strip() == expected
    )
