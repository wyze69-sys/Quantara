"""Logistic training quality evidence tests for slice 012.

Covers the new ``lane_kill_criteria`` hard check and pins the frozen slice 011
ridge check order.
"""

from __future__ import annotations

import copy
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from quantara.jcs import canonicalize
from quantara.training_descriptor import load_training_descriptor
from quantara.training_metrics_logistic import (
    DECIMAL_CONTRACT,
    build_logistic_training_records,
    build_logistic_training_summaries,
    evaluate_kill_criteria,
)
from quantara.training_quality import (
    CHECK_IDS,
    DISCLAIMER,
    LOGISTIC_ARTIFACT_SCHEMA,
    LOGISTIC_CHECK_IDS,
    TRAINING_ARTIFACT_SCHEMA,
    TrainingQualityReport,
    evaluate_logistic_training_quality,
    training_commit_identity,
    training_content_hash,
    training_schema_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = (
    REPO_ROOT
    / "configs"
    / "datasets"
    / "binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml"
)


def _rows() -> list[tuple]:
    """A separable-enough synthetic fold so the clean fixture passes K1-K4.

    The kill criteria are pre-registered constants, so the PASS-path fixture
    must be a genuinely learnable series; the FAIL path is exercised by
    mutating the artifact's kill block, never by relaxing a threshold.
    """
    rows = []
    for index in range(270):
        direction = 1 if (index % 7) in (0, 1, 2, 3) else -1
        base = Decimal((index % 17) - 8) / Decimal(10)
        feature = base + (Decimal("0.6") if direction == 1 else Decimal("-0.6"))
        rows.append(
            (
                1704067200000 + index * 3600000,
                feature,
                Decimal((index * 7 % 23) - 11),
                Decimal((index % 7) + 1),
                Decimal((index % 11) + 2),
                Decimal(direction) * Decimal((index % 13) + 1) / Decimal(100),
                direction,
            )
        )
    rows[10] = (*rows[10][:6], 0)
    return rows


def _inputs() -> dict:
    descriptor = load_training_descriptor(CONFIG)
    rows = _rows()
    folds = [
        {
            "fold_id": 0,
            "train_range": [0, 240],
            "embargo_range": [240, 264],
            "test_range": [264, 270],
        }
    ]
    validation_artifact = {
        "folds": folds,
        "coverage": {"fold_count": 1},
        "parent_rows": len(rows),
    }
    records = build_logistic_training_records(folds, rows)
    summaries, baselines = build_logistic_training_summaries(records)
    kill = evaluate_kill_criteria(summaries, baselines)
    validation_bytes = canonicalize(validation_artifact).encode() + b"\n"
    validation_info = {
        "dataset_id": descriptor.parent_descriptor.dataset_id,
        "commit_address": "a" * 64,
        "canonical_content_hash": "b" * 64,
        "artifact_sha256": hashlib.sha256(validation_bytes).hexdigest(),
        "artifact_size": len(validation_bytes),
        "schema_fingerprint": "c" * 64,
    }
    research_info = {
        "dataset_id": descriptor.parent_descriptor.parent_descriptor.dataset_id,
        "commit_address": "d" * 64,
        "canonical_content_hash": "e" * 64,
        "parquet_sha256": "f" * 64,
        "parquet_size": 123,
    }
    training_info = {
        "dataset_id": "binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1",
        "commit_address": "1" * 64,
        "canonical_content_hash": "2" * 64,
        "artifact_sha256": "3" * 64,
        "artifact_size": 4096,
    }
    validation_lineage = {
        "parent_dataset_id": research_info["dataset_id"],
        "parent_commit_address": research_info["commit_address"],
        "parent_canonical_content_hash": research_info["canonical_content_hash"],
        "parent_parquet_sha256": research_info["parquet_sha256"],
        "parent_parquet_size": research_info["parquet_size"],
    }
    artifact = {
        "schema": LOGISTIC_ARTIFACT_SCHEMA,
        "dataset_id": descriptor.dataset_id,
        "provider": descriptor.provider,
        "instrument_id": descriptor.instrument_id,
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"},
        "features": list(descriptor.features),
        "target": descriptor.target,
        "model": dict(descriptor.model),
        "training_set": dict(descriptor.training_set),
        "decimal_contract": dict(DECIMAL_CONTRACT),
        "research_parent": dict(research_info),
        "validation_parent": {
            key: validation_info[key]
            for key in (
                "dataset_id",
                "commit_address",
                "canonical_content_hash",
                "artifact_sha256",
                "artifact_size",
            )
        },
        "training_parent": dict(training_info),
        "records": records,
        "summaries": summaries,
        "baselines": baselines,
        "kill_criteria": kill,
        "disclaimer": DISCLAIMER,
    }
    artifact_bytes = canonicalize(artifact).encode() + b"\n"
    schema_fp = training_schema_fingerprint(
        validation_info["schema_fingerprint"], LOGISTIC_ARTIFACT_SCHEMA
    )
    content_hash = training_content_hash(schema_fp, artifact_bytes)
    training_from = {
        "validation_dataset_id": validation_info["dataset_id"],
        "validation_commit_address": validation_info["commit_address"],
        "validation_canonical_content_hash": validation_info["canonical_content_hash"],
        "validation_artifact_sha256": validation_info["artifact_sha256"],
        "validation_artifact_size": validation_info["artifact_size"],
        "research_dataset_id": research_info["dataset_id"],
        "research_commit_address": research_info["commit_address"],
        "research_canonical_content_hash": research_info["canonical_content_hash"],
        "research_parquet_sha256": research_info["parquet_sha256"],
        "research_parquet_size": research_info["parquet_size"],
        "training_dataset_id": training_info["dataset_id"],
        "training_commit_address": training_info["commit_address"],
        "training_canonical_content_hash": training_info["canonical_content_hash"],
        "training_artifact_sha256": training_info["artifact_sha256"],
        "training_artifact_size": training_info["artifact_size"],
    }
    return {
        "descriptor": descriptor,
        "validation_parent_info": validation_info,
        "research_parent_info": research_info,
        "training_parent_info": training_info,
        "validation_artifact": validation_artifact,
        "research_rows": rows,
        "validation_artifact_bytes": validation_bytes,
        "validation_quality_state": "PASS",
        "research_quality_state": "PASS",
        "training_quality_state": "PASS",
        "validation_lineage": validation_lineage,
        "artifact": artifact,
        "artifact_bytes": artifact_bytes,
        "schema_fingerprint": schema_fp,
        "canonical_content_hash": content_hash,
        "training_from": training_from,
        "prospective_commit_identity": training_commit_identity(content_hash, training_from),
    }


def _rebuild(inputs: dict) -> None:
    """Recanonicalize after mutating the artifact so only the target check fails."""
    inputs["artifact_bytes"] = canonicalize(inputs["artifact"]).encode() + b"\n"
    inputs["schema_fingerprint"] = training_schema_fingerprint(
        inputs["validation_parent_info"]["schema_fingerprint"], LOGISTIC_ARTIFACT_SCHEMA
    )
    inputs["canonical_content_hash"] = training_content_hash(
        inputs["schema_fingerprint"], inputs["artifact_bytes"]
    )
    inputs["prospective_commit_identity"] = training_commit_identity(
        inputs["canonical_content_hash"], inputs["training_from"]
    )


def test_logistic_check_order_extends_the_frozen_ridge_order() -> None:
    assert LOGISTIC_CHECK_IDS[: len(CHECK_IDS)] == CHECK_IDS
    assert LOGISTIC_CHECK_IDS[-1] == "lane_kill_criteria"
    assert len(LOGISTIC_CHECK_IDS) == len(CHECK_IDS) + 1
    assert "lane_kill_criteria" not in CHECK_IDS
    assert CHECK_IDS == (
        "parents_authenticated",
        "lineage_binding",
        "descriptor_identity",
        "fold_alignment",
        "train_matrix",
        "numeric_domain",
        "solver_determinism",
        "metric_recomputation",
        "metric_bounds",
        "baseline_presence",
        "canonical_structure",
        "identity_contract",
    )


def test_ridge_and_logistic_artifact_schemas_are_distinct() -> None:
    assert TRAINING_ARTIFACT_SCHEMA == "quantara.model_training/v1"
    assert LOGISTIC_ARTIFACT_SCHEMA == "quantara.model_training_logistic/v1"
    fingerprint_ridge = training_schema_fingerprint("c" * 64)
    fingerprint_logistic = training_schema_fingerprint("c" * 64, LOGISTIC_ARTIFACT_SCHEMA)
    assert fingerprint_ridge != fingerprint_logistic


def test_clean_logistic_pass_with_stable_identity() -> None:
    inputs = _inputs()
    report = evaluate_logistic_training_quality(**inputs)
    assert isinstance(report, TrainingQualityReport)
    assert report.state == "PASS", report.failing_checks()
    assert [finding.check_id for finding in report.findings] == list(LOGISTIC_CHECK_IDS)
    assert report.identity() == report.identity()


def _kill_finding(report: TrainingQualityReport) -> dict:
    return next(
        item.evidence for item in report.findings if item.check_id == "lane_kill_criteria"
    )


def test_kill_criteria_constants_must_match_the_descriptor() -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"]["constants"]["brier_max"] = (
        "0.900000000000000000"
    )
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()
    assert _kill_finding(report)["constants_match"] is False


