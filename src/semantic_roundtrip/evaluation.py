"""Exact-match evaluation rules for title predictions."""

EVALUATION_METHOD = "casefold_exact_v1"


def title_exact_match(expected_title: str, predicted_title: str) -> bool:
    """Compare titles case-insensitively without other normalization."""
    return expected_title.casefold() == predicted_title.casefold()


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
