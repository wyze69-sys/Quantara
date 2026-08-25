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
    put_object,
    read_and_verify_current,
    stage_commit,
    verify_commit_graph,
    write_current,
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

# Idempotency evidence = slice 001 key set extended with the lineage block
# and the derived commit identity that binds them together.
DERIVED_EVIDENCE_KEYS = (
    "source_sha256",
    "descriptor_sha256",
    "schema_fingerprint",
    "parser_version",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "derived_from",
    "derived_commit_identity",
)


def derived_commit_identity(canonical_content_hash: str, lineage: dict) -> str:
    """Deterministic derived commit address (correction 3).

    Binds the logical canonical row content to the authenticated parent
    lineage evidence: sha256 over a domain-separated JCS payload. A changed
    authenticated lineage therefore yields a distinct immutable commit even
    when every aggregated row — and the canonical_content_hash — is
    unchanged; identical content plus identical lineage reproduces it exactly,
    preserving idempotent VERIFIED_NO_OP behavior.
    """
    payload = {
        "domain": "quantara-derived-commit-identity-v1",
        "canonical_content_hash": canonical_content_hash.lower(),
        "derived_from": lineage,
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


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


def _verify_parent(parent_dir: Path, data_root: Path, base) -> dict:
    """Full parent verification before any computation (correction 2).

    Verifies, in order: current.json structure and protocol version, commit
    directory identity, COMMITTED marker + content.json + every referenced
    object hash (via read_and_verify_current), canonical content identity
    against the commit directory name, manifest.json bytes against the
    pointer's pinned digest, required manifest fields, actual Parquet byte
    hash and size, and committed descriptor/schema/quality evidence against
    the approved loaded base descriptor. Any missing, malformed, fabricated,
    or mismatched evidence raises QuantaraError → BLOCKED.
    """
    pointer_path = parent_dir / "current.json"
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
        raise QuantaraError(
            "current.json protocol version "
            f"{pointer['publication_protocol_version']!r} is not "
            f"{PUBLICATION_PROTOCOL_VERSION!r}"
        )
    commit_hash = pointer["commit"]
    pinned_digest = pointer["manifest_sha256"]
    for label, value in (
        ("commit", commit_hash),
        ("manifest_sha256", pinned_digest),
    ):
        lowered = value.lower() if isinstance(value, str) else ""
        if len(lowered) != 64 or any(ch not in "0123456789abcdef" for ch in lowered):
            raise QuantaraError(
                f"current.json {label} is not a sha256 hex digest: {value!r}"
            )

    # COMMITTED marker, content.json, object existence and hashes.
    content = read_and_verify_current(parent_dir, data_root)
    commit_dir = parent_dir / "commits" / commit_hash

    # Canonical content identity: the commit directory IS the address of the
    # canonical content it holds.
    if content.get("canonical_content_hash") != commit_hash:
        raise QuantaraError(
            "canonical content identity mismatch: content.json records "
            f"{content.get('canonical_content_hash')!r} but the commit "
            f"directory is {commit_hash!r}"
        )

    # Manifest bytes are pinned by the pointer's digest.
    manifest_path = commit_dir / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise QuantaraError(f"parent manifest.json unreadable: {exc}") from exc
    if sha256_hex(manifest_bytes) != pinned_digest:
        raise QuantaraError(
            "parent manifest.json bytes disagree with current.json "
            "manifest_sha256"
        )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"parent manifest not valid JSON: {exc}") from exc

    required_fields = (
        "dataset_id",
        "instrument_id",
        "schema_version",
        "schema_fingerprint",
        "timestamp_semantics",
        "quality_policy_version",
        "quality_state",
        "canonical_content_hash",
        "parquet_sha256",
        "parquet_size",
    )
    missing = [
        field
        for field in required_fields
        if manifest.get(field) in (None, "")
    ]
    if missing:
        raise QuantaraError(
            f"parent manifest missing required fields: {sorted(missing)}"
        )

    # Committed descriptor/schema/quality evidence vs the approved base
    # descriptor — fabricated-but-internally-consistent graphs are caught
    # here against the authoritative loaded configuration.
    if manifest["dataset_id"] != base.dataset_id:
        raise QuantaraError(
            f"parent dataset_id {manifest['dataset_id']!r} does not match "
            f"the approved base descriptor's {base.dataset_id!r}"
        )
    if manifest["instrument_id"] != base.instrument_id:
        raise QuantaraError(
            "parent instrument_id does not match the approved base descriptor"
        )
    if manifest["schema_version"] != base.schema_version:
        raise QuantaraError(
            f"parent schema_version {manifest['schema_version']!r} does not "
            f"match the approved base descriptor's {base.schema_version!r}"
        )
    expected_fingerprint = schema_fingerprint(base.schema_version)
    if manifest["schema_fingerprint"] != expected_fingerprint:
        raise QuantaraError(
            "parent schema_fingerprint does not match the approved base "
            "descriptor's logical schema fingerprint"
        )
    if manifest["timestamp_semantics"] != base.timestamp_semantics:
        raise QuantaraError(
            "parent timestamp_semantics does not match the approved base "
            "descriptor"
        )
    if str(manifest["quality_policy_version"]) != str(base.quality_policy_version):
        raise QuantaraError(
            "parent quality_policy_version does not match the approved base "
            "descriptor"
        )
    if manifest["quality_state"] != "PASS":
        raise QuantaraError(
            f"parent quality state is {manifest['quality_state']!r}; a "
            "less-than-verified parent is never a derivation input"
        )
    if manifest["canonical_content_hash"] != commit_hash:
        raise QuantaraError(
            "parent manifest canonical_content_hash disagrees with the commit "
            "directory identity"
        )

    normalized_refs = [
        ref
        for ref in content.get("object_refs", [])
        if ref.get("kind") == "normalized"
    ]
    if not normalized_refs:
        raise QuantaraError("parent commit references no normalized object")
    stored_sha = normalized_refs[0]["sha256"]
    if manifest["parquet_sha256"] != stored_sha:
        raise QuantaraError(
            "parent manifest Parquet SHA-256 disagrees with object ref"
        )
    object_path = data_root / "objects" / "normalized" / "sha256" / stored_sha
    parquet_bytes = object_path.read_bytes()
    if sha256_hex(parquet_bytes) != stored_sha:
        raise QuantaraError("parent Parquet object bytes fail their own digest")
    if manifest["parquet_size"] != len(parquet_bytes):
        raise QuantaraError(
            f"parent Parquet size {len(parquet_bytes)} disagrees with the "
            f"committed manifest value {manifest['parquet_size']}"
        )
    return {
        "commit": commit_hash,
        "canonical_content_hash": commit_hash,
        "parquet_sha256": stored_sha,
        "parquet_size": len(parquet_bytes),
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
        parent = _verify_parent(parent_dir, data, base)
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

    # Correction 3: the commit address binds canonical content to the
    # authenticated lineage, so changed lineage yields a distinct commit
    # even when every aggregated row is unchanged.
    commit_address = derived_commit_identity(content_hash, lineage)
    identity_evidence["derived_commit_identity"] = commit_address

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
        commit_identity=commit_address,
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
            staged_commit, derived_dir / "commits", commit_address
        )
    except QuantaraError:
        # Recovery: an equivalent commit already exists (e.g., pointer loss).
        candidate = derived_dir / "commits" / commit_address
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
    write_current(derived_dir, commit_address, sha256_hex(manifest_bytes))
    read_and_verify_current(derived_dir, data)

    shutil.rmtree(staging, ignore_errors=True)
    _write_attempt(
        data,
        root,
        terminal_result="PUBLISHED",
        dispositions={"normalized_parquet": "published"},
        referenced_commit=commit_address,
        diagnostics=[],
    )
    return EXIT_OK

