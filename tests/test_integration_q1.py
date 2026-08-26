"""Real Q1 range-chain acceptance for data slice 005.

Serial and networked by construction: one test drives the complete CLI chain,
checks every pinned acceptance number, proves idempotent reruns, and restores
the pre-test January discovery pointers so predecessor integration modules keep
their frozen-current assumptions. Published Q1 commits remain retained.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.research_pipeline import read_research_rows

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = REPO_ROOT / "configs" / "datasets"

DESCRIPTORS = {
    "base": CONFIG_ROOT / "binance-usdm-btcusdt-1m-2024-q1.yaml",
    "derived_1h": CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-derived.yaml",
    "derived_1d": CONFIG_ROOT / "binance-usdm-btcusdt-1d-2024-q1-derived.yaml",
    "research": (
        CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-research-core-v1.yaml"
    ),
    "validation": (
        CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-q1-validation-wf-v1.yaml"
    ),
}


def _dataset_dir(layer: str, interval: str) -> Path:
    category = "klines" if layer == "klines" else layer
    return (
        DATA_ROOT
        / "datasets"
        / "binance"
        / "usdm"
        / category
        / "BTCUSDT"
        / interval
        / "year=2024"
        / "month=01"
    )


LAYER_DIRS = {
    "base": _dataset_dir("klines", "1m"),
    "derived_1h": _dataset_dir("klines", "1h"),
    "derived_1d": _dataset_dir("klines", "1d"),
    "research": _dataset_dir("research", "1h"),
    "validation": _dataset_dir("validation", "1h"),
}

ATTEMPT_DIRS = {
    "base": DATA_ROOT / "attempts",
    "derived_1h": DATA_ROOT / "attempts",
    "derived_1d": DATA_ROOT / "attempts",
    "research": DATA_ROOT / "attempts",
    "validation": DATA_ROOT / "attempts" / "validation",
}


def _pointer_bytes(directory: Path) -> bytes:
    return (directory / "current.json").read_bytes()


def _commit(directory: Path) -> str:
    return json.loads(_pointer_bytes(directory))["commit"]


def _commit_dir(directory: Path) -> Path:
    return directory / "commits" / _commit(directory)


def _manifest(directory: Path) -> dict:
    return json.loads(
        (_commit_dir(directory) / "manifest.json").read_text(encoding="utf-8")
    )


def _quality(directory: Path) -> dict:
    return json.loads(
        (_commit_dir(directory) / "quality.json").read_text(encoding="utf-8")
    )


def _tree_digest(directory: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _attempt_files(directory: Path) -> set[Path]:
    return set(directory.glob("*.json")) if directory.exists() else set()


def _assert_new_no_op(directory: Path, before: set[Path]) -> None:
    new_files = _attempt_files(directory) - before
    assert new_files, f"no attempt manifest appeared under {directory}"
    results = {
        json.loads(path.read_text(encoding="utf-8"))["terminal_result"]
        for path in new_files
    }
    assert results == {"VERIFIED_NO_OP"}


def _restore_pointer(directory: Path, payload: bytes) -> None:
    pointer = directory / "current.json"
    temporary = pointer.with_name("current.restore.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, pointer)


def _run_cli(descriptor: Path) -> int:
    return main(
        ["--descriptor", str(descriptor), "--data-root", str(DATA_ROOT)]
    )


def _assert_undersized_daily_validation_blocks() -> None:
    base = DESCRIPTORS["derived_1d"].resolve().as_posix()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        research = temporary / "q1-daily-research.yaml"
        validation = temporary / "q1-daily-validation.yaml"
        research.write_text(
            f"""\
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1d_2024_q1_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1d_2024_q1
base_descriptor: {base}
period: {{ start: "2024-01-01T00:00:00Z", end: "2024-04-01T00:00:00Z" }}
feature_set: {{ name: btcusdt_core_v1, version: "1" }}
parameters: {{ roc_window: 60, vol_window: 20, volume_window: 20, label_horizon: 24 }}
schema_version: quantara_research_featureset_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
""",
            encoding="utf-8",
        )
        validation.write_text(
            f"""\
