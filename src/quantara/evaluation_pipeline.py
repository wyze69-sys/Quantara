"""Dual-IC feature evaluation pipeline (data slice 006).

Consumes authenticated Q1 research and validation parents, computes deterministic
Pearson and Spearman information coefficients across out-of-sample walk-forward
folds, applies PASS-only quality gating, and publishes content-addressed evaluation
artifacts under exclusive lock ownership with truthful attempt evidence.
"""

from __future__ import annotations

from quantara.hashing import HashPayloadError, sha256_hex
from quantara.jcs import canonicalize

__all__ = [
    "EVALUATION_EVIDENCE_KEYS",
    "evaluation_commit_identity",
]

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
