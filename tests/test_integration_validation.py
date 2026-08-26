"""Real-parent validation folds acceptance (plan Task 10).

Invoked explicitly: ``uv run pytest -m integration``. Publishes the walk-forward
validation folds from the REAL verified January 2024 1h research parent through
the CLI entry point:
- Proves exact design §4 numbers on N=744: 5 folds, excluded 360, test coverage 384,
  last test length 96.
- Proves lineage binding to the real research parent commit.
- Proves idempotent rerun yields byte-identical pointer and single retained commit.
- Proves parent tree digest is unchanged across invocations (parent immutability).
- Proves undersized parent (1d) is structurally BLOCKED (exit code 2).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from quantara.cli import main

pytestmark = [pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"

VALIDATION_DESCRIPTOR = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-01-validation-wf-v1.yaml"
)


def _research_dir() -> Path:
    return (
        DATA_ROOT
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _validation_dir() -> Path:
    return (
        DATA_ROOT
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _tree_digest(directory: Path) -> dict[str, str]:
    snapshot = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        if path.is_file():
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            snapshot[rel] = "<dir>"
    return snapshot


def _require_research_parent() -> Path:
    parent = _research_dir()
    pointer = parent / "current.json"
    if not pointer.exists():
        raise AssertionError(f"retained research parent artifacts missing: {pointer}")
    return parent


def test_real_parent_validation_acceptance() -> None:
    parent = _require_research_parent()
    baseline = _tree_digest(parent)

    # 1. Publish validation folds through the CLI entry point
    exit_code = main(["--descriptor", str(VALIDATION_DESCRIPTOR), "--data-root", str(DATA_ROOT)])
    assert exit_code == 0

    dataset_dir = _validation_dir()
    pointer_path = dataset_dir / "current.json"
    first_pointer = pointer_path.read_bytes()
    commit = json.loads(first_pointer)["commit"]

    content = json.loads((dataset_dir / "commits" / commit / "content.json").read_text())
    manifest = json.loads((dataset_dir / "commits" / commit / "manifest.json").read_text())
    quality = json.loads((dataset_dir / "commits" / commit / "quality.json").read_text())

    # Lineage binds to parent research table
    parent_pointer = json.loads((parent / "current.json").read_text())
    lineage = content["validation_from"]
    assert lineage["parent_commit_address"] == parent_pointer["commit"]
    assert lineage["fold_set_name"] == "btcusdt_core_v1_wf72_v1"
    assert lineage["scheme"] == "anchored_walkforward_v1"
    assert lineage["parameters"] == {"test_size": 72, "min_train_size": 336}
    assert lineage["embargo"] == 24

    # Quality state PASS
    assert quality["state"] == "PASS"
    assert manifest["quality_state"] == "PASS"
    assert manifest["parent_row_count"] == 744
    assert manifest["fold_count"] == 5

    # CAS analytical object verification
    stored_sha = manifest["artifact_sha256"]
    artifact_path = DATA_ROOT / "objects" / "normalized" / "sha256" / stored_sha
    assert artifact_path.exists()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    # Design §4 exact acceptance numbers
    assert artifact["schema"] == "quantara.validation_folds/v1"
    assert artifact["parent_rows"] == 744
    assert artifact["excluded_head_rows"] == 360
    assert len(artifact["folds"]) == 5

    expected_test_ranges = [
        [360, 432],
        [432, 504],
        [504, 576],
        [576, 648],
        [648, 744],
    ]
    actual_test_ranges = [f["test_range"] for f in artifact["folds"]]
    assert actual_test_ranges == expected_test_ranges

    test_lengths = [f["test_range"][1] - f["test_range"][0] for f in artifact["folds"]]
    assert test_lengths == [72, 72, 72, 72, 96]  # last test length 96!

    # Coverage accounting (truthful aggregates; design amendment 2026-08-26)
    assert artifact["coverage"] == {
        "total_rows": 744,
        "fold_count": 5,
        "test_rows": 384,
    }
    assert artifact["excluded_head_rows"] == 360

    # Fold 4 structural nulls check
    fold_4_stats = artifact["folds"][4]["stats"]
    assert fold_4_stats["null_counts"]["l_fwdret_24"] == 24
    assert fold_4_stats["null_counts"]["l_fwddir_24"] == 24
    for f_idx in range(4):
        f_stats = artifact["folds"][f_idx]["stats"]
        assert f_stats["null_counts"]["l_fwdret_24"] == 0
        assert f_stats["null_counts"]["l_fwddir_24"] == 0

    # 2. Idempotent rerun: byte-identical pointer, no additional retained commit
    # (commit-count equality, not == 1: the immutable store legitimately retains
    # older validation commits across content-schema evolutions)
    commits_dir = dataset_dir / "commits"
    commits_after_first = sorted(p.name for p in commits_dir.iterdir())
    second = main(["--descriptor", str(VALIDATION_DESCRIPTOR), "--data-root", str(DATA_ROOT)])
    assert second == 0
    assert pointer_path.read_bytes() == first_pointer
    assert sorted(p.name for p in commits_dir.iterdir()) == commits_after_first

    # 3. Parent immutability across both invocations
    assert _tree_digest(parent) == baseline


def test_undersized_parent_is_structurally_blocked() -> None:
    _require_research_parent()
    with tempfile.TemporaryDirectory() as tmp:
        variant = Path(tmp) / "daily-validation.yaml"
        # Points to daily research parent (31 rows < 432)
        variant.write_text(
            """\
schema: quantara.validation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1d_2024_01_validation_wf_v1
dataset_type: validation_folds
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
parent_dataset_id: binance_usdm_btcusdt_klines_1d_2024_01_research_core_v1
parent_descriptor: configs/datasets/binance-usdm-btcusdt-1d-2024-01-research-core-v1.yaml
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
fold_set:
  name: btcusdt_core_v1_wf72_v1
  version: "1"
scheme: anchored_walkforward_v1
parameters:
  test_size: 72
  min_train_size: 336
schema_version: quantara_validation_folds_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
""",
            encoding="utf-8",
        )
        code = main(["--descriptor", str(variant), "--data-root", str(DATA_ROOT)])
        assert code == 2
