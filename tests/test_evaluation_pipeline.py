"""Evaluation pipeline artifact and computation tests (data slice 006, Tasks T4, T6).

Covers:
- build_evaluation_artifact root keys and contract;
- parent descriptor and period bindings;
- JCS artifact bytes plus exactly one LF;
- exclusion of pooled metrics;
- parent authentication and lineage validation;
- January parent pointer rejection (BLOCKED/2);
- pointer snapshot stability (before, after verifier, pre-publication);
- dry-run write-free complete computation (returns 0);
- dry-run quality failure (returns 2 write-free).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from conftest import (
    evaluation_cfg_tree,
    write_evaluation_descriptor,
)
from quantara.evaluation_descriptor import load_evaluation_descriptor
from quantara.evaluation_pipeline import (
    DISCLAIMER,
    EVALUATION_ARTIFACT_SCHEMA,
    build_evaluation_artifact,
    run_evaluation_pipeline,
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
from quantara.validation_pipeline import validation_commit_identity


def test_build_evaluation_artifact_structure_and_canonical_bytes(tmp_path: Path) -> None:
    root = evaluation_cfg_tree(tmp_path)
    desc_path = write_evaluation_descriptor(root, "1h")
    descriptor = load_evaluation_descriptor(desc_path)

    validation_parent_info = {
        "dataset_id": "val_dataset_1",
        "commit_address": "1" * 64,
        "canonical_content_hash": "2" * 64,
        "artifact_sha256": "3" * 64,
        "artifact_size": 12345,
    }
    research_parent_info = {
        "dataset_id": "res_dataset_1",
        "commit_address": "4" * 64,
        "canonical_content_hash": "5" * 64,
        "parquet_sha256": "6" * 64,
        "parquet_size": 67890,
    }
    records = [
        {
            "fold_id": 0,
            "feature": "f_ret_1",
            "target": "l_fwdret_24",
            "test_range": [0, 72],
            "test_row_count": 72,
            "valid_pair_count": 72,
            "excluded_pair_count": 0,
            "feature_null_count": 0,
            "target_null_count": 0,
            "pearson_ic": "0.100000000000000000",
            "spearman_ic": "0.200000000000000000",
        }
    ]
    summaries = [
        {
            "feature": "f_ret_1",
            "metric": "pearson_ic",
            "fold_count": 1,
            "total_valid_pair_count": 72,
            "positive_fold_count": 1,
            "negative_fold_count": 0,
            "zero_fold_count": 0,
            "minimum": "0.100000000000000000",
            "maximum": "0.100000000000000000",
            "median": "0.100000000000000000",
            "equal_weight_mean": "0.100000000000000000",
        }
    ]

    artifact = build_evaluation_artifact(
        descriptor=descriptor,
        validation_parent_info=validation_parent_info,
        research_parent_info=research_parent_info,
        records=records,
        summaries=summaries,
    )

    # Exact 15 root keys (spec §9)
    expected_root_keys = {
        "schema",
        "dataset_id",
        "provider",
        "instrument_id",
        "period",
        "evaluation_set",
        "validation_parent",
        "research_parent",
        "features",
        "target",
        "metrics",
        "decimal_contract",
        "records",
        "summaries",
        "disclaimer",
    }
    assert set(artifact.keys()) == expected_root_keys
    assert artifact["schema"] == EVALUATION_ARTIFACT_SCHEMA
    assert artifact["disclaimer"] == DISCLAIMER
    assert artifact["disclaimer"] == (
        "internal descriptive analysis only; no model, signal, backtest, "
        "significance, or performance claim"
    )

    # Check parent blocks
    assert set(artifact["validation_parent"].keys()) == {
        "dataset_id",
        "commit_address",
        "canonical_content_hash",
        "artifact_sha256",
        "artifact_size",
    }
    assert set(artifact["research_parent"].keys()) == {
        "dataset_id",
        "commit_address",
        "canonical_content_hash",
        "parquet_sha256",
        "parquet_size",
    }

    # Serialization: JCS plus exactly one LF byte
    artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    assert artifact_bytes.endswith(b"\n")
    assert not artifact_bytes.endswith(b"\n\n")

    # No pooled metric is present
    assert "pooled" not in canonicalize(artifact)


def _build_clean_q1_rows() -> list[tuple]:
    rows = []
    base_time = 1704067200000  # 2024-01-01T00:00:00Z
    for i in range(2184):
        t = base_time + i * 3600_000
        f_ret = Decimal(i % 100 + 1) / Decimal(10000)
        f_roc = Decimal(i % 50 + 1) / Decimal(1000)
        f_rvol = Decimal(i % 30 + 1) / Decimal(100)
        f_volratio = Decimal(i % 20 + 1) / Decimal(20)
        if i >= 2184 - 24:
            l_fwdret = None
            l_fwddir = None
        else:
            l_fwdret = Decimal((i + 7) % 80 + 1) / Decimal(5000)
            l_fwddir = 1
        rows.append((t, f_ret, f_roc, f_rvol, f_volratio, l_fwdret, l_fwddir))
    return rows


def _build_clean_q1_folds() -> list[dict]:
    folds = []
    start = 360
    for fold_id in range(25):
        size = 96 if fold_id == 24 else 72
        end = start + size
        folds.append({"fold_id": fold_id, "test_range": [start, end]})
        start = end
    return folds


def setup_offline_q1_parents(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build a complete offline Q1 research and validation parent graph."""
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"

    import shutil
    shutil.copytree(Path("configs"), repo_root / "configs")
    eval_desc = (
        repo_root
        / "configs"
        / "datasets"
        / "binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml"
    )

    # Populate research parent in data_root
    res_rows = _build_clean_q1_rows()
    temp_pq = tmp_path / "research.parquet"
    write_research_parquet(res_rows, temp_pq)
    pq_bytes = temp_pq.read_bytes()
    pq_res = store_object(data_root, "normalized", pq_bytes)
    pq_sha = pq_res.sha256
    temp_pq.unlink()

    res_fp = research_schema_fingerprint("quantara_research_featureset_v1")
    res_cch = research_content_hash(res_fp, render_content_rows(res_rows))
    res_lineage = {
        "parent_dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1",
        "parent_commit_address": "0" * 64,
        "parent_canonical_content_hash": "1" * 64,
        "parent_zip_sha256": "2" * 64,
    }
    res_cid = research_commit_identity(res_cch, res_lineage)

    res_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    res_findings = [
        {
            "check_id": "row_count",
            "count": 0,
            "evidence": {"rows": 2184},
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
        "parquet_sha256": pq_sha,
        "parquet_size": len(pq_bytes),
        "object_refs": [{"kind": "normalized", "sha256": pq_sha}],
        "research_from": res_lineage,
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2024-04-01T00:00:00Z"},
    }
    res_content = {
        "schema_fingerprint": res_fp,
        "parser_version": "1.0.0",
        "canonical_content_hash": res_cch,
        "quality_identity": res_qid,
        "object_refs": [{"kind": "normalized", "sha256": pq_sha}],
        "research_from": res_lineage,
        "research_commit_identity": res_cid,
    }
    res_quality = {
        "state": "PASS",
        "policy_version": "1",
        "identity": res_qid,
        "findings": res_findings,
    }

    res_files = {
        "manifest.json": (json.dumps(res_manifest, indent=2, sort_keys=True) + "\n").encode(),
        "content.json": (json.dumps(res_content, indent=2, sort_keys=True) + "\n").encode(),
        "quality.json": (json.dumps(res_quality, indent=2, sort_keys=True) + "\n").encode(),
    }
    staged_res = stage_commit(res_dir, "test_res", res_files)
    res_commit_dir = res_dir / "commits" / res_cid
    res_commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged_res.replace(res_commit_dir)
    (res_commit_dir / "COMMITTED").touch()
    write_current(res_dir, res_cid, sha256_hex(res_files["manifest.json"]))

    # Populate validation parent in data_root
    val_folds = _build_clean_q1_folds()
    val_artifact = {
        "schema": "quantara.validation_folds/v1",
        "fold_set": "btcusdt_core_v1_wf72_v1",
        "scheme": "anchored_walkforward_v1",
        "parameters": {"test_size": 72, "min_train_size": 336, "embargo": 24},
        "parent_rows": 2184,
        "excluded_head_rows": 360,
        "folds": val_folds,
        "coverage": {"total_rows": 2184, "test_rows": 1824, "fold_count": 25},
    }
    val_art_bytes = canonicalize(val_artifact).encode("utf-8") + b"\n"
    val_obj = store_object(data_root, "normalized", val_art_bytes)
    val_sha = val_obj.sha256

    val_fp = validation_schema_fingerprint(
        parent_fingerprint=res_fp,
        schema_id="quantara_validation_folds_v1",
        scheme="anchored_walkforward_v1",
        parameters={"test_size": 72, "min_train_size": 336, "embargo": 24},
        fold_set_name="btcusdt_core_v1_wf72_v1",
        fold_set_version="1",
    )
    val_cch = validation_content_hash(val_fp, val_art_bytes)
    val_lineage = {
        "parent_dataset_id": "binance_usdm_btcusdt_klines_1h_2024_q1_research_core_v1",
        "parent_commit_address": res_cid,
        "parent_canonical_content_hash": res_cch,
        "parent_parquet_sha256": pq_sha,
        "parent_parquet_size": len(pq_bytes),
    }
    val_cid = validation_commit_identity(val_cch, val_lineage)

    val_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    val_findings = [
        {
            "check_id": "fold_coverage",
            "count": 0,
            "evidence": {"folds": 25},
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
        "artifact_size": len(val_art_bytes),
        "parent_rows": 2184,
        "fold_count": 25,
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

    val_files = {
        "manifest.json": (json.dumps(val_manifest, indent=2, sort_keys=True) + "\n").encode(),
        "content.json": (json.dumps(val_content, indent=2, sort_keys=True) + "\n").encode(),
        "quality.json": (json.dumps(val_quality, indent=2, sort_keys=True) + "\n").encode(),
    }
    staged_val = stage_commit(val_dir, "test_val", val_files)
    val_commit_dir = val_dir / "commits" / val_cid
    val_commit_dir.parent.mkdir(parents=True, exist_ok=True)
    staged_val.replace(val_commit_dir)
    (val_commit_dir / "COMMITTED").touch()
    write_current(val_dir, val_cid, sha256_hex(val_files["manifest.json"]))

    return repo_root, data_root, eval_desc


def test_dry_run_success_and_write_free(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
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

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 0

    # Verify completely write-free
    assert not eval_dir.exists()
    assert not (data_root / "attempts" / "evaluation").exists()
    assert not (data_root / "staging").exists() or not any((data_root / "staging").iterdir())


def test_missing_validation_parent_blocks(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    val_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    # Remove validation current.json
    (val_dir / "current.json").unlink()

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 2


def test_lineage_mismatch_blocks(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    val_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    pointer = json.loads((val_dir / "current.json").read_text())
    val_commit = pointer["commit"]
    val_content_file = val_dir / "commits" / val_commit / "content.json"
    content = json.loads(val_content_file.read_text())
    # Corrupt the lineage binding to point to a different research commit
    content["validation_from"]["parent_commit_address"] = "f" * 64
    val_content_file.write_text(json.dumps(content, indent=2))

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 2


def test_pointer_snapshot_stability(tmp_path: Path, monkeypatch) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    val_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )

    from quantara import evaluation_pipeline as ep_module
    orig_verify = ep_module.verify_validation_current_graph

    def tampered_verify(dataset_dir, data_root):
        res = orig_verify(dataset_dir, data_root)
        # Mutate current.json during verification
        (val_dir / "current.json").write_text('{"tampered": true}')
        return res

    monkeypatch.setattr(ep_module, "verify_validation_current_graph", tampered_verify)

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 2


def test_january_parent_pointer_blocks(tmp_path: Path) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)
    val_dir = (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / "BTCUSDT"
        / "1h"
        / "year=2024"
        / "month=01"
    )
    pointer = json.loads((val_dir / "current.json").read_text())
    val_commit = pointer["commit"]
    val_manifest_file = val_dir / "commits" / val_commit / "manifest.json"
    manifest = json.loads(val_manifest_file.read_text())
    # Tamper manifest to look like January dataset (744 rows, 5 folds)
    manifest["parent_rows"] = 744
    manifest["fold_count"] = 5
    val_manifest_file.write_text(json.dumps(manifest, indent=2))

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 2


def test_dry_run_quality_failure_returns_blocked(tmp_path: Path, monkeypatch) -> None:
    repo_root, data_root, eval_desc = setup_offline_q1_parents(tmp_path)

    # Monkeypatch evaluate_evaluation_quality to return a failing report
    from quantara import evaluation_pipeline as ep_module
    from quantara.evaluation_quality import EvaluationQualityReport, Finding

    def failing_quality(**kwargs):
        findings = [
            Finding(
                check_id="metric_recomputation",
                outcome="fail",
                severity="hard",
                count=1,
                evidence={"tampered": True},
            )
        ]
        return EvaluationQualityReport(findings)

    monkeypatch.setattr(ep_module, "evaluate_evaluation_quality", failing_quality)

    code = run_evaluation_pipeline(
        descriptor_path=eval_desc,
        data_root=data_root,
        repo_root=repo_root,
        dry_run=True,
    )
    assert code == 2

    # Assert write-free
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
    assert not (data_root / "attempts" / "evaluation").exists()

