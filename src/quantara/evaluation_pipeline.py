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
from datetime import datetime
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
    QUALITY_POLICY_VERSION,
    evaluate_evaluation_quality,
)
from quantara.hashing import (
    HashPayloadError,
    evaluation_content_hash,
    evaluation_schema_fingerprint,
    quality_identity,
    sha256_hex,
)
from quantara.jcs import canonicalize
from quantara.manifests import (
    attempt_id_now,
    environment_evidence,
    new_attempt_manifest,
    write_json,
)
from quantara.publication import (
    publish_commit,
    stage_commit,
    store_object,
    verify_commit_graph,
    write_current,
)
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
    "verify_evaluation_current_graph",
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
    terminal_result: str,
    dispositions: dict[str, str | bool | None],
    referenced_commit: str | None,
    diagnostics: list[str],
) -> None:
    attempt = new_attempt_manifest(
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
                terminal_result=terminal_result,
                dispositions={
                    "evaluation_artifact": "not_written",
                    "lock_acquired": False,
                    "lock_released": False,
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

    # 8. Require Q1 dataset, period, 2,184 rows, 25 folds, approved fold set, PASS
    if (
        val_manifest.get("dataset_id") != descriptor.parent_descriptor.dataset_id
        or val_manifest.get("parent_rows") != 2184
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

    attempt_id = attempt_id_now()
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
            **milestones,
            "attempt_staging": cleanup_state["staging"],
        }
        if extra:
            dispositions.update(extra)
        return dispositions

    def _release_lock() -> None:
        if milestones.get("lock_acquired") and not milestones.get("lock_released"):
            try:
                if lock_path.exists():
                    lock_path.unlink()
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
            terminal_result=terminal_result,
            dispositions=_dispositions(extra),
            referenced_commit=referenced_commit,
            diagnostics=diagnostics,
        )

    # 18. Lock acquisition
    lock_path = eval_dir / "evaluation.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"attempt_id": attempt_id, "pid": os.getpid()}))
        milestones["lock_acquired"] = True
    except OSError:
        print(f"lock contested: {lock_path}", file=sys.stderr)
        _write_terminal_attempt("BLOCKED", None, ["lock_contested"])
        return EXIT_BLOCKED

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

        if pointer_file.exists():
            try:
                parsed_pointer = json.loads(pointer_file.read_text(encoding="utf-8"))
                if parsed_pointer.get("commit") == prospective_commit:
                    verify_evaluation_current_graph(eval_dir, data)
                    milestones["discovery_verified"] = True
                    _write_terminal_attempt(
                        "VERIFIED_NO_OP",
                        prospective_commit,
                        [],
                        {"evaluation_artifact": "already_published"},
                    )
                    return EXIT_OK
            except Exception:
                pass

        # Step 21: Lost-pointer recovery check
        if candidate_commit_dir.exists() and (candidate_commit_dir / "COMMITTED").is_file():
            try:
                verify_commit_graph(data, candidate_commit_dir)
                cand_manifest_bytes = (candidate_commit_dir / "manifest.json").read_bytes()
                write_current(eval_dir, prospective_commit, sha256_hex(cand_manifest_bytes))
                milestones["pointer_replaced"] = True
                verify_evaluation_current_graph(eval_dir, data)
                milestones["discovery_verified"] = True
                _write_terminal_attempt(
                    "PUBLISHED",
                    prospective_commit,
                    [],
                    {"evaluation_artifact": "already_published", "lost_pointer_recovered": True},
                )
                return EXIT_OK
            except Exception as exc:
                print(f"candidate commit unverified: {exc}", file=sys.stderr)

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
        content_evidence = {
            "descriptor_sha256": sha256_hex(descriptor_file.read_bytes()),
            "schema_fingerprint": schema_fp,
            "parser_version": "1.0.0",
            "canonical_content_hash": content_hash,
            "quality_identity": quality_report.identity(),
            "object_refs": [{"kind": "normalized", "sha256": stored_obj.sha256}],
            "evaluation_from": evaluation_from,
            "evaluation_commit_identity": prospective_commit,
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
        try:
            publish_commit(staged_commit, commits_dir, prospective_commit)
            milestones["commit_renamed"] = True
        except QuantaraError:
            if not candidate_commit_dir.is_dir():
                raise
            milestones["commit_renamed"] = True

        write_current(eval_dir, prospective_commit, sha256_hex(manifest_bytes))
        milestones["pointer_replaced"] = True

        verify_evaluation_current_graph(eval_dir, data)
        milestones["discovery_verified"] = True

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
        print(f"evaluation publication failed: {exc}", file=sys.stderr)
        _write_terminal_attempt("FAILED", None, [diagnostic])
        return EXIT_FAILED
    finally:
        _release_lock()


def verify_evaluation_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    """Full lock-free authentication of an evaluation current graph (spec §11, §13)."""
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
    content = verify_commit_graph(Path(data_root), commit_dir)

    try:
        manifest_bytes = (commit_dir / "manifest.json").read_bytes()
    except OSError as exc:
        raise QuantaraError(f"manifest.json unreadable: {exc}") from exc
    if sha256_hex(manifest_bytes) != str(pointer["manifest_sha256"]).lower():
        raise QuantaraError("manifest bytes disagree with current.json manifest_sha256")

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

    # Authenticate artifact object from CAS
    art_sha = normalized_refs[0]["sha256"]
    art_path = Path(data_root) / "objects" / "normalized" / "sha256" / art_sha
    if not art_path.exists():
        raise QuantaraError(f"referenced artifact object missing from CAS: {art_path}")
    art_bytes = art_path.read_bytes()
    if sha256_hex(art_bytes) != art_sha:
        raise QuantaraError("artifact bytes disagree with SHA-256 in CAS")
    if len(art_bytes) != manifest.get("artifact_size"):
        raise QuantaraError("artifact byte size disagrees with manifest artifact_size")

    # Recompute content hash from artifact bytes
    recomputed_cch = evaluation_content_hash(content["schema_fingerprint"], art_bytes)
    if recomputed_cch != content_hash:
        raise QuantaraError(
            f"artifact canonical content hash mismatch: recomputed {recomputed_cch!r} "
            f"vs recorded {content_hash!r}"
        )

    # Authenticate quality document
    quality_path = commit_dir / "quality.json"
    if not quality_path.exists():
        raise QuantaraError("quality.json missing in commit directory")
    try:
        quality_doc = json.loads(quality_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"quality.json invalid: {exc}") from exc
    if not isinstance(quality_doc, dict):
        raise QuantaraError("quality.json must be a JSON object")

    if quality_doc.get("state") != "PASS" or manifest.get("quality_state") != "PASS":
        raise QuantaraError(
            "evaluation quality state is not PASS; unverified graph cannot be honored"
        )

    committed_findings = quality_doc.get("findings", [])
    expected_qid = quality_identity(committed_findings)
    if (
        quality_doc.get("identity") != expected_qid
        or manifest.get("quality_identity") != expected_qid
    ):
        raise QuantaraError("quality identity disagrees with findings")

    return {**content, "commit": address}
