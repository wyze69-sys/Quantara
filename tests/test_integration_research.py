"""Real-parent research acceptance (plan Task 10).

Invoked explicitly: ``uv run pytest -m integration``. Publishes the research
table from the REAL verified January 2024 1h parent through the CLI entry
point, proves exact row/null-budget numbers and lineage binding to frozen
commit ``702dab9f…``, proves idempotent reruns byte-identical, proves parent
immutability, and proves the 31-bar 1d base is structurally BLOCKED.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from quantara.cli import main

pytestmark = [pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
PARENT_COMMIT_PREFIX = "702dab9f"
EXPECTED_ROWS = 744
NULL_BUDGETS = {
    "f_ret_1": 1,
    "f_roc_60": 60,
    "f_rvol_20": 20,
    "f_volratio_20": 19,
    "l_fwdret_24": 24,
    "l_fwddir_24": 24,
}
DESCRIPTOR = (
    REPO_ROOT / "configs" / "datasets" / "binance-usdm-btcusdt-1h-2024-01-research-core-v1.yaml"
)


def _parent_dir() -> Path:
    return (
        DATA_ROOT
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
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


def _tree_digest(directory: Path) -> dict[str, str]:
    snapshot = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        snapshot[rel] = path.read_bytes().hex() if path.is_file() else "<dir>"
    return snapshot


def _require_parent() -> Path:
    parent = _parent_dir()
    pointer = parent / "current.json"
    if not pointer.exists():  # fail loudly, never skip
        raise AssertionError(f"retained parent artifacts missing: {pointer}")
    commit = json.loads(pointer.read_text())["commit"]
    assert commit.startswith(PARENT_COMMIT_PREFIX), (
        f"parent commit {commit} does not match frozen lineage prefix"
    )
    return parent


def test_real_parent_research_acceptance() -> None:
    parent = _require_parent()
    baseline = _tree_digest(parent)

    # Publish the research table through the CLI entry point.
    exit_code = main(["--descriptor", str(DESCRIPTOR), "--data-root", str(DATA_ROOT)])
    assert exit_code == 0

    dataset_dir = _research_dir()
    pointer_path = dataset_dir / "current.json"
    first_pointer = pointer_path.read_bytes()
    commit = json.loads(first_pointer)["commit"]
    content = json.loads((dataset_dir / "commits" / commit / "content.json").read_text())
    manifest = json.loads((dataset_dir / "commits" / commit / "manifest.json").read_text())

    # Lineage binds to the frozen real parent commit.
    parent_pointer = json.loads((parent / "current.json").read_text())
    lineage = content["research_from"]
    assert lineage["base_dataset_id"] == "binance_usdm_btcusdt_klines_1h_2024_01"
    assert lineage["base_commit_address"] == parent_pointer["commit"]
    assert lineage["base_commit_address"].startswith(PARENT_COMMIT_PREFIX)

    # Exact row count and designed null budgets from the published Parquet.
    from quantara.research_pipeline import read_research_rows

    object_path = DATA_ROOT / "objects" / "normalized" / "sha256" / manifest["parquet_sha256"]
    rows = read_research_rows(object_path)
    assert len(rows) == EXPECTED_ROWS == manifest["canonical_row_count"]
    names = [
        "f_ret_1",
        "f_roc_60",
        "f_rvol_20",
        "f_volratio_20",
        "l_fwdret_24",
        "l_fwddir_24",
    ]
    null_counts = {
        name: sum(1 for row in rows if row[i + 1] is None) for i, name in enumerate(names)
    }
    print(f"[research] rows={len(rows)} null_budgets={null_counts}")
    assert null_counts == NULL_BUDGETS
    assert manifest["designed_null_budgets"] == NULL_BUDGETS
    assert manifest["quality_state"] == "PASS"

    # Idempotent rerun: byte-identical pointer, single commit.
    second = main(["--descriptor", str(DESCRIPTOR), "--data-root", str(DATA_ROOT)])
    assert second == 0
    assert pointer_path.read_bytes() == first_pointer
    commits = [p for p in (dataset_dir / "commits").iterdir()]
    assert len(commits) == 1

    # Parent immutability across both invocations.
    assert _tree_digest(parent) == baseline


def test_daily_base_is_structurally_blocked() -> None:
    _require_parent()
    with tempfile.TemporaryDirectory() as tmp:
        variant = Path(tmp) / "daily-research.yaml"
        base_reference = (
            REPO_ROOT / "configs" / "datasets" / "binance-usdm-btcusdt-1d-2024-01-derived.yaml"
        ).resolve()
        variant.write_text(
            f"""\
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1d_2024_01_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1d_2024_01
base_descriptor: {base_reference.as_posix()}
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-02-01T00:00:00Z"
feature_set:
  name: btcusdt_core_v1
  version: "1"
parameters:
  roc_window: 60
  vol_window: 20
  volume_window: 20
  label_horizon: 24
schema_version: quantara_research_featureset_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
""",
            encoding="utf-8",
        )
        code = main(["--descriptor", str(variant), "--data-root", str(DATA_ROOT)])
        assert code == 2
