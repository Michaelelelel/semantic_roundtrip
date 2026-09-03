"""Model-free checks for the held-out style pilot selection."""

import importlib.util
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "style_pilot", ROOT / "scripts/datasets/build_style_pilot.py"
)
PILOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOT)


class StylePilotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "id": f"{domain}_{i}",
                "domain": domain,
                "source_rank": str(i),
                "source_id": str(i),
                "selection_group": str(i // 2),
            }
            for domain in PILOT.DOMAINS
            for i in range(12)
        ]

    def test_counts_exclusions_artist_uniqueness_and_reproduction(self):
        excluded = {f"{domain}_0" for domain in PILOT.DOMAINS}
        selected = PILOT.select_pilot(self.rows, excluded, titles_per_domain=4)
        self.assertEqual(
            Counter(row["domain"] for row in selected), dict.fromkeys(PILOT.DOMAINS, 4)
        )
        self.assertFalse(excluded.intersection(row["id"] for row in selected))
        self.assertEqual(
            len(
                {row["selection_group"] for row in selected if row["domain"] == "songs"}
            ),
            4,
        )
        self.assertEqual(
            selected,
            PILOT.select_pilot(
                list(reversed(self.rows)), excluded, titles_per_domain=4
            ),
        )

    def test_insufficient_unique_artists_fails(self):
        with self.assertRaisesRegex(ValueError, "eligible songs"):
            PILOT.select_pilot(self.rows, set(), titles_per_domain=7)

    def test_invalid_count_fails(self):
        with self.assertRaises(ValueError):
            PILOT.select_pilot(self.rows, set(), titles_per_domain=0)


if __name__ == "__main__":
    unittest.main()
