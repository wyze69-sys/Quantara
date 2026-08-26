"""Lineage-bound validation-folds orchestration (data slice 004).

Mirrors the research-table pipeline: validation descriptor validation plus
the ``analyze_internal`` gate on the v2 rights record, full authentication of
the parent research graph (pointer protocol, lineage-bound address equation,
manifest digest pinning, Parquet byte hashes, decoded-row content identity,
authenticated PASS quality evidence), pure deterministic walk-forward fold
construction with label-horizon embargo, per-fold exact Decimal test statistics
with structural-null equality, PASS-only validation quality gating, CAS object
storage under analytical kind "normalized", domain-separated lineage-bound
commit address, immutable publication through the unchanged protocol with
idempotent VERIFIED_NO_OP detection over extended evidence keys, and attempt
manifests carrying truthful milestones (including the 290c963 post-pointer
failure contract).
Exit codes: 0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from quantara.descriptor import load_rights_record
from quantara.errors import QuantaraError
from quantara.fold_stats import FoldStats, compute_fold_stats
from quantara.folds import FoldPartition, build_walkforward_folds
from quantara.hashing import (
    descriptor_hash,
    quality_identity,
    render_decimal_18,
    research_content_hash,
    research_schema_fingerprint,
    sha256_hex,
    validation_content_hash,
    validation_schema_fingerprint,
)
from quantara.jcs import canonicalize
from quantara.manifests import (
    PARSER_VERSION,
    attempt_id_now,
    build_dataset_manifest,
    environment_evidence,
    new_attempt_manifest,
    write_json,
)
from quantara.publication import (
    PUBLICATION_PROTOCOL_VERSION,
    existing_commit_matches,
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
from quantara.validation_descriptor import (
    UndersizedParentDataset,
    ValidationDescriptor,
    load_validation_descriptor,
)
from quantara.validation_quality import (
    QUALITY_POLICY_VERSION,
    evaluate_validation_quality,
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

# Idempotency evidence = key set extended with the validation
# lineage block and the lineage-bound commit identity binding them together.
VALIDATION_EVIDENCE_KEYS = (
    "source_sha256",
    "descriptor_sha256",
    "schema_fingerprint",
    "parser_version",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "validation_from",
    "validation_commit_identity",
)


def validation_commit_identity(content_hash: str, lineage: dict) -> str:
    """Deterministic validation commit address (design §8).

    Domain-separated SHA-256 over JCS of ``{domain, canonical_content_hash,
    validation_from}``: the logical validation artifact content bound to the
    authenticated parent lineage evidence.
    """
    payload = {
        "domain": "quantara-validation-commit-identity-v1",
        "canonical_content_hash": content_hash.lower(),
        "validation_from": lineage,
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def epoch_ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def _dataset_dir(data_root: Path, symbol: str, interval: str, start: datetime) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "validation"
        / symbol
        / interval
        / f"year={start:%Y}"
        / f"month={start:%m}"
    )


def _parent_research_dir(data_root: Path, symbol: str, interval: str, start: datetime) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "research"
        / symbol
        / interval
        / f"year={start:%Y}"
        / f"month={start:%m}"
    )


class ValidationGraphVerificationFailed(QuantaraError):
    error_id = "validation_current_verification_failed"


def render_content_rows(rows: list[tuple]) -> list[list[object]]:
    rendered = []
    for row in rows:
        rendered.append(
            [
                row[0],
                *[None if row[i] is None else render_decimal_18(row[i]) for i in range(1, 6)],
                row[6],
            ]
        )
    return rendered


def _write_attempt(
    data_root: Path,
    repo_root: Path,
    *,
    terminal_result: str,
    dispositions: dict[str, str],
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
    attempts_dir = Path(data_root) / "attempts" / "validation"
    target = attempts_dir / f"{attempt['attempt_id']}.json"
    try:
        write_json(target, attempt)
    except OSError as exc:
        print(f"warning: attempt manifest write failed: {exc}", file=sys.stderr)


def _resolve_rights(descriptor_path: Path, legal_record: str) -> Path:
    target = descriptor_path.resolve().parent
    rights_path = target / legal_record
    while not rights_path.exists() and target != target.parent:
        target = target.parent
        rights_path = target / legal_record
    return rights_path


def _verify_parent(parent_dir: Path, data_root: Path, parent_desc) -> dict:
    """Full authentication of parent research table."""
    pointer_path = parent_dir / "current.json"
    if not pointer_path.exists():
        raise QuantaraError(f"parent current.json missing under {parent_dir}")
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"parent current.json unreadable: {exc}") from exc
    if not isinstance(pointer, dict):
        raise QuantaraError("parent current.json must be a JSON object")

    graph = verify_research_current_graph(parent_dir, data_root)
    commit_dir = parent_dir / "commits" / graph["commit"]
    try:
        manifest = json.loads((commit_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"parent manifest unreadable: {exc}") from exc

    if manifest.get("dataset_id") != parent_desc.dataset_id:
        raise QuantaraError(
            f"parent dataset_id {manifest.get('dataset_id')!r} "
            f"does not match {parent_desc.dataset_id!r}"
        )

    expected_fp = research_schema_fingerprint(parent_desc.schema_version)
    if manifest.get("schema_fingerprint") != expected_fp:
        raise QuantaraError("parent research schema_fingerprint does not match descriptor")

    normalized_refs = [
        ref for ref in graph.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if len(normalized_refs) != 1:
        raise QuantaraError("parent commit must reference exactly one normalized object")
    stored_sha = normalized_refs[0]["sha256"]
    parquet_path = data_root / "objects" / "normalized" / "sha256" / stored_sha
    if not parquet_path.exists():
        raise QuantaraError(f"parent Parquet object missing at {parquet_path}")

    parquet_bytes = parquet_path.read_bytes()
    if sha256_hex(parquet_bytes) != stored_sha:
        raise QuantaraError("parent Parquet object bytes fail their own digest")
    if manifest.get("parquet_size") != len(parquet_bytes):
        raise QuantaraError(
            f"parent Parquet size {len(parquet_bytes)} disagrees with "
            f"manifest {manifest.get('parquet_size')}"
        )

    decoded_rows = read_research_rows(parquet_path)
    recomputed_cch = research_content_hash(expected_fp, render_content_rows(decoded_rows))
    if recomputed_cch != manifest.get("canonical_content_hash"):
        raise QuantaraError("parent research content identity does not match retained rows")

    return {
        "commit": graph["commit"],
        "canonical_content_hash": manifest["canonical_content_hash"],
        "parquet_sha256": stored_sha,
        "parquet_size": len(parquet_bytes),
        "parquet_path": parquet_path,
        "row_count": len(decoded_rows),
        "decoded_rows": decoded_rows,
        "quality_identity": graph.get("quality_identity"),
    }


def _authenticate_validation_quality_document(commit_dir: Path, manifest: dict) -> dict:
    try:
        quality_doc = json.loads((commit_dir / "quality.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"quality.json missing or invalid: {exc}") from exc
    if not isinstance(quality_doc, dict):
        raise QuantaraError("quality.json must be a JSON object")
    expected_keys = {"state", "policy_version", "identity", "findings"}
    if set(quality_doc) != expected_keys:
        raise QuantaraError(f"quality.json keys must be exactly {sorted(expected_keys)}")
    committed_findings = quality_doc["findings"]
    if not isinstance(committed_findings, list) or not committed_findings:
        raise QuantaraError("quality findings must be a non-empty list")

    authenticated_identity = quality_identity(committed_findings)
    if quality_doc["identity"] != authenticated_identity:
        raise QuantaraError("quality identity disagrees with its committed findings")
    if manifest.get("quality_state") != quality_doc["state"]:
        raise QuantaraError("manifest quality state disagrees with quality.json")
    if str(manifest.get("quality_policy_version")) != str(quality_doc["policy_version"]):
        raise QuantaraError("manifest quality policy version disagrees with quality.json")
    if manifest.get("quality_identity") != authenticated_identity:
        raise QuantaraError("manifest quality identity disagrees with quality.json")
    return quality_doc


def verify_validation_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    """Full authentication of a validation current graph."""
    pointer_path = dataset_dir / "current.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"unreadable current.json: {exc}") from exc
    if not isinstance(pointer, dict):
        raise QuantaraError("current.json must be a JSON object")

    expected_pointer_keys = {
        "publication_protocol_version",
        "commit",
        "manifest_sha256",
    }
    if set(pointer) != expected_pointer_keys:
        raise QuantaraError(
            "current.json keys must be exactly "
            f"{sorted(expected_pointer_keys)}, got {sorted(pointer)}"
        )
    if pointer["publication_protocol_version"] != PUBLICATION_PROTOCOL_VERSION:
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

    lineage = content.get("validation_from")
    content_hash = content.get("canonical_content_hash")
    recorded_address = content.get("validation_commit_identity")
    if lineage is None or content_hash is None or recorded_address is None:
        raise QuantaraError("content.json lacks validation identity evidence")

    recomputed_address = validation_commit_identity(content_hash, lineage)
    if recomputed_address != address or recorded_address != address:
        raise ValidationGraphVerificationFailed(
            f"address binding mismatch: recomputed {recomputed_address!r}, "
            f"recorded {recorded_address!r}, pointer/commit {address!r}"
        )

    for key in (
        "schema_fingerprint",
        "parser_version",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "validation_from",
    ):
        if manifest.get(key) != content.get(key):
            raise QuantaraError(f"manifest/content disagreement on {key!r}")
    if manifest.get("commit_identity") != address:
        raise QuantaraError("manifest commit_identity disagrees with commit address")

    normalized_refs = [
        ref for ref in content.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if (
        len(normalized_refs) != 1
        or manifest.get("artifact_sha256") != normalized_refs[0]["sha256"]
    ):
        raise QuantaraError("manifest artifact SHA-256 disagrees with object ref")

    quality_doc = _authenticate_validation_quality_document(commit_dir, manifest)
    if quality_doc["state"] != "PASS" or manifest.get("quality_state") != "PASS":
        raise ValidationGraphVerificationFailed(
            "validation quality state is not PASS; less-than-verified graph is never honored"
        )

    return {**content, "commit": address}


def _quality_payload(report) -> dict:
    return {
        "state": report.state,
        "policy_version": QUALITY_POLICY_VERSION,
        "identity": report.identity(),
        "findings": [
            {
                "check_id": f.check_id,
                "outcome": f.outcome,
                "severity": f.severity,
                "count": f.count,
                "evidence": f.evidence,
            }
            for f in report.findings
        ],
    }


def build_validation_artifact(
    descriptor: ValidationDescriptor,
    partition: FoldPartition,
    fold_stats_list: list[FoldStats],
) -> dict:
    return {
        "schema": "quantara.validation_folds/v1",
        "fold_set": descriptor.fold_set["name"],
        "scheme": descriptor.scheme,
        "parameters": {
            "test_size": descriptor.parameters["test_size"],
            "min_train_size": descriptor.parameters["min_train_size"],
            "embargo": descriptor.embargo,
        },
        "parent_rows": partition.parent_rows,
        "excluded_head_rows": partition.excluded_head_rows,
        "folds": [
            {
                "fold_id": fold.fold_id,
                "train_range": list(fold.train_range) if fold.train_range else None,
                "embargo_range": list(fold.embargo_range) if fold.embargo_range else None,
                "test_range": list(fold.test_range),
                "stats": stats.to_dict(),
            }
            for fold, stats in zip(partition.folds, fold_stats_list, strict=True)
        ],
        "coverage": partition.coverage,
    }


def run_validation_pipeline(
    descriptor_path: Path | str,
    data_root: Path | str,
    repo_root: Path | str | None = None,
    dry_run: bool = False,
) -> int:
    """Execute the walk-forward validation folds pipeline."""
    data = Path(data_root)
    root = Path(repo_root) if repo_root is not None else Path(descriptor_path).resolve().parents[2]
    descriptor_file = Path(descriptor_path)

    try:
        descriptor = load_validation_descriptor(descriptor_file)
    except UndersizedParentDataset as exc:
        print(f"undersized_parent_dataset: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"validation_artifact": "not_written"},
            referenced_commit=None,
            diagnostics=["undersized_parent_dataset"],
        )
        return EXIT_BLOCKED
    except QuantaraError as exc:
        print(f"invalid_descriptor: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"validation_artifact": "not_written"},
            referenced_commit=None,
            diagnostics=[getattr(exc, "error_id", "invalid_descriptor")],
        )
        return EXIT_BLOCKED

    # Step 1: Legal gate — v2 record, analyze_internal check
    try:
        rights_record = load_rights_record(
            _resolve_rights(descriptor_file, descriptor.legal_record)
        )
    except (QuantaraError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"rights record unavailable: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"validation_artifact": "not_written"},
            referenced_commit=None,
            diagnostics=["rights_record_unavailable"],
        )
        return EXIT_FAILED

    if not rights_record.permits("analyze_internal"):
        print("legal gate blocks analyze_internal", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"analyze_internal": "blocked"},
            referenced_commit=None,
            diagnostics=["legal_gate_blocked"],
        )
        return EXIT_BLOCKED

    parent_desc = descriptor.parent_descriptor
    symbol = parent_desc.base_descriptor.provider_symbol
    interval = parent_desc.base_descriptor.interval
    parent_dir = _parent_research_dir(data, symbol, interval, parent_desc.start_utc)
    validation_dir = _dataset_dir(data, symbol, interval, descriptor.start_utc)

    # Step 2: Parent research table authentication — BLOCKED otherwise
    try:
        parent = _verify_parent(parent_dir, data, parent_desc)
    except (QuantaraError, OSError, ValueError, KeyError) as exc:
        diagnostic = getattr(exc, "error_id", None) or "parent_dataset_unavailable"
        print(f"parent_dataset_unavailable: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"validation_artifact": "not_written"},
            referenced_commit=None,
            diagnostics=[diagnostic],
        )
        return EXIT_BLOCKED

    # Step 3: Check actual parent rows against minimum rows
    actual_parent_rows = parent["row_count"]
    if actual_parent_rows < descriptor.minimum_rows:
        print(
            f"undersized_parent_dataset: actual {actual_parent_rows} < "
            f"minimum {descriptor.minimum_rows}",
            file=sys.stderr,
        )
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"validation_artifact": "not_written"},
            referenced_commit=None,
            diagnostics=["undersized_parent_dataset"],
        )
        return EXIT_BLOCKED

    if dry_run:
        # Steps 1–3 verification only; no mutations
        return EXIT_OK

    attempt_id = attempt_id_now()
    staging = data / "staging" / attempt_id
    validation_dot_staging = validation_dir / "commits" / f".staging-{attempt_id}"
    milestones = {
        "attempt_staged": False,
        "object_written": False,
        "commit_renamed": False,
        "pointer_replaced": False,
        "discovery_verified": False,
    }
    artifact_state = "not_written"
    cleanup_state = {"staging": "pending"}
    commit_address: str | None = None

    def _cleanup_attempt() -> None:
        ok = True
        for directory in (staging, validation_dot_staging):
            try:
                shutil.rmtree(directory)
            except OSError:
                if directory.exists():
                    ok = False
        cleanup_state["staging"] = "discarded" if ok else "cleanup_failed"

    def _dispositions(extra: dict | None = None) -> dict:
        dispositions = {
            "validation_artifact": artifact_state,
            **milestones,
            "attempt_staging": cleanup_state["staging"],
        }
        if extra:
            dispositions.update(extra)
        return dispositions

    def _terminal_failure(
        diagnostic: str,
        referenced: str | None,
        extra: dict | None = None,
        exc: Exception | None = None,
    ) -> int:
        _cleanup_attempt()
        detail = f"{diagnostic}: {exc}" if exc is not None else diagnostic
        print(f"validation pipeline failed: {detail}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions=_dispositions(extra),
            referenced_commit=referenced,
            diagnostics=[diagnostic],
        )
        return EXIT_FAILED

    try:
        for stale in (validation_dir / "commits").glob(".staging-*"):
            shutil.rmtree(stale, ignore_errors=True)

        staging.mkdir(parents=True, exist_ok=True)
        milestones["attempt_staged"] = True

        parent_rows = parent["decoded_rows"]
        partition = build_walkforward_folds(
            n_rows=len(parent_rows),
            test_size=descriptor.parameters["test_size"],
            min_train_size=descriptor.parameters["min_train_size"],
            embargo=descriptor.embargo,
        )

        fold_stats_list = [
            compute_fold_stats(
                parent_rows,
                fold.test_range,
                total_parent_rows=len(parent_rows),
                parameters=parent_desc.parameters,
            )
            for fold in partition.folds
        ]

        report = evaluate_validation_quality(
            partition=partition,
            fold_stats_list=fold_stats_list,
            expected_parent_rows=len(parent_rows),
            min_train_size=descriptor.parameters["min_train_size"],
            embargo=descriptor.embargo,
        )
        artifact_state = "staged_not_published"

        if report.state != "PASS":
            failing_checks = report.failing_checks() or [f"quality_state_{report.state}"]
            print(f"quality state {report.state} blocks publication", file=sys.stderr)
            _cleanup_attempt()
            _write_attempt(
                data,
                root,
                terminal_result="BLOCKED",
                dispositions=_dispositions(),
                referenced_commit=None,
                diagnostics=failing_checks,
            )
            return EXIT_BLOCKED

        artifact = build_validation_artifact(descriptor, partition, fold_stats_list)
        artifact_bytes = canonicalize(artifact).encode("utf-8") + b"\n"

        fingerprint = validation_schema_fingerprint(
            parent_fingerprint=research_schema_fingerprint(parent_desc.schema_version),
            schema_id=descriptor.schema_version,
            scheme=descriptor.scheme,
            parameters=dict(descriptor.parameters, embargo=descriptor.embargo),
            fold_set_name=descriptor.fold_set["name"],
            fold_set_version=descriptor.fold_set["version"],
        )
        descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
        content_hash = validation_content_hash(fingerprint, artifact_bytes)

        lineage = {
            "parent_dataset_id": parent_desc.dataset_id,
            "parent_commit_address": parent["commit"],
            "parent_canonical_content_hash": parent["canonical_content_hash"],
            "parent_parquet_sha256": parent["parquet_sha256"],
            "parent_parquet_size": parent["parquet_size"],
            "fold_set_name": descriptor.fold_set["name"],
            "fold_set_version": descriptor.fold_set["version"],
            "scheme": descriptor.scheme,
            "parameters": dict(descriptor.parameters),
            "embargo": descriptor.embargo,
        }
        commit_address = validation_commit_identity(content_hash, lineage)

        stored_normalized = store_object(data, "normalized", artifact_bytes)
        normalized_ref = stored_normalized.sha256
        milestones["object_written"] = stored_normalized.created
        artifact_state = "object_written" if stored_normalized.created else "object_reused"

        object_refs = [{"kind": "normalized", "sha256": normalized_ref}]
        identity_evidence = {
            "source_sha256": parent["parquet_sha256"],
            "descriptor_sha256": descriptor_sha,
            "schema_fingerprint": fingerprint,
            "parser_version": PARSER_VERSION,
            "canonical_content_hash": content_hash,
            "quality_identity": report.identity(),
            "object_refs": object_refs,
            "validation_from": lineage,
            "validation_commit_identity": commit_address,
        }

        # Idempotency check: verify retained commit if pointer exists
        pointer = validation_dir / "current.json"
        if pointer.exists():
            try:
                parsed_pointer = json.loads(pointer.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise QuantaraError(f"unreadable current.json: {exc}") from exc
            if not isinstance(parsed_pointer, dict):
                raise QuantaraError("current.json must be a JSON object")
            pointer_commit_name = str(parsed_pointer.get("commit", "")).lower()
            pointer_target = validation_dir / "commits" / pointer_commit_name
            pointer_lost = not (pointer_target / "COMMITTED").is_file()
            if not pointer_lost:
                verify_validation_current_graph(validation_dir, data)
                existing_dir = validation_dir / "commits" / parsed_pointer["commit"]
                if existing_commit_matches(
                    data,
                    existing_dir,
                    identity_evidence,
                    keys=VALIDATION_EVIDENCE_KEYS,
                ):
                    milestones["discovery_verified"] = True
                    _cleanup_attempt()
                    _write_attempt(
                        data,
                        root,
                        terminal_result="VERIFIED_NO_OP",
                        dispositions=_dispositions({"validation_artifact": "already_published"}),
                        referenced_commit=parsed_pointer["commit"],
                        diagnostics=[],
                    )
                    return EXIT_OK

        manifest = build_dataset_manifest(
            dataset_id=descriptor.dataset_id,
            instrument_id=descriptor.instrument_id,
            schema_version=descriptor.schema_version,
            schema_fingerprint=fingerprint,
            timestamp_semantics="closed_interval_v1",
            quality_policy_version=QUALITY_POLICY_VERSION,
            quality_identity=report.identity(),
            quality_state=report.state,
            parent_row_count=partition.parent_rows,
            fold_count=len(partition.folds),
            canonical_content_hash=content_hash,
            commit_identity=commit_address,
            artifact_sha256=normalized_ref,
            artifact_size=len(artifact_bytes),
            object_refs=object_refs,
            legal_record_id=rights_record.record_id,
            legal_states={name: entry.state for name, entry in rights_record.operations.items()},
            environment=environment_evidence(root),
            validation_from=lineage,
            fold_set=dict(descriptor.fold_set),
            scheme=descriptor.scheme,
            parameters=dict(descriptor.parameters),
            embargo=descriptor.embargo,
        )
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        files = {
            "manifest.json": manifest_bytes,
            "quality.json": (
                json.dumps(_quality_payload(report), indent=2, sort_keys=True) + "\n"
            ).encode(),
            "content.json": (
                json.dumps(identity_evidence, indent=2, sort_keys=True) + "\n"
            ).encode(),
        }
        staged_commit = stage_commit(validation_dir, attempt_id, files)
        try:
            commit_dir = publish_commit(staged_commit, validation_dir / "commits", commit_address)
            milestones["commit_renamed"] = True
        except QuantaraError:
            candidate = validation_dir / "commits" / commit_address
            if not (
                candidate.is_dir()
                and existing_commit_matches(
                    data,
                    candidate,
                    identity_evidence,
                    keys=VALIDATION_EVIDENCE_KEYS,
                )
            ):
                raise QuantaraError(
                    "commit rename failed and no equivalent commit exists"
                ) from None
            commit_dir = candidate
            manifest_bytes = (commit_dir / "manifest.json").read_bytes()

        verify_commit_graph(data, commit_dir)
        write_current(validation_dir, commit_address, sha256_hex(manifest_bytes))
        milestones["pointer_replaced"] = True
        verify_validation_current_graph(validation_dir, data)
        milestones["discovery_verified"] = True
    except (QuantaraError, OSError) as exc:
        diagnostic = getattr(exc, "error_id", None) or (
            "os_error" if isinstance(exc, OSError) else "validation_failure"
        )
        post_pointer = milestones["pointer_replaced"]
        extra = {"post_pointer": "published_unverified"} if post_pointer else None
        referenced = commit_address if post_pointer else None
        return _terminal_failure(diagnostic, referenced, extra, exc)

    _cleanup_attempt()
    _write_attempt(
        data,
        root,
        terminal_result="PUBLISHED",
        dispositions=_dispositions({"validation_artifact": "published"}),
        referenced_commit=commit_address,
        diagnostics=[],
    )
    return EXIT_OK
