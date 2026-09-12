"""Compare the completed Core assessment with saved decisions. Read-only, no models."""

import argparse
import csv
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

JOB_ID = "20260903T230744Z_final-direct-core_faa7afcb"
RUN_IDS = (
    "20260903T230744Z_direct-pg-q25-bi-q25_07602cd9",
    "20260903T230744Z_direct-pg-q38-bi-q38_0654c583",
    "20260903T230745Z_direct-pg-g3-bi-g3_adbddd23",
    "20260903T230745Z_direct-pg-g4-bi-g4_203979fc",
)
LABELS = (
    Path(__file__).resolve().parents[1] / "manual_evaluation/verifier_assessment.csv"
)


def evaluate(labels_csv, job_dir):
    """Return counts and print agreement over all 360 fixed image/prompt pairs."""
    job = Path(job_dir).resolve()
    with closing(
        sqlite3.connect((job / "job_state.sqlite").as_uri() + "?mode=ro", uri=True)
    ) as db:
        db.execute("BEGIN")
        if db.execute("PRAGMA user_version").fetchone()[0] != 4:
            raise ValueError("Expected job database version 4.")
        if db.execute("SELECT job_id,status FROM job_metadata").fetchall() != [
            (JOB_ID, "completed")
        ]:
            raise ValueError(f"Expected completed source job {JOB_ID}.")
        if (
            db.execute("SELECT status FROM job_entries").fetchall()
            != [("completed",)] * 16
        ):
            raise ValueError("All 16 source child runs must be completed.")

    with Path(labels_csv).open(encoding="utf-8-sig", newline="") as stream:
        delimiter = csv.Sniffer().sniff(stream.readline(), delimiters=",;").delimiter
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter, strict=True)
        if reader.fieldnames != [
            "run_id",
            "image_id",
            "title",
            "prompt_text",
            "prompt_title_use",
            "flag_strict",
            "flag_title_aware",
            "notes",
        ]:
            raise ValueError("Unexpected CSV columns.")
        labels = list(reader)
    if len(labels) != 360:
        raise ValueError("Expected exactly 360 assessment rows.")

    saved, missing, title_sets = {}, {}, []
    for run_id in RUN_IDS:
        path = job / "runs" / run_id / "pipeline_state.sqlite"
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA user_version").fetchone()[0] != 12:
                raise ValueError(f"Expected run database version 12: {run_id}")
            if db.execute("SELECT run_id,status FROM run_metadata").fetchall() != [
                (run_id, "completed")
            ]:
                raise ValueError(
                    f"Source run is not completed or has the wrong ID: {run_id}"
                )
            if db.execute(
                "SELECT count(*) FROM stage_tasks WHERE status NOT IN ('completed','failed')"
            ).fetchone()[0]:
                raise ValueError(f"Source run has unfinished tasks: {run_id}")
            db.row_factory = sqlite3.Row
            rows = db.execute("""
                SELECT i.image_id, d.item_key, d.domain, d.title, p.text AS prompt_text,
                       pv.passed AS prompt, sv.passed AS strict, tv.passed AS title_aware
                FROM images i JOIN prompts p USING(prompt_id)
                JOIN dataset_items d USING(item_id)
                LEFT JOIN prompt_verifications pv USING(prompt_id)
                LEFT JOIN image_verifications sv ON sv.image_id=i.image_id AND sv.policy='strict'
                LEFT JOIN image_verifications tv ON tv.image_id=i.image_id AND tv.policy='title_aware'
                WHERE p.sampling_seed=1000 AND p.prompt_index=0 AND i.seed=8566257
            """).fetchall()
            if len(rows) != 90 or Counter(r["domain"] for r in rows) != {
                "songs": 30,
                "movies": 30,
                "bands": 30,
            }:
                raise ValueError(
                    f"Expected 30 titles per domain at the fixed seed pair: {run_id}"
                )
            title_sets.append({(r["item_key"], r["domain"], r["title"]) for r in rows})
            for row in rows:
                key = (run_id, row["image_id"])
                if key in saved:
                    raise ValueError(f"Duplicate source observation: {key}")
                saved[key] = dict(row)
            # The last error distinguishes an invalid response from an absent decision.
            for error in db.execute("""
                SELECT t.image_id, t.task_key, e.message
                FROM stage_tasks t JOIN stage_errors e USING(task_id)
                WHERE t.stage='verification_image' AND
                    (t.task_key GLOB 'verification_image:strict:*' OR
                     t.task_key GLOB 'verification_image:title_aware:*')
                ORDER BY e.error_id
            """):
                invalid = error["message"].startswith(
                    (
                        "Verifier response is not valid verification JSON.",
                        "Verification response was truncated because the token limit was reached.",
                    )
                )
                policy = error["task_key"].split(":")[1]
                missing[run_id, error["image_id"], policy] = (
                    "invalid_decision" if invalid else "missing_decision"
                )
    if any(titles != title_sets[0] or len(titles) != 90 for titles in title_sets):
        raise ValueError("Source runs do not contain the same 90 titles.")

    policies = {policy: Counter() for policy in ("strict", "title_aware")}
    prompts = {code: Counter() for code in ("0", "n", "e")}
    seen = set()
    for line, row in enumerate(labels, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV row {line}: wrong number of fields.")
        key = (row["run_id"], int(row["image_id"]))
        if key not in saved or key in seen:
            raise ValueError(f"CSV row {line}: unknown or duplicate image ID.")
        seen.add(key)
        source = saved[key]
        if any(row[field] != source[field] for field in ("title", "prompt_text")):
            raise ValueError(f"CSV row {line}: source title or prompt differs.")
        if row["prompt_title_use"] not in prompts or any(
            row[f"flag_{p}"] not in ("0", "1") for p in policies
        ):
            raise ValueError(
                f"CSV row {line}: use explicit 0/n/e and 0/1 labels. Blank is not zero."
            )
        category = {None: "missing", 0: "flagged", 1: "passed"}.get(
            source["prompt"], "invalid"
        )
        prompts[row["prompt_title_use"]][category] += 1
        for policy, counts in policies.items():
            passed, reject = source[policy], int(row[f"flag_{policy}"])
            if passed is None:
                category = missing.get((*key, policy), "missing_decision")
            elif passed not in (0, 1):
                category = "invalid_decision"
            elif reject == 1 - passed:
                category = "both_reject" if reject else "both_accept"
            else:
                category = "false_accept" if reject else "false_reject"
            counts[category] += 1

    print(
        f"Source: {JOB_ID}\nSample: 360 pairs, 90 titles, four PG roots, seeds 1000 / 8566257"
    )
    for policy, counts in policies.items():
        agreement = counts["both_accept"] + counts["both_reject"]
        print(f"\n{policy}: agreement {agreement}/360 = {agreement / 360:.1%}")
        for category in (
            "both_accept",
            "both_reject",
            "false_accept",
            "false_reject",
            "missing_decision",
            "invalid_decision",
        ):
            print(f"  {category}: {counts[category]}")
    print("\nPrompt contexts versus saved lexical check (not a confusion matrix):")
    for code, counts in prompts.items():
        print(
            f"  {code}: {sum(counts.values())}, "
            + ", ".join(
                f"{k}={counts[k]}" for k in ("passed", "flagged", "missing", "invalid")
            )
        )
    return {"policies": policies, "prompt_contexts": prompts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--job", type=Path, required=True, help="Completed Direct Core job directory"
    )
    parser.add_argument("--labels", type=Path, default=LABELS)
    args = parser.parse_args()
    try:
        evaluate(args.labels, args.job)
    except (ValueError, OSError, sqlite3.Error, csv.Error) as error:
        parser.exit(1, f"Assessment failed: {error}\n")
