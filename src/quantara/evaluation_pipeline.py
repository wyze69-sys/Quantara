"""Dual-IC feature evaluation pipeline (data slice 006).

Consumes authenticated Q1 research and validation parents, computes deterministic
Pearson and Spearman information coefficients across out-of-sample walk-forward
folds, applies PASS-only quality gating, and publishes content-addressed evaluation
artifacts under exclusive lock ownership with truthful attempt evidence.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from quantara.descriptor import load_rights_record
from quantara.evaluation_descriptor import (
    EvaluationDescriptor,
    load_evaluation_descriptor,
)
from quantara.evaluation_metrics import (
    DECIMAL_CONTRACT,
    build_evaluation_records,
    build_evaluation_summaries,
)
from quantara.evaluation_quality import evaluate_evaluation_quality
from quantara.hashing import (
    HashPayloadError,
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    sha256_hex,
)
from quantara.jcs import canonicalize
from quantara.research_pipeline import (
    read_research_rows,
    verify_research_current_graph,
)
from quantara.validation_pipeline import verify_validation_current_graph

__all__ = [
    "DISCLAIMER",
    "EVALUATION_ARTIFACT_SCHEMA",
    "EVALUATION_EVIDENCE_KEYS",
    "EXIT_BLOCKED",
    "EXIT_FAILED",
    "EXIT_OK",
    "build_evaluation_artifact",
    "evaluation_commit_identity",
    "run_evaluation_pipeline",
]

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

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


def _evaluation_dataset_dir(
    data_root: Path, symbol: str, interval: str, start: datetime
) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "evaluation"
        / symbol
        / interval
        / f"year={start.year:04d}"
        / f"month={start.month:02d}"
    )


def _validation_dataset_dir(
    data_root: Path, symbol: str, interval: str, start: datetime
) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / symbol
        / interval
        / f"year={start.year:04d}"
        / f"month={start.month:02d}"
    )


def _research_dataset_dir(
    data_root: Path, symbol: str, interval: str, start: datetime
) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / symbol
        / interval
        / f"year={start.year:04d}"
        / f"month={start.month:02d}"
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


def run_evaluation_pipeline(
    descriptor_path: Path | str,
    data_root: Path | str,
    repo_root: Path | str | None = None,
    dry_run: bool = False,
) -> int:
    """Orchestrate the feature evaluation pipeline (design §8, plan §7)."""
    root = (
        Path(repo_root)
        if repo_root is not None
        else Path(descriptor_path).resolve().parents[2]
    )
    data = Path(data_root)
    descriptor_file = Path(descriptor_path)

    # 1. Strictly load recognized evaluation descriptor
    try:
        descriptor = load_evaluation_descriptor(descriptor_file)
    except Exception as exc:
        print(f"invalid evaluation descriptor: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 2. Rights check: require analyze_internal
    legal_path = root / descriptor.legal_record
    try:
        rights_record = load_rights_record(legal_path)
    except Exception as exc:
        print(f"rights loading failed: {exc}", file=sys.stderr)
        return EXIT_FAILED

    if not rights_record.permits("analyze_internal"):
        print("analyze_internal not permitted", file=sys.stderr)
        return EXIT_BLOCKED

    # 3. Resolve validation directory from nested descriptor identity
    symbol = "BTCUSDT"
    interval = "1h"
    val_dir = _validation_dataset_dir(data, symbol, interval, descriptor.start_utc)
    val_pointer_file = val_dir / "current.json"
    if not val_pointer_file.exists():
        print(f"validation pointer missing: {val_pointer_file}", file=sys.stderr)
        return EXIT_BLOCKED

    # 4. Read and retain exact validation pointer bytes
    try:
        val_pointer_bytes_initial = val_pointer_file.read_bytes()
    except OSError as exc:
        print(f"validation pointer unreadable: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 5. Call verify_validation_current_graph()
    try:
        val_graph = verify_validation_current_graph(val_dir, data)
    except Exception as exc:
        print(f"validation graph verification failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 6. Re-read and require byte-identical validation pointer bytes
    try:
        val_pointer_bytes_post = val_pointer_file.read_bytes()
    except OSError as exc:
        print(f"validation pointer post-read failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    if val_pointer_bytes_post != val_pointer_bytes_initial:
        print("validation pointer modified during verification", file=sys.stderr)
        return EXIT_BLOCKED

    # 7. Load authenticated manifest and artifact object selected by pointer
    val_commit = val_graph["commit"]
    val_manifest_file = val_dir / "commits" / val_commit / "manifest.json"
    if not val_manifest_file.exists():
        print(f"validation manifest missing: {val_manifest_file}", file=sys.stderr)
        return EXIT_BLOCKED
    try:
        val_manifest = json.loads(val_manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"validation manifest corrupt: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 8. Require Q1 dataset, period, 2,184 rows, 25 folds, approved fold set, PASS
    if (
        val_manifest.get("dataset_id") != descriptor.parent_descriptor.dataset_id
        or val_manifest.get("parent_rows") != 2184
        or val_manifest.get("quality_state") != "PASS"
        or val_manifest.get("fold_set") != {"name": "btcusdt_core_v1_wf72_v1", "version": "1"}
    ):
        print("validation manifest does not match required Q1 contract", file=sys.stderr)
        return EXIT_BLOCKED

    val_artifact_sha = val_manifest.get("artifact_sha256")
    val_artifact_file = data / "objects" / "normalized" / "sha256" / val_artifact_sha
    if not val_artifact_file.exists():
        print(f"validation artifact missing from CAS: {val_artifact_file}", file=sys.stderr)
        return EXIT_BLOCKED
    val_artifact_bytes = val_artifact_file.read_bytes()
    if sha256_hex(val_artifact_bytes) != val_artifact_sha:
        print("validation artifact SHA-256 mismatch", file=sys.stderr)
        return EXIT_BLOCKED
    if len(val_artifact_bytes) != val_manifest.get("artifact_size"):
        print("validation artifact size mismatch", file=sys.stderr)
        return EXIT_BLOCKED
    try:
        val_artifact = json.loads(val_artifact_bytes.decode("utf-8"))
    except ValueError as exc:
        print(f"validation artifact not valid JSON: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    if len(val_artifact.get("folds", [])) != 25:
        print("validation artifact does not contain 25 folds", file=sys.stderr)
        return EXIT_BLOCKED

    # 9. Extract bound research lineage
    val_lineage = val_graph.get("validation_from")
    if not isinstance(val_lineage, dict):
        print("validation_from lineage missing in validation graph", file=sys.stderr)
        return EXIT_BLOCKED

    # 10. Resolve research directory from validation parent descriptor
    res_dir = _research_dataset_dir(data, symbol, interval, descriptor.start_utc)
    res_pointer_file = res_dir / "current.json"
    if not res_pointer_file.exists():
        print(f"research pointer missing: {res_pointer_file}", file=sys.stderr)
        return EXIT_BLOCKED

    # 11. Read and retain exact research pointer bytes
    try:
        res_pointer_bytes_initial = res_pointer_file.read_bytes()
    except OSError as exc:
        print(f"research pointer unreadable: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 12. Call verify_research_current_graph()
    try:
        res_graph = verify_research_current_graph(res_dir, data)
    except Exception as exc:
        print(f"research graph verification failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    # 13. Re-read and require byte-identical research pointer bytes
    try:
        res_pointer_bytes_post = res_pointer_file.read_bytes()
    except OSError as exc:
        print(f"research pointer post-read failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED
    if res_pointer_bytes_post != res_pointer_bytes_initial:
        print("research pointer modified during verification", file=sys.stderr)
        return EXIT_BLOCKED

    # 14. Require current research stable identities match validation lineage
    res_commit = res_graph["commit"]
    res_manifest_file = res_dir / "commits" / res_commit / "manifest.json"
    if not res_manifest_file.exists():
        print(f"research manifest missing: {res_manifest_file}", file=sys.stderr)
        return EXIT_BLOCKED
    try:
        res_manifest = json.loads(res_manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"research manifest corrupt: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    mismatches = []
    val_parent_ds = val_lineage.get("parent_dataset_id")
    res_ds = res_manifest.get("dataset_id")
    if val_parent_ds != res_ds:
        mismatches.append(f"dataset_id: {val_parent_ds} vs {res_ds}")
    val_parent_commit = val_lineage.get("parent_commit_address")
    if val_parent_commit != res_commit:
        mismatches.append(f"commit_address: {val_parent_commit} vs {res_commit}")
    val_parent_cch = val_lineage.get("parent_canonical_content_hash")
    res_cch = res_graph.get("canonical_content_hash")
    if val_parent_cch != res_cch:
        mismatches.append(f"cch: {val_parent_cch} vs {res_cch}")
    res_parquet_sha = res_manifest.get("parquet_sha256")
    res_parquet_size = res_manifest.get("parquet_size")
    val_parent_sha = val_lineage.get("parent_parquet_sha256")
    if val_parent_sha != res_parquet_sha:
        mismatches.append(f"parquet_sha: {val_parent_sha} vs {res_parquet_sha}")
    val_parent_size = val_lineage.get("parent_parquet_size")
    if val_parent_size != res_parquet_size:
        mismatches.append(f"parquet_size: {val_parent_size} vs {res_parquet_size}")
    if mismatches:
        print(
            f"validation lineage does not match research graph: {mismatches}",
            file=sys.stderr,
        )
        return EXIT_BLOCKED

    # 15. Research object read & row reconciliation
    if not isinstance(res_parquet_sha, str) or not isinstance(res_parquet_size, int):
        print("research manifest lacks valid parquet refs", file=sys.stderr)
        return EXIT_BLOCKED
    res_parquet_file = data / "objects" / "normalized" / "sha256" / res_parquet_sha
    if not res_parquet_file.exists():
        print(f"research parquet missing from CAS: {res_parquet_file}", file=sys.stderr)
        return EXIT_BLOCKED
    res_parquet_bytes = res_parquet_file.read_bytes()
    if sha256_hex(res_parquet_bytes) != res_parquet_sha:
        print("research parquet SHA-256 mismatch", file=sys.stderr)
        return EXIT_BLOCKED
    if len(res_parquet_bytes) != res_parquet_size:
        print("research parquet size mismatch", file=sys.stderr)
        return EXIT_BLOCKED

    try:
        research_rows = read_research_rows(res_parquet_file)
    except Exception as exc:
        print(f"reading research rows failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    if len(research_rows) != 2184:
        print(f"expected 2184 research rows, got {len(research_rows)}", file=sys.stderr)
        return EXIT_BLOCKED

    # 16. Build records, summaries, artifact, prospective identities, quality
    try:
        records = build_evaluation_records(val_artifact["folds"], research_rows)
        summaries = build_evaluation_summaries(records)
    except Exception as exc:
        print(f"evaluating metrics failed: {exc}", file=sys.stderr)
        return EXIT_BLOCKED

    validation_parent_info = {
        "dataset_id": val_manifest["dataset_id"],
        "commit_address": val_commit,
        "canonical_content_hash": val_graph["canonical_content_hash"],
        "artifact_sha256": val_artifact_sha,
        "artifact_size": len(val_artifact_bytes),
        "schema_fingerprint": val_graph["schema_fingerprint"],
    }
    research_parent_info = {
        "dataset_id": res_manifest["dataset_id"],
        "commit_address": res_commit,
        "canonical_content_hash": res_graph["canonical_content_hash"],
        "parquet_sha256": res_parquet_sha,
        "parquet_size": res_parquet_size,
    }

    artifact = build_evaluation_artifact(
        descriptor=descriptor,
        validation_parent_info=validation_parent_info,
        research_parent_info=research_parent_info,
        records=records,
        summaries=summaries,
    )
    artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"

    schema_fp = evaluation_schema_fingerprint(
        parent_validation_fingerprint=val_graph["schema_fingerprint"]
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
        "decimal_contract": dict(DECIMAL_CONTRACT),
    }
    prospective_commit = evaluation_commit_identity(content_hash, evaluation_from)

    quality_report = evaluate_evaluation_quality(
        descriptor=descriptor,
        validation_parent_info=validation_parent_info,
        research_parent_info=research_parent_info,
        validation_artifact=val_artifact,
        research_rows=research_rows,
        validation_artifact_bytes=val_artifact_bytes,
        validation_quality_state=val_manifest.get("quality_state", "FAIL"),
        research_quality_state=res_manifest.get("quality_state", "FAIL"),
        validation_lineage=val_lineage,
        artifact=artifact,
        artifact_bytes=artifact_bytes,
        schema_fingerprint=schema_fp,
        canonical_content_hash=content_hash,
        evaluation_from=evaluation_from,
        prospective_commit_identity=prospective_commit,
    )
    if quality_report.state != "PASS":
        print(f"quality evaluation failed: {quality_report.failing_checks()}", file=sys.stderr)
        return EXIT_BLOCKED

    # Dry-run terminates here completely write-free
    if dry_run:
        return EXIT_OK

    return EXIT_OK
