"""Domain-separated hashing and identity vector tests (data slice 006, Task T2).

Covers:
- evaluation schema fingerprint determinism, domain separation, parameter sensitivity;
- parent validation fingerprint requirement (lowercase hex, no uppercase coercion);
- frozen evaluation schema fingerprint vector (d454a7e142ac...);
- evaluation content hash framing, determinism, types (dict, str, bytes);
- uppercase fingerprint rejection;
- evaluation commit identity in evaluation_pipeline.py;
- verification that all predecessor fingerprints and frozen hashes remain unchanged.
"""

from __future__ import annotations

import pytest

from quantara.evaluation_pipeline import evaluation_commit_identity
from quantara.hashing import (
    EVALUATION_CONTENT_HASH_DOMAIN,
    EVALUATION_SCHEMA_VERSION,
    HashPayloadError,
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    research_schema_fingerprint,
    schema_fingerprint,
    validation_content_hash,
    validation_schema_fingerprint,
)
from quantara.jcs import canonicalize

FROZEN_VALIDATION_FP = (
    "06f0cff54df3b5f61943423f6925c6e4ab7b4ed323c59eeb2a91f2d309d17c1c"
)
FROZEN_EVALUATION_FP = (
    "d454a7e142ac19cfbb75ccabd53f1fb20f26bc471968c6e4b84203030aa10843"
)


def test_evaluation_constants() -> None:
    assert EVALUATION_CONTENT_HASH_DOMAIN == "quantara-evaluation-content-v1"
    assert EVALUATION_SCHEMA_VERSION == "quantara_feature_evaluation_v1"


def test_frozen_identity_vector_evaluation_schema_fingerprint() -> None:
    val_fp = validation_schema_fingerprint()
    assert val_fp == FROZEN_VALIDATION_FP
    eval_fp = evaluation_schema_fingerprint(parent_validation_fingerprint=val_fp)
    assert eval_fp == FROZEN_EVALUATION_FP
    # No-argument default matches
    assert evaluation_schema_fingerprint() == FROZEN_EVALUATION_FP


def test_predecessors_unchanged() -> None:
    assert (
        schema_fingerprint()
        == "feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8"
    )
    assert (
        research_schema_fingerprint()
        == "89e5bad5b2c825b60adf5585aec4edc01426062d69d5c6bfeead14487171908e"
    )
    assert validation_schema_fingerprint() == FROZEN_VALIDATION_FP


def test_evaluation_schema_fingerprint_sensitivity() -> None:
    base = evaluation_schema_fingerprint()
    assert len(base) == 64
    assert base != schema_fingerprint()
    assert base != research_schema_fingerprint()
    assert base != validation_schema_fingerprint()

    # Sensitivity to schema_id
    assert base != evaluation_schema_fingerprint(schema_id="other_schema")
    # Sensitivity to evaluation_set
    assert base != evaluation_schema_fingerprint(
        evaluation_set={"name": "other_set", "version": "1"}
    )
    assert base != evaluation_schema_fingerprint(
        evaluation_set={"name": "btcusdt_core_v1_dual_ic_v1", "version": "2"}
    )
    # Sensitivity to features
    assert base != evaluation_schema_fingerprint(features=["f_ret_1", "f_roc_60"])
    # Sensitivity to target
    assert base != evaluation_schema_fingerprint(target="l_fwdret_12")
    # Sensitivity to metrics
    assert base != evaluation_schema_fingerprint(metrics=["pearson_ic"])
    # Sensitivity to parent validation fingerprint
    assert base != evaluation_schema_fingerprint(
        parent_validation_fingerprint="0" * 64
    )


def test_evaluation_schema_fingerprint_requires_lowercase_parent() -> None:
    upper = FROZEN_VALIDATION_FP.upper()
    with pytest.raises(HashPayloadError):
        evaluation_schema_fingerprint(parent_validation_fingerprint=upper)

    with pytest.raises(HashPayloadError):
        evaluation_schema_fingerprint(parent_validation_fingerprint="not_hex")

    with pytest.raises(HashPayloadError):
        evaluation_schema_fingerprint(parent_validation_fingerprint="abc")


def test_evaluation_content_hash_determinism_and_types() -> None:
    fp = evaluation_schema_fingerprint()
    artifact = {
        "schema": "quantara.feature_evaluation/v1",
        "dataset_id": "test_evaluation_dataset",
        "records": [],
    }
    h1 = evaluation_content_hash(fp, artifact)
    assert len(h1) == 64
    assert h1 == evaluation_content_hash(fp, artifact)

    # String and bytes forms match
    canonical_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
    canonical_str = canonical_bytes.decode("utf-8")
    assert h1 == evaluation_content_hash(fp, canonical_str)
    assert h1 == evaluation_content_hash(fp, canonical_bytes)

    # Domain separation from validation content hash
    assert h1 != validation_content_hash(fp, canonical_bytes)

    # Sensitivity to content
    artifact_diff = dict(artifact, dataset_id="different_id")
    assert h1 != evaluation_content_hash(fp, artifact_diff)

    # Sensitivity to fingerprint
    assert h1 != evaluation_content_hash("0" * 64, artifact)

    # Rejection of uppercase fingerprint
    with pytest.raises(HashPayloadError):
        evaluation_content_hash(fp.upper(), artifact)

    # Rejection of unsupported type
    with pytest.raises(HashPayloadError):
        evaluation_content_hash(fp, 12345)  # type: ignore[arg-type]


def test_evaluation_commit_identity() -> None:
    content_hash = "7" * 64
    lineage = {"parent_commit": "abc"}
    cid = evaluation_commit_identity(content_hash, lineage)
    assert len(cid) == 64
    assert cid == evaluation_commit_identity(content_hash, lineage)

    # Sensitivity to content_hash
    assert cid != evaluation_commit_identity("8" * 64, lineage)
    # Sensitivity to lineage
    assert cid != evaluation_commit_identity(content_hash, {"parent_commit": "def"})

    # Lowercase requirement
    with pytest.raises(HashPayloadError):
        evaluation_commit_identity(("a" * 64).upper(), lineage)

    # Type checks
    with pytest.raises(HashPayloadError):
        evaluation_commit_identity(content_hash, "not_a_dict")  # type: ignore[arg-type]