def test_kill_criteria_observed_must_match_the_artifact_summaries() -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"]["observed"]["log_loss_mean"] = (
        "0.100000000000000000"
    )
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()
    assert _kill_finding(report)["observed_match"] is False


def test_kill_criteria_observed_baseline_mean_must_match() -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"]["observed"][
        "climatology_p_brier_mean"
    ] = "0.100000000000000000"
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()
    assert _kill_finding(report)["observed_match"] is False


@pytest.mark.parametrize(
    "flag",
    ["k1_directional_accuracy", "k2_direction_ic", "k3_log_loss", "k4_brier"],
)
def test_any_false_kill_boolean_fails_the_publish_path(flag: str) -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"]["results"][flag] = False
    inputs["artifact"]["kill_criteria"]["all_passed"] = False
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()
    assert _kill_finding(report)["all_passed"] is False


def test_all_passed_must_agree_with_the_four_booleans() -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"]["all_passed"] = False
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()


def test_kill_criteria_block_shape_is_enforced() -> None:
    inputs = _inputs()
    inputs["artifact"]["kill_criteria"].pop("results")
    _rebuild(inputs)
    report = evaluate_logistic_training_quality(**inputs)
    assert "lane_kill_criteria" in report.failing_checks()


def test_every_logistic_quality_check_can_fail() -> None:
    mutations = {
        "parents_authenticated": lambda i: i.update(training_quality_state="FAIL"),
        "lineage_binding": lambda i: i["training_from"].update(
            training_commit_address="0" * 64
        ),
        "descriptor_identity": lambda i: i["artifact"].update(dataset_id="wrong"),
        "fold_alignment": lambda i: i["validation_artifact"]["folds"][0].update(
            train_range=[0, 265]
        ),
        "train_matrix": lambda i: i["artifact"]["records"][0].update(
            usable_train_count=199
        ),
        "numeric_domain": lambda i: i["artifact"]["records"][0].update(brier=1.0),
        "solver_determinism": lambda i: i["artifact"]["records"][0].update(
            solver_deterministic=False
        ),
        "metric_recomputation": lambda i: i["artifact"]["records"][0].update(
            log_loss="0.100000000000000000"
        ),
        "metric_bounds": lambda i: i["artifact"]["records"][0].update(
            directional_accuracy="1.000000000000000001"
        ),
        "baseline_presence": lambda i: i["artifact"]["records"][0]["baselines"].pop(
            "climatology_p"
        ),
        "canonical_structure": lambda i: i["artifact"].pop("disclaimer"),
        "identity_contract": lambda i: i.update(schema_fingerprint="0" * 64),
        "lane_kill_criteria": lambda i: i["artifact"]["kill_criteria"]["results"].update(
            k4_brier=False
        ),
    }
    assert tuple(mutations) == LOGISTIC_CHECK_IDS
    for check_id, mutate in mutations.items():
        inputs = copy.deepcopy(_inputs())
        mutate(inputs)
        if check_id not in ("canonical_structure", "identity_contract"):
            try:
                _rebuild(inputs)
            except Exception:
                # A float mutation cannot be canonicalized; the pre-mutation
                # bytes stay in place and numeric_domain is the check under test.
                pass
        report = evaluate_logistic_training_quality(**inputs)
        assert check_id in report.failing_checks(), check_id
