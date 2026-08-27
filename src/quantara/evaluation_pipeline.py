"""Dual-IC feature evaluation pipeline (data slice 006).

Consumes authenticated Q1 research and validation parents, computes deterministic
Pearson and Spearman information coefficients across out-of-sample walk-forward
folds, applies PASS-only quality gating, and publishes content-addressed evaluation
artifacts under exclusive lock ownership with truthful attempt evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantara.descriptor import load_rights_record
from quantara.errors import QuantaraError
from quantara.evaluation_descriptor import (
    EvaluationDescriptor,
    load_evaluation_descriptor,
)
from quantara.evaluation_metrics import (
    DECIMAL_CONTRACT,
    build_evaluation_records,
    build_evaluation_summaries,
)
from quantara.evaluation_quality import (
    CHECK_IDS,
    QUALITY_POLICY_VERSION,
    evaluate_evaluation_quality,
)
from quantara.hashing import (
    HashPayloadError,
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    quality_identity,
    research_content_hash,
    research_schema_fingerprint,
    sha256_hex,
    validation_content_hash,
    validation_schema_fingerprint,
)
from quantara.jcs import canonicalize
from quantara.manifests import (
    attempt_id_now,
    environment_evidence,
    new_attempt_manifest,
    write_json,
)
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    stage_commit,
    store_object,
    verify_commit_graph,
    write_current,
)
from quantara.research_pipeline import (
    read_research_rows,
    render_content_rows,
    research_commit_identity,
    verify_research_current_graph,
)
from quantara.validation_pipeline import (
    validation_commit_identity,
    verify_validation_current_graph,
)

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
    "verify_evaluation_current_graph",
]

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

# --- Exact Q1 half-open validation-period contract (requirement 6) ------------

APPROVED_Q1_PERIOD: dict[str, str] = {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-04-01T00:00:00Z",
}
Q1_START_EPOCH_MS = 1704067200000  # 2024-01-01T00:00:00Z inclusive
Q1_END_EXCLUSIVE_EPOCH_MS = 1711929600000  # 2024-04-01T00:00:00Z exclusive
HOUR_MS = 3_600_000
_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=UTC)


def _epoch_ms(moment: datetime) -> int:
    """Exact integer epoch milliseconds (no binary float arithmetic)."""
    return (moment.astimezone(UTC) - _EPOCH_UTC) // timedelta(milliseconds=1)


def verify_validation_parent_q1_period(
    *,
    descriptor_start_utc: datetime,
    descriptor_end_utc: datetime,
    val_manifest: dict,
    val_artifact: dict,
    research_rows: Sequence[Sequence],
) -> None:
    """Authenticate the validation parent's exact Q1 half-open period and its
    required timestamp/cadence endpoints against authenticated research rows.

    Raises QuantaraError on any mismatch; returns silently on full agreement.
    """
    start_ms = _epoch_ms(descriptor_start_utc)
    end_ms = _epoch_ms(descriptor_end_utc)
    if start_ms != Q1_START_EPOCH_MS or end_ms != Q1_END_EXCLUSIVE_EPOCH_MS:
        raise QuantaraError(
            "validation parent period is not the exact half-open Q1 2024 window"
        )
    if start_ms >= end_ms:
        raise QuantaraError("half-open period must satisfy start < end")

    manifest_period = val_manifest.get("period")
    if manifest_period is not None and manifest_period != APPROVED_Q1_PERIOD:
        raise QuantaraError(
            f"validation parent manifest period {manifest_period!r} is not "
            f"the approved half-open window {APPROVED_Q1_PERIOD!r}"
        )

    excluded_head_rows = val_artifact.get("excluded_head_rows")
    folds = val_artifact.get("folds")
    if not isinstance(excluded_head_rows, int) or isinstance(excluded_head_rows, bool):
        raise QuantaraError("validation artifact lacks integer excluded_head_rows")
    if not isinstance(folds, list) or len(folds) != 25:
        raise QuantaraError("validation artifact must contain exactly 25 folds")

    row_count = len(research_rows)
    ordered_ranges = []
    for fold in sorted(folds, key=lambda item: item["test_range"][0]):
        fold_range = fold.get("test_range")
        if (
            not isinstance(fold_range, list)
            or len(fold_range) != 2
            or any(isinstance(x, bool) or not isinstance(x, int) for x in fold_range)
            or fold_range[0] >= fold_range[1]
        ):
            raise QuantaraError(f"invalid fold test_range {fold_range!r}")
        ordered_ranges.append((fold_range[0], fold_range[1]))

    cursor = excluded_head_rows
    for begin, end in ordered_ranges:
        if begin != cursor:
            raise QuantaraError(
                f"fold test ranges do not tile contiguously from excluded head "
                f"(expected start {cursor}, found {begin})"
            )
        cursor = end
    if cursor != row_count:
        raise QuantaraError(
            f"fold test ranges stop at row {cursor}, expected {row_count}"
        )

    first_index = ordered_ranges[0][0]
    last_index = ordered_ranges[-1][1] - 1

    # Hourly cadence across the entire tested span.
    for index in range(first_index, last_index):
        if research_rows[index + 1][0] - research_rows[index][0] != HOUR_MS:
            raise QuantaraError(
                f"hourly cadence broken at tested row {index}"
            )

    expected_first_ts = start_ms + excluded_head_rows * HOUR_MS
    expected_last_ts = end_ms - HOUR_MS
    if research_rows[first_index][0] != expected_first_ts:
        raise QuantaraError(
            f"tested-window start timestamp {research_rows[first_index][0]} "
            f"!= required {expected_first_ts}"
        )
    if research_rows[last_index][0] != expected_last_ts:
        raise QuantaraError(
            f"tested-window end timestamp {research_rows[last_index][0]} "
            f"!= half-open exclusive-end predecessor {expected_last_ts}"
        )

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

EXPECTED_ARTIFACT_KEYS: frozenset[str] = frozenset(
    {
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
)

EXPECTED_EVALUATION_FROM_KEYS: frozenset[str] = frozenset(
    {
        "validation_dataset_id",
        "validation_commit_address",
        "validation_canonical_content_hash",
        "validation_artifact_sha256",
        "validation_artifact_size",
        "research_dataset_id",
        "research_commit_address",
        "research_canonical_content_hash",
        "research_parquet_sha256",
        "research_parquet_size",
        "evaluation_set_name",
        "evaluation_set_version",
        "features",
        "target",
        "metrics",
        "decimal_contract",
    }
)


def _evaluation_dataset_dir(data_root: Path, symbol: str, interval: str, start: datetime) -> Path:
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


def _validation_dataset_dir(data_root: Path, symbol: str, interval: str, start: datetime) -> Path:
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


def _research_dataset_dir(data_root: Path, symbol: str, interval: str, start: datetime) -> Path:
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


def _write_attempt(
    data_root: Path,
    repo_root: Path,
    *,
    attempt_id: str,
    terminal_result: str,
    dispositions: dict[str, str | bool | None],
    referenced_commit: str | None,
    diagnostics: list[str],
) -> None:
    attempt = new_attempt_manifest(
        attempt_id=attempt_id,
        terminal_result=terminal_result,
        artifact_dispositions=dispositions,
        retry_evidence=[],
        http_statuses=[],
        referenced_commit=referenced_commit,
        diagnostics=diagnostics,
        repo_root=repo_root,
    )
    attempts_dir = Path(data_root) / "attempts" / "evaluation"
    target = attempts_dir / f"{attempt['attempt_id']}.json"
    try:
        attempts_dir.mkdir(parents=True, exist_ok=True)
        write_json(target, attempt)
    except OSError as exc:
        print(f"failed to record attempt manifest {target}: {exc}", file=sys.stderr)


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
        raise HashPayloadError("canonical_content_hash must be a 64-character lowercase hex digest")
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
    root = Path(repo_root) if repo_root is not None else Path(descriptor_path).resolve().parents[2]
    data = Path(data_root)
    descriptor_file = Path(descriptor_path)

    # One invocation identity for the whole non-dry-run invocation: lock
    # ownership, staging paths, cleanup ownership, and every attempt manifest.
    attempt_id = attempt_id_now()

    def _pre_attempt(
        terminal_result: str,
        diagnostic: str | list[str],
        referenced: str | None = None,
    ) -> None:
        if not dry_run:
            diagnostics_list = [diagnostic] if isinstance(diagnostic, str) else list(diagnostic)
            _write_attempt(
                data,
                root,
                attempt_id=attempt_id,
                terminal_result=terminal_result,
                dispositions={
                    "evaluation_artifact": "not_written",
                    "lock_acquired": False,
                    "lock_released": False,
                    "lock_cleanup": "none",
                    "attempt_staged": False,
                    "object_written": False,
                    "commit_renamed": False,
                    "pointer_replaced": False,
                    "discovery_verified": False,
                    "attempt_staging": "not_staged",
                },
                referenced_commit=referenced,
                diagnostics=diagnostics_list,
            )

    # 1. Strictly load recognized evaluation descriptor
    try:
        descriptor = load_evaluation_descriptor(descriptor_file)
    except Exception as exc:
        print(f"invalid evaluation descriptor: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "invalid_descriptor")
        return EXIT_BLOCKED

    # 2. Rights check: require analyze_internal
    legal_path = root / descriptor.legal_record
    try:
        rights_record = load_rights_record(legal_path)
    except Exception as exc:
        print(f"rights loading failed: {exc}", file=sys.stderr)
        _pre_attempt("FAILED", "rights_loading_failed")
        return EXIT_FAILED

    if not rights_record.permits("analyze_internal"):
        print("analyze_internal not permitted", file=sys.stderr)
        _pre_attempt("BLOCKED", "legal_not_permitted")
        return EXIT_BLOCKED

    # 3. Resolve validation directory from nested descriptor identity
    symbol = "BTCUSDT"
    interval = "1h"
    val_dir = _validation_dataset_dir(data, symbol, interval, descriptor.start_utc)
    val_pointer_file = val_dir / "current.json"
    if not val_pointer_file.exists():
        print(f"validation pointer missing: {val_pointer_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_validation_pointer")
        return EXIT_BLOCKED

    # 4. Read and retain exact validation pointer bytes
    try:
        val_pointer_bytes_initial = val_pointer_file.read_bytes()
    except OSError as exc:
        print(f"validation pointer unreadable: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "unreadable_validation_pointer")
        return EXIT_BLOCKED

    # 5. Call verify_validation_current_graph()
    try:
        val_graph = verify_validation_current_graph(val_dir, data)
    except Exception as exc:
        print(f"validation graph verification failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_graph_verification_failed")
        return EXIT_BLOCKED

    # 6. Re-read and require byte-identical validation pointer bytes
    try:
        val_pointer_bytes_post = val_pointer_file.read_bytes()
    except OSError as exc:
        print(f"validation pointer post-read failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "unreadable_validation_pointer_post")
        return EXIT_BLOCKED
    if val_pointer_bytes_post != val_pointer_bytes_initial:
        print("validation pointer modified during verification", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_pointer_modified")
        return EXIT_BLOCKED

    # 7. Load authenticated manifest and artifact object selected by pointer
    val_commit = val_graph["commit"]
    val_manifest_file = val_dir / "commits" / val_commit / "manifest.json"
    if not val_manifest_file.exists():
        print(f"validation manifest missing: {val_manifest_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_validation_manifest")
        return EXIT_BLOCKED
    try:
        val_manifest = json.loads(val_manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"validation manifest corrupt: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "corrupt_validation_manifest")
        return EXIT_BLOCKED

    # 8. Require Q1 dataset, 2,184 rows, 25 folds, approved fold set, PASS
    val_parent_rows = val_manifest.get("parent_row_count", val_manifest.get("parent_rows"))
    if (
        val_manifest.get("dataset_id") != descriptor.parent_descriptor.dataset_id
        or val_parent_rows != 2184
        or val_manifest.get("quality_state") != "PASS"
        or val_manifest.get("fold_set") != {"name": "btcusdt_core_v1_wf72_v1", "version": "1"}
    ):
        print("validation manifest does not match required Q1 contract", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_manifest_contract_mismatch")
        return EXIT_BLOCKED

    val_artifact_sha = val_manifest.get("artifact_sha256")
    val_artifact_file = data / "objects" / "normalized" / "sha256" / val_artifact_sha
    if not val_artifact_file.exists():
        print(f"validation artifact missing from CAS: {val_artifact_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_validation_artifact_object")
        return EXIT_BLOCKED
    val_artifact_bytes = val_artifact_file.read_bytes()
    if sha256_hex(val_artifact_bytes) != val_artifact_sha:
        print("validation artifact SHA-256 mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_artifact_sha_mismatch")
        return EXIT_BLOCKED
    if len(val_artifact_bytes) != val_manifest.get("artifact_size"):
        print("validation artifact size mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_artifact_size_mismatch")
        return EXIT_BLOCKED

    # Freshly recompute validation schema fingerprint, content hash, commit identity
    try:
        expected_val_fp = validation_schema_fingerprint(
            parent_fingerprint=research_schema_fingerprint(
                descriptor.parent_descriptor.parent_descriptor.schema_version
            ),
            schema_id=descriptor.parent_descriptor.schema_version,
            scheme=descriptor.parent_descriptor.scheme,
            parameters=dict(
                descriptor.parent_descriptor.parameters,
                embargo=descriptor.parent_descriptor.embargo,
            ),
            fold_set_name=descriptor.parent_descriptor.fold_set["name"],
            fold_set_version=descriptor.parent_descriptor.fold_set["version"],
        )
    except Exception as exc:
        print(f"failed to recompute validation schema fingerprint: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_schema_fingerprint_recomputation_failed")
        return EXIT_BLOCKED

    if expected_val_fp != val_graph["schema_fingerprint"]:
        print("validation schema fingerprint mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_schema_fingerprint_mismatch")
        return EXIT_BLOCKED

    recomputed_val_cch = validation_content_hash(expected_val_fp, val_artifact_bytes)
    if recomputed_val_cch != val_graph["canonical_content_hash"]:
        print("validation canonical content hash mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_content_hash_mismatch")
        return EXIT_BLOCKED

    recomputed_val_commit = validation_commit_identity(
        recomputed_val_cch, val_graph["validation_from"]
    )
    if recomputed_val_commit != val_commit:
        print("validation commit identity mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_commit_identity_mismatch")
        return EXIT_BLOCKED

    try:
        val_artifact = json.loads(val_artifact_bytes.decode("utf-8"))
    except ValueError as exc:
        print(f"validation artifact not valid JSON: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "invalid_validation_artifact_json")
        return EXIT_BLOCKED

    if len(val_artifact.get("folds", [])) != 25:
        print("validation artifact does not contain 25 folds", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_fold_count_mismatch")
        return EXIT_BLOCKED

    # 9. Extract bound research lineage
    val_lineage = val_graph.get("validation_from")
    if not isinstance(val_lineage, dict):
        print("validation_from lineage missing in validation graph", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_validation_lineage")
        return EXIT_BLOCKED

    # 10. Resolve research directory from validation parent descriptor
    res_dir = _research_dataset_dir(data, symbol, interval, descriptor.start_utc)
    res_pointer_file = res_dir / "current.json"
    if not res_pointer_file.exists():
        print(f"research pointer missing: {res_pointer_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_research_pointer")
        return EXIT_BLOCKED

    # 11. Read and retain exact research pointer bytes
    try:
        res_pointer_bytes_initial = res_pointer_file.read_bytes()
    except OSError as exc:
        print(f"research pointer unreadable: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "unreadable_research_pointer")
        return EXIT_BLOCKED

    # 12. Call verify_research_current_graph()
    try:
        res_graph = verify_research_current_graph(res_dir, data)
    except Exception as exc:
        print(f"research graph verification failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_graph_verification_failed")
        return EXIT_BLOCKED

    # 13. Re-read and require byte-identical research pointer bytes
    try:
        res_pointer_bytes_post = res_pointer_file.read_bytes()
    except OSError as exc:
        print(f"research pointer post-read failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "unreadable_research_pointer_post")
        return EXIT_BLOCKED
    if res_pointer_bytes_post != res_pointer_bytes_initial:
        print("research pointer modified during verification", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_pointer_modified")
        return EXIT_BLOCKED

    # 14. Require current research stable identities match validation lineage
    res_commit = res_graph["commit"]
    res_manifest_file = res_dir / "commits" / res_commit / "manifest.json"
    if not res_manifest_file.exists():
        print(f"research manifest missing: {res_manifest_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_research_manifest")
        return EXIT_BLOCKED
    try:
        res_manifest = json.loads(res_manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"research manifest corrupt: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "corrupt_research_manifest")
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
        _pre_attempt("BLOCKED", "lineage_mismatch")
        return EXIT_BLOCKED

    # 15. Research object read & row reconciliation
    if not isinstance(res_parquet_sha, str) or not isinstance(res_parquet_size, int):
        print("research manifest lacks valid parquet refs", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_parquet_refs")
        return EXIT_BLOCKED
    res_parquet_file = data / "objects" / "normalized" / "sha256" / res_parquet_sha
    if not res_parquet_file.exists():
        print(f"research parquet missing from CAS: {res_parquet_file}", file=sys.stderr)
        _pre_attempt("BLOCKED", "missing_research_parquet_object")
        return EXIT_BLOCKED
    res_parquet_bytes = res_parquet_file.read_bytes()
    if sha256_hex(res_parquet_bytes) != res_parquet_sha:
        print("research parquet SHA-256 mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_parquet_sha_mismatch")
        return EXIT_BLOCKED
    if len(res_parquet_bytes) != res_parquet_size:
        print("research parquet size mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_parquet_size_mismatch")
        return EXIT_BLOCKED

    try:
        research_rows = read_research_rows(res_parquet_file)
    except Exception as exc:
        print(f"reading research rows failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "read_research_rows_failed")
        return EXIT_BLOCKED

    if len(research_rows) != 2184:
        print(f"expected 2184 research rows, got {len(research_rows)}", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_row_count_mismatch")
        return EXIT_BLOCKED

    # Freshly recompute research parent schema fingerprint, content hash, commit identity
    expected_res_fp = research_schema_fingerprint(res_manifest.get("schema_version"))
    if expected_res_fp != res_graph["schema_fingerprint"]:
        print("research schema fingerprint mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_schema_fingerprint_mismatch")
        return EXIT_BLOCKED

    recomputed_res_cch = research_content_hash(expected_res_fp, render_content_rows(research_rows))
    if recomputed_res_cch != res_graph["canonical_content_hash"]:
        print("research canonical content hash mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_content_hash_mismatch")
        return EXIT_BLOCKED

    recomputed_res_commit = research_commit_identity(
        recomputed_res_cch, res_manifest.get("research_from")
    )
    if recomputed_res_commit != res_commit:
        print("research commit identity mismatch", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_commit_identity_mismatch")
        return EXIT_BLOCKED

    # Exact Q1 period and research timestamp endpoints
    if research_rows[0][0] != 1704067200000 or research_rows[-1][0] != 1711926000000:
        print("research timestamp endpoints do not match Q1 2024", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_endpoints_mismatch")
        return EXIT_BLOCKED

    if not all(research_rows[i + 1][0] - research_rows[i][0] == 3600000 for i in range(2183)):
        print("research rows hourly cadence broken", file=sys.stderr)
        _pre_attempt("BLOCKED", "research_cadence_mismatch")
        return EXIT_BLOCKED

    # Exact Q1 half-open validation-period, timestamp, and cadence endpoints
    try:
        verify_validation_parent_q1_period(
            descriptor_start_utc=descriptor.start_utc,
            descriptor_end_utc=descriptor.end_utc,
            val_manifest=val_manifest,
            val_artifact=val_artifact,
            research_rows=research_rows,
        )
    except QuantaraError as exc:
        print(f"validation parent Q1 period authentication failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "validation_period_authentication_failed")
        return EXIT_BLOCKED

    # 16. Build records, summaries, artifact, prospective identities, quality
    try:
        records = build_evaluation_records(val_artifact["folds"], research_rows)
        summaries = build_evaluation_summaries(records)
    except Exception as exc:
        print(f"evaluating metrics failed: {exc}", file=sys.stderr)
        _pre_attempt("BLOCKED", "metric_evaluation_failed")
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
        failing = quality_report.failing_checks() or ["quality_failed"]
        _pre_attempt("BLOCKED", failing)
        return EXIT_BLOCKED

    # Dry-run terminates here completely write-free
    if dry_run:
        return EXIT_OK

    # 17. Non-dry-run publication setup
    eval_dir = _evaluation_dataset_dir(data, symbol, interval, descriptor.start_utc)
    eval_dir.mkdir(parents=True, exist_ok=True)
    commits_dir = eval_dir / "commits"
    commits_dir.mkdir(parents=True, exist_ok=True)

    staging_dir = eval_dir / "commits" / f".staging-{attempt_id}"
    staging_root = data / "staging" / f"attempt-{attempt_id}"

    milestones: dict[str, bool] = {
        "lock_acquired": False,
        "lock_released": False,
        "attempt_staged": False,
        "object_written": False,
        "commit_renamed": False,
        "pointer_replaced": False,
        "discovery_verified": False,
    }
    artifact_state = "not_written"
    cleanup_state: dict[str, str] = {"staging": "pending", "lock_cleanup": "pending"}

    def _cleanup_staging() -> None:
        ok = True
        for directory in (staging_dir, staging_root):
            try:
                if directory.exists():
                    shutil.rmtree(directory)
            except OSError:
                if directory.exists():
                    ok = False
        cleanup_state["staging"] = "discarded" if ok else "cleanup_failed"

    def _dispositions(extra: dict | None = None) -> dict:
        dispositions = {
            "evaluation_artifact": artifact_state,
            "lock_acquired": milestones["lock_acquired"],
            "lock_released": milestones["lock_released"],
            "lock_cleanup": cleanup_state["lock_cleanup"],
            "attempt_staged": milestones["attempt_staged"],
            "object_written": milestones["object_written"],
            "commit_renamed": milestones["commit_renamed"],
            "pointer_replaced": milestones["pointer_replaced"],
            "discovery_verified": milestones["discovery_verified"],
            "attempt_staging": cleanup_state["staging"],
        }
        if extra:
            dispositions.update(extra)
        return dispositions

    lock_path = eval_dir / "evaluation.lock"

    def _release_lock() -> None:
        if milestones.get("lock_acquired") and not milestones.get("lock_released"):
            try:
                if lock_path.exists():
                    lock_content = lock_path.read_text(encoding="utf-8")
                    try:
                        lock_data = json.loads(lock_content)
                        if (
                            isinstance(lock_data, dict)
                            and lock_data.get("attempt_id") == attempt_id
                        ):
                            lock_path.unlink()
                            milestones["lock_released"] = True
                            cleanup_state["lock_cleanup"] = "cleaned"
                        else:
                            cleanup_state["lock_cleanup"] = "cleanup_failed"
                    except ValueError:
                        cleanup_state["lock_cleanup"] = "cleanup_failed"
                else:
                    milestones["lock_released"] = True
                    cleanup_state["lock_cleanup"] = "cleaned"
            except Exception:
                cleanup_state["lock_cleanup"] = "cleanup_failed"

    def _write_terminal_attempt(
        terminal_result: str,
        referenced_commit: str | None,
        diagnostics: list[str],
        extra: dict | None = None,
    ) -> None:
        _release_lock()
        _write_attempt(
            data,
            root,
            attempt_id=attempt_id,
            terminal_result=terminal_result,
            dispositions=_dispositions(extra),
            referenced_commit=referenced_commit,
            diagnostics=diagnostics,
        )

    # 18. Lock acquisition (atomic create-if-absent, exact owner evidence)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"lock contested: {lock_path}", file=sys.stderr)
        cleanup_state["lock_cleanup"] = "none"
        cleanup_state["staging"] = "not_staged"
        _write_terminal_attempt("BLOCKED", None, ["lock_contested"])
        return EXIT_BLOCKED
    except OSError as exc:
        print(f"lock unavailable: {exc}", file=sys.stderr)
        cleanup_state["lock_cleanup"] = "none"
        cleanup_state["staging"] = "not_staged"
        _write_terminal_attempt("BLOCKED", None, ["lock_unavailable"])
        return EXIT_BLOCKED

    # The O_EXCL create succeeded: this lock file was created by THIS
    # invocation and no one else. Durable owner evidence must be established
    # before ownership counts; on failure only this freshly created lock file
    # is removed -- never any pre-existing or replaced lock.
    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"attempt_id": attempt_id}) + "\n")
            f.flush()
            os.fsync(f.fileno())
        milestones["lock_acquired"] = True
    except OSError as exc:
        print(f"lock owner evidence failed: {exc}", file=sys.stderr)
        cleanup_state["staging"] = "not_staged"
        try:
            lock_path.unlink(missing_ok=True)
        except OSError as unlink_exc:
            print(f"own-lock cleanup failed: {unlink_exc}", file=sys.stderr)
        cleanup_state["lock_cleanup"] = (
            "cleaned" if not lock_path.exists() else "cleanup_failed"
        )
        _write_terminal_attempt("FAILED", None, ["lock_owner_evidence_failed"])
        return EXIT_FAILED

    try:
        # Step 19: Immediately before publication, re-read both parent pointers
        try:
            if val_pointer_file.read_bytes() != val_pointer_bytes_initial:
                print("validation pointer drifted before publication", file=sys.stderr)
                _write_terminal_attempt("BLOCKED", None, ["validation_pointer_drift"])
                return EXIT_BLOCKED
            if res_pointer_file.read_bytes() != res_pointer_bytes_initial:
                print("research pointer drifted before publication", file=sys.stderr)
                _write_terminal_attempt("BLOCKED", None, ["research_pointer_drift"])
                return EXIT_BLOCKED
        except OSError as exc:
            print(f"pointer re-read error: {exc}", file=sys.stderr)
            _write_terminal_attempt("BLOCKED", None, ["parent_pointer_unreadable"])
            return EXIT_BLOCKED

        # Step 20: Check existing pointer and idempotency
        pointer_file = eval_dir / "current.json"
        candidate_commit_dir = commits_dir / prospective_commit

        val_ptr_doc = json.loads(val_pointer_bytes_initial.decode("utf-8"))
        res_ptr_doc = json.loads(res_pointer_bytes_initial.decode("utf-8"))

        content_evidence = {
            "descriptor_sha256": sha256_hex(descriptor_file.read_bytes()),
            "schema_fingerprint": schema_fp,
            "parser_version": "1.0.0",
            "canonical_content_hash": content_hash,
            "quality_identity": quality_report.identity(),
            "object_refs": [{"kind": "normalized", "sha256": sha256_hex(artifact_bytes)}],
            "evaluation_from": evaluation_from,
            "evaluation_commit_identity": prospective_commit,
        }

        if pointer_file.exists():
            try:
                parsed_pointer = json.loads(pointer_file.read_text(encoding="utf-8"))
                if parsed_pointer.get("commit") == prospective_commit:
                    if candidate_commit_dir.exists() and existing_commit_matches(
                        data, candidate_commit_dir, content_evidence, keys=EVALUATION_EVIDENCE_KEYS
                    ):
                        verify_evaluation_current_graph(eval_dir, data)
                        milestones["discovery_verified"] = True
                        _cleanup_staging()
                        _write_terminal_attempt(
                            "VERIFIED_NO_OP",
                            prospective_commit,
                            [],
                            {"evaluation_artifact": "already_published"},
                        )
                        return EXIT_OK
            except Exception:
                pass

        # Step 21: Safe lost-pointer recovery check.
        # The retained candidate must be FULLY authenticated -- including
        # quality.json structure/identity/exact PASS, canonical artifact bytes,
        # commit equations, complete dual-parent lineage reconciliation against
        # retained parent evidence, and agreement with this invocation's fresh
        # evidence -- via the same explicit verifier used for current-pointer
        # verification. Only then may write_current() be called.
        if candidate_commit_dir.exists() and (candidate_commit_dir / "COMMITTED").is_file():
            try:
                verified_candidate = _authenticate_retained_evaluation_commit(
                    candidate_commit_dir, prospective_commit, data
                )
                if not existing_commit_matches(
                    data, candidate_commit_dir, content_evidence, keys=EVALUATION_EVIDENCE_KEYS
                ):
                    raise QuantaraError(
                        "retained candidate evidence disagrees with this invocation"
                    )
                write_current(
                    eval_dir,
                    prospective_commit,
                    verified_candidate["manifest_sha256"],
                )
                milestones["pointer_replaced"] = True
                verify_evaluation_current_graph(eval_dir, data)
                milestones["discovery_verified"] = True
                _cleanup_staging()
                _write_terminal_attempt(
                    "PUBLISHED",
                    prospective_commit,
                    [],
                    {
                        "evaluation_artifact": "already_published",
                        "lost_pointer_recovered": True,
                    },
                )
                return EXIT_OK
            except Exception as exc:
                print(f"candidate commit unverified for recovery: {exc}", file=sys.stderr)

        # Step 22: Fresh publication
        stored_obj = store_object(data, "normalized", artifact_bytes)
        milestones["object_written"] = stored_obj.created
        artifact_state = "object_written" if stored_obj.created else "object_reused"

        staging_dir.mkdir(parents=True, exist_ok=True)
        milestones["attempt_staged"] = True

        env_ev = environment_evidence(root)
        manifest = {
            "dataset_id": descriptor.dataset_id,
            "schema_version": descriptor.schema_version,
            "schema_fingerprint": schema_fp,
            "parser_version": "1.0.0",
            "canonical_content_hash": content_hash,
            "quality_identity": quality_report.identity(),
            "quality_state": quality_report.state,
            "quality_policy_version": QUALITY_POLICY_VERSION,
            "commit_identity": prospective_commit,
            "artifact_sha256": stored_obj.sha256,
            "artifact_size": len(artifact_bytes),
            "object_refs": [{"kind": "normalized", "sha256": stored_obj.sha256}],
            "evaluation_from": evaluation_from,
            "parent_discovery": {
                "validation_pointer_manifest_sha256": val_ptr_doc["manifest_sha256"],
                "research_pointer_manifest_sha256": res_ptr_doc["manifest_sha256"],
            },
            "period": {
                "start": descriptor.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": descriptor.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "evaluation_set": dict(descriptor.evaluation_set),
            "features": list(descriptor.features),
            "target": descriptor.target,
            "metrics": list(descriptor.metrics),
            "decimal_contract": dict(DECIMAL_CONTRACT),
            "legal_record_id": rights_record.record_id,
            "legal_states": {name: entry.state for name, entry in rights_record.operations.items()},
            "environment": env_ev,
        }
        quality_payload = {
            "state": quality_report.state,
            "policy_version": QUALITY_POLICY_VERSION,
            "identity": quality_report.identity(),
            "findings": [
                {
                    "check_id": f.check_id,
                    "count": f.count,
                    "evidence": f.evidence,
                    "outcome": f.outcome,
                    "severity": f.severity,
                }
                for f in quality_report.findings
            ],
        }

        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        files = {
            "manifest.json": manifest_bytes,
            "content.json": (json.dumps(content_evidence, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
            "quality.json": (json.dumps(quality_payload, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        }
        staged_commit = stage_commit(eval_dir, attempt_id, files)
        publish_commit(staged_commit, commits_dir, prospective_commit)
        milestones["commit_renamed"] = True

        write_current(eval_dir, prospective_commit, sha256_hex(manifest_bytes))
        milestones["pointer_replaced"] = True

        try:
            verify_evaluation_current_graph(eval_dir, data)
            milestones["discovery_verified"] = True
        except Exception as exc:
            _cleanup_staging()
            print(f"post-pointer verification failed: {exc}", file=sys.stderr)
            _write_terminal_attempt(
                "FAILED",
                prospective_commit,
                ["post_pointer_verification_failed"],
            )
            return EXIT_FAILED

        _cleanup_staging()
        _write_terminal_attempt(
            "PUBLISHED",
            prospective_commit,
            [],
            {"evaluation_artifact": "published"},
        )
        return EXIT_OK
    except Exception as exc:
        _cleanup_staging()
        diagnostic = getattr(exc, "error_id", None) or "evaluation_publication_failed"
        ref_commit = prospective_commit if milestones.get("pointer_replaced") else None
        print(f"evaluation publication failed: {exc}", file=sys.stderr)
        _write_terminal_attempt("FAILED", ref_commit, [diagnostic])
        return EXIT_FAILED
    finally:
        _release_lock()


def _authenticate_retained_evaluation_commit(
    commit_dir: Path, address: str, data_root: Path
) -> dict:
    """Explicit retained-commit verifier (requirements 2 and 5).

    Fully authenticates one retained evaluation commit directory BEFORE any
    pointer write may reference it: manifest/content/CAS bytes, canonical JCS
    artifact bytes, exact structure, schema fingerprint, canonical content
    hash, quality.json envelope with exact PASS and identity agreement, plus
    complete stable dual-parent reconciliation against freshly authenticated
    retained validation/research parent evidence and the recorded discovery
    digests. Returns ``{"commit", "manifest_sha256", **content}``.
    """
    content = verify_commit_graph(Path(data_root), commit_dir)

    # 1. Exact eight content.json keys
    if set(content.keys()) != set(EVALUATION_EVIDENCE_KEYS):
        expected_keys = sorted(EVALUATION_EVIDENCE_KEYS)
        raise QuantaraError(
            f"content.json keys must be exactly {expected_keys}, got {sorted(content)}"
        )

    try:
        manifest_bytes = (commit_dir / "manifest.json").read_bytes()
    except OSError as exc:
        raise QuantaraError(f"manifest.json unreadable: {exc}") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"manifest not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise QuantaraError("manifest.json must be a JSON object")

    lineage = content.get("evaluation_from")
    content_hash = content.get("canonical_content_hash")
    recorded_address = content.get("evaluation_commit_identity")
    if lineage is None or content_hash is None or recorded_address is None:
        raise QuantaraError("content.json lacks evaluation identity evidence")

    # Complete evaluation_from shape and commit equation
    if not isinstance(lineage, dict) or set(lineage.keys()) != EXPECTED_EVALUATION_FROM_KEYS:
        raise QuantaraError("evaluation_from keys mismatch")

    recomputed_address = evaluation_commit_identity(content_hash, lineage)
    if recomputed_address != address or recorded_address != address:
        raise QuantaraError(
            f"address binding mismatch: recomputed {recomputed_address!r}, "
            f"recorded {recorded_address!r}, pointer/commit {address!r}"
        )

    for key in (
        "schema_fingerprint",
        "parser_version",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "evaluation_from",
    ):
        if manifest.get(key) != content.get(key):
            raise QuantaraError(f"manifest/content disagreement on {key!r}")
    if manifest.get("commit_identity") != address:
        raise QuantaraError("manifest commit_identity disagrees with commit address")

    normalized_refs = [
        ref for ref in content.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if len(normalized_refs) != 1 or manifest.get("artifact_sha256") != normalized_refs[0]["sha256"]:
        raise QuantaraError("manifest artifact SHA-256 disagrees with object ref")

    # 2. Authenticate artifact object from CAS
    art_sha = normalized_refs[0]["sha256"]
    art_path = Path(data_root) / "objects" / "normalized" / "sha256" / art_sha
    if not art_path.exists():
        raise QuantaraError(f"referenced artifact object missing from CAS: {art_path}")
    art_bytes = art_path.read_bytes()
    if sha256_hex(art_bytes) != art_sha:
        raise QuantaraError("artifact bytes disagree with SHA-256 in CAS")
    if len(art_bytes) != manifest.get("artifact_size"):
        raise QuantaraError("artifact byte size disagrees with manifest artifact_size")

    # 3. Canonical JCS artifact bytes plus exactly one LF
    try:
        art_doc = json.loads(art_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"artifact object is not valid JSON: {exc}") from exc
    if not isinstance(art_doc, dict):
        raise QuantaraError("artifact root must be a JSON object")

    expected_art_bytes = canonicalize(art_doc).encode("utf-8") + b"\n"
    if art_bytes != expected_art_bytes:
        raise QuantaraError("artifact bytes are not canonical JCS plus exactly one LF")

    # 4. Exact artifact root, record, summary, parent, decimal, schema, and disclaimer structure
    if set(art_doc.keys()) != EXPECTED_ARTIFACT_KEYS:
        expected_art_keys = sorted(EXPECTED_ARTIFACT_KEYS)
        raise QuantaraError(
            f"artifact root keys must be exactly {expected_art_keys}, got {sorted(art_doc)}"
        )
    if art_doc.get("schema") != EVALUATION_ARTIFACT_SCHEMA:
        raise QuantaraError("artifact schema invalid")
    if art_doc.get("disclaimer") != DISCLAIMER:
        raise QuantaraError("artifact disclaimer invalid")
    if art_doc.get("decimal_contract") != DECIMAL_CONTRACT:
        raise QuantaraError("artifact decimal_contract invalid")

    val_parent = art_doc.get("validation_parent")
    if not isinstance(val_parent, dict) or set(val_parent.keys()) != {
        "dataset_id",
        "commit_address",
        "canonical_content_hash",
        "artifact_sha256",
        "artifact_size",
    }:
        raise QuantaraError("artifact validation_parent structure invalid")

    res_parent = art_doc.get("research_parent")
    if not isinstance(res_parent, dict) or set(res_parent.keys()) != {
        "dataset_id",
        "commit_address",
        "canonical_content_hash",
        "parquet_sha256",
        "parquet_size",
    }:
        raise QuantaraError("artifact research_parent structure invalid")

    period = art_doc.get("period")
    if not isinstance(period, dict) or set(period.keys()) != {"start", "end"}:
        raise QuantaraError("artifact period structure invalid")

    eval_set = art_doc.get("evaluation_set")
    if not isinstance(eval_set, dict) or set(eval_set.keys()) != {"name", "version"}:
        raise QuantaraError("artifact evaluation_set structure invalid")

    records = art_doc.get("records")
    rec_keys = {
        "fold_id",
        "feature",
        "target",
        "test_range",
        "test_row_count",
        "valid_pair_count",
        "excluded_pair_count",
        "feature_null_count",
        "target_null_count",
        "pearson_ic",
        "spearman_ic",
    }
    if (
        not isinstance(records, list)
        or len(records) == 0
        or not all(isinstance(r, dict) and set(r.keys()) == rec_keys for r in records)
    ):
        raise QuantaraError("artifact records structure invalid")

    summaries = art_doc.get("summaries")
    sum_keys = {
        "feature",
        "metric",
        "fold_count",
        "total_valid_pair_count",
        "positive_fold_count",
        "negative_fold_count",
        "zero_fold_count",
        "minimum",
        "maximum",
        "median",
        "equal_weight_mean",
    }
    if (
        not isinstance(summaries, list)
        or len(summaries) == 0
        or not all(isinstance(s, dict) and set(s.keys()) == sum_keys for s in summaries)
    ):
        raise QuantaraError("artifact summaries structure invalid")

    # 5. Evaluation schema fingerprint recomputed from authenticated validation fingerprint
    val_commit = lineage["validation_commit_address"]
    symbol = "BTCUSDT"
    interval = "1h"
    start_dt = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
    val_dir = _validation_dataset_dir(Path(data_root), symbol, interval, start_dt)
    val_commit_dir = val_dir / "commits" / val_commit
    if not val_commit_dir.is_dir():
        raise QuantaraError(f"validation commit directory missing: {val_commit_dir}")
    val_content = verify_commit_graph(Path(data_root), val_commit_dir)
    val_fp = val_content["schema_fingerprint"]

    expected_schema_fp = evaluation_schema_fingerprint(parent_validation_fingerprint=val_fp)
    if content["schema_fingerprint"] != expected_schema_fp:
        raise QuantaraError(
            f"evaluation schema fingerprint mismatch: recorded {content['schema_fingerprint']!r} "
            f"vs recomputed {expected_schema_fp!r}"
        )

    # 6. Canonical content hash over exact artifact bytes
    recomputed_cch = evaluation_content_hash(content["schema_fingerprint"], art_bytes)
    if recomputed_cch != content_hash:
        raise QuantaraError(
            f"artifact canonical content hash mismatch: recomputed {recomputed_cch!r} "
            f"vs recorded {content_hash!r}"
        )

    # 7. Exact quality.json keys, policy version, and 13 ordered hard/pass findings
    quality_path = commit_dir / "quality.json"
    if not quality_path.exists():
        raise QuantaraError("quality.json missing in commit directory")
    try:
        quality_doc = json.loads(quality_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"quality.json invalid: {exc}") from exc
    if not isinstance(quality_doc, dict):
        raise QuantaraError("quality.json must be a JSON object")

    expected_quality_keys = {"state", "policy_version", "identity", "findings"}
    if set(quality_doc.keys()) != expected_quality_keys:
        expected_q_keys = sorted(expected_quality_keys)
        raise QuantaraError(
            f"quality.json keys must be exactly {expected_q_keys}, got {sorted(quality_doc)}"
        )
    if str(quality_doc.get("policy_version")) != str(QUALITY_POLICY_VERSION):
        raise QuantaraError("quality.json policy_version mismatch")
    if str(manifest.get("quality_policy_version")) != str(QUALITY_POLICY_VERSION):
        raise QuantaraError("manifest quality_policy_version mismatch")

    if quality_doc.get("state") != "PASS" or manifest.get("quality_state") != "PASS":
        raise QuantaraError(
            "evaluation quality state is not PASS; unverified graph cannot be honored"
        )

    committed_findings = quality_doc.get("findings", [])
    if len(committed_findings) != 13:
        raise QuantaraError(f"expected exactly 13 quality findings, got {len(committed_findings)}")
    if [f.get("check_id") for f in committed_findings] != list(CHECK_IDS):
        raise QuantaraError("quality findings check_id order mismatch")
    if any(f.get("outcome") != "pass" or f.get("severity") != "hard" for f in committed_findings):
        raise QuantaraError("quality findings not all pass/hard")

    expected_qid = quality_identity(committed_findings)
    if (
        quality_doc.get("identity") != expected_qid
        or manifest.get("quality_identity") != expected_qid
        or content.get("quality_identity") != expected_qid
    ):
        raise QuantaraError("quality identity disagrees with findings")

    # 8. Complete manifest/content/artifact/quality agreement
    if manifest.get("dataset_id") != art_doc.get("dataset_id"):
        raise QuantaraError("manifest/artifact dataset_id disagreement")
    if manifest.get("schema_version") != "quantara_feature_evaluation_v1":
        raise QuantaraError("manifest schema_version invalid")

    parent_disc = manifest.get("parent_discovery")
    if not isinstance(parent_disc, dict) or set(parent_disc.keys()) != {
        "validation_pointer_manifest_sha256",
        "research_pointer_manifest_sha256",
    }:
        raise QuantaraError("manifest parent_discovery block missing or invalid")
    for key in ("validation_pointer_manifest_sha256", "research_pointer_manifest_sha256"):
        val = str(parent_disc[key]).lower()
        if len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
            raise QuantaraError(f"parent_discovery {key} is not a valid sha256 hex digest")

    # --- Requirement 5: complete duplicated parent-field reconciliation ------
    _DUPLICATED_PARENT_FIELDS = (
        # (artifact field, lineage field, label)
        ("dataset_id", "validation_dataset_id", "validation dataset_id"),
        ("commit_address", "validation_commit_address", "validation commit address"),
        (
            "canonical_content_hash",
            "validation_canonical_content_hash",
            "validation canonical content hash",
        ),
        ("artifact_sha256", "validation_artifact_sha256", "validation artifact sha256"),
        ("artifact_size", "validation_artifact_size", "validation artifact size"),
        ("dataset_id", "research_dataset_id", "research dataset_id"),
        ("commit_address", "research_commit_address", "research commit address"),
        (
            "canonical_content_hash",
            "research_canonical_content_hash",
            "research canonical content hash",
        ),
        ("parquet_sha256", "research_parquet_sha256", "research parquet sha256"),
        ("parquet_size", "research_parquet_size", "research parquet size"),
    )
    for artifact_field, lineage_field, label in _DUPLICATED_PARENT_FIELDS:
        source = val_parent if label.startswith("validation") else res_parent
        left = str(source[artifact_field]).lower()
        right = str(lineage[lineage_field]).lower()
        try:
            numeric_equal = int(left) == int(right)
        except ValueError:
            numeric_equal = False
        if left != right and not (numeric_equal and "." not in left):
            raise QuantaraError(
                f"reconciliation failure: {label} differs between artifact "
                f"parent ({source[artifact_field]!r}) and evaluation_from "
                f"({lineage[lineage_field]!r})"
            )

    # --- Requirement 5: freshly authenticated retained parent evidence -------
    # Reconcile evaluation_from against the ACTUAL retained validation and
    # research parent commits (dataset ids, canonical content hashes, artifact/
    # parquet sha256+size), and authenticate the recorded discovery digests
    # against those exact retained manifest bytes.
    start_dt = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
    val_dir = _validation_dataset_dir(
        Path(data_root), "BTCUSDT", "1h", start_dt
    )
    res_dir = _research_dataset_dir(Path(data_root), "BTCUSDT", "1h", start_dt)

    val_parent_commit_dir = (
        val_dir / "commits" / str(lineage["validation_commit_address"]).lower()
    )
    if not val_parent_commit_dir.is_dir():
        raise QuantaraError(f"retained validation commit missing: {val_parent_commit_dir}")
    val_parent_content = verify_commit_graph(Path(data_root), val_parent_commit_dir)
    try:
        val_parent_manifest_bytes = (val_parent_commit_dir / "manifest.json").read_bytes()
    except OSError as exc:
        raise QuantaraError(f"retained validation manifest unreadable: {exc}") from exc
    if sha256_hex(val_parent_manifest_bytes) != str(
        parent_disc["validation_pointer_manifest_sha256"]
    ).lower():
        raise QuantaraError(
            "parent_discovery validation digest disagrees with actual retained "
            "validation manifest bytes"
        )
    try:
        val_manifest_doc = json.loads(val_parent_manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"retained validation manifest not valid JSON: {exc}") from exc

    res_parent_commit_dir = (
        res_dir / "commits" / str(lineage["research_commit_address"]).lower()
    )
    if not res_parent_commit_dir.is_dir():
        raise QuantaraError(f"retained research commit missing: {res_parent_commit_dir}")
    res_parent_content = verify_commit_graph(Path(data_root), res_parent_commit_dir)
    try:
        res_parent_manifest_bytes = (res_parent_commit_dir / "manifest.json").read_bytes()
    except OSError as exc:
        raise QuantaraError(f"retained research manifest unreadable: {exc}") from exc
    if sha256_hex(res_parent_manifest_bytes) != str(
        parent_disc["research_pointer_manifest_sha256"]
    ).lower():
        raise QuantaraError(
            "parent_discovery research digest disagrees with actual retained "
            "research manifest bytes"
        )
    try:
        res_manifest_doc = json.loads(res_parent_manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"retained research manifest not valid JSON: {exc}") from exc

    _FRESH_PARENT_BINDINGS = (
        ("validation_dataset_id", val_manifest_doc.get("dataset_id")),
        ("validation_canonical_content_hash", val_manifest_doc.get("canonical_content_hash")),
        ("validation_artifact_sha256", val_manifest_doc.get("artifact_sha256")),
        ("validation_artifact_size", val_manifest_doc.get("artifact_size")),
        ("validation_canonical_content_hash", val_parent_content.get("canonical_content_hash")),
        ("research_dataset_id", res_manifest_doc.get("dataset_id")),
        ("research_canonical_content_hash", res_manifest_doc.get("canonical_content_hash")),
        ("research_parquet_sha256", res_manifest_doc.get("parquet_sha256")),
        ("research_parquet_size", res_manifest_doc.get("parquet_size")),
        ("research_canonical_content_hash", res_parent_content.get("canonical_content_hash")),
    )
    for lineage_field, fresh_value in _FRESH_PARENT_BINDINGS:
        if lineage_field not in lineage:
            raise QuantaraError(f"evaluation_from lacks {lineage_field!r}")
        recorded = lineage[lineage_field]
        if isinstance(recorded, int) or isinstance(fresh_value, int):
            equal = isinstance(recorded, int) and recorded == fresh_value
        else:
            if fresh_value is None:
                equal = False
            else:
                equal = str(recorded).lower() == str(fresh_value).lower()
        if not equal:
            raise QuantaraError(
                f"reconciliation failure: evaluation_from {lineage_field}="
                f"{recorded!r} disagrees with freshly authenticated retained "
                f"parent evidence {fresh_value!r}"
            )

    return {
        "commit": address,
        "manifest_sha256": sha256_hex(manifest_bytes),
        **content,
    }


def verify_evaluation_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    """Full lock-free authentication of an evaluation current graph (spec §11, §13).

    Parses and pins current.json, then delegates all retained-commit
    authentication to ``_authenticate_retained_evaluation_commit`` so pointer
    verification and lost-pointer recovery share one explicit verifier.
    """
    pointer_path = dataset_dir / "current.json"
    if not pointer_path.exists():
        raise QuantaraError(f"no current.json under {dataset_dir}")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"invalid current.json: {exc}") from exc
    if not isinstance(pointer, dict):
        raise QuantaraError("current.json must be a JSON object")

    expected_pointer_keys = {
        "publication_protocol_version",
        "commit",
        "manifest_sha256",
    }
    if set(pointer) != expected_pointer_keys:
        raise QuantaraError(
            f"current.json keys must be exactly {sorted(expected_pointer_keys)}, "
            f"got {sorted(pointer)}"
        )
    if pointer["publication_protocol_version"] != "v1":
        raise QuantaraError("unsupported publication protocol version")

    for label in ("commit", "manifest_sha256"):
        val = str(pointer[label]).lower()
        if len(val) != 64 or any(c not in "0123456789abcdef" for c in val):
            raise QuantaraError(f"pointer {label} is not a sha256 hex digest")

    address = str(pointer["commit"]).lower()
    commit_dir = dataset_dir / "commits" / address

    verified = _authenticate_retained_evaluation_commit(commit_dir, address, Path(data_root))

    # Pointer-level binding: manifest bytes must match the pinned digest.
    if verified["manifest_sha256"] != str(pointer["manifest_sha256"]).lower():
        raise QuantaraError("manifest bytes disagree with current.json manifest_sha256")

    evidence_keys = set(EVALUATION_EVIDENCE_KEYS)
    return {"commit": address, **{k: v for k, v in verified.items() if k in evidence_keys}}
