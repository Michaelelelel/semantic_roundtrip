"""Title comparisons and report-only prompt checks; run with unittest discovery."""

import json
import unittest
from datetime import UTC, datetime
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from semantic_roundtrip.adapters.errors import AdapterError
from semantic_roundtrip.config import (
    PromptGenerationStage,
    ResolvedAppConfig,
    ResolvedRunInheritance,
)
from semantic_roundtrip.config_resolution import load_effective_config
from semantic_roundtrip.domain import BenchmarkItem, GeneratedPrompt, PromptResponse
from semantic_roundtrip.evaluation import (
    EXACT_MATCH_METHOD,
    NORMALIZED_EXACT_METHOD,
    PROMPT_TITLE_MATCH_METHOD,
    normalize_title_text,
    title_exact_match,
    title_normalized_exact_match,
    title_occurs_in_text,
)
from semantic_roundtrip.inheritance.materialize import materialize_inheritance
from semantic_roundtrip.persistence.run.config_snapshot import (
    create_effective_config_snapshot,
)
from semantic_roundtrip.persistence.run.database import RunDatabase
from semantic_roundtrip.persistence.run.manager import RunContext
from semantic_roundtrip.persistence.run.schema import initialize_database
from semantic_roundtrip.pipeline.runner import (
    PROMPT_TITLE_CHECK_FILENAME,
    execute_stages,
)
from semantic_roundtrip.prompting import PromptProfile


