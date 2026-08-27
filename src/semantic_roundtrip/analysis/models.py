"""Small DataFrame bundle returned by the read-only study loader."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class StudyFrames:
    """Normalized thesis inputs derived directly from selected SQLite runs."""

    observations: pd.DataFrame
    runs: pd.DataFrame
    errors: pd.DataFrame
    verifier: pd.DataFrame
    runtimes: pd.DataFrame