schema: quantara.validation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1d_2024_q1_validation_wf_v1
dataset_type: validation_folds
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1d_2024_q1
parent_descriptor: {research.resolve().as_posix()}
period: {{ start: "2024-01-01T00:00:00Z", end: "2024-04-01T00:00:00Z" }}
feature_set: {{ name: btcusdt_core_v1, version: "1" }}
scheme: anchored_walkforward_v1
fold_set: {{ name: btcusdt_core_v1_wf72_v1, version: "1" }}
parameters: {{ test_size: 72, min_train_size: 336 }}
schema_version: quantara_validation_folds_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
""",
            encoding="utf-8",
        )
        assert _run_cli(validation) == 2


def test_real_q1_chain_acceptance_and_idempotency() -> None:
    january_pointers = {
        name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()
    }
    january_commits = {
        name: _commit_dir(directory) for name, directory in LAYER_DIRS.items()
    }
    january_digests = {
        name: _tree_digest(directory) for name, directory in january_commits.items()
    }
    for name, directory in LAYER_DIRS.items():
        assert "2024_01" in _manifest(directory)["dataset_id"], name

    try:
        for name in ("base", "derived_1h", "derived_1d", "research", "validation"):
            assert _run_cli(DESCRIPTORS[name]) == 0

        base_manifest = _manifest(LAYER_DIRS["base"])
        assert base_manifest["dataset_id"].endswith("_1m_2024_q1")
        assert base_manifest["source_row_count"] == 131_040
        assert base_manifest["canonical_row_count"] == 131_040
        assert len(base_manifest["archive_url"]) == 3
        assert _quality(LAYER_DIRS["base"])["state"] == "PASS"

        hourly_manifest = _manifest(LAYER_DIRS["derived_1h"])
        daily_manifest = _manifest(LAYER_DIRS["derived_1d"])
        assert hourly_manifest["canonical_row_count"] == 2_184
        assert daily_manifest["canonical_row_count"] == 91
        assert _quality(LAYER_DIRS["derived_1h"])["state"] == "PASS"
        assert _quality(LAYER_DIRS["derived_1d"])["state"] == "PASS"

        research_manifest = _manifest(LAYER_DIRS["research"])
        research_object = (
            DATA_ROOT
            / "objects"
            / "normalized"
            / "sha256"
            / research_manifest["parquet_sha256"]
        )
        research_rows = read_research_rows(research_object)
        names = (
            "f_ret_1",
            "f_roc_60",
            "f_rvol_20",
            "f_volratio_20",
            "l_fwdret_24",
            "l_fwddir_24",
        )
        null_counts = {
            name: sum(1 for row in research_rows if row[index + 1] is None)
            for index, name in enumerate(names)
        }
        expected_nulls = {
            "f_ret_1": 1,
            "f_roc_60": 60,
            "f_rvol_20": 20,
            "f_volratio_20": 19,
            "l_fwdret_24": 24,
            "l_fwddir_24": 24,
        }
        assert len(research_rows) == 2_184
        assert null_counts == expected_nulls
        assert research_manifest["designed_null_budgets"] == expected_nulls
        assert _quality(LAYER_DIRS["research"])["state"] == "PASS"

        validation_manifest = _manifest(LAYER_DIRS["validation"])
        validation_object = (
            DATA_ROOT
            / "objects"
            / "normalized"
            / "sha256"
            / validation_manifest["artifact_sha256"]
        )
        artifact = json.loads(validation_object.read_text(encoding="utf-8"))
        test_lengths = [
            fold["test_range"][1] - fold["test_range"][0]
            for fold in artifact["folds"]
        ]
        assert artifact["parent_rows"] == 2_184
        assert artifact["excluded_head_rows"] == 360
        assert artifact["folds"][0]["test_range"][0] == 360
        assert len(artifact["folds"]) == 25
        assert test_lengths == [72] * 24 + [96]
        assert artifact["coverage"] == {
            "total_rows": 2_184,
            "fold_count": 25,
            "test_rows": 1_824,
        }
        assert _quality(LAYER_DIRS["validation"])["state"] == "PASS"

        _assert_undersized_daily_validation_blocks()

        q1_pointers = {
            name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()
        }
        q1_digests = {
            name: _tree_digest(_commit_dir(directory))
            for name, directory in LAYER_DIRS.items()
        }
        for name in ("base", "derived_1h", "derived_1d", "research", "validation"):
            before_attempts = _attempt_files(ATTEMPT_DIRS[name])
            assert _run_cli(DESCRIPTORS[name]) == 0
            assert _pointer_bytes(LAYER_DIRS[name]) == q1_pointers[name]
            assert _tree_digest(_commit_dir(LAYER_DIRS[name])) == q1_digests[name]
            _assert_new_no_op(ATTEMPT_DIRS[name], before_attempts)

        print(
            "Q1_ACCEPTANCE "
            "canonical=131040 derived_1h=2184 derived_1d=91 "
            "research=2184 folds=25 test_rows=1824 excluded_head_rows=360"
        )
        print(f"Q1_RESEARCH_NULL_BUDGETS {null_counts}")
        print("Q1_RERUNS VERIFIED_NO_OP layers=5")
    finally:
        for name, directory in LAYER_DIRS.items():
            _restore_pointer(directory, january_pointers[name])

    assert {
        name: _tree_digest(directory) for name, directory in january_commits.items()
    } == january_digests
    assert {
        name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()
    } == january_pointers
    print(f"JANUARY_V1_COMMIT_DIGESTS_UNCHANGED {january_digests}")