class NormalizeTitleTextTests(unittest.TestCase):
    def test_unicode_case_and_whitespace(self):
        cases = (
            ("  CAFE\u0301\tNOIR\n", "café noir"),
            ("Straße", "strasse"),
            ("ΣΙΣΥΦΟΣ", "σισυφοσ"),
            ("  The\u00a0\u2003Dark\n\tSide  ", "the dark side"),
            ("", ""),
            (" \t\r\n\u00a0", ""),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_title_text(value), expected)
                self.assertEqual(normalize_title_text(expected), expected)

    def test_exact_dash_translation_set(self):
        for codepoint in (0x00B7, *range(0x2010, 0x2016)):
            with self.subTest(codepoint=hex(codepoint)):
                self.assertEqual(
                    normalize_title_text(f"WALL{chr(codepoint)}E"), "wall-e"
                )

    def test_other_punctuation_is_preserved(self):
        cases = (
            '"Heroes"',
            "'Heroes'",
            "“Heroes”",
            "AC/DC",
            "C++",
            "P!nk",
            "(What's the Story) Morning Glory?",
            "WALL.E",
            "WALL•E",  # U+2022 BULLET is not U+00B7 MIDDLE DOT.
            "WALL−E",  # U+2212 MINUS SIGN is not a typographic dash.
            "WALL\u00adE",  # A soft hyphen is not silently removed.
            "WALL－E",  # No compatibility normalization of full-width forms.
            "Beyoncé",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(normalize_title_text(value), value.casefold())


class ExactMatchTests(unittest.TestCase):
    def test_method_versions(self):
        self.assertEqual(EXACT_MATCH_METHOD, "strict_trimmed_exact_v1")
        self.assertEqual(
            NORMALIZED_EXACT_METHOD,
            "nfc_casefold_whitespace_middot_dashes_outer_quotes_exact_v3",
        )
        self.assertEqual(
            PROMPT_TITLE_MATCH_METHOD,
            "nfc_casefold_whitespace_middot_dashes_word_boundaries_v1",
        )

    def test_strict_match_is_still_trim_only(self):
        cases = (
            ("Up", "Up", True),
            (" \tUp\n", "Up\u00a0", True),
            ("Up", "up", False),
            ("Café", "Cafe\u0301", False),
            ("The Dark Side", "The  Dark Side", False),
            ("WALL·E", "WALL-E", False),
            ("WALL–E", "WALL-E", False),
            ("Up", '"Up"', False),
            ('"Heroes"', "Heroes", False),
            ("", "", True),
            (" \n", "\t", True),
        )
        for expected, predicted, match in cases:
            with self.subTest(expected=expected, predicted=predicted):
                self.assertIs(title_exact_match(expected, predicted), match)

    def test_normalized_exact_shares_text_normalization(self):
        cases = (
            ("Café Noir", "  CAFE\u0301\tNOIR\n"),
            ("Straße", "STRASSE"),
            ("The Dark Side", "The\u00a0\nDark\tSide"),
            ("WALL·E", "WALL-E"),
            ("WALL-E", "wall·e"),
            ("WALL—E", "wall‑e"),
            ("", " \t"),
        )
        for expected, predicted in cases:
            with self.subTest(expected=expected, predicted=predicted):
                self.assertTrue(title_normalized_exact_match(expected, predicted))

    def test_one_extra_matching_prediction_quote_pair(self):
        for opening, closing in (
            ('"', '"'),
            ("'", "'"),
            ("“", "”"),
            ("‘", "’"),
            ("„", "“"),
            ("‚", "‘"),
        ):
            with self.subTest(opening=opening, closing=closing):
                prediction = f" \n{opening}\tWALL-E\u00a0{closing} "
                self.assertTrue(title_normalized_exact_match("WALL·E", prediction))
                self.assertFalse(title_exact_match("WALL·E", prediction))
                self.assertFalse(
                    title_normalized_exact_match(
                        "WALL·E", f"{opening}{opening}WALL-E{closing}{closing}"
                    )
                )

    def test_mismatched_and_unsupported_quotes_are_not_removed(self):
        for predicted in ("\"Up'", "“Up“", "‘Up‘", "„Up”", "«Up»", '"Up', 'Up"'):
            with self.subTest(predicted=predicted):
                self.assertFalse(title_normalized_exact_match("Up", predicted))

    def test_reference_punctuation_is_never_stripped(self):
        cases = (
            ('"Heroes"', "Heroes", False),
            ('"Heroes"', '"heroes"', True),
            ('"Heroes"', '“"Heroes"”', True),
            ('"Heroes"', '""Heroes""', True),
            ('"Heroes"', "“Heroes”", False),
            ("'Heroes'", "Heroes", False),
            ("Heroes", "\"'Heroes'\"", False),
            ("(Up)", "Up", False),
            ("Up!", "Up", False),
            ("Up", "Up!", False),
        )
        for expected, predicted, match in cases:
            with self.subTest(expected=expected, predicted=predicted):
                self.assertIs(title_normalized_exact_match(expected, predicted), match)

    def test_no_semantic_aliases_or_fuzzy_punctuation(self):
        cases = (
            ("WALL·E", "Wally"),
            ("WALL·E", "WALLE"),
            ("WALL·E", "Wall E"),
            ("WALL·E", "WALL.E"),
            ("WALL·E", "WALL - E"),
            ("AC/DC", "ACDC"),
            ("P!nk", "Pink"),
            ("Beyoncé", "Beyonce"),
            ("Up", "Above"),
        )
        for expected, predicted in cases:
            with self.subTest(expected=expected, predicted=predicted):
                self.assertFalse(title_normalized_exact_match(expected, predicted))


class PromptTitleMatchTests(unittest.TestCase):
    def test_normalized_whole_phrase_matches(self):
        cases = (
            ("Up", "Up"),
            ("Up", "Look UP!"),
            ("Up", 'A sign reading "Up".'),
            ("Up", "A group below; up above."),
            ("Café Noir", "A CAFE\u0301\n\tNOIR sign."),
            ("Straße", "Die STRASSE ist leer."),
            ("WALL·E", "A WALL-E robot."),
            ("WALL-E", "A wall—e robot."),
            ("東京", "A 東京 sign."),
        )
        for title, text in cases:
            with self.subTest(title=title, text=text):
                self.assertTrue(title_occurs_in_text(title, text))

    def test_unicode_word_boundaries(self):
        for text in (
            "group",
            "UPPER",
            "backup",
            "up2",
            "2up",
            "_up",
            "up_",
            "éup",
            "upé",
            "中up",
            "up中",
            "αup",
            "upβ",
        ):
            with self.subTest(text=text):
                self.assertFalse(title_occurs_in_text("Up", text))
        self.assertFalse(title_occurs_in_text("東京", "東京都"))

    def test_punctuation_titles_have_both_edges_guarded(self):
        for title in ("C++", "!Up", "(Up)", '"Heroes"', "AC/DC", "!!!"):
            with self.subTest(title=title):
                self.assertTrue(title_occurs_in_text(title, f"About {title}."))
                self.assertFalse(title_occurs_in_text(title, f"x{title}"))
                self.assertFalse(title_occurs_in_text(title, f"{title}x"))
                self.assertFalse(title_occurs_in_text(title, f"_{title}"))
                self.assertFalse(title_occurs_in_text(title, f"{title}_"))
                self.assertFalse(title_occurs_in_text(title, f"中{title}"))
                self.assertFalse(title_occurs_in_text(title, f"{title}é"))

    def test_regex_metacharacters_are_literal(self):
        for title, nonmatch in (
            ("a.b", "axb"),
            ("C++", "C"),
            ("[Up]", "U"),
            ("A|B", "A"),
            ("$Up^", "Up"),
            ("Up?", "U"),
            (r"A\B", "AB"),
        ):
            with self.subTest(title=title):
                self.assertTrue(title_occurs_in_text(title, title))
                self.assertFalse(title_occurs_in_text(title, nonmatch))

    def test_title_quotes_are_not_removed(self):
        self.assertFalse(title_occurs_in_text('"Heroes"', "A Heroes poster."))
        self.assertFalse(title_occurs_in_text('"Heroes"', "A “Heroes” poster."))
        self.assertTrue(title_occurs_in_text('"Heroes"', 'A "Heroes" poster.'))
        self.assertTrue(title_occurs_in_text("Heroes", 'A "Heroes" poster.'))

    def test_empty_inputs_never_match(self):
        for title, text in (
            ("", ""),
            ("", "Up"),
            ("Up", ""),
            (" \t\u00a0", "Look up!"),
            ("Up", " \n\u2003"),
        ):
            with self.subTest(title=title, text=text):
                self.assertFalse(title_occurs_in_text(title, text))

    def test_no_semantic_or_partial_phrase_matches(self):
        cases = (
            ("WALL·E", "A Wally robot."),
            ("WALL·E", "A WALLE robot."),
            ("WALL·E", "A small waste-collecting robot."),
            ("Up", "A house floats beneath many balloons."),
            ("Dark Side", "A dark and ominous side."),
            ("Dark Side", "Dark sides of the moon."),
            ("AC/DC", "An ACDC poster."),
        )
        for title, text in cases:
            with self.subTest(title=title, text=text):
                self.assertFalse(title_occurs_in_text(title, text))


class PromptTitleReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        context = RunContext("title-check-test", self.directory, datetime.now(UTC))
        database_path = initialize_database(
            context,
            "title-check-test",
            self.directory / "input.yaml",
            self.directory / "effective.yaml",
        )
        self.database = self.enterContext(RunDatabase(database_path, context))
        self.config = ResolvedAppConfig.model_validate(
            {
                "schema_version": 8,
                "run": {"name": "title-check-test"},
                "dataset": {
                    "dataset_id": "test_titles",
                    "items": [
                        {"id": "up", "domain": "movie", "title": "Up"},
                        {"id": "wall_e", "domain": "movie", "title": "WALL·E"},
                    ],
                },
                "experiment": {
                    "prompt_seeds": [1000, 1001],
                    "image_seeds": [1234],
                    "retry_limit": 1,
                },
                "backends": {
                    "unused": {
                        "source_profile": "unused.yaml",
                        "adapter": "mock",
                        "runtime": {"controller": "none", "resource_group": "test"},
                    }
                },
                "stages": {
                    "prompt_generation": {
                        "backend": "unused",
                        "prompt_profile": "unused.yaml",
                    },
                    "image_generation": {"backend": "unused"},
                },
            }
        )
        self.profile = PromptProfile(
            profile_id="synthetic-test",
            version=1,
            output_format="plain_text",
            messages=[{"role": "user", "content": "$title"}],
        )
        self.texts = ["UP!", "\tgroup \n", "A WALL-E robot.", "A Wally robot."]
        self.adapters = Mock()
        self.adapters.prompt_generator.generate_prompt.side_effect = [
            PromptResponse(text=text, raw_response=text) for text in self.texts
        ]
        self.runtime = Mock()
        self.image_stage = self.enterContext(
            patch("semantic_roundtrip.pipeline.runner.execute_image_generation_stage")
        )
        self.report_path = self.directory / PROMPT_TITLE_CHECK_FILENAME

    def execute(self):
        execute_stages(
            config=self.config,
            database=self.database,
            images_directory=self.directory / "images",
            adapters=self.adapters,
            illustratability_profile=None,
            prompt_profile=self.profile,
            runtime_session=self.runtime,
        )

    def test_report_defaults_off_for_old_configs(self):
        self.assertFalse(self.config.stages.prompt_generation.title_check_report)
        self.execute()
        self.assertFalse(self.report_path.exists())
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 4)
        self.image_stage.assert_called_once()

    def test_enabled_flag_survives_snapshot_roundtrip(self):
        self.config.stages.prompt_generation.title_check_report = True
        restored = ResolvedAppConfig.model_validate_json(self.config.model_dump_json())
        self.assertTrue(restored.stages.prompt_generation.title_check_report)
        stage = PromptGenerationStage(
            backend="unused",
            prompt_profile=Path("unused.yaml"),
            title_check_report=True,
        )
        self.assertEqual(stage.parameters, {})

    def test_report_contains_raw_prompts_and_never_retries_matches(self):
        self.config.stages.prompt_generation.title_check_report = True
        self.execute()
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertIs(report["report_only"], True)
        self.assertEqual(report["method"], PROMPT_TITLE_MATCH_METHOD)
        self.assertEqual(report["expected_prompts"], 4)
        self.assertEqual(report["checked_prompts"], 4)
        self.assertEqual(report["missing_prompts"], 0)
        self.assertEqual(report["matched_prompts"], 2)
        self.assertEqual([row["prompt_text"] for row in report["prompts"]], self.texts)
        self.assertEqual(
            [row["title_occurs"] for row in report["prompts"]],
            [True, False, True, False],
        )
        self.assertEqual(
            [row["prompt_seed"] for row in report["prompts"]], [1000, 1001, 1000, 1001]
        )
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 4)
        self.assertEqual(self.database.tasks.count_failed(), 0)
        self.assertFalse(self.report_path.with_suffix(".json.tmp").exists())
        self.image_stage.assert_called_once()

    def test_resume_rebuilds_identical_report_without_regeneration(self):
        self.config.stages.prompt_generation.title_check_report = True
        self.execute()
        initial = self.report_path.read_bytes()
        stored = self.database.results.list_prompts()
        self.report_path.unlink()
        self.runtime.reset_mock()
        self.execute()
        self.assertEqual(self.report_path.read_bytes(), initial)
        self.assertEqual(self.database.results.list_prompts(), stored)
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 4)
        self.assertEqual(self.image_stage.call_count, 2)
        activated = [
            call.args[1] for call in self.runtime.activate_stage.call_args_list
        ]
        self.assertNotIn("prompt_generation", activated)

    def test_missing_prompts_are_counted_and_not_treated_as_nonmatches(self):
        self.config.stages.prompt_generation.title_check_report = True
        self.adapters.prompt_generator.generate_prompt.side_effect = [
            PromptResponse(text="UP!", raw_response="UP!"),
            AdapterError("synthetic technical error"),
            AdapterError("synthetic technical error"),
            *[PromptResponse(text=text, raw_response=text) for text in self.texts[2:]],
        ]
        self.execute()
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["expected_prompts"], 4)
        self.assertEqual(report["checked_prompts"], 3)
        self.assertEqual(report["missing_prompts"], 1)
        self.assertEqual(report["matched_prompts"], 2)
        self.assertEqual(self.database.tasks.count_failed(), 1)
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 5)
        self.execute()
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 5)
        self.assertEqual(
            json.loads(self.report_path.read_text(encoding="utf-8")), report
        )

    def test_all_failed_prompts_still_produce_an_empty_report(self):
        self.config.stages.prompt_generation.title_check_report = True
        self.adapters.prompt_generator.generate_prompt.side_effect = AdapterError(
            "synthetic technical error"
        )
        self.execute()
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["checked_prompts"], 0)
        self.assertEqual(report["missing_prompts"], 4)
        self.assertEqual(report["matched_prompts"], 0)
        self.assertEqual(report["prompts"], [])
        self.assertEqual(self.database.tasks.count_failed(), 4)

    def test_inherited_pg_is_not_reexecuted_or_reported(self):
        self.config.stages.prompt_generation = None
        self.profile = None
        item_id = self.database.results.get_or_add_dataset_item(
            0, BenchmarkItem(item_key="up", domain="movie", title="Up")
        )
        response = PromptResponse(text="Look UP!", raw_response="Look UP!")
        self.database.results.add_prompt(
            item_id=item_id,
            prompt=GeneratedPrompt(index=0, text=response.text),
            sampling_seed=1000,
            response=response,
        )
        self.execute()
        self.adapters.prompt_generator.generate_prompt.assert_not_called()
        self.assertFalse(self.report_path.exists())
        stored = self.database.results.list_prompts()[0]
        self.assertTrue(title_occurs_in_text(stored.item.title, stored.prompt.text))
        self.image_stage.assert_called_once()

    def test_report_enabled_source_can_be_materialized_and_resumed(self):
        self.config.stages.prompt_generation.title_check_report = True
        source_snapshot = create_effective_config_snapshot(self.config, self.directory)
        source_config = load_effective_config(source_snapshot)
        self.assertTrue(source_config.stages.prompt_generation.title_check_report)
        self.execute()
        self.database.update_status("completed")
        initial_report = self.report_path.read_bytes()

        target_directory = self.directory / "derived"
        target_directory.mkdir()
        context = RunContext("derived-test", target_directory, datetime.now(UTC))
        target_database_path = initialize_database(
            context,
            "derived-test",
            target_directory / "input.yaml",
            target_directory / "effective.yaml",
        )
        inherited = self.config.model_copy(deep=True)
        inherited.stages.prompt_generation = None
        inherited.inherit = ResolvedRunInheritance(
            source_kind="from_run",
            source_run=self.directory,
            source_run_id="title-check-test",
            stages=["prompt_generation"],
        )
        snapshot = create_effective_config_snapshot(inherited, target_directory)
        inherited = load_effective_config(snapshot)
        self.assertTrue(materialize_inheritance(inherited, target_directory))
        self.assertFalse(materialize_inheritance(inherited, target_directory))
        with RunDatabase(target_database_path, context) as target:
            self.assertEqual(
                [work.prompt.text for work in target.results.list_prompts()], self.texts
            )
            self.assertEqual(target.tasks.count_terminal_local("prompt_generation"), 0)
            execute_stages(
                config=inherited,
                database=target,
                images_directory=target_directory / "images",
                adapters=self.adapters,
                illustratability_profile=None,
                prompt_profile=None,
                runtime_session=self.runtime,
            )
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 4)
        self.assertEqual(self.report_path.read_bytes(), initial_report)
        self.assertFalse((target_directory / PROMPT_TITLE_CHECK_FILENAME).exists())

    def test_report_io_failure_does_not_gate_downstream_work(self):
        self.config.stages.prompt_generation.title_check_report = True
        self.report_path.mkdir()  # A file cannot atomically replace a directory.
        with self.assertLogs("semantic_roundtrip.pipeline.runner", level="WARNING"):
            self.execute()
        self.assertEqual(self.adapters.prompt_generator.generate_prompt.call_count, 4)
        self.assertEqual(self.database.tasks.count_failed(), 0)
        self.assertFalse(self.report_path.with_suffix(".json.tmp").exists())
        self.image_stage.assert_called_once()


