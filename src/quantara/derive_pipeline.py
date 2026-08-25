"""Lineage-bound derivation orchestration (data slice 002).

Mirrors the slice 001 pipeline structure: derived descriptor/rights validation
(gated on ``normalize_internal`` alone), full verification of the parent graph
through ``current.json`` (a missing or unverifiable parent is BLOCKED, never a
bypass), exact aggregation of complete canonical minute groups, staged Parquet
write/read-back/reconciliation, PASS-only quality gating, parameterized
identities plus a ``derived_from`` lineage block in the idempotency evidence,
and immutable publication through the unchanged content-addressed protocol.
Exit codes: 0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantara.aggregation import aggregate_timeframe, rows_from_persisted
from quantara.canonical import (
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.derive_descriptor import load_derived_descriptor
from quantara.derive_quality import evaluate_derived_quality
from quantara.descriptor import load_rights_record
from quantara.errors import QuantaraError
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    schema_fingerprint,
    sha256_hex,
)
from quantara.manifests import (
    PARSER_VERSION,
    attempt_id_now,
    build_dataset_manifest,
    environment_evidence,
    new_attempt_manifest,
    write_json,
)
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    put_object,
    read_and_verify_current,
    stage_commit,
    verify_commit_graph,
    write_current,
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

# Idempotency evidence = slice 001 key set extended with the lineage block.
DERIVED_EVIDENCE_KEYS = (
    "source_sha256",
    "descriptor_sha256",
    "schema_fingerprint",
    "parser_version",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "derived_from",
)


@dataclass(frozen=True)
class _QualityView:
    """Adapter exposing the temporal surface evaluate_derived_quality needs."""

    timeframe_ms: int
    start_utc_open_ms: int


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def epoch_ms(moment: datetime) -> int:
    """Exact UTC epoch milliseconds via integer timedelta division — never
    a binary float."""
    return (moment - EPOCH) // timedelta(milliseconds=1)


def _dataset_dir(data_root: Path, symbol: str, interval: str, start) -> Path:
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / symbol
        / interval
        / f"year={start:%Y}"
        / f"month={start:%m}"
    )


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
    write_json(Path(data_root) / "attempts" / f"{attempt['attempt_id']}.json", attempt)


def _quality_payload(report) -> dict:
    return {
        "state": report.state,
        "policy_version": "1",
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


def _resolve_rights(descriptor_path: Path, legal_record: str) -> Path:
    target = descriptor_path.resolve().parent
    rights_path = target / legal_record
    while not rights_path.exists() and target != target.parent:
        target = target.parent
        rights_path = target / legal_record
    return rights_path


def _derive_rows(parent_parquet_path: Path, descriptor, staging: Path):
    """Aggregate complete groups only, write staged Parquet with the fixed
    writer config, read back, reconcile field-by-field exactly, and evaluate
    derived quality (the reconciliation outcome is supplied by the pipeline)."""
    minutes = rows_from_persisted(read_canonical_rows(parent_parquet_path))
    bars = aggregate_timeframe(
        minutes, descriptor.identity_tuple(), descriptor.timeframe_ms
    )
    parquet_path = staging / "canonical.parquet"
    write_canonical_parquet(bars, parquet_path)
    persisted = read_canonical_rows(parquet_path)
    reconciliation_ok = True
    try:
        reconcile_rows(bars, persisted)
    except QuantaraError:
        reconciliation_ok = False
    view = _QualityView(descriptor.timeframe_ms, epoch_ms(descriptor.start_utc))
    report = evaluate_derived_quality(
        bars,
        view,
        expected_count=descriptor.expected_row_count,
        reconciliation_ok=reconciliation_ok,
    )
    return minutes, bars, parquet_path, report


def _verify_parent(parent_dir: Path, data_root: Path) -> dict:
    """Full parent verification; raises QuantaraError on any failure."""
    pointer = json.loads((parent_dir / "current.json").read_text(encoding="utf-8"))
    commit_hash = pointer["commit"]
    content = read_and_verify_current(parent_dir, data_root)
    manifest_path = parent_dir / "commits" / commit_hash / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    normalized_refs = [
        ref for ref in content.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if not normalized_refs:
        raise QuantaraError("parent commit references no normalized object")
    stored_sha = normalized_refs[0]["sha256"]
    if manifest.get("parquet_sha256") != stored_sha:
        raise QuantaraError("parent manifest Parquet SHA-256 disagrees with object ref")
    object_path = data_root / "objects" / "normalized" / "sha256" / stored_sha
    if not object_path.exists():
        raise QuantaraError("parent normalized object missing")
    return {
        "commit": commit_hash,
        "canonical_content_hash": content.get(
            "canonical_content_hash", commit_hash
        ),
        "parquet_sha256": stored_sha,
        "parquet_size": manifest.get("parquet_size"),
        "parquet_path": object_path,
    }


def run_derivation_pipeline(
    descriptor_path: str | Path,
    data_root: str | Path,
    dry_run: bool = False,
    repo_root: str | Path | None = None,
) -> int:
    root = Path(repo_root) if repo_root else Path.cwd()
    data = Path(data_root)
    descriptor_file = Path(descriptor_path)

    # Step 1: load + validate the derived descriptor; gate normalize_internal.
    try:
        descriptor = load_derived_descriptor(descriptor_file)
    except QuantaraError as exc:
        print(f"invalid descriptor: {exc}", file=sys.stderr)
        return EXIT_FAILED

    rights_record = load_rights_record(
        _resolve_rights(descriptor_file, descriptor.legal_record)
    )
    if not rights_record.permits("normalize_internal"):
        print("legal gate blocks normalize_internal", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"normalize_internal": "blocked"},
            referenced_commit=None,
            diagnostics=["legal_gate_blocked"],
        )
        return EXIT_BLOCKED

    base = descriptor.base_descriptor
    parent_dir = _dataset_dir(data, base.provider_symbol, "1m", base.start_utc)
    derived_dir = _dataset_dir(data, descriptor.provider_symbol,
                               descriptor.interval, descriptor.start_utc)

    # Step 2: the parent must resolve and fully verify — BLOCKED otherwise.
    try:
        parent = _verify_parent(parent_dir, data)
    except (QuantaraError, OSError, ValueError, KeyError) as exc:
        print(f"parent_dataset_unavailable: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"normalized_parquet": "not_written"},
            referenced_commit=None,
            diagnostics=["parent_dataset_unavailable"],
        )
        return EXIT_BLOCKED

    if dry_run:
        # Steps 1–2 verification only; no mutation of any dataset directory.
        return EXIT_OK

    # Recovery: stale staging directories are safe orphans; discard them.
    for stale in (derived_dir / "commits").glob(".staging-*"):
        shutil.rmtree(stale, ignore_errors=True)

    attempt_id = attempt_id_now()
    staging = data / "staging" / attempt_id
    staging.mkdir(parents=True, exist_ok=True)
    try:
        minutes, bars, parquet_path, report = _derive_rows(
            parent["parquet_path"], descriptor, staging
        )

        # PASS-only policy: exactly PASS publishes.
        if report.state != "PASS":
            print(f"quality state {report.state} blocks publication",
                  file=sys.stderr)
            _write_attempt(
                data,
                root,
                terminal_result="BLOCKED",
                dispositions={"normalized_parquet": "not_written"},
                referenced_commit=None,
                diagnostics=[
                    f.check_id for f in report.findings if f.outcome != "pass"
                ]
                or [f"quality_state_{report.state}"],
            )
            return EXIT_BLOCKED

        # Identities over the parameterized fingerprint.
        fingerprint = schema_fingerprint(descriptor.schema_version)
        descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
        content_hash = canonical_content_hash(
            fingerprint, [row.to_content_array() for row in bars]
        )
        parquet_bytes = parquet_path.read_bytes()
        parquet_sha = sha256_hex(parquet_bytes)
        normalized_ref = put_object(data, "normalized", parquet_bytes)
    except QuantaraError as exc:
        print(f"derivation failed: {exc}", file=sys.stderr)
        return EXIT_FAILED



    object_refs = [{"kind": "normalized", "sha256": normalized_ref}]
    lineage = {
        "parent_dataset_id": base.dataset_id,
        "parent_canonical_content_hash": parent["canonical_content_hash"],
        "parent_parquet_sha256": parent["parquet_sha256"],
        "parent_parquet_size": parent["parquet_size"],
        "parent_descriptor_sha256": descriptor_hash(base.canonical_semantics()),
        "parent_schema_fingerprint": schema_fingerprint(base.schema_version),
        "transformation": {
            "name": descriptor.transformation["name"],
            "version": descriptor.transformation["version"],
            "timeframe_ms": descriptor.timeframe_ms,
        },
    }

    # Step 6: identity evidence = slice 001 key set + derived_from lineage.
    identity_evidence = {
        # Derivation input bytes stand where the source ZIP stood in slice 001.
        "source_sha256": parent["parquet_sha256"],
        "descriptor_sha256": descriptor_sha,
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": content_hash,
        "quality_identity": report.identity(),
        "object_refs": object_refs,
        "derived_from": lineage,
    }

    # Idempotent rerun: verify the existing commit incl. its parent binding.
    pointer = derived_dir / "current.json"
    if pointer.exists():
        current_commit = json.loads(pointer.read_text(encoding="utf-8")).get(
            "commit", ""
        )
        commit_dir = derived_dir / "commits" / current_commit
        if existing_commit_matches(
            data, commit_dir, identity_evidence, keys=DERIVED_EVIDENCE_KEYS
        ):
            shutil.rmtree(staging, ignore_errors=True)
            _write_attempt(
                data,
                root,
                terminal_result="VERIFIED_NO_OP",
                dispositions={"normalized_parquet": "already_published"},
                referenced_commit=current_commit,
                diagnostics=[],
            )
            return EXIT_OK



    # Steps 7–8: staged evidence, atomic publication, verified pointer.
    manifest = build_dataset_manifest(
        dataset_id=descriptor.dataset_id,
        instrument_id=descriptor.instrument_id,
        schema_version=descriptor.schema_version,
        schema_fingerprint=fingerprint,
        timestamp_semantics=descriptor.timestamp_semantics,
        quality_policy_version="1",
        quality_identity=report.identity(),
        quality_state=report.state,
        source_row_count=len(minutes),
        canonical_row_count=len(bars),
        canonical_content_hash=content_hash,
        parquet_sha256=parquet_sha,
        parquet_size=len(parquet_bytes),
        object_refs=object_refs,
        legal_record_id=rights_record.record_id,
        legal_states={
            name: entry.state for name, entry in rights_record.operations.items()
        },
        environment=environment_evidence(root),
        derived_from=lineage,
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
    staged_commit = stage_commit(derived_dir, attempt_id, files)
    try:
        commit_dir = publish_commit(
            staged_commit, derived_dir / "commits", content_hash
        )
    except QuantaraError:
        # Recovery: an equivalent commit already exists (e.g., pointer loss).
        candidate = derived_dir / "commits" / content_hash
        if not (
            candidate.is_dir()
            and existing_commit_matches(
                data, candidate, identity_evidence, keys=DERIVED_EVIDENCE_KEYS
            )
        ):
            print(
                "publication failed: existing commit differs from current evidence",
                file=sys.stderr,
            )
            return EXIT_FAILED
        commit_dir = candidate

    verify_commit_graph(data, commit_dir)
    write_current(derived_dir, content_hash, sha256_hex(manifest_bytes))
    read_and_verify_current(derived_dir, data)

    shutil.rmtree(staging, ignore_errors=True)
    _write_attempt(
        data,
        root,
        terminal_result="PUBLISHED",
        dispositions={"normalized_parquet": "published"},
        referenced_commit=content_hash,
        diagnostics=[],
    )
    return EXIT_OK

