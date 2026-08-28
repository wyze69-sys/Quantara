"""Training quality evidence tests for slice 011."""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

from quantara.jcs import canonicalize
from quantara.training_descriptor import load_training_descriptor
from quantara.training_metrics import (
    DECIMAL_CONTRACT,
    build_training_records,
    build_training_summaries,
)
from quantara.training_quality import (
    CHECK_IDS,
    DISCLAIMER,
    TRAINING_ARTIFACT_SCHEMA,
    TrainingQualityReport,
    evaluate_training_quality,
    training_commit_identity,
    training_content_hash,
    training_schema_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "configs" / "datasets" / "binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml"


def _rows() -> list[tuple]:
    rows = []
    for i in range(228):
        d = Decimal(i)
        rows.append(
            (
                1704067200000 + i * 3600000,
                d + 1,
                d * d + 2,
                Decimal((i % 7) + 1),
                Decimal((i % 11) + 2),
                d / Decimal(100) - 1,
                1 if i % 2 == 0 else -1,
            )
        )
    return rows


def _inputs() -> dict:
    descriptor = load_training_descriptor(CONFIG)
    rows = _rows()
    folds = [
        {
            "fold_id": 0,
            "train_range": [0, 200],
            "embargo_range": [200, 224],
            "test_range": [224, 228],
        }
    ]
    validation_artifact = {"folds": folds, "coverage": {"fold_count": 1}, "parent_rows": len(rows)}
    records = build_training_records(folds, rows)
    summaries, baselines = build_training_summaries(records)
    validation_bytes = canonicalize(validation_artifact).encode() + b"\n"
    validation_info = {
        "dataset_id": descriptor.parent_descriptor.dataset_id,
        "commit_address": "a" * 64,
        "canonical_content_hash": "b" * 64,
        "artifact_sha256": __import__("hashlib").sha256(validation_bytes).hexdigest(),
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
    validation_lineage = {
        "parent_dataset_id": research_info["dataset_id"],
        "parent_commit_address": research_info["commit_address"],
        "parent_canonical_content_hash": research_info["canonical_content_hash"],
        "parent_parquet_sha256": research_info["parquet_sha256"],
        "parent_parquet_size": research_info["parquet_size"],
    }
    artifact = {
        "schema": TRAINING_ARTIFACT_SCHEMA,
        "dataset_id": descriptor.dataset_id,
        "provider": descriptor.provider,
        "instrument_id": descriptor.instrument_id,
        "period": {"start": "2024-01-01T00:00:00Z", "end": "2025-01-01T00:00:00Z"},
        "features": list(descriptor.features),
        "target": descriptor.target,
        "model": dict(descriptor.model),
        "training_set": dict(descriptor.training_set),
        "decimal_contract": DECIMAL_CONTRACT,
        "research_parent": research_info,
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
        "records": records,
        "summaries": summaries,
        "baselines": baselines,
        "disclaimer": DISCLAIMER,
    }
    artifact_bytes = canonicalize(artifact).encode() + b"\n"
    schema_fp = training_schema_fingerprint(validation_info["schema_fingerprint"])
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
    }
    return {
        "descriptor": descriptor,
        "validation_parent_info": validation_info,
        "research_parent_info": research_info,
        "validation_artifact": validation_artifact,
        "research_rows": rows,
        "validation_artifact_bytes": validation_bytes,
        "validation_quality_state": "PASS",
        "research_quality_state": "PASS",
        "validation_lineage": validation_lineage,
        "artifact": artifact,
        "artifact_bytes": artifact_bytes,
        "schema_fingerprint": schema_fp,
        "canonical_content_hash": content_hash,
        "training_from": training_from,
        "prospective_commit_identity": training_commit_identity(content_hash, training_from),
    }


def test_check_order_clean_pass_and_stable_identity() -> None:
    inputs = _inputs()
    report = evaluate_training_quality(**inputs)
    assert isinstance(report, TrainingQualityReport)
    assert report.state == "PASS", report.failing_checks()
    assert [finding.check_id for finding in report.findings] == list(CHECK_IDS)
    assert report.identity() == report.identity()


def test_each_quality_check_can_fail() -> None:
    mutations = {
        "parents_authenticated": lambda i: i.update(validation_quality_state="FAIL"),
        "lineage_binding": lambda i: i["training_from"].update(validation_commit_address="0" * 64),
        "descriptor_identity": lambda i: i["artifact"].update(dataset_id="wrong"),
        "fold_alignment": lambda i: i["validation_artifact"]["folds"][0].update(
            train_range=[0, 225]
        ),
        "train_matrix": lambda i: i["artifact"]["records"][0].update(usable_train_count=199),
        "numeric_domain": lambda i: i["artifact"]["records"][0].update(mse=1.0),
        "solver_determinism": lambda i: i["artifact"]["records"][0].update(
            solver_deterministic=False
        ),
        "metric_recomputation": lambda i: i["artifact"]["records"][0].update(
            pearson_ic="0.000000000000000000"
        ),
        "metric_bounds": lambda i: i["artifact"]["records"][0].update(
            directional_accuracy="1.000000000000000001"
        ),
        "baseline_presence": lambda i: i["artifact"]["records"][0]["baselines"].pop("sign_f_ret_1"),
        "canonical_structure": lambda i: i["artifact"].pop("disclaimer"),
        "identity_contract": lambda i: i.update(schema_fingerprint="0" * 64),
    }
    assert tuple(mutations) == CHECK_IDS
    for check_id, mutate in mutations.items():
        inputs = copy.deepcopy(_inputs())
        mutate(inputs)
        report = evaluate_training_quality(**inputs)
        assert check_id in report.failing_checks(), check_id
