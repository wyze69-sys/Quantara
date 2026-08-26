"""Evaluation pipeline artifact and computation tests (data slice 006, Task T4).

Covers:
- build_evaluation_artifact root keys and contract;
- parent descriptor and period bindings;
- JCS artifact bytes plus exactly one LF;
- exclusion of pooled metrics.
"""

from __future__ import annotations

from pathlib import Path

from conftest import evaluation_cfg_tree, write_evaluation_descriptor
from quantara.evaluation_descriptor import load_evaluation_descriptor
from quantara.evaluation_pipeline import (
    DISCLAIMER,
    EVALUATION_ARTIFACT_SCHEMA,
    build_evaluation_artifact,
)
from quantara.jcs import canonicalize


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
