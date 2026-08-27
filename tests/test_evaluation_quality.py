"""Evaluation quality policy tests (data slice 006, Task T5).

Covers:
- 13 ordered PASS-only quality checks:
  1. parents_authenticated
  2. lineage_binding
  3. descriptor_identity
  4. fold_ranges
  5. row_alignment
  6. record_matrix
  7. pair_counts
  8. numeric_domain
  9. metric_recomputation
  10. metric_bounds
  11. summary_recomputation
  12. canonical_structure
  13. identity_contract
- Clean Q1 inputs evaluate to exact PASS;
- Weak, negative, or zero IC values still receive PASS;
- Deterministic quality_identity;
- Mutate one invariant per test to verify each check fails closed.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

from conftest import evaluation_cfg_tree, write_evaluation_descriptor
from quantara.evaluation_descriptor import load_evaluation_descriptor
from quantara.evaluation_metrics import (
    build_evaluation_records,
    build_evaluation_summaries,
)
from quantara.evaluation_pipeline import (
    build_evaluation_artifact,
    evaluation_commit_identity,
)
from quantara.evaluation_quality import (
    CHECK_IDS,
    QUALITY_POLICY_VERSION,
    EvaluationQualityReport,
    evaluate_evaluation_quality,
)
from quantara.hashing import (
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    sha256_hex,
)
from quantara.jcs import canonicalize


def _build_clean_q1_rows() -> list[tuple]:
    """Generate 2,184 synthetic hourly rows for Q1."""
    rows = []
    base_time = 1704067200000  # 2024-01-01T00:00:00Z
    for i in range(2184):
        t = base_time + i * 3600_000
        # Feature values: small distinct values to ensure variance
        f_ret = Decimal(str((i % 100 + 1) * 0.0001))
        f_roc = Decimal(str((i % 50 + 1) * 0.001))
        f_rvol = Decimal(str((i % 30 + 1) * 0.01))
        f_volratio = Decimal(str((i % 20 + 1) * 0.05))

        # Target label: structural nulls for final 24 rows
        if i >= 2184 - 24:
            l_fwdret = None
            l_fwddir = None
        else:
            l_fwdret = Decimal(str(((i + 7) % 80 + 1) * 0.0002))
            l_fwddir = 1
        rows.append((t, f_ret, f_roc, f_rvol, f_volratio, l_fwdret, l_fwddir))
    return rows


def _build_clean_q1_folds() -> list[dict]:
    """Generate 25 walk-forward test folds matching Q1."""
    folds = []
    start = 360
    for fold_id in range(25):
        size = 96 if fold_id == 24 else 72
        end = start + size
        folds.append({"fold_id": fold_id, "test_range": [start, end]})
        start = end
    return folds


def _build_clean_inputs(tmp_path: Path) -> dict:
    root = evaluation_cfg_tree(tmp_path)
    desc_path = write_evaluation_descriptor(root, "1h")
    descriptor = load_evaluation_descriptor(desc_path)

    research_rows = _build_clean_q1_rows()
    folds = _build_clean_q1_folds()

    validation_artifact = {
        "schema": "quantara.validation_folds/v1",
        "parent_rows": 2184,
        "folds": folds,
    }
    validation_artifact_bytes = canonicalize(validation_artifact).encode("utf-8") + b"\n"
    val_sha = sha256_hex(validation_artifact_bytes)

    res_commit = "a" * 64
    res_content_hash = "b" * 64
    res_parquet_sha = "c" * 64
    res_parquet_size = 54321

    validation_parent_info = {
        "dataset_id": descriptor.parent_descriptor.dataset_id,
        "commit_address": "d" * 64,
        "canonical_content_hash": "e" * 64,
        "artifact_sha256": val_sha,
        "artifact_size": len(validation_artifact_bytes),
        "schema_fingerprint": "06f0cff54df3b5f61943423f6925c6e4ab7b4ed323c59eeb2a91f2d309d17c1c",
    }
    research_parent_info = {
        "dataset_id": descriptor.parent_descriptor.parent_descriptor.dataset_id,
        "commit_address": res_commit,
        "canonical_content_hash": res_content_hash,
        "parquet_sha256": res_parquet_sha,
        "parquet_size": res_parquet_size,
    }
    validation_lineage = {
        "parent_dataset_id": research_parent_info["dataset_id"],
        "parent_commit_address": res_commit,
        "parent_canonical_content_hash": res_content_hash,
        "parent_parquet_sha256": res_parquet_sha,
        "parent_parquet_size": res_parquet_size,
    }

    records = build_evaluation_records(folds, research_rows)
    summaries = build_evaluation_summaries(records)

    artifact = build_evaluation_artifact(
        descriptor=descriptor,
        validation_parent_info=validation_parent_info,
        research_parent_info=research_parent_info,
        records=records,
        summaries=summaries,
    )
    artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"

    schema_fp = evaluation_schema_fingerprint(
        parent_validation_fingerprint=validation_parent_info["schema_fingerprint"]
    )
    content_hash = evaluation_content_hash(schema_fp, artifact_bytes)

    evaluation_from = {
        "validation_dataset_id": validation_parent_info["dataset_id"],
        "validation_commit_address": validation_parent_info["commit_address"],
        "validation_canonical_content_hash": validation_parent_info["canonical_content_hash"],
        "validation_artifact_sha256": validation_parent_info["artifact_sha256"],
        "validation_artifact_size": validation_parent_info["artifact_size"],
        "research_dataset_id": research_parent_info["dataset_id"],
        "research_commit_address": research_parent_info["commit_address"],
        "research_canonical_content_hash": research_parent_info["canonical_content_hash"],
        "research_parquet_sha256": research_parent_info["parquet_sha256"],
        "research_parquet_size": research_parent_info["parquet_size"],
        "evaluation_set_name": descriptor.evaluation_set["name"],
        "evaluation_set_version": descriptor.evaluation_set["version"],
        "features": list(descriptor.features),
        "target": descriptor.target,
        "metrics": list(descriptor.metrics),
        "decimal_contract": copy.deepcopy(artifact["decimal_contract"]),
    }
    commit_id = evaluation_commit_identity(content_hash, evaluation_from)

    return {
        "descriptor": descriptor,
        "validation_parent_info": validation_parent_info,
        "research_parent_info": research_parent_info,
        "validation_artifact": validation_artifact,
        "research_rows": research_rows,
        "validation_artifact_bytes": validation_artifact_bytes,
        "validation_quality_state": "PASS",
        "research_quality_state": "PASS",
        "validation_lineage": validation_lineage,
        "artifact": artifact,
        "artifact_bytes": artifact_bytes,
        "schema_fingerprint": schema_fp,
        "canonical_content_hash": content_hash,
        "evaluation_from": evaluation_from,
        "prospective_commit_identity": commit_id,
    }


def test_clean_evaluation_quality_passes(tmp_path: Path) -> None:
    assert QUALITY_POLICY_VERSION == "1"
    inputs = _build_clean_inputs(tmp_path)
    report = evaluate_evaluation_quality(**inputs)
    assert isinstance(report, EvaluationQualityReport)
    assert report.state == "PASS"
    assert report.failing_checks() == []
    assert len(report.findings) == len(CHECK_IDS) == 13
    assert [f.check_id for f in report.findings] == list(CHECK_IDS)
    for f in report.findings:
        assert f.outcome == "pass"

    ident = report.identity()
    assert isinstance(ident, str) and len(ident) > 0
    assert ident == report.identity()


def test_parents_authenticated_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    inputs["validation_quality_state"] = "FAIL"
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "parents_authenticated" in report.failing_checks()


def test_lineage_binding_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    inputs["validation_lineage"] = dict(
        inputs["validation_lineage"],
        parent_commit_address="0" * 64,
    )
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "lineage_binding" in report.failing_checks()


def test_descriptor_identity_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_artifact = dict(inputs["artifact"], dataset_id="wrong_dataset_id")
    inputs["artifact"] = bad_artifact
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "descriptor_identity" in report.failing_checks()


def test_fold_ranges_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_folds = copy.deepcopy(inputs["validation_artifact"]["folds"])
    bad_folds[1]["test_range"] = [430, 502]  # overlaps with fold 0 (360..432)
    inputs["validation_artifact"] = dict(inputs["validation_artifact"], folds=bad_folds)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "fold_ranges" in report.failing_checks()


def test_row_alignment_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    # Undersized rows
    inputs["research_rows"] = inputs["research_rows"][:2000]
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "row_alignment" in report.failing_checks()


def test_record_matrix_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    # Duplicate first record, remove last
    bad_records = list(inputs["artifact"]["records"])
    bad_records[-1] = bad_records[0]
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "record_matrix" in report.failing_checks()


def test_pair_counts_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_records = copy.deepcopy(inputs["artifact"]["records"])
    bad_records[0]["valid_pair_count"] = 71
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "pair_counts" in report.failing_checks()


def test_numeric_domain_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_records = copy.deepcopy(inputs["artifact"]["records"])
    bad_records[0]["pearson_ic"] = "0.123"  # not 18 decimal places
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "numeric_domain" in report.failing_checks()


def test_metric_recomputation_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_records = copy.deepcopy(inputs["artifact"]["records"])
    # Change the IC value slightly
    bad_records[0]["pearson_ic"] = "0.999999999999999999"
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "metric_recomputation" in report.failing_checks()


def test_metric_bounds_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_records = copy.deepcopy(inputs["artifact"]["records"])
    bad_records[0]["pearson_ic"] = "1.000000000000000001"  # > 1
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "metric_bounds" in report.failing_checks()


def test_summary_recomputation_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_summaries = copy.deepcopy(inputs["artifact"]["summaries"])
    bad_summaries[0]["median"] = "0.000000000000000000"
    inputs["artifact"] = dict(inputs["artifact"], summaries=bad_summaries)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "summary_recomputation" in report.failing_checks()


def test_canonical_structure_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_artifact = copy.deepcopy(inputs["artifact"])
    bad_artifact.pop("disclaimer")
    inputs["artifact"] = bad_artifact
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "canonical_structure" in report.failing_checks()


def test_identity_contract_failure(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    inputs["schema_fingerprint"] = "0" * 64
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "identity_contract" in report.failing_checks()


def test_metric_recomputation_range_tamper_rejected(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    bad_records = copy.deepcopy(inputs["artifact"]["records"])
    # Tamper with record test_range so it differs from validation fold
    bad_records[0]["test_range"] = [360, 431]
    inputs["artifact"] = dict(inputs["artifact"], records=bad_records)
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "metric_recomputation" in report.failing_checks()


def test_canonical_structure_missing_or_extra_subkeys(tmp_path: Path) -> None:
    inputs = _build_clean_inputs(tmp_path)
    # Tamper with validation_parent subkeys
    bad_artifact = copy.deepcopy(inputs["artifact"])
    bad_artifact["validation_parent"].pop("artifact_size")
    inputs["artifact"] = bad_artifact
    report = evaluate_evaluation_quality(**inputs)
    assert report.state == "FAIL"
    assert "canonical_structure" in report.failing_checks()
