"""Dual-IC feature evaluation pipeline (data slice 006).

Consumes authenticated Q1 research and validation parents, computes deterministic
Pearson and Spearman information coefficients across out-of-sample walk-forward
folds, applies PASS-only quality gating, and publishes content-addressed evaluation
artifacts under exclusive lock ownership with truthful attempt evidence.
"""

from __future__ import annotations

from quantara.evaluation_descriptor import EvaluationDescriptor
from quantara.evaluation_metrics import DECIMAL_CONTRACT
from quantara.hashing import HashPayloadError, sha256_hex
from quantara.jcs import canonicalize

__all__ = [
    "DISCLAIMER",
    "EVALUATION_ARTIFACT_SCHEMA",
    "EVALUATION_EVIDENCE_KEYS",
    "build_evaluation_artifact",
    "evaluation_commit_identity",
]

DISCLAIMER = (
    "internal descriptive analysis only; no model, signal, backtest, "
    "significance, or performance claim"
)
EVALUATION_ARTIFACT_SCHEMA = "quantara.feature_evaluation/v1"

EVALUATION_EVIDENCE_KEYS: tuple[str, ...] = (
    "descriptor_sha256",
    "schema_fingerprint",
    "parser_version",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "evaluation_from",
    "evaluation_commit_identity",
)


def evaluation_commit_identity(canonical_content_hash: str, evaluation_from: dict) -> str:
    """Deterministic evaluation commit address (design §9.4).

    Domain-separated SHA-256 over JCS of ``{domain, canonical_content_hash,
    evaluation_from}``: the logical evaluation artifact content bound to the
    authenticated parent lineage evidence.
    """
    if (
        not isinstance(canonical_content_hash, str)
        or len(canonical_content_hash) != 64
        or any(c not in "0123456789abcdef" for c in canonical_content_hash)
    ):
        raise HashPayloadError(
            "canonical_content_hash must be a 64-character lowercase hex digest"
        )
    if not isinstance(evaluation_from, dict):
        raise HashPayloadError("evaluation_from must be a dict")
    payload = {
        "domain": "quantara-evaluation-commit-identity-v1",
        "canonical_content_hash": canonical_content_hash,
        "evaluation_from": evaluation_from,
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


def build_evaluation_artifact(
    descriptor: EvaluationDescriptor,
    validation_parent_info: dict,
    research_parent_info: dict,
    records: list[dict],
    summaries: list[dict],
) -> dict:
    """Build the canonical evaluation artifact document (design §9)."""
    return {
        "schema": EVALUATION_ARTIFACT_SCHEMA,
        "dataset_id": descriptor.dataset_id,
        "provider": descriptor.provider,
        "instrument_id": descriptor.instrument_id,
        "period": {
            "start": descriptor.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": descriptor.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "evaluation_set": dict(descriptor.evaluation_set),
        "validation_parent": {
            "dataset_id": validation_parent_info["dataset_id"],
            "commit_address": validation_parent_info["commit_address"],
            "canonical_content_hash": validation_parent_info["canonical_content_hash"],
            "artifact_sha256": validation_parent_info["artifact_sha256"],
            "artifact_size": validation_parent_info["artifact_size"],
        },
        "research_parent": {
            "dataset_id": research_parent_info["dataset_id"],
            "commit_address": research_parent_info["commit_address"],
            "canonical_content_hash": research_parent_info["canonical_content_hash"],
            "parquet_sha256": research_parent_info["parquet_sha256"],
            "parquet_size": research_parent_info["parquet_size"],
        },
        "features": list(descriptor.features),
        "target": descriptor.target,
        "metrics": list(descriptor.metrics),
        "decimal_contract": dict(DECIMAL_CONTRACT),
        "records": records,
        "summaries": summaries,
        "disclaimer": DISCLAIMER,
    }