@unittest.skipUnless(
    find_spec("pandas") is not None and find_spec("numpy") is not None,
    "Score regression requires the project's existing analysis extra.",
)
class ScoreRegressionTests(unittest.TestCase):
    def test_prompt_check_cannot_gate_existing_strict_scores(self):
        import pandas as pd

        from semantic_roundtrip.analysis.statistics import score_observations

        raw = pd.DataFrame(
            {
                "expected_title": ["Up", "Up", "WALL·E", "Up"],
                "predicted_title": ["Up", "Up", "WALL-E", None],
                "verification_passed": [True, True, True, False],
                "prompt_text": ["UP!", "A house.", "WALL-E robot.", None],
            }
        )
        original = raw.copy(deep=True)
        raw["prompt_title_match"] = pd.array(
            [
                None if text is None else title_occurs_in_text(title, text)
                for title, text in zip(raw.expected_title, raw.prompt_text, strict=True)
            ],
            dtype="boolean",
        )
        scored = score_observations(raw)
        baseline = score_observations(original)
        pd.testing.assert_frame_equal(raw.drop(columns="prompt_title_match"), original)
        pd.testing.assert_frame_equal(
            scored.drop(columns="prompt_title_match"), baseline
        )
        self.assertEqual(scored.end_to_end_strict_score.tolist(), [1, 1, 0, 0])
        self.assertEqual(scored.end_to_end_normalized_score.tolist(), [1, 1, 1, 0])
        self.assertEqual(scored.end_to_end_strict_score.mean(), 0.5)
        self.assertAlmostEqual(scored.strict_exact_match.mean(), 2 / 3)
        self.assertEqual(scored.predicted_title.notna().mean(), 0.75)
        self.assertTrue(pd.isna(scored.strict_exact_match.iloc[3]))
        self.assertTrue(pd.isna(scored.normalized_exact_match.iloc[3]))

    def test_rejections_and_missing_verification_stay_zero(self):
        import pandas as pd

        from semantic_roundtrip.analysis.statistics import score_observations

        scored = score_observations(
            pd.DataFrame(
                {
                    "expected_title": ["Up"] * 4,
                    "predicted_title": ["Up", "Up", "Above", None],
                    "verification_passed": [True, False, True, None],
                }
            )
        )
        self.assertEqual(scored.end_to_end_strict_score.tolist(), [1, 0, 0, 0])
        self.assertEqual(scored.end_to_end_strict_score.mean(), 0.25)
        self.assertAlmostEqual(scored.strict_exact_match.mean(), 2 / 3)
        accepted = scored[scored.verification_passed.eq(True)]
        self.assertEqual(accepted.end_to_end_strict_score.mean(), 0.5)


if __name__ == "__main__":
    unittest.main()
