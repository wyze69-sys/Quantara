"""Real full-year 2024 range-chain acceptance for data slice 010.

Serial and networked by construction: one test drives the complete CLI chain,
checks the frozen year acceptance contracts, proves idempotent reruns, and
restores all pre-test discovery pointers. January and Q1 immutable commits stay
retained and byte-identical; newly published year commits intentionally remain
retained after the test.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from quantara.cli import main
from quantara.jcs import canonicalize
from quantara.research_pipeline import read_research_rows

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = REPO_ROOT / "configs" / "datasets"

YEAR_SCHEMA_FINGERPRINT = "f0d6a8dd92a1a4f1dcf29c4f9222c4ec7daa75a2e648ead6b4bfa453d347724a"

DESCRIPTORS = {
    "base": CONFIG_ROOT / "binance-usdm-btcusdt-1m-2024.yaml",
    "derived_1h": CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-derived.yaml",
    "derived_1d": CONFIG_ROOT / "binance-usdm-btcusdt-1d-2024-derived.yaml",
    "research": CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-research-core-v1.yaml",
    "validation": CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml",
    "evaluation": CONFIG_ROOT / "binance-usdm-btcusdt-1h-2024-evaluation-dual-ic-v1.yaml",
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
    "evaluation": _dataset_dir("evaluation", "1h"),
}

ATTEMPT_DIRS = {
    "base": DATA_ROOT / "attempts",
    "derived_1h": DATA_ROOT / "attempts",
    "derived_1d": DATA_ROOT / "attempts",
    "research": DATA_ROOT / "attempts",
    "validation": DATA_ROOT / "attempts" / "validation",
    "evaluation": DATA_ROOT / "attempts" / "evaluation",
}


def _pointer_bytes(directory: Path) -> bytes:
    return (directory / "current.json").read_bytes()


def _commit(directory: Path) -> str:
    return json.loads(_pointer_bytes(directory))["commit"]


def _commit_dir(directory: Path) -> Path:
    return directory / "commits" / _commit(directory)


def _manifest(directory: Path) -> dict:
    return json.loads((_commit_dir(directory) / "manifest.json").read_text(encoding="utf-8"))


def _quality(directory: Path) -> dict:
    return json.loads((_commit_dir(directory) / "quality.json").read_text(encoding="utf-8"))


def _tree_digest(directory: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in directory.rglob("*") if item.is_file()):
        hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _retained_commit_digests(directory: Path) -> dict[str, str]:
    commits_dir = directory / "commits"
    return {
        commit_dir.name: _tree_digest(commit_dir)
        for commit_dir in sorted(commits_dir.iterdir())
        if commit_dir.is_dir() and not commit_dir.name.startswith(".")
    }


def _attempt_files(directory: Path) -> set[Path]:
    return set(directory.glob("*.json")) if directory.exists() else set()


def _assert_new_no_op(directory: Path, before: set[Path]) -> None:
    new_files = _attempt_files(directory) - before
    assert new_files, f"no attempt manifest appeared under {directory}"
    assert {
        json.loads(path.read_text(encoding="utf-8"))["terminal_result"] for path in new_files
    } == {"VERIFIED_NO_OP"}


def _restore_pointer(directory: Path, payload: bytes) -> None:
    pointer = directory / "current.json"
    temporary = pointer.with_name("current.restore.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, pointer)


def _run_cli(descriptor: Path) -> int:
    return main(["--descriptor", str(descriptor), "--data-root", str(DATA_ROOT)])


def _assert_undersized_daily_validation_blocks() -> None:
    derived = DESCRIPTORS["derived_1d"].resolve().as_posix()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        research = temporary / "year-daily-research.yaml"
        validation = temporary / "year-daily-validation.yaml"
        research.write_text(
            f"""\
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1d_2024_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1d_2024
base_descriptor: {derived}
period: {{ start: "2024-01-01T00:00:00Z", end: "2025-01-01T00:00:00Z" }}
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
dataset_id: binance_usdm_btcusdt_klines_1d_2024_validation_wf_v1
dataset_type: validation_folds
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1d_2024
parent_descriptor: {research.resolve().as_posix()}
period: {{ start: "2024-01-01T00:00:00Z", end: "2025-01-01T00:00:00Z" }}
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


