"""Real retained-year-chain IC stability diagnostic for the 012 KILL data."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.ic_stability_diagnostic import (
    GateVerdict,
    _run_ic_stability_report,
)
from quantara.training_pipeline import EXIT_KILL_CRITERIA_FAILED, EXIT_OK

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
LOGISTIC_DESCRIPTOR = (
    CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml"
)
DIAGNOSTIC_DIR = DATA_ROOT / "diagnostic" / "training"


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


SNAPSHOT_DIRS = [
    _directory("klines", "1m"),
    _directory("klines", "1h"),
    _directory("klines", "1d"),
    _directory("research", "1h"),
    _directory("validation", "1h"),
    _directory("evaluation", "1h"),
    _directory("training", "1h"),
]


def _restore(path: Path, payload: bytes) -> None:
    target = path / "current.json"
    temporary = target.with_name("current.ic-stability-restore.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, target)


def _run(descriptor: Path) -> int:
    return main(["--descriptor", str(descriptor), "--data-root", str(DATA_ROOT)])


def test_real_year_chain_ic_stability_on_012_kill_data() -> None:
    snapshot = {
        directory: (directory / "current.json").read_bytes()
        for directory in SNAPSHOT_DIRS
    }
    before_sidecars = set(DIAGNOSTIC_DIR.glob("per_fold_*.json"))
    year_commits: list[Path] = []
    try:
        for descriptor in DESCRIPTORS:
            assert _run(descriptor) == EXIT_OK
        year_commits = [
            directory
            / "commits"
            / json.loads((directory / "current.json").read_text(encoding="utf-8"))[
                "commit"
            ]
            for directory in SNAPSHOT_DIRS[:-1]
        ]
        assert all(
            commit.is_dir() and (commit / "COMMITTED").is_file()
            for commit in year_commits
        )

        assert _run(LOGISTIC_DESCRIPTOR) == EXIT_KILL_CRITERIA_FAILED
        new_sidecars = set(DIAGNOSTIC_DIR.glob("per_fold_*.json")) - before_sidecars
        assert len(new_sidecars) == 1
        sidecar = new_sidecars.pop()
        attempt_id = sidecar.stem.removeprefix("per_fold_")
        report_path = DIAGNOSTIC_DIR / f"ic_stability_{attempt_id}.json"

        report = _run_ic_stability_report(sidecar, report_path)

        assert report_path.exists()
        assert report["gate_verdict"] in {verdict.value for verdict in GateVerdict}
        assert not sidecar.exists()
        print("IC_STABILITY_REPORT " + json.dumps(report, sort_keys=True))
        print(f"IC_STABILITY_REPORT_PATH {report_path}")
    finally:
        for directory, payload in snapshot.items():
            _restore(directory, payload)
        assert {
            directory: (directory / "current.json").read_bytes()
            for directory in SNAPSHOT_DIRS
        } == snapshot
        for directory, payload in snapshot.items():
            commit = json.loads(payload.decode("utf-8"))["commit"]
            print(f"IC_STABILITY_POINTER_RESTORED {directory} {commit}")
