"""Authenticated publication pipeline for exact-decimal training.

Slice 011 published the ``ridge_linear`` family. Slice 012 adds a
``logistic_irls`` dual path: on a clean pre-registered kill-criteria pass the
artifact publishes exactly as before; on any kill-criteria failure nothing is
staged, the lane pointer is left byte-unchanged, an attempt manifest with
terminal result ``KILL_CRITERIA_FAILED`` records the observed values, and the
pipeline exits with code 4.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from quantara.descriptor import load_rights_record
from quantara.errors import QuantaraError
from quantara.hashing import quality_identity, sha256_hex
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
from quantara.research_pipeline import read_research_rows, verify_research_current_graph
from quantara.training_descriptor import (
    LOGISTIC_FAMILY,
    TrainingDescriptor,
    load_training_descriptor,
)
from quantara.training_metrics import (
    DECIMAL_CONTRACT,
    build_training_records,
    build_training_summaries,
)
from quantara.training_metrics_logistic import (
    build_logistic_training_records,
    build_logistic_training_summaries,
    evaluate_kill_criteria,
)
from quantara.training_quality import (
    CHECK_IDS,
    DISCLAIMER,
    LOGISTIC_ARTIFACT_SCHEMA,
    LOGISTIC_CHECK_IDS,
    QUALITY_POLICY_VERSION,
    TRAINING_ARTIFACT_SCHEMA,
    evaluate_logistic_training_quality,
    evaluate_training_quality,
    training_commit_identity,
    training_content_hash,
    training_schema_fingerprint,
)
from quantara.validation_pipeline import verify_validation_current_graph

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3
# Reserved exclusively for a pre-registered kill-criteria failure.
EXIT_KILL_CRITERIA_FAILED = 4
KILL_CRITERIA_FAILED = "KILL_CRITERIA_FAILED"
RIDGE_DATASET_SUFFIX = "_training_ridge_v1"
LOGISTIC_DATASET_SUFFIX = "_training_logistic_v1"
TRAINING_EVIDENCE_KEYS = (
    "descriptor_sha256",
    "schema_fingerprint",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "training_from",
    "training_commit_identity",
)


def _write_per_fold_sidecar(records: list[dict], path: Path) -> None:
    """Write the non-publication snapshot consumed by the IC diagnostic.

    The sidecar is fold-count agnostic: the writer accepts any record list
    (Q1 chain, full-year chain, or any future chain) and the fold-count
    validation lives in the diagnostic module's ``load_per_fold_ics`` (where
    the expected count is bound to the descriptor under test). Defense in
    depth without over-constraining the writer.
    """
    prefix = "per_fold_"
    if not path.stem.startswith(prefix) or path.stem == prefix:
        raise ValueError("per-fold sidecar path must encode an attempt id")
    if len(records) == 0:
        raise ValueError("per-fold sidecar requires at least one record")
    normalized_records: list[dict] = []
    for expected_index, record in enumerate(records):
        fold_index = record.get("fold_index", record.get("fold_id"))
        if fold_index != expected_index:
            raise ValueError("per-fold sidecar records must be in fold order")
        normalized = dict(record)
        normalized.pop("fold_id", None)
        normalized["fold_index"] = fold_index
        normalized_records.append(normalized)

    code_revision = environment_evidence(
        Path(__file__).resolve().parents[2]
    ).get("git_head")
    if not isinstance(code_revision, str):
        raise ValueError("per-fold sidecar requires a code revision")
    write_json(
        path,
        {
            "schema_version": "quantara.ic_stability_sidecar/v1",
            "attempt_id": path.stem.removeprefix(prefix),
            "code_revision": code_revision,
            "records": normalized_records,
        },
    )



def _dataset_dir(data_root: Path, lane: str, start: datetime) -> Path:
    return (
        data_root
        / "datasets"
        / "binance"
        / "usdm"
        / lane
        / "BTCUSDT"
        / "1h"
        / f"year={start.year:04d}"
        / f"month={start.month:02d}"
    )


def _write_attempt(
    data_root: Path,
    repo_root: Path,
    attempt_id: str,
    terminal_result: str,
    referenced_commit: str | None,
    diagnostics: list[str],
    dispositions: dict,
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
    target = data_root / "attempts" / "training" / f"{attempt['attempt_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, attempt)


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _kill_attempt_manifest(
    *,
    attempt_id: str,
    diagnostics: list[str],
    repo_root: Path,
) -> dict:
    """Attempt manifest for the kill-criteria branch.

    ``quantara.manifests.new_attempt_manifest`` enumerates the frozen terminal
    results of the acquisition lanes and is not modified by this slice, so the
    training lane builds its own ``KILL_CRITERIA_FAILED`` record in the exact
    same shape.
    """
    return {
        "attempt_id": attempt_id,
        "started_at_utc": _utc_now(),
        "finished_at_utc": _utc_now(),
        "terminal_result": KILL_CRITERIA_FAILED,
        "artifact_dispositions": {
            "training_artifact": "not_written",
            "pointer_replaced": False,
        },
        "retry_evidence": [],
        "http_statuses": [],
        "referenced_commit": None,
        "diagnostics": diagnostics,
        "code_revision": environment_evidence(repo_root).get("git_head"),
        "runtime": {"python": platform.python_version(), "executable": sys.executable},
    }


def _kill_diagnostics(kill: dict) -> list[str]:
    """Observed-vs-constant diagnostics naming exactly which criteria failed."""
    constants = kill["constants"]
    observed = kill["observed"]
    results = kill["results"]
    failed = [name for name, passed in results.items() if not passed]
    return [
        KILL_CRITERIA_FAILED.lower(),
        f"failed_criteria={','.join(failed)}",
        (
            "k1_directional_accuracy_mean="
            f"{observed['directional_accuracy_mean']} min="
            f"{constants['directional_accuracy_min']} "
            f"passed={str(results['k1_directional_accuracy']).lower()}"
        ),
        (
            "k2_direction_ic_mean="
            f"{observed['direction_ic_mean']} min="
            f"{constants['direction_ic_min']} "
            f"passed={str(results['k2_direction_ic']).lower()}"
        ),
        (
            "k3_log_loss_mean="
            f"{observed['log_loss_mean']} max={constants['log_loss_max']} "
            f"passed={str(results['k3_log_loss']).lower()}"
        ),
        (
            "k4_brier_mean="
            f"{observed['brier_mean']} max={constants['brier_max']} "
            f"passed={str(results['k4_brier']).lower()}"
        ),
        (
            "baseline_majority_class_train_window_directional_accuracy_mean="
            f"{observed['majority_class_train_window_directional_accuracy_mean']}"
        ),
        (
            "baseline_sign_f_ret_1_directional_accuracy_mean="
            f"{observed['sign_f_ret_1_directional_accuracy_mean']}"
        ),
        (
            "baseline_climatology_p_log_loss_mean="
            f"{observed['climatology_p_log_loss_mean']}"
        ),
        f"baseline_climatology_p_brier_mean={observed['climatology_p_brier_mean']}",
    ]


def _write_kill_attempt(
    data_root: Path, repo_root: Path, attempt_id: str, kill: dict
) -> None:
    attempt = _kill_attempt_manifest(
        attempt_id=attempt_id,
        diagnostics=_kill_diagnostics(kill),
        repo_root=repo_root,
    )
    target = data_root / "attempts" / "training" / f"{attempt['attempt_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, attempt)


def build_training_artifact(
    descriptor: TrainingDescriptor,
    validation_parent_info: dict,
    research_parent_info: dict,
    records: list[dict],
    summaries: list[dict],
    baselines: dict,
) -> dict:
    return {
        "schema": TRAINING_ARTIFACT_SCHEMA,
        "dataset_id": descriptor.dataset_id,
        "provider": descriptor.provider,
        "instrument_id": descriptor.instrument_id,
        "period": {
            "start": descriptor.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": descriptor.end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "features": list(descriptor.features),
        "target": descriptor.target,
        "model": dict(descriptor.model),
        "training_set": dict(descriptor.training_set),
        "decimal_contract": dict(DECIMAL_CONTRACT),
        "research_parent": {
            key: research_parent_info[key]
            for key in (
                "dataset_id",
                "commit_address",
                "canonical_content_hash",
                "parquet_sha256",
                "parquet_size",
            )
        },
        "validation_parent": {
            key: validation_parent_info[key]
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


def build_logistic_training_artifact(
    descriptor: TrainingDescriptor,
    validation_parent_info: dict,
    research_parent_info: dict,
    training_parent_info: dict,
    records: list[dict],
    summaries: list[dict],
    baselines: dict,
    kill_criteria: dict,
) -> dict:
    """The logistic artifact: the 011 header plus training lineage and the
    pre-registered kill-criteria block."""
    artifact = build_training_artifact(
        descriptor,
        validation_parent_info,
        research_parent_info,
        records,
        summaries,
        baselines,
    )
    artifact["schema"] = LOGISTIC_ARTIFACT_SCHEMA
    artifact["training_parent"] = {
        key: training_parent_info[key]
        for key in (
            "dataset_id",
            "commit_address",
            "canonical_content_hash",
            "artifact_sha256",
            "artifact_size",
        )
    }
    artifact["kill_criteria"] = kill_criteria
    return artifact


def _load_training_parent_state(descriptor: TrainingDescriptor, data: Path) -> dict:
    """Authenticate the retained slice 011 ridge commit as the lane parent.

    Discovery is deterministic and idempotent: normally the lane pointer still
    references the ridge commit; once this slice's logistic commit is the head,
    the ridge parent is resolved through the head's own recorded
    ``training_from.training_commit_address`` and re-authenticated, so a rerun
    binds the identical parent and detects a no-op.
    """
    training_dir = _dataset_dir(data, "training", descriptor.start_utc)
    pointer = training_dir / "current.json"
    if not pointer.exists():
        raise QuantaraError("training lane parent pointer missing")
    pointer_bytes = pointer.read_bytes()
    head = verify_training_current_graph(training_dir, data)
    if pointer.read_bytes() != pointer_bytes:
        raise QuantaraError("training lane pointer modified during verification")

    expected_parent_id = descriptor.dataset_id[: -len(LOGISTIC_DATASET_SUFFIX)] + (
        RIDGE_DATASET_SUFFIX
    )
    if head["artifact_schema"] == LOGISTIC_ARTIFACT_SCHEMA:
        lineage = head.get("training_from") or {}
        commit = lineage.get("training_commit_address")
        if not isinstance(commit, str):
            raise QuantaraError("retained logistic head lacks a training lane parent")
        verified = _authenticate_retained_training_commit(
            training_dir / "commits" / commit, commit, data
        )
    else:
        commit = head["commit"]
        verified = head
    if verified["artifact_schema"] != TRAINING_ARTIFACT_SCHEMA:
        raise QuantaraError(
            "logistic training parent must be the retained ridge lane commit"
        )
    manifest_bytes = (training_dir / "commits" / commit / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("dataset_id") != expected_parent_id:
        raise QuantaraError(
            "logistic training parent must be the retained ridge lane commit"
        )
    if manifest.get("quality_state") != "PASS":
        raise QuantaraError("training lane parent must have PASS quality")
    artifact_sha = manifest.get("artifact_sha256")
    artifact_size = manifest.get("artifact_size")
    if not isinstance(artifact_sha, str) or not isinstance(artifact_size, int):
        raise QuantaraError("training lane parent lacks artifact references")
    artifact_file = data / "objects" / "normalized" / "sha256" / artifact_sha
    artifact_bytes = artifact_file.read_bytes()
    if sha256_hex(artifact_bytes) != artifact_sha or len(artifact_bytes) != artifact_size:
        raise QuantaraError("training lane parent artifact authentication failed")
    return {
        "training_dir": training_dir,
        "pointer_bytes": pointer_bytes,
        "manifest": manifest,
        "info": {
            "dataset_id": manifest["dataset_id"],
            "commit_address": commit,
            "canonical_content_hash": verified["canonical_content_hash"],
            "artifact_sha256": artifact_sha,
            "artifact_size": artifact_size,
        },
        "quality_state": manifest["quality_state"],
    }


def _load_parent_state(descriptor: TrainingDescriptor, data: Path) -> dict:
    val_dir = _dataset_dir(data, "validation", descriptor.start_utc)
    res_dir = _dataset_dir(data, "research", descriptor.start_utc)
    val_pointer = val_dir / "current.json"
    res_pointer = res_dir / "current.json"
    if not val_pointer.exists() or not res_pointer.exists():
        raise QuantaraError("training parent current pointer missing")
    val_pointer_bytes = val_pointer.read_bytes()
    res_pointer_bytes = res_pointer.read_bytes()
    val_graph = verify_validation_current_graph(val_dir, data)
    res_graph = verify_research_current_graph(res_dir, data)
    if (
        val_pointer.read_bytes() != val_pointer_bytes
        or res_pointer.read_bytes() != res_pointer_bytes
    ):
        raise QuantaraError("parent pointer modified during verification")

    val_commit = val_graph["commit"]
    res_commit = res_graph["commit"]
    val_manifest_bytes = (val_dir / "commits" / val_commit / "manifest.json").read_bytes()
    res_manifest_bytes = (res_dir / "commits" / res_commit / "manifest.json").read_bytes()
    val_manifest = json.loads(val_manifest_bytes.decode("utf-8"))
    res_manifest = json.loads(res_manifest_bytes.decode("utf-8"))
    if val_manifest.get("dataset_id") != descriptor.parent_descriptor.dataset_id:
        raise QuantaraError("validation parent dataset identity mismatch")
    if res_manifest.get("dataset_id") != descriptor.parent_descriptor.parent_descriptor.dataset_id:
        raise QuantaraError("research parent dataset identity mismatch")
    if val_manifest.get("quality_state") != "PASS" or res_manifest.get("quality_state") != "PASS":
        raise QuantaraError("training parents must both have PASS quality")

    artifact_sha = val_manifest.get("artifact_sha256")
    artifact_size = val_manifest.get("artifact_size")
    if not isinstance(artifact_sha, str) or not isinstance(artifact_size, int):
        raise QuantaraError("validation parent lacks artifact references")
    artifact_file = data / "objects" / "normalized" / "sha256" / artifact_sha
    artifact_bytes = artifact_file.read_bytes()
    if sha256_hex(artifact_bytes) != artifact_sha or len(artifact_bytes) != artifact_size:
        raise QuantaraError("validation artifact object authentication failed")
    validation_artifact = json.loads(artifact_bytes.decode("utf-8"))

    parquet_sha = res_manifest.get("parquet_sha256")
    parquet_size = res_manifest.get("parquet_size")
    if not isinstance(parquet_sha, str) or not isinstance(parquet_size, int):
        raise QuantaraError("research parent lacks parquet references")
    parquet_file = data / "objects" / "normalized" / "sha256" / parquet_sha
    parquet_bytes = parquet_file.read_bytes()
    if sha256_hex(parquet_bytes) != parquet_sha or len(parquet_bytes) != parquet_size:
        raise QuantaraError("research parquet object authentication failed")
    research_rows = read_research_rows(parquet_file)

    lineage = val_graph.get("validation_from")
    if not isinstance(lineage, dict):
        raise QuantaraError("validation parent lacks research lineage")
    bindings = {
        "parent_dataset_id": res_manifest["dataset_id"],
        "parent_commit_address": res_commit,
        "parent_canonical_content_hash": res_graph["canonical_content_hash"],
        "parent_parquet_sha256": parquet_sha,
        "parent_parquet_size": parquet_size,
    }
    if any(lineage.get(key) != value for key, value in bindings.items()):
        raise QuantaraError("validation lineage does not bind authenticated research parent")

    folds = validation_artifact.get("folds")
    coverage = validation_artifact.get("coverage")
    if not isinstance(folds, list) or not isinstance(coverage, dict):
        raise QuantaraError("validation artifact fold structure missing")
    if len(folds) != coverage.get("fold_count"):
        raise QuantaraError("validation fold count disagrees with coverage")
    if validation_artifact.get("parent_rows") != len(research_rows):
        raise QuantaraError("validation parent row count disagrees with research rows")
    is_year = descriptor.dataset_id in (
        "binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1",
        "binance_usdm_btcusdt_klines_1h_2024_training_logistic_v1",
    )
    if is_year and (len(research_rows) != 8784 or len(folds) != 117):
        raise QuantaraError("year training contract requires 8,784 rows and 117 folds")
    for fold in folds:
        train = fold.get("train_range")
        embargo = fold.get("embargo_range")
        test = fold.get("test_range")
        if not (
            isinstance(train, list)
            and isinstance(embargo, list)
            and isinstance(test, list)
            and len(train) == len(embargo) == len(test) == 2
            and train[0] == 0
            and train[1] == embargo[0]
            and embargo[1] == test[0]
            and embargo[1] - embargo[0] == 24
            and test[1] <= len(research_rows)
        ):
            raise QuantaraError("validation fold train/embargo/test alignment invalid")
    return {
        "val_dir": val_dir,
        "res_dir": res_dir,
        "val_pointer_bytes": val_pointer_bytes,
        "res_pointer_bytes": res_pointer_bytes,
        "val_graph": val_graph,
        "res_graph": res_graph,
        "val_manifest": val_manifest,
        "res_manifest": res_manifest,
        "val_manifest_bytes": val_manifest_bytes,
        "res_manifest_bytes": res_manifest_bytes,
        "validation_artifact": validation_artifact,
        "validation_artifact_bytes": artifact_bytes,
        "research_rows": research_rows,
        "validation_lineage": lineage,
        "artifact_sha": artifact_sha,
        "parquet_sha": parquet_sha,
        "parquet_size": parquet_size,
    }


def run_training_pipeline(
    descriptor_path: Path | str,
    data_root: Path | str,
    repo_root: Path | str | None = None,
    dry_run: bool = False,
) -> int:
    descriptor_file = Path(descriptor_path)
    root = Path(repo_root) if repo_root is not None else descriptor_file.resolve().parents[2]
    data = Path(data_root)
    attempt_id = attempt_id_now()

    def pre_attempt(result: str, diagnostic: str) -> None:
        if not dry_run:
            _write_attempt(
                data,
                root,
                attempt_id,
                result,
                None,
                [diagnostic],
                {"training_artifact": "not_written", "pointer_replaced": False},
            )

    try:
        descriptor = load_training_descriptor(descriptor_file)
    except Exception as exc:
        print(f"invalid training descriptor: {exc}", file=sys.stderr)
        pre_attempt("BLOCKED", "invalid_descriptor")
        return EXIT_BLOCKED
    try:
        rights = load_rights_record(root / descriptor.legal_record)
    except Exception as exc:
        print(f"rights loading failed: {exc}", file=sys.stderr)
        pre_attempt("FAILED", "rights_loading_failed")
        return EXIT_FAILED
    if not (
        rights.permits("analyze_internal")
        and rights.permits("model_train_internal")
    ):
        print("analyze_internal and model_train_internal are both required", file=sys.stderr)
        pre_attempt("BLOCKED", "legal_not_permitted")
        return EXIT_BLOCKED
    try:
        parents = _load_parent_state(descriptor, data)
    except Exception as exc:
        print(f"training parent authentication failed: {exc}", file=sys.stderr)
        pre_attempt("BLOCKED", "parent_authentication_failed")
        return EXIT_BLOCKED

    validation_parent_info = {
        "dataset_id": parents["val_manifest"]["dataset_id"],
        "commit_address": parents["val_graph"]["commit"],
        "canonical_content_hash": parents["val_graph"]["canonical_content_hash"],
        "artifact_sha256": parents["artifact_sha"],
        "artifact_size": len(parents["validation_artifact_bytes"]),
        "schema_fingerprint": parents["val_graph"]["schema_fingerprint"],
    }
    research_parent_info = {
        "dataset_id": parents["res_manifest"]["dataset_id"],
        "commit_address": parents["res_graph"]["commit"],
        "canonical_content_hash": parents["res_graph"]["canonical_content_hash"],
        "parquet_sha256": parents["parquet_sha"],
        "parquet_size": parents["parquet_size"],
    }
    logistic = descriptor.model_family == LOGISTIC_FAMILY
    training_parent: dict | None = None
    kill: dict | None = None
    if logistic:
        try:
            training_parent = _load_training_parent_state(descriptor, data)
        except Exception as exc:
            print(f"training lane parent authentication failed: {exc}", file=sys.stderr)
            pre_attempt("BLOCKED", "training_parent_authentication_failed")
            return EXIT_BLOCKED
    try:
        if logistic:
            assert training_parent is not None
            records = build_logistic_training_records(
                parents["validation_artifact"]["folds"], parents["research_rows"]
            )
            summaries, baselines = build_logistic_training_summaries(records)
            kill = evaluate_kill_criteria(summaries, baselines, descriptor.kill_criteria)
            artifact = build_logistic_training_artifact(
                descriptor,
                validation_parent_info,
                research_parent_info,
                training_parent["info"],
                records,
                summaries,
                baselines,
                kill,
            )
        else:
            records = build_training_records(
                parents["validation_artifact"]["folds"], parents["research_rows"]
            )
            summaries, baselines = build_training_summaries(records)
            artifact = build_training_artifact(
                descriptor,
                validation_parent_info,
                research_parent_info,
                records,
                summaries,
                baselines,
            )
        artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"
        schema_fp = training_schema_fingerprint(
            validation_parent_info["schema_fingerprint"],
            LOGISTIC_ARTIFACT_SCHEMA if logistic else TRAINING_ARTIFACT_SCHEMA,
        )
        content_hash = training_content_hash(schema_fp, artifact_bytes)
        training_from = {
            "validation_dataset_id": validation_parent_info["dataset_id"],
            "validation_commit_address": validation_parent_info["commit_address"],
            "validation_canonical_content_hash": validation_parent_info[
                "canonical_content_hash"
            ],
            "validation_artifact_sha256": validation_parent_info["artifact_sha256"],
            "validation_artifact_size": validation_parent_info["artifact_size"],
            "research_dataset_id": research_parent_info["dataset_id"],
            "research_commit_address": research_parent_info["commit_address"],
            "research_canonical_content_hash": research_parent_info[
                "canonical_content_hash"
            ],
            "research_parquet_sha256": research_parent_info["parquet_sha256"],
            "research_parquet_size": research_parent_info["parquet_size"],
        }
        if logistic:
            assert training_parent is not None
            training_from.update(
                {
                    "training_dataset_id": training_parent["info"]["dataset_id"],
                    "training_commit_address": training_parent["info"]["commit_address"],
                    "training_canonical_content_hash": training_parent["info"][
                        "canonical_content_hash"
                    ],
                    "training_artifact_sha256": training_parent["info"]["artifact_sha256"],
                    "training_artifact_size": training_parent["info"]["artifact_size"],
                }
            )
        prospective_commit = training_commit_identity(content_hash, training_from)
        common = {
            "descriptor": descriptor,
            "validation_parent_info": validation_parent_info,
            "research_parent_info": research_parent_info,
            "validation_artifact": parents["validation_artifact"],
            "research_rows": parents["research_rows"],
            "validation_artifact_bytes": parents["validation_artifact_bytes"],
            "validation_quality_state": parents["val_manifest"]["quality_state"],
            "research_quality_state": parents["res_manifest"]["quality_state"],
            "validation_lineage": parents["validation_lineage"],
            "artifact": artifact,
            "artifact_bytes": artifact_bytes,
            "schema_fingerprint": schema_fp,
            "canonical_content_hash": content_hash,
            "training_from": training_from,
            "prospective_commit_identity": prospective_commit,
        }
        if logistic:
            assert training_parent is not None
            # The kill gate sits between artifact construction and quality
            # evaluation: a failing artifact is never scored for publication.
            if kill["all_passed"]:
                report = evaluate_logistic_training_quality(
                    training_parent_info=training_parent["info"],
                    training_quality_state=training_parent["quality_state"],
                    **common,
                )
            else:
                report = None
        else:
            report = evaluate_training_quality(**common)
    except Exception as exc:
        print(f"training computation failed: {exc}", file=sys.stderr)
        pre_attempt("BLOCKED", "training_computation_failed")
        return EXIT_BLOCKED

    if logistic and not kill["all_passed"]:
        # Pre-registered kill criteria failed: nothing is staged, the lane
        # pointer is untouched, and the attempt manifest carries the evidence.
        failed = [name for name, passed in kill["results"].items() if not passed]
        print(
            f"kill criteria failed: {failed}; observed={kill['observed']}",
            file=sys.stderr,
        )
        if not dry_run:
            _write_per_fold_sidecar(
                records,
                data
                / "diagnostic"
                / "training"
                / f"per_fold_{attempt_id}.json",
            )
            _write_kill_attempt(data, root, attempt_id, kill)
        return EXIT_KILL_CRITERIA_FAILED

    if report.state != "PASS":
        print(f"training quality failed: {report.failing_checks()}", file=sys.stderr)
        pre_attempt("BLOCKED", "training_quality_failed")
        return EXIT_BLOCKED
    if dry_run:
        return EXIT_OK

    training_dir = _dataset_dir(data, "training", descriptor.start_utc)
    commits_dir = training_dir / "commits"
    commits_dir.mkdir(parents=True, exist_ok=True)
    lock_path = training_dir / "training.lock"
    lock_owned = False
    staging_dir = commits_dir / f".staging-{attempt_id}"

    def finish(result: str, referenced: str | None, diagnostics: list[str], state: str) -> None:
        _write_attempt(
            data,
            root,
            attempt_id,
            result,
            referenced,
            diagnostics,
            {
                "training_artifact": state,
                "pointer_replaced": result in ("PUBLISHED",),
            },
        )

    try:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            finish("BLOCKED", None, ["lock_contested"], "not_written")
            return EXIT_BLOCKED
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"attempt_id": attempt_id}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        lock_owned = True
        if (
            (parents["val_dir"] / "current.json").read_bytes()
            != parents["val_pointer_bytes"]
            or (parents["res_dir"] / "current.json").read_bytes()
            != parents["res_pointer_bytes"]
        ):
            finish("BLOCKED", None, ["parent_pointer_drift"], "not_written")
            return EXIT_BLOCKED

        object_ref = {"kind": "normalized", "sha256": sha256_hex(artifact_bytes)}
        evidence = {
            "descriptor_sha256": sha256_hex(descriptor_file.read_bytes()),
            "schema_fingerprint": schema_fp,
            "canonical_content_hash": content_hash,
            "quality_identity": report.identity(),
            "object_refs": [object_ref],
            "training_from": training_from,
            "training_commit_identity": prospective_commit,
        }
        candidate = commits_dir / prospective_commit
        pointer_file = training_dir / "current.json"
        if pointer_file.exists() and candidate.is_dir():
            pointer = json.loads(pointer_file.read_text(encoding="utf-8"))
            if pointer.get("commit") == prospective_commit and existing_commit_matches(
                data, candidate, evidence, keys=TRAINING_EVIDENCE_KEYS
            ):
                verify_training_current_graph(training_dir, data)
                finish("VERIFIED_NO_OP", prospective_commit, [], "already_published")
                return EXIT_OK
        if candidate.is_dir() and (candidate / "COMMITTED").exists():
            verified = _authenticate_retained_training_commit(candidate, prospective_commit, data)
            if not existing_commit_matches(
                data, candidate, evidence, keys=TRAINING_EVIDENCE_KEYS
            ):
                raise QuantaraError("retained candidate evidence mismatch")
            write_current(training_dir, prospective_commit, verified["manifest_sha256"])
            verify_training_current_graph(training_dir, data)
            finish("PUBLISHED", prospective_commit, [], "already_published")
            return EXIT_OK

        stored = store_object(data, "normalized", artifact_bytes)
        manifest = {
            "dataset_id": descriptor.dataset_id,
            "schema_version": descriptor.schema_version,
            "schema_fingerprint": schema_fp,
            "parser_version": "1.0.0",
            "canonical_content_hash": content_hash,
            "quality_identity": report.identity(),
            "quality_state": "PASS",
            "quality_policy_version": QUALITY_POLICY_VERSION,
            "commit_identity": prospective_commit,
            "artifact_sha256": stored.sha256,
            "artifact_size": len(artifact_bytes),
            "object_refs": [{"kind": "normalized", "sha256": stored.sha256}],
            "training_from": training_from,
            "parent_discovery": {
                "validation_pointer_manifest_sha256": json.loads(
                    parents["val_pointer_bytes"]
                )["manifest_sha256"],
                "research_pointer_manifest_sha256": json.loads(
                    parents["res_pointer_bytes"]
                )["manifest_sha256"],
            },
            "period": artifact["period"],
            "model": dict(descriptor.model),
            "training_set": dict(descriptor.training_set),
            "features": list(descriptor.features),
            "target": descriptor.target,
            "metrics": list(descriptor.metrics),
            "baselines": list(descriptor.baselines),
            "decimal_contract": dict(DECIMAL_CONTRACT),
            "legal_record_id": rights.record_id,
            "legal_states": {name: entry.state for name, entry in rights.operations.items()},
            "environment": environment_evidence(root),
        }
        quality_doc = {
            "state": "PASS",
            "policy_version": QUALITY_POLICY_VERSION,
            "identity": report.identity(),
            "findings": [
                {
                    "check_id": item.check_id,
                    "count": item.count,
                    "evidence": item.evidence,
                    "outcome": item.outcome,
                    "severity": item.severity,
                }
                for item in report.findings
            ],
        }
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        files = {
            "manifest.json": manifest_bytes,
            "content.json": (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode(),
            "quality.json": (json.dumps(quality_doc, indent=2, sort_keys=True) + "\n").encode(),
        }
        staged = stage_commit(training_dir, attempt_id, files)
        publish_commit(staged, commits_dir, prospective_commit)
        write_current(training_dir, prospective_commit, sha256_hex(manifest_bytes))
        verify_training_current_graph(training_dir, data)
        finish("PUBLISHED", prospective_commit, [], "published")
        return EXIT_OK
    except Exception as exc:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        print(f"training publication failed: {exc}", file=sys.stderr)
        finish(
            "FAILED",
            None,
            [getattr(exc, "error_id", "training_publication_failed")],
            "not_written",
        )
        return EXIT_FAILED
    finally:
        if lock_owned:
            try:
                owner = json.loads(lock_path.read_text(encoding="utf-8"))
                if owner.get("attempt_id") == attempt_id:
                    lock_path.unlink()
            except Exception:
                pass


def _authenticate_retained_training_commit(
    commit_dir: Path, address: str, data_root: Path
) -> dict:
    content = verify_commit_graph(data_root, commit_dir)
    manifest_bytes = (commit_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    quality = json.loads((commit_dir / "quality.json").read_text(encoding="utf-8"))
    if manifest.get("commit_identity") != address:
        raise QuantaraError("training manifest commit identity mismatch")
    if content.get("training_commit_identity") != address:
        raise QuantaraError("training content commit identity mismatch")
    if set(content) != set(TRAINING_EVIDENCE_KEYS):
        raise QuantaraError("training content evidence key set mismatch")
    artifact_sha = manifest.get("artifact_sha256")
    artifact_size = manifest.get("artifact_size")
    artifact_file = data_root / "objects" / "normalized" / "sha256" / artifact_sha
    artifact_bytes = artifact_file.read_bytes()
    if sha256_hex(artifact_bytes) != artifact_sha or len(artifact_bytes) != artifact_size:
        raise QuantaraError("training artifact object authentication failed")
    artifact = json.loads(artifact_bytes.decode("utf-8"))
    if artifact_bytes != canonicalize(artifact).encode("utf-8") + b"\n":
        raise QuantaraError("training artifact is not canonical JCS plus LF")
    artifact_schema = artifact.get("schema")
    if artifact_schema == LOGISTIC_ARTIFACT_SCHEMA:
        expected_checks = LOGISTIC_CHECK_IDS
    elif artifact_schema == TRAINING_ARTIFACT_SCHEMA:
        expected_checks = CHECK_IDS
    else:
        raise QuantaraError(f"unknown training artifact schema {artifact_schema!r}")
    findings = quality.get("findings", [])
    if (
        quality.get("state") != "PASS"
        or manifest.get("quality_state") != "PASS"
        or len(findings) != len(expected_checks)
        or [item.get("check_id") for item in findings] != list(expected_checks)
        or any(item.get("outcome") != "pass" or item.get("severity") != "hard" for item in findings)
    ):
        raise QuantaraError("training retained quality evidence is not exact PASS")
    qid = quality_identity(findings)
    if not (
        qid
        == quality.get("identity")
        == manifest.get("quality_identity")
        == content.get("quality_identity")
    ):
        raise QuantaraError("training quality identity disagreement")
    if artifact_schema == LOGISTIC_ARTIFACT_SCHEMA:
        kill = artifact.get("kill_criteria")
        if not isinstance(kill, dict) or kill.get("all_passed") is not True:
            raise QuantaraError("retained logistic artifact did not pass its kill criteria")
    expected_schema = training_schema_fingerprint(
        _retained_parent_fingerprint(data_root, manifest, "validation"), artifact_schema
    )
    expected_content = training_content_hash(expected_schema, artifact_bytes)
    lineage = content.get("training_from")
    expected_commit = training_commit_identity(expected_content, lineage)
    if not (
        expected_schema == manifest.get("schema_fingerprint") == content.get("schema_fingerprint")
        and expected_content
        == manifest.get("canonical_content_hash")
        == content.get("canonical_content_hash")
        and expected_commit == address
    ):
        raise QuantaraError("training retained identity equations disagree")
    if artifact.get("dataset_id") != manifest.get("dataset_id"):
        raise QuantaraError("training artifact/manifest dataset mismatch")
    return {
        "manifest_sha256": sha256_hex(manifest_bytes),
        "artifact_sha256": artifact_sha,
        "artifact_schema": artifact_schema,
        "canonical_content_hash": expected_content,
        "schema_fingerprint": expected_schema,
        "quality_identity": qid,
        "training_from": lineage,
        "records": artifact.get("records", []),
        "summaries": artifact.get("summaries", []),
        "baselines": artifact.get("baselines", {}),
        "kill_criteria": artifact.get("kill_criteria"),
    }


def _retained_parent_fingerprint(data_root: Path, manifest: dict, lane: str) -> str:
    lineage = manifest["training_from"]
    prefix = "validation" if lane == "validation" else "research"
    commit = lineage[f"{prefix}_commit_address"]
    period = manifest["period"]
    start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
    parent_dir = _dataset_dir(data_root, lane, start) / "commits" / commit
    parent_content = verify_commit_graph(data_root, parent_dir)
    parent_manifest_bytes = (parent_dir / "manifest.json").read_bytes()
    parent_manifest = json.loads(parent_manifest_bytes.decode("utf-8"))
    discovery_key = f"{prefix}_pointer_manifest_sha256"
    if sha256_hex(parent_manifest_bytes) != manifest["parent_discovery"][discovery_key]:
        raise QuantaraError(f"retained {lane} discovery digest mismatch")
    if parent_manifest.get("canonical_content_hash") != lineage[f"{prefix}_canonical_content_hash"]:
        raise QuantaraError(f"retained {lane} canonical content mismatch")
    if parent_content.get("canonical_content_hash") != lineage[f"{prefix}_canonical_content_hash"]:
        raise QuantaraError(f"retained {lane} content evidence mismatch")
    return parent_manifest["schema_fingerprint"]


def verify_training_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    pointer_bytes = (dataset_dir / "current.json").read_bytes()
    pointer = json.loads(pointer_bytes.decode("utf-8"))
    if set(pointer) != {"publication_protocol_version", "commit", "manifest_sha256"}:
        raise QuantaraError("training current pointer key set mismatch")
    if pointer.get("publication_protocol_version") != "v1":
        raise QuantaraError("unsupported training publication protocol")
    address = pointer.get("commit")
    if not isinstance(address, str) or len(address) != 64:
        raise QuantaraError("training pointer commit is not a SHA-256 address")
    verified = _authenticate_retained_training_commit(
        dataset_dir / "commits" / address, address, Path(data_root)
    )
    if verified["manifest_sha256"] != pointer.get("manifest_sha256"):
        raise QuantaraError("training pointer manifest digest mismatch")
    return {"commit": address, **verified}
