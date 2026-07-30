"""Versioned evaluation rules for title predictions."""

EXACT_MATCH_METHOD = "strict_trimmed_exact_v1"
CONTAINS_MATCH_METHOD = "casefold_contains_v1"


def title_exact_match(expected_title: str, predicted_title: str) -> bool:
    """Compare titles case-sensitively after trimming outer whitespace."""
    return expected_title.strip() == predicted_title.strip()


def title_casefold_contains_match(
    expected_title: str,
    predicted_title: str,
) -> bool:
    """Check whether the complete expected title occurs in the prediction."""
    expected = expected_title.strip().casefold()
    predicted = predicted_title.strip().casefold()
    return expected in predicted


def apply_verification_policy(
    *,
    title_matches: bool,
    verification_passed: bool,
    failed_verification: str,
) -> tuple[bool, bool | None]:
    """Return whether a result is included and its score under the policy."""
    if verification_passed:
        return True, title_matches

    if failed_verification == "count_as_failure":
        return True, False

    return False, None
