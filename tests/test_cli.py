"""CLI entrypoint unit tests for feature_evaluation (Task T10).

Covers:
- --dataset-type feature_evaluation --descriptor <path> --dry-run (exits 0, write-free);
- --dataset-type feature_evaluation without --descriptor (exits non-zero);
- unapproved dataset types (exits non-zero);
- missing descriptor file (exits non-zero).
"""

from __future__ import annotations

from pathlib import Path

from quantara.cli import main
from test_evaluation_pipeline import setup_offline_q1_parents


def test_cli_evaluation_dry_run_success(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    exit_code = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--descriptor",
            str(eval_desc),
            "--data-root",
            str(data_root),
            "--dry-run",
        ]
    )
    assert exit_code == 0

    # Verify write-free
    attempts_dir = data_root / "attempts" / "evaluation"
    assert not attempts_dir.exists() or not any(attempts_dir.iterdir())
    eval_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "evaluation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    assert not eval_dir.exists()


def test_cli_evaluation_missing_descriptor(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exit_code = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--data-root",
            str(data_root),
        ]
    )
    assert exit_code != 0


def test_cli_unapproved_dataset_type(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exit_code = main(
        [
            "--dataset-type",
            "arbitrary_model_signal",
            "--descriptor",
            "nonexistent.yaml",
            "--data-root",
            str(data_root),
        ]
    )
    assert exit_code != 0


def test_cli_nonexistent_descriptor_file(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    exit_code = main(
        [
            "--dataset-type",
            "feature_evaluation",
            "--descriptor",
            str(tmp_path / "does_not_exist.yaml"),
            "--data-root",
            str(data_root),
        ]
    )
    assert exit_code != 0