def test_real_year_chain_acceptance_and_idempotency() -> None:
    pre_test_pointers = {name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()}
    predecessor_commits = {
        name: _retained_commit_digests(directory) for name, directory in LAYER_DIRS.items()
    }
    for name, directory in LAYER_DIRS.items():
        predecessor_dataset_id = _manifest(directory)["dataset_id"]
        assert "_2024_01" in predecessor_dataset_id or "_2024_q1" in predecessor_dataset_id, name

    try:
        for name in ("base", "derived_1h", "derived_1d", "research", "validation", "evaluation"):
            assert _run_cli(DESCRIPTORS[name]) == 0

        base_manifest = _manifest(LAYER_DIRS["base"])
        assert base_manifest["dataset_id"].endswith("_1m_2024")
        assert base_manifest["source_row_count"] == 527_040
        assert base_manifest["canonical_row_count"] == 527_040
        assert len(base_manifest["archive_url"]) == 12
        assert base_manifest["schema_fingerprint"] == YEAR_SCHEMA_FINGERPRINT
        assert (
            base_manifest["canonical_content_hash"]
            == "28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5"
        )
        assert base_manifest["quality_policy_version"] == "2"
        assert base_manifest["quality_state"] == "WARN_APPROVED"
        assert base_manifest["quality_raw_state"] == "WARN_BLOCKED"
        assert (
            base_manifest["quality_approval_record_id"]
            == "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
        )
        assert (
            base_manifest["quality_approval_record_sha256"]
            == "83cdcf816a9e2a5d36e6446acab713ebaa934567be8dfe5524b632e9327da580"
        )

        base_quality = _quality(LAYER_DIRS["base"])
        assert base_quality["state"] == "WARN_APPROVED"
        assert base_quality["raw_state"] == "WARN_BLOCKED"
        assert base_quality["policy_version"] == "2"
        assert (
            base_quality["approval_record_id"]
            == "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
        )
        assert (
            base_quality["approval_record_sha256"]
            == "83cdcf816a9e2a5d36e6446acab713ebaa934567be8dfe5524b632e9327da580"
        )
        assert (
            base_quality["identity_sha256"]
            == "10e100b458244a3d496666afaf37ef1518da15e8d8503d463abc632eccf343b8"
        )
        warn_findings = [f for f in base_quality["findings"] if f["outcome"] != "pass"]
        assert len(warn_findings) == 1
        assert warn_findings[0]["check_id"] == "zero_volume_candle"
        assert warn_findings[0]["count"] == 89
        assert warn_findings[0]["outcome"] == "warn"
        assert warn_findings[0]["severity"] == "warning"
        pass_findings = [f for f in base_quality["findings"] if f["outcome"] == "pass"]
        assert len(pass_findings) == 14

        approval_bytes = (
            _commit_dir(LAYER_DIRS["base"]) / "quality-approval.json"
        ).read_bytes()
        approval_doc = json.loads(approval_bytes.decode("utf-8"))
        assert approval_doc["record_id"] == "binance-usdm-btcusdt-1m-2024-zero-volume-v1"
        assert (
            approval_doc["canonical_content_hash"]
            == "28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5"
        )

        hourly_manifest = _manifest(LAYER_DIRS["derived_1h"])
        daily_manifest = _manifest(LAYER_DIRS["derived_1d"])
        assert hourly_manifest["canonical_row_count"] == 8_784
        assert daily_manifest["canonical_row_count"] == 366
        assert hourly_manifest["quality_policy_version"] == "2"
        assert hourly_manifest["quality_state"] == "WARN_APPROVED"
        assert hourly_manifest["quality_raw_state"] == "WARN_BLOCKED"
        assert (
            hourly_manifest["canonical_content_hash"]
            == "9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e"
        )
        assert (
            hourly_manifest["quality_identity_sha256"]
            == "14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20"
        )
        assert (
            hourly_manifest["quality_approval_record_id"]
            == "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
        )
        assert (
            hourly_manifest["quality_approval_record_sha256"]
            == "b394ec101cb69293c39af2028a0995029f50599a9413604ab0834c8921433878"
        )

        hourly_quality = _quality(LAYER_DIRS["derived_1h"])
        assert hourly_quality["state"] == "WARN_APPROVED"
        assert hourly_quality["raw_state"] == "WARN_BLOCKED"
        assert hourly_quality["policy_version"] == "2"
        assert (
            hourly_quality["identity_sha256"]
            == "14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20"
        )
        assert (
            hourly_quality["approval_record_id"]
            == "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
        )
        assert (
            hourly_quality["approval_record_sha256"]
            == "b394ec101cb69293c39af2028a0995029f50599a9413604ab0834c8921433878"
        )
        hourly_warn_findings = [
            finding
            for finding in hourly_quality["findings"]
            if finding["outcome"] == "warn"
        ]
        assert hourly_warn_findings == [
            {
                "check_id": "derived_zero_volume_bucket",
                "outcome": "warn",
                "severity": "warning",
                "count": 1,
                "evidence": {"occurrences": 1},
            }
        ]
        assert len(
            [
                finding
                for finding in hourly_quality["findings"]
                if finding["outcome"] == "pass"
            ]
        ) == 12

        hourly_approval = json.loads(
            (
                _commit_dir(LAYER_DIRS["derived_1h"])
                / "quality-approval.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            hourly_approval["record_id"]
            == "binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1"
        )
        assert (
            hourly_approval["canonical_content_hash"]
            == "9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e"
        )
        assert (
            hashlib.sha256(canonicalize(hourly_approval).encode("utf-8")).hexdigest()
            == "b394ec101cb69293c39af2028a0995029f50599a9413604ab0834c8921433878"
        )
        assert _quality(LAYER_DIRS["derived_1d"])["state"] == "PASS"

        research_manifest = _manifest(LAYER_DIRS["research"])
        research_object = (
            DATA_ROOT / "objects" / "normalized" / "sha256" / research_manifest["parquet_sha256"]
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
        assert len(research_rows) == 8_784
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
        validation_artifact = json.loads(validation_object.read_text(encoding="utf-8"))
        assert validation_artifact["parent_rows"] == 8_784
        assert validation_artifact["excluded_head_rows"] == 360
        assert validation_artifact["folds"][0]["test_range"][0] == 360
        assert len(validation_artifact["folds"]) == 117
        assert validation_artifact["folds"][-1]["test_range"] == [8_712, 8_784]
        assert validation_artifact["coverage"] == {
            "total_rows": 8_784,
            "fold_count": 117,
            "test_rows": 8_424,
        }
        assert _quality(LAYER_DIRS["validation"])["state"] == "PASS"

        evaluation_manifest = _manifest(LAYER_DIRS["evaluation"])
        evaluation_object = (
            DATA_ROOT
            / "objects"
            / "normalized"
            / "sha256"
            / evaluation_manifest["artifact_sha256"]
        )
        evaluation_artifact = json.loads(evaluation_object.read_text(encoding="utf-8"))
        assert (
            evaluation_artifact["validation_parent"]["dataset_id"]
            == validation_manifest["dataset_id"]
        )
        assert (
            evaluation_artifact["research_parent"]["dataset_id"]
            == research_manifest["dataset_id"]
        )
        assert evaluation_artifact["metrics"] == ["pearson_ic", "spearman_ic"]
        assert len(evaluation_artifact["records"]) == 4 * 117
        assert {record["fold_id"] for record in evaluation_artifact["records"]} == set(
            range(117)
        )
        assert all(
            {"pearson_ic", "spearman_ic"} <= set(record)
            for record in evaluation_artifact["records"]
        )
        assert _quality(LAYER_DIRS["evaluation"])["state"] == "PASS"

        _assert_undersized_daily_validation_blocks()

        year_pointers = {name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()}
        year_commits = {
            name: _retained_commit_digests(directory) for name, directory in LAYER_DIRS.items()
        }
        for name in ("base", "derived_1h", "derived_1d", "research", "validation", "evaluation"):
            before_attempts = _attempt_files(ATTEMPT_DIRS[name])
            assert _run_cli(DESCRIPTORS[name]) == 0
            assert _pointer_bytes(LAYER_DIRS[name]) == year_pointers[name]
            assert _retained_commit_digests(LAYER_DIRS[name]) == year_commits[name]
            _assert_new_no_op(ATTEMPT_DIRS[name], before_attempts)

        print(
            "YEAR_ACCEPTANCE canonical=527040 derived_1h=8784 derived_1d=366 "
            "research=8784 folds=117 test_rows=8424 excluded_head_rows=360 "
            "last_test=(8712,8784)"
        )
        print(f"YEAR_SCHEMA_FINGERPRINT {base_manifest['schema_fingerprint']}")
        print(f"YEAR_RESEARCH_NULL_BUDGETS {null_counts}")
        print("YEAR_1D_VALIDATION BLOCKED undersized=366<432")
        print("YEAR_RERUNS VERIFIED_NO_OP layers=6")
    finally:
        for name, directory in LAYER_DIRS.items():
            _restore_pointer(directory, pre_test_pointers[name])

    for name, expected_digests in predecessor_commits.items():
        retained = _retained_commit_digests(LAYER_DIRS[name])
        assert {commit: retained[commit] for commit in expected_digests} == expected_digests
    assert {
        name: _pointer_bytes(directory) for name, directory in LAYER_DIRS.items()
    } == pre_test_pointers
    print(f"JANUARY_Q1_COMMIT_DIGESTS_UNCHANGED {predecessor_commits}")
