"""Real retained-year-chain acceptance for logistic training slice 012.

Dual-outcome by design: the pre-registered kill criteria are frozen in the
descriptor before this run, so BOTH branches are legitimate and asserted.

- exit 0 -> the artifact published: 117 records, quality PASS including
  ``lane_kill_criteria``, all four kill booleans true, ``training_parent`` bound
  to the slice 011 ridge commit, and an idempotent byte-identical rerun.
- exit 4 -> the criteria failed: the training pointer is byte-identical to the
  pre-run snapshot (still the 011 commit), no new commit directory exists, and
  an attempt manifest records ``KILL_CRITERIA_FAILED`` with the four observed
  values.

Either way the per-fold causal baselines are recomputed independently in-test
and all seven resting pointers are restored byte-exactly in ``finally``.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.research_pipeline import read_research_rows
from quantara.training_metrics_logistic import (
    KILL_CRITERIA,
    climatology_probability,
)
from quantara.training_pipeline import (
    EXIT_KILL_CRITERIA_FAILED,
    EXIT_OK,
    KILL_CRITERIA_FAILED,
    verify_training_current_graph,
)
from quantara.training_quality import LOGISTIC_ARTIFACT_SCHEMA, LOGISTIC_CHECK_IDS

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = REPO_ROOT / "configs" / "datasets"
DESCRIPTORS = [
    CONFIG_ROOT / "binance-usdm-btcusdt-1m-2024.yaml",
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-derived.yaml",
    CONFIG_ROOT / "binance-usdm-btcusdt-1d-2024-derived.yaml",
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-research-core-v1.yaml",
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml",
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-evaluation-dual-ic-v1.yaml",
]
LOGISTIC_DESCRIPTOR = CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml"


def _directory(lane: str, interval: str) -> Path:
    return (
        DATA_ROOT
        / "datasets"
        / "binance"
        / "usdm"
        / lane
        / "BTCUSDT"
        / interval
        / "year=2024"
        / "month=01"
    )


RESTING_DIRS = [
    _directory("klines", "1m"),
    _directory("klines", "1h"),
    _directory("klines", "1d"),
    _directory("research", "1h"),
    _directory("validation", "1h"),
    _directory("evaluation", "1h"),
]
TRAINING_DIR = _directory("training", "1h")
SNAPSHOT_DIRS = [*RESTING_DIRS, TRAINING_DIR]


def _restore(path: Path, payload: bytes) -> None:
    target = path / "current.json"
    temporary = target.with_name("current.logistic-restore.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, target)


def _run(descriptor: Path) -> int:
    return main(["--descriptor", str(descriptor), "--data-root", str(DATA_ROOT)])


def _latest_attempt() -> dict:
    attempts = sorted((DATA_ROOT / "attempts" / "training").glob("*.json"))
    return json.loads(attempts[-1].read_text(encoding="utf-8"))


def test_real_year_logistic_run_against_pre_registered_criteria() -> None:
    snapshot = {
        directory: (directory / "current.json").read_bytes() for directory in SNAPSHOT_DIRS
    }
    training_pointer_before = snapshot[TRAINING_DIR]
    ridge_commit = json.loads(training_pointer_before.decode("utf-8"))["commit"]
    commits_before = sorted(path.name for path in (TRAINING_DIR / "commits").iterdir())
    year_commits: list[Path] = []
    published_commit_dir: Path | None = None
    try:
        for descriptor in DESCRIPTORS:
            assert _run(descriptor) == EXIT_OK
        year_commits = [
            directory
            / "commits"
            / json.loads((directory / "current.json").read_text())["commit"]
            for directory in RESTING_DIRS
        ]

        research_manifest = json.loads(
            (year_commits[3] / "manifest.json").read_text(encoding="utf-8")
        )
        research_rows = read_research_rows(
            DATA_ROOT
            / "objects"
            / "normalized"
            / "sha256"
            / research_manifest["parquet_sha256"]
        )
        validation_manifest = json.loads(
            (year_commits[4] / "manifest.json").read_text(encoding="utf-8")
        )
        validation = json.loads(
            (
                DATA_ROOT
                / "objects"
                / "normalized"
                / "sha256"
                / validation_manifest["artifact_sha256"]
            ).read_text(encoding="utf-8")
        )
        assert len(research_rows) == 8784
        assert len(validation["folds"]) == 117

        code = _run(LOGISTIC_DESCRIPTOR)
        assert code in (EXIT_OK, EXIT_KILL_CRITERIA_FAILED), code
        attempt = _latest_attempt()

        # Per-fold causality, asserted on both branches: the causal baselines
        # depend only on the fold's own train range.
        expected_baselines = []
        for fold in validation["folds"]:
            begin, end = fold["train_range"]
            labels = [row[6] for row in research_rows[begin:end] if row[6] is not None]
            expected_baselines.append(
                {
                    "majority": 1 if labels.count(1) >= labels.count(-1) else -1,
                    "up_count": labels.count(1),
                    "down_count": labels.count(-1),
                    "climatology": climatology_probability(
                        labels.count(1), labels.count(-1)
                    ),
                }
            )
        assert len(expected_baselines) == 117
        assert all(item["climatology"] > Decimal(0) for item in expected_baselines)

        if code == EXIT_KILL_CRITERIA_FAILED:
            # Expected possible outcome: no publication, pointer untouched.
            assert (TRAINING_DIR / "current.json").read_bytes() == training_pointer_before
            assert (
                json.loads((TRAINING_DIR / "current.json").read_text(encoding="utf-8"))[
                    "commit"
                ]
                == ridge_commit
            )
            assert (
                sorted(path.name for path in (TRAINING_DIR / "commits").iterdir())
                == commits_before
            )
            assert not list((TRAINING_DIR / "commits").glob(".staging-*"))
            assert attempt["terminal_result"] == KILL_CRITERIA_FAILED
            assert attempt["referenced_commit"] is None
            assert attempt["artifact_dispositions"] == {
                "training_artifact": "not_written",
                "pointer_replaced": False,
            }
            diagnostics = attempt["diagnostics"]
            for prefix in (
                "k1_directional_accuracy_mean=",
                "k2_direction_ic_mean=",
                "k3_log_loss_mean=",
                "k4_brier_mean=",
            ):
                assert any(item.startswith(prefix) for item in diagnostics), prefix
            for constant in KILL_CRITERIA.values():
                assert any(constant in item for item in diagnostics), constant
            print("LOGISTIC_KILL_CRITERIA_FAILED " + json.dumps(diagnostics, indent=1))
            print(f"LOGISTIC_POINTER_UNCHANGED commit={ridge_commit}")
        else:
            graph = verify_training_current_graph(TRAINING_DIR, DATA_ROOT)
            published_commit_dir = TRAINING_DIR / "commits" / graph["commit"]
            pointer_after = (TRAINING_DIR / "current.json").read_bytes()
            assert graph["commit"] != ridge_commit
            assert graph["artifact_schema"] == LOGISTIC_ARTIFACT_SCHEMA
            assert attempt["terminal_result"] == "PUBLISHED"

            manifest = json.loads(
                (published_commit_dir / "manifest.json").read_text(encoding="utf-8")
            )
            quality = json.loads(
                (published_commit_dir / "quality.json").read_text(encoding="utf-8")
            )
            artifact = json.loads(
                (
                    DATA_ROOT
                    / "objects"
                    / "normalized"
                    / "sha256"
                    / manifest["artifact_sha256"]
                ).read_text(encoding="utf-8")
            )
            assert quality["state"] == "PASS"
            assert [item["check_id"] for item in quality["findings"]] == list(
                LOGISTIC_CHECK_IDS
            )
            assert all(item["outcome"] == "pass" for item in quality["findings"])
            assert len(artifact["records"]) == 117
            assert artifact["training_parent"]["commit_address"] == ridge_commit
            assert artifact["kill_criteria"]["constants"] == dict(KILL_CRITERIA)
            assert artifact["kill_criteria"]["results"] == {
                "k1_directional_accuracy": True,
                "k2_direction_ic": True,
                "k3_log_loss": True,
                "k4_brier": True,
            }
            assert artifact["kill_criteria"]["all_passed"] is True
            assert set(artifact["baselines"]) == {
                "majority_class_train_window",
                "sign_f_ret_1",
                "climatology_p",
            }
            for record, expected in zip(
                artifact["records"], expected_baselines, strict=True
            ):
                assert Decimal(0) <= Decimal(record["directional_accuracy"]) <= Decimal(1)
                assert Decimal(record["log_loss"]) >= 0
                assert Decimal(0) <= Decimal(record["brier"]) <= Decimal(1)
                assert Decimal(-1) <= Decimal(record["direction_ic"]) <= Decimal(1)
                assert set(record["baselines"]) == {
                    "majority_class_train_window",
                    "sign_f_ret_1",
                    "climatology_p",
                }
                majority = record["baselines"]["majority_class_train_window"]
                assert majority["predicted_direction"] == expected["majority"]
                assert majority["train_up_count"] == expected["up_count"]
                assert majority["train_down_count"] == expected["down_count"]
                assert record["baselines"]["climatology_p"]["probability"] == format(
                    expected["climatology"], "f"
                )

            assert _run(LOGISTIC_DESCRIPTOR) == EXIT_OK
            assert (TRAINING_DIR / "current.json").read_bytes() == pointer_after
            assert _latest_attempt()["terminal_result"] == "VERIFIED_NO_OP"
            print(
                "LOGISTIC_ACCEPTANCE "
                f"commit={graph['commit']} artifact={manifest['artifact_sha256']} "
                f"canonical_content_hash={manifest['canonical_content_hash']}"
            )
            print("LOGISTIC_SUMMARIES " + json.dumps(artifact["summaries"], sort_keys=True))
            print("LOGISTIC_BASELINES " + json.dumps(artifact["baselines"], sort_keys=True))
            print("LOGISTIC_KILL " + json.dumps(artifact["kill_criteria"], sort_keys=True))
    finally:
        for directory, payload in snapshot.items():
            _restore(directory, payload)

    assert all(path.is_dir() and (path / "COMMITTED").is_file() for path in year_commits)
    if published_commit_dir is not None:
        assert published_commit_dir.is_dir()
        assert (published_commit_dir / "COMMITTED").is_file()
    assert {
        directory: (directory / "current.json").read_bytes()
        for directory in SNAPSHOT_DIRS
    } == snapshot
