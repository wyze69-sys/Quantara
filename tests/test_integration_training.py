"""Real retained-year-chain acceptance for training slice 011."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.research_pipeline import read_research_rows
from quantara.training_pipeline import verify_training_current_graph

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
TRAINING_DESCRIPTOR = (
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml"
)


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


def _restore(path: Path, payload: bytes) -> None:
    target = path / "current.json"
    temporary = target.with_name("current.training-restore.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, target)


def _run(descriptor: Path) -> int:
    return main(["--descriptor", str(descriptor), "--data-root", str(DATA_ROOT)])


def test_real_year_training_acceptance_and_idempotency() -> None:
    resting = {directory: (directory / "current.json").read_bytes() for directory in RESTING_DIRS}
    year_commits: list[Path] = []
    training_commit_dir: Path | None = None
    try:
        for descriptor in DESCRIPTORS:
            assert _run(descriptor) == 0
        year_commits = [
            directory
            / "commits"
            / json.loads((directory / "current.json").read_text())["commit"]
            for directory in RESTING_DIRS
        ]
        assert _run(TRAINING_DESCRIPTOR) == 0
        graph = verify_training_current_graph(TRAINING_DIR, DATA_ROOT)
        pointer_before = (TRAINING_DIR / "current.json").read_bytes()
        training_commit_dir = TRAINING_DIR / "commits" / graph["commit"]
        manifest = json.loads(
            (training_commit_dir / "manifest.json").read_text(encoding="utf-8")
        )
        quality = json.loads(
            (training_commit_dir / "quality.json").read_text(encoding="utf-8")
        )
        artifact_path = (
            DATA_ROOT
            / "objects"
            / "normalized"
            / "sha256"
            / manifest["artifact_sha256"]
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert quality["state"] == "PASS"
        assert all(item["outcome"] == "pass" for item in quality["findings"])
        assert len(artifact["records"]) == 117
        assert set(artifact["baselines"]) == {
            "majority_class_train_window",
            "sign_f_ret_1",
        }
        for record in artifact["records"]:
            assert Decimal(-1) <= Decimal(record["pearson_ic"]) <= Decimal(1)
            assert Decimal(0) <= Decimal(record["directional_accuracy"]) <= Decimal(1)
            assert Decimal(record["mse"]) >= 0
            assert set(record["baselines"]) == {
                "majority_class_train_window",
                "sign_f_ret_1",
            }

        research_manifest = json.loads(
            (
                year_commits[3] / "manifest.json"
            ).read_text(encoding="utf-8")
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
        for fold, record in zip(validation["folds"], artifact["records"], strict=True):
            begin, end = fold["train_range"]
            labels = [row[6] for row in research_rows[begin:end] if row[6] is not None]
            expected = 1 if labels.count(1) >= labels.count(-1) else -1
            assert record["baselines"]["majority_class_train_window"][
                "predicted_direction"
            ] == expected

        assert _run(TRAINING_DESCRIPTOR) == 0
        assert (TRAINING_DIR / "current.json").read_bytes() == pointer_before
        print(
            "TRAINING_ACCEPTANCE "
            f"commit={graph['commit']} artifact={manifest['artifact_sha256']} "
            f"canonical_content_hash={manifest['canonical_content_hash']}"
        )
        print("TRAINING_SUMMARIES " + json.dumps(artifact["summaries"], sort_keys=True))
        print("TRAINING_BASELINES " + json.dumps(artifact["baselines"], sort_keys=True))
    finally:
        for directory, payload in resting.items():
            _restore(directory, payload)

    assert all(path.is_dir() and (path / "COMMITTED").is_file() for path in year_commits)
    assert training_commit_dir is not None
    assert training_commit_dir.is_dir() and (training_commit_dir / "COMMITTED").is_file()
    assert {
        directory: (directory / "current.json").read_bytes()
        for directory in RESTING_DIRS
    } == resting
