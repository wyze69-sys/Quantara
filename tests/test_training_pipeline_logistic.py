"""Dual-path logistic training pipeline tests for slice 012.

Both branches are asserted: a clean pre-registered kill-criteria pass publishes
with a pointer move and an idempotent ``VERIFIED_NO_OP`` rerun, and a failing
criterion exits 4 with a ``KILL_CRITERIA_FAILED`` attempt manifest, no staged
commit, and a byte-unchanged lane pointer.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from conftest import (
    LOGISTIC_KILL_CRITERIA_IMPOSSIBLE,
    rights_v2_yaml_dict,
    write_training_descriptor,
    write_training_descriptor_logistic,
)
from quantara.hashing import (
    quality_identity,
    research_content_hash,
    research_schema_fingerprint,
    sha256_hex,
    validation_content_hash,
    validation_schema_fingerprint,
)
from quantara.jcs import canonicalize
from quantara.publication import stage_commit, store_object, write_current
from quantara.research_pipeline import (
    render_content_rows,
    research_commit_identity,
    write_research_parquet,
)
from quantara.training_pipeline import (
    EXIT_BLOCKED,
    EXIT_KILL_CRITERIA_FAILED,
    EXIT_OK,
    KILL_CRITERIA_FAILED,
    run_training_pipeline,
    verify_training_current_graph,
)
from quantara.training_quality import LOGISTIC_ARTIFACT_SCHEMA, LOGISTIC_CHECK_IDS
from quantara.validation_pipeline import validation_commit_identity

Q1_ROWS = 2184
Q1_FOLDS = 25


def _separable_rows() -> list[tuple]:
    """Synthetic Q1 rows with a learnable direction signal in f_ret_1.

    The kill criteria are pre-registered constants, so a PASS-path fixture has
    to actually clear them; the failing branch is driven by an impossible
    threshold in a variant descriptor, never by weakening the real constants.
    """
    rows = []
    for index in range(Q1_ROWS):
        direction = 1 if (index % 7) in (0, 1, 2, 3) else -1
        base = Decimal((index % 17) - 8) / Decimal(10)
        feature = base + (Decimal("0.6") if direction == 1 else Decimal("-0.6"))
        open_time = 1704067200000 + index * 3600000
        if index >= Q1_ROWS - 24:
            rows.append(
                (
                    open_time,
                    feature,
                    Decimal((index * 7 % 23) - 11),
                    Decimal((index % 30) + 1) / Decimal(100),
                    Decimal((index % 20) + 1) / Decimal(20),
                    None,
                    None,
                )
            )
        else:
            rows.append(
                (
                    open_time,
                    feature,
                    Decimal((index * 7 % 23) - 11),
                    Decimal((index % 30) + 1) / Decimal(100),
                    Decimal((index % 20) + 1) / Decimal(20),
                    Decimal(direction) * Decimal((index % 13) + 1) / Decimal(100),
                    direction,
                )
            )
    return rows


def _folds() -> list[dict]:
    folds = []
    start = 360
    for fold_id in range(Q1_FOLDS):
        end = start + (96 if fold_id == Q1_FOLDS - 1 else 72)
        folds.append(
            {
                "fold_id": fold_id,
                "train_range": [0, start - 24],
                "embargo_range": [start - 24, start],
                "test_range": [start, end],
            }
        )
        start = end
    return folds


def _lane_dir(data_root: Path, lane: str) -> Path:
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / lane
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )


def _publish(dataset_dir: Path, attempt: str, commit: str, files: dict[str, bytes]) -> None:
    staged = stage_commit(dataset_dir, attempt, files)
    commit_dir = dataset_dir / "commits" / commit
    commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(commit_dir)
    (commit_dir / "COMMITTED").touch()
    write_current(dataset_dir, commit, sha256_hex(files["manifest.json"]))


def _json_files(manifest: dict, content: dict, quality: dict) -> dict[str, bytes]:
    return {
        "manifest.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        "content.json": (json.dumps(content, indent=2, sort_keys=True) + "\n").encode(),
        "quality.json": (json.dumps(quality, indent=2, sort_keys=True) + "\n").encode(),
    }


def _setup_chain(tmp_path: Path) -> tuple[Path, Path]:
    """Publish a separable offline Q1 research + walk-forward validation chain."""
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    shutil.copytree(Path("configs"), repo_root / "configs")

    rows = _separable_rows()
    parquet_path = tmp_path / "research.parquet"
    write_research_parquet(rows, parquet_path)
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = store_object(data_root, "normalized", parquet_bytes).sha256
    parquet_path.unlink()

    res_fp = research_schema_fingerprint("quantara_research_featureset_v1")
    res_cch = research_content_hash(res_fp, render_content_rows(rows))
    res_lineage = {
        "parent_dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1",
        "parent_commit_address": "0" * 64,
        "parent_canonical_content_hash": "1" * 64,
        "parent_zip_sha256": "2" * 64,
    }
    res_cid = research_commit_identity(res_cch, res_lineage)
    res_findings = [
        {
            "check_id": "row_count",
            "count": 0,
            "evidence": {"rows": Q1_ROWS},
            "outcome": "pass",
            "severity": "hard",
        }
    ]
    res_qid = quality_identity(res_findings)
    res_manifest = {
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1_research_core_v1",
        "schema_version": "quantara_research_featureset_v1",
        "schema_fingerprint": res_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": res_cch,
        "quality_identity": res_qid,
        "quality_state": "PASS",
        "quality_policy_version": "1",
        "commit_identity": res_cid,
        "parquet_sha256": parquet_sha,
        "parquet_size": len(parquet_bytes),
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
        "research_from": res_lineage,
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2024-04-01T00:00:00Z"},
    }
    res_content = {
        "schema_fingerprint": res_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": res_cch,
        "quality_identity": res_qid,
        "object_refs": [{"kind": "normalized", "sha256": parquet_sha}],
        "research_from": res_lineage,
        "research_commit_identity": res_cid,
    }
    res_quality = {
        "state": "PASS",
        "policy_version": "1",
        "identity": res_qid,
        "findings": res_findings,
    }
    _publish(
        _lane_dir(data_root, "research"),
        "logistic_res",
        res_cid,
        _json_files(res_manifest, res_content, res_quality),
    )

    folds = _folds()
    val_artifact = {
        "schema": "quantara.validation_folds/v1",
        "fold_set": "btcusdt_core_v1_wf72_v1",
        "scheme": "anchored_walkforward_v1",
        "parameters": {"test_size": 72, "min_train_size": 336, "embargo": 24},
        "parent_rows": Q1_ROWS,
        "excluded_head_rows": 360,
        "folds": folds,
        "coverage": {"total_rows": Q1_ROWS, "test_rows": 1824, "fold_count": Q1_FOLDS},
    }
    val_bytes = canonicalize(val_artifact).encode("utf-8") + b"\n"
    val_sha = store_object(data_root, "normalized", val_bytes).sha256
    val_fp = validation_schema_fingerprint(
        parent_fingerprint=res_fp,
        schema_id="quantara_validation_folds_v1",
        scheme="anchored_walkforward_v1",
        parameters={"test_size": 72, "min_train_size": 336, "embargo": 24},
        fold_set_name="btcusdt_core_v1_wf72_v1",
        fold_set_version="1",
    )
    val_cch = validation_content_hash(val_fp, val_bytes)
    val_lineage = {
        "parent_dataset_id": res_manifest["dataset_id"],
        "parent_commit_address": res_cid,
        "parent_canonical_content_hash": res_cch,
        "parent_parquet_sha256": parquet_sha,
        "parent_parquet_size": len(parquet_bytes),
    }
    val_cid = validation_commit_identity(val_cch, val_lineage)
    val_findings = [
        {
            "check_id": "fold_coverage",
            "count": 0,
            "evidence": {"folds": Q1_FOLDS},
            "outcome": "pass",
            "severity": "hard",
        }
    ]
    val_qid = quality_identity(val_findings)
    val_manifest = {
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1_validation_wf_v1",
        "schema_version": "quantara_validation_folds_v1",
        "schema_fingerprint": val_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": val_cch,
        "quality_identity": val_qid,
        "quality_state": "PASS",
        "quality_policy_version": "1",
        "commit_identity": val_cid,
        "artifact_sha256": val_sha,
        "artifact_size": len(val_bytes),
        "parent_rows": Q1_ROWS,
        "fold_count": Q1_FOLDS,
        "fold_set": {"name": "btcusdt_core_v1_wf72_v1", "version": "1"},
        "scheme": "anchored_walkforward_v1",
        "parameters": {"test_size": 72, "min_train_size": 336},
        "embargo": 24,
        "object_refs": [{"kind": "normalized", "sha256": val_sha}],
        "validation_from": val_lineage,
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2024-04-01T00:00:00Z"},
    }
    val_content = {
        "schema_fingerprint": val_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": val_cch,
        "quality_identity": val_qid,
        "object_refs": [{"kind": "normalized", "sha256": val_sha}],
        "validation_from": val_lineage,
        "validation_commit_identity": val_cid,
    }
    val_quality = {
        "state": "PASS",
        "policy_version": "1",
        "identity": val_qid,
        "findings": val_findings,
    }
    _publish(
        _lane_dir(data_root, "validation"),
        "logistic_val",
        val_cid,
        _json_files(val_manifest, val_content, val_quality),
    )
    return repo_root, data_root


def _setup(tmp_path: Path, kill_criteria: dict | None = None) -> tuple[Path, Path, Path]:
    """Chain plus a published ridge lane parent plus a logistic descriptor."""
    repo_root, data_root = _setup_chain(tmp_path)
    ridge_descriptor = write_training_descriptor(repo_root)
    assert run_training_pipeline(ridge_descriptor, data_root, repo_root=repo_root) == EXIT_OK
    logistic_descriptor = write_training_descriptor_logistic(
        repo_root, kill_criteria=kill_criteria
    )
    return repo_root, data_root, logistic_descriptor


def _attempts(data_root: Path) -> list[dict]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((data_root / "attempts" / "training").glob("*.json"))
    ]


def test_ridge_path_still_publishes_untouched(tmp_path: Path) -> None:
    repo_root, data_root = _setup_chain(tmp_path)
    ridge_descriptor = write_training_descriptor(repo_root)
    assert run_training_pipeline(ridge_descriptor, data_root, repo_root=repo_root) == EXIT_OK
    training_dir = _lane_dir(data_root, "training")
    graph = verify_training_current_graph(training_dir, data_root)
    assert graph["artifact_schema"] == "quantara.model_training/v1"
    assert graph["kill_criteria"] is None
    assert len(graph["records"]) == Q1_FOLDS
    pointer = (training_dir / "current.json").read_bytes()
    assert run_training_pipeline(ridge_descriptor, data_root, repo_root=repo_root) == EXIT_OK
    assert (training_dir / "current.json").read_bytes() == pointer
    assert _attempts(data_root)[-1]["terminal_result"] == "VERIFIED_NO_OP"


def test_logistic_pass_publishes_with_kill_evidence_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repo_root, data_root, descriptor = _setup(tmp_path)
    training_dir = _lane_dir(data_root, "training")
    ridge_pointer = json.loads((training_dir / "current.json").read_text(encoding="utf-8"))
    assert run_training_pipeline(descriptor, data_root, repo_root=repo_root) == EXIT_OK

    graph = verify_training_current_graph(training_dir, data_root)
    assert graph["commit"] != ridge_pointer["commit"]
    assert graph["artifact_schema"] == LOGISTIC_ARTIFACT_SCHEMA
    assert len(graph["records"]) == Q1_FOLDS
    assert graph["kill_criteria"]["all_passed"] is True
    assert graph["training_from"]["training_commit_address"] == ridge_pointer["commit"]

    commit_dir = training_dir / "commits" / graph["commit"]
    quality = json.loads((commit_dir / "quality.json").read_text(encoding="utf-8"))
    assert quality["state"] == "PASS"
    assert [item["check_id"] for item in quality["findings"]] == list(LOGISTIC_CHECK_IDS)
    manifest = json.loads((commit_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_id"].endswith("_training_logistic_v1")
    artifact = json.loads(
        (
            data_root / "objects" / "normalized" / "sha256" / manifest["artifact_sha256"]
        ).read_text(encoding="utf-8")
    )
    assert artifact["training_parent"]["commit_address"] == ridge_pointer["commit"]
    assert set(artifact["baselines"]) == {
        "majority_class_train_window",
        "sign_f_ret_1",
        "climatology_p",
    }
    assert artifact["kill_criteria"]["constants"] == {
        "directional_accuracy_min": "0.534900284900284900",
        "direction_ic_min": "0.020000000000000000",
        "log_loss_max": "0.762500000000000000",
        "brier_max": "0.250000000000000000",
    }
    assert artifact["kill_criteria"]["results"] == {
        "k1_directional_accuracy": True,
        "k2_direction_ic": True,
        "k3_log_loss": True,
        "k4_brier": True,
    }
    assert _attempts(data_root)[-1]["terminal_result"] == "PUBLISHED"

    pointer_before = (training_dir / "current.json").read_bytes()
    assert run_training_pipeline(descriptor, data_root, repo_root=repo_root) == EXIT_OK
    assert (training_dir / "current.json").read_bytes() == pointer_before
    assert _attempts(data_root)[-1]["terminal_result"] == "VERIFIED_NO_OP"


def test_logistic_kill_failure_exits_four_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quantara import training_descriptor

    monkeypatch.setitem(
        training_descriptor.APPROVED_KILL_CRITERIA,
        "directional_accuracy_min",
        LOGISTIC_KILL_CRITERIA_IMPOSSIBLE["directional_accuracy_min"],
    )
    repo_root, data_root, descriptor = _setup(
        tmp_path, kill_criteria=LOGISTIC_KILL_CRITERIA_IMPOSSIBLE
    )
    training_dir = _lane_dir(data_root, "training")
    pointer_before = (training_dir / "current.json").read_bytes()
    ridge_commit = json.loads(pointer_before.decode("utf-8"))["commit"]
    commits_before = sorted(path.name for path in (training_dir / "commits").iterdir())

    assert (
        run_training_pipeline(descriptor, data_root, repo_root=repo_root)
        == EXIT_KILL_CRITERIA_FAILED
    )

    # The training pointer still references the ridge commit, byte-for-byte.
    assert (training_dir / "current.json").read_bytes() == pointer_before
    assert json.loads(
        (training_dir / "current.json").read_text(encoding="utf-8")
    )["commit"] == ridge_commit
    assert sorted(path.name for path in (training_dir / "commits").iterdir()) == commits_before
    assert not list((training_dir / "commits").glob(".staging-*"))

    attempt = _attempts(data_root)[-1]
    assert attempt["terminal_result"] == KILL_CRITERIA_FAILED
    assert attempt["referenced_commit"] is None
    assert attempt["artifact_dispositions"] == {
        "training_artifact": "not_written",
        "pointer_replaced": False,
    }
    diagnostics = attempt["diagnostics"]
    assert diagnostics[0] == "kill_criteria_failed"
    assert "k1_directional_accuracy" in diagnostics[1]
    for prefix in (
        "k1_directional_accuracy_mean=",
        "k2_direction_ic_mean=",
        "k3_log_loss_mean=",
        "k4_brier_mean=",
    ):
        assert any(item.startswith(prefix) for item in diagnostics), prefix
    assert any(
        item.startswith("k1_directional_accuracy_mean=")
        and "min=0.990000000000000000" in item
        and "passed=false" in item
        for item in diagnostics
    )
    assert any(item.startswith("baseline_climatology_p_log_loss_mean=") for item in diagnostics)

    # A rerun stays on the kill branch and still publishes nothing.
    assert (
        run_training_pipeline(descriptor, data_root, repo_root=repo_root)
        == EXIT_KILL_CRITERIA_FAILED
    )
    assert (training_dir / "current.json").read_bytes() == pointer_before


def test_logistic_requires_the_ridge_lane_parent(tmp_path: Path) -> None:
    repo_root, data_root = _setup_chain(tmp_path)
    descriptor = write_training_descriptor_logistic(repo_root)
    assert (
        run_training_pipeline(descriptor, data_root, repo_root=repo_root) == EXIT_BLOCKED
    )
    assert _attempts(data_root)[-1]["diagnostics"] == [
        "training_parent_authentication_failed"
    ]


def test_logistic_rights_unknown_blocks_before_any_model_run(tmp_path: Path) -> None:
    repo_root, data_root, descriptor = _setup(tmp_path)
    rights = rights_v2_yaml_dict()
    rights["record_id"] = "synthetic-logistic-blocked"
    (repo_root / "configs" / "legal" / "binance-usdm-provider-rights.v3.yaml").write_text(
        yaml.safe_dump(rights, sort_keys=False), encoding="utf-8"
    )
    training_dir = _lane_dir(data_root, "training")
    pointer_before = (training_dir / "current.json").read_bytes()
    assert (
        run_training_pipeline(descriptor, data_root, repo_root=repo_root) == EXIT_BLOCKED
    )
    assert (training_dir / "current.json").read_bytes() == pointer_before
    assert _attempts(data_root)[-1]["diagnostics"] == ["legal_not_permitted"]


def test_cli_dispatches_the_logistic_descriptor(tmp_path: Path) -> None:
    from quantara.cli import main

    repo_root, data_root, descriptor = _setup(tmp_path)
    assert (
        main(
            [
                "--dataset-type",
                "model_training",
                "--descriptor",
                str(descriptor),
                "--data-root",
                str(data_root),
                "--dry-run",
            ]
        )
        == EXIT_OK
    )
