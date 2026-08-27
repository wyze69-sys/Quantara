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

import yaml

from quantara.aggregation import aggregate_timeframe, rows_from_persisted
from quantara.canonical import (
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.derive_descriptor import load_derived_descriptor
from quantara.derive_quality import evaluate_derived_quality
from quantara.descriptor import V1_SCHEMA, load_rights_record
from quantara.errors import QuantaraError
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    quality_identity,
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
    read_and_verify_current,
    stage_commit,
    store_object,
    verify_commit_graph,
    write_current,
)
from quantara.quality import evaluate_quality

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
    """Record one attempt manifest; a fault here is reported to stderr and
    never allowed to mask the pipeline's primary terminal result."""
    try:
        _record_attempt(
            data_root,
            repo_root,
            terminal_result=terminal_result,
            dispositions=dispositions,
            referenced_commit=referenced_commit,
            diagnostics=diagnostics,
        )
    except (OSError, QuantaraError) as exc:
        print(f"failed to record attempt manifest: {exc}", file=sys.stderr)


def _record_attempt(
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


def _parent_schema_fingerprint(base) -> str:
    """Return the retained base fingerprint without changing v1 identity.

    V1 descriptors internally carry a one-month tuple for acquisition, but their
    frozen fingerprint deliberately excludes it. V2 range descriptors bind the
    ordered month set into the fingerprint.
    """
    months = None if base.schema == V1_SCHEMA else base.months
    return schema_fingerprint(base.schema_version, months=months)


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
    if not isinstance(manifest, dict):
        raise QuantaraError("parent manifest.json must be a JSON object")

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
    expected_fingerprint = _parent_schema_fingerprint(base)
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

    # Closure 2.1: authenticate the ACTUAL retained rows — decode the Parquet
    # through the approved reader without binary floats and recompute the
    # canonical content identity from every real row in canonical order.
    decoded_rows = rows_from_persisted(read_canonical_rows(object_path))
    recomputed_cch = canonical_content_hash(
        expected_fingerprint,
        (row.to_content_array() for row in decoded_rows),
    )
    if recomputed_cch != commit_hash:
        raise QuantaraError(
            "parent canonical content identity does not match its retained "
            f"rows: recomputed {recomputed_cch!r} but commit directory and "
            f"evidence claim {commit_hash!r}"
        )

    # Closure 2.2: authenticate committed parent quality evidence — never
    # trust a literal manifest quality_state alone.
    quality_path = commit_dir / "quality.json"
    try:
        quality_bytes = quality_path.read_bytes()
    except OSError as exc:
        raise QuantaraError(
            f"parent quality.json missing or unreadable: {exc}"
        ) from exc
    try:
        quality_doc = json.loads(quality_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"parent quality.json not valid JSON: {exc}") from exc
    if not isinstance(quality_doc, dict):
        raise QuantaraError("parent quality.json must be a JSON object")
    expected_quality_keys = {"state", "policy_version", "identity", "findings"}
    if set(quality_doc) != expected_quality_keys:
        raise QuantaraError(
            "parent quality.json keys must be exactly "
            f"{sorted(expected_quality_keys)}, got {sorted(quality_doc)}"
        )
    committed_findings = quality_doc["findings"]
    if not isinstance(committed_findings, list) or not committed_findings:
        raise QuantaraError("parent quality findings must be a non-empty list")
    finding_keys = {"check_id", "outcome", "severity", "count", "evidence"}
    for position, finding in enumerate(committed_findings):
        if not isinstance(finding, dict) or set(finding) != finding_keys:
            raise QuantaraError(
                f"parent quality finding {position} must carry exactly "
                f"{sorted(finding_keys)}"
            )
    authenticated_identity = quality_identity(committed_findings)
    if quality_doc["identity"] != authenticated_identity:
        raise QuantaraError(
            "parent quality identity disagrees with its committed findings"
        )
    if quality_doc["state"] != manifest["quality_state"]:
        raise QuantaraError(
            f"parent quality state {quality_doc['state']!r} disagrees with "
            f"the manifest's {manifest['quality_state']!r}"
        )
    committed_policy = str(quality_doc["policy_version"])
    if (
        committed_policy != str(manifest["quality_policy_version"])
        or committed_policy != str(base.quality_policy_version)
    ):
        raise QuantaraError(
            "parent quality policy version disagrees across quality.json, "
            "the manifest, and the approved base descriptor"
        )
    if manifest["quality_identity"] != authenticated_identity:
        raise QuantaraError(
            "manifest quality identity disagrees with the authenticated "
            "committed quality evidence"
        )
    content_quality = content.get("quality_identity")
    if content_quality is not None and content_quality != authenticated_identity:
        raise QuantaraError(
            "content.json quality identity disagrees with the authenticated "
            "committed quality evidence"
        )

    # Fresh independent evaluation of the actual retained rows under the
    # approved Slice 001 evaluator and the approved period/count.
    fresh_report = evaluate_quality(
        decoded_rows,
        base,
        source_order_valid=True,
        expected_count=base.expected_row_count,
    )
    if fresh_report.state != "PASS":
        raise QuantaraError(
            f"fresh parent evaluation is {fresh_report.state}; a less-than-"
            "PASS parent is never a derivation input"
        )
    if fresh_report.identity() != authenticated_identity:
        raise QuantaraError(
            "freshly evaluated parent quality identity drifts from the "
            "authenticated committed quality evidence"
        )
    return {
        "commit": commit_hash,
        "canonical_content_hash": commit_hash,
        "parquet_sha256": stored_sha,
        "parquet_size": len(parquet_bytes),
        "parquet_path": object_path,
    }


class DerivedGraphVerificationFailed(QuantaraError):
    error_id = "derived_current_verification_failed"


def _authenticate_quality_document(
    commit_dir: Path,
    manifest: dict,
    content_evidence: dict | None = None,
) -> dict:
    """Closure 2.2/2.6: load, shape-check, and authenticate a committed
    quality.json against its own findings and every recorded identity."""
    quality_path = commit_dir / "quality.json"
    try:
        quality_bytes = quality_path.read_bytes()
    except OSError as exc:
        raise QuantaraError(
            f"quality.json missing or unreadable: {exc}"
        ) from exc
    try:
        quality_doc = json.loads(quality_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"quality.json not valid JSON: {exc}") from exc
    if not isinstance(quality_doc, dict):
        raise QuantaraError("quality.json must be a JSON object")
    expected_keys = {"state", "policy_version", "identity", "findings"}
    if set(quality_doc) != expected_keys:
        raise QuantaraError(
            f"quality.json keys must be exactly {sorted(expected_keys)}, "
            f"got {sorted(quality_doc)}"
        )
    committed_findings = quality_doc["findings"]
    if not isinstance(committed_findings, list) or not committed_findings:
        raise QuantaraError("quality findings must be a non-empty list")
    finding_keys = {"check_id", "outcome", "severity", "count", "evidence"}
    for position, finding in enumerate(committed_findings):
        if not isinstance(finding, dict) or set(finding) != finding_keys:
            raise QuantaraError(
                f"quality finding {position} must carry exactly "
                f"{sorted(finding_keys)}"
            )
    authenticated_identity = quality_identity(committed_findings)
    if quality_doc["identity"] != authenticated_identity:
        raise QuantaraError(
            "quality identity disagrees with its committed findings"
        )
    if manifest.get("quality_state") not in (None, quality_doc["state"]):
        raise QuantaraError(
            f"manifest quality state {manifest['quality_state']!r} disagrees "
            f"with quality.json state {quality_doc['state']!r}"
        )
    if manifest.get("quality_policy_version") is not None and str(
        manifest["quality_policy_version"]
    ) != str(quality_doc["policy_version"]):
        raise QuantaraError(
            "manifest quality policy version disagrees with quality.json"
        )
    if manifest.get("quality_identity") not in (None, authenticated_identity):
        raise QuantaraError(
            "manifest quality identity disagrees with the authenticated "
            "committed quality evidence"
        )
    if content_evidence is not None:
        content_quality = content_evidence.get("quality_identity")
        if content_quality is not None and content_quality != (
            authenticated_identity
        ):
            raise QuantaraError(
                "content.json quality identity disagrees with the "
                "authenticated committed quality evidence"
            )
    return quality_doc


def verify_derived_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    """Closure 2.6: full authentication of a derived current graph.

    Enforces strict pointer structure and protocol, 64-hex digests, the
    deterministic lineage-bound address equation ``pointer commit ==
    derived_commit_identity(content cch, lineage)``, commit-directory/content/
    manifest address agreement, manifest-content mutual consistency, object
    hashes, manifest digest pinning, and authenticated quality evidence.
    VERIFIED_NO_OP may only follow this verification.
    """
    pointer_path = dataset_dir / "current.json"
    try:
        raw_pointer = pointer_path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"unreadable current.json: {exc}") from exc
    try:
        pointer = json.loads(raw_pointer)
    except ValueError as exc:
        raise QuantaraError(f"current.json not valid JSON: {exc}") from exc
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
    if pointer["publication_protocol_version"] != PUBLICATION_PROTOCOL_VERSION:
        raise QuantaraError("unsupported publication protocol version")
    for label in ("commit", "manifest_sha256"):
        value = str(pointer[label]).lower()
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise QuantaraError(f"pointer {label} is not a sha256 hex digest")

    address = str(pointer["commit"]).lower()
    commit_dir = dataset_dir / "commits" / address
    content = verify_commit_graph(Path(data_root), commit_dir)

    try:
        manifest_bytes = (commit_dir / "manifest.json").read_bytes()
    except OSError as exc:
        raise QuantaraError(f"manifest.json unreadable: {exc}") from exc
    if sha256_hex(manifest_bytes) != str(pointer["manifest_sha256"]).lower():
        raise QuantaraError(
            "manifest bytes disagree with current.json manifest_sha256"
        )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"manifest not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise QuantaraError("manifest.json must be a JSON object")

    lineage = content.get("derived_from")
    content_cch = content.get("canonical_content_hash")
    recorded_address = content.get("derived_commit_identity")
    if lineage is None or content_cch is None or recorded_address is None:
        raise QuantaraError(
            "content.json lacks lineage/canonical/commit identity evidence"
        )
    recomputed_address = derived_commit_identity(content_cch, lineage)
    if recomputed_address != address or recorded_address != address:
        raise DerivedGraphVerificationFailed(
            f"address binding mismatch: recomputed {recomputed_address!r}, "
            f"recorded {recorded_address!r}, pointer/commit {address!r}"
        )
    for key in (
        "schema_fingerprint",
        "parser_version",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "derived_from",
    ):
        if manifest.get(key) != content.get(key):
            raise QuantaraError(f"manifest/content disagreement on {key!r}")
    if manifest.get("commit_identity") != address:
        raise QuantaraError(
            "manifest commit_identity disagrees with the commit address"
        )
    normalized_refs = [
        ref for ref in content.get("object_refs", [])
        if ref.get("kind") == "normalized"
    ]
    if len(normalized_refs) != 1 or manifest.get("parquet_sha256") != (
        normalized_refs[0]["sha256"]
    ):
        raise QuantaraError(
            "manifest Parquet SHA-256 disagrees with the object ref"
        )
    quality_doc = _authenticate_quality_document(commit_dir, manifest, content)
    # PASS-only policy: an authenticated graph whose committed quality state
    # (or manifest claim) is anything other than exactly PASS is never a
    # candidate for VERIFIED_NO_OP.
    if quality_doc["state"] != "PASS":
        raise DerivedGraphVerificationFailed(
            f"derived quality state {quality_doc['state']!r} is not PASS; a "
            "less-than-verified derived graph is never honored"
        )
    if manifest.get("quality_state") != "PASS":
        raise DerivedGraphVerificationFailed(
            f"manifest quality state {manifest.get('quality_state')!r} is "
            "not PASS; a less-than-verified derived graph is never honored"
        )
    return {**content, "commit": address}


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
    except (QuantaraError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"invalid descriptor: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"normalized_parquet": "not_written"},
            referenced_commit=None,
            diagnostics=["invalid_descriptor"],
        )
        return EXIT_FAILED

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
            dispositions={"normalized_parquet": "not_written"},
            referenced_commit=None,
            diagnostics=["rights_record_unavailable"],
        )
        return EXIT_FAILED
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

    # Recovery/cleanup re-armed per attempt: no normal or dot-prefixed
    # staging residue may survive any terminal path (closure 2.5).
    attempt_id = attempt_id_now()
    staging = data / "staging" / attempt_id
    derived_dot_staging = derived_dir / "commits" / f".staging-{attempt_id}"
    milestones = {
        "attempt_staged": False,
        "object_written": False,
        "commit_renamed": False,
        "pointer_replaced": False,
        "discovery_verified": False,
    }
    parquet_state = "not_written"
    cleanup_state = {"staging": "pending"}

    def _cleanup_attempt() -> None:
        ok = True
        for directory in (staging, derived_dot_staging):
            try:
                shutil.rmtree(directory)
            except OSError:
                if directory.exists():
                    ok = False
        cleanup_state["staging"] = "discarded" if ok else "cleanup_failed"

    def _dispositions(extra: dict | None = None) -> dict:
        dispositions = {
            "normalized_parquet": parquet_state,
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
        print(f"derivation failed: {detail}", file=sys.stderr)
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
        for stale in (derived_dir / "commits").glob(".staging-*"):
            shutil.rmtree(stale, ignore_errors=True)

        staging.mkdir(parents=True, exist_ok=True)
        milestones["attempt_staged"] = True

        minutes, bars, parquet_path, report = _derive_rows(
            parent["parquet_path"], descriptor, staging
        )
        parquet_state = "staged_not_published"

        # PASS-only policy: exactly PASS publishes.
        if report.state != "PASS":
            failing_checks = [
                f.check_id for f in report.findings if f.outcome != "pass"
            ] or [f"quality_state_{report.state}"]
            print(f"quality state {report.state} blocks publication",
                  file=sys.stderr)
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

        fingerprint = schema_fingerprint(descriptor.schema_version)
        descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
        content_hash = canonical_content_hash(
            fingerprint, (row.to_content_array() for row in bars)
        )
        parquet_bytes = parquet_path.read_bytes()
        parquet_sha = sha256_hex(parquet_bytes)
        stored_normalized = store_object(data, "normalized", parquet_bytes)
        normalized_ref = stored_normalized.sha256
        # Truthful milestone: only an object this invocation actually created
        # counts as written; a deduplicated pre-existing identical object was
        # left byte-for-byte (and mtime) untouched.
        milestones["object_written"] = stored_normalized.created
        parquet_state = (
            "object_written" if stored_normalized.created else "object_reused"
        )

        object_refs = [{"kind": "normalized", "sha256": normalized_ref}]
        lineage = {
            "parent_dataset_id": base.dataset_id,
            "parent_canonical_content_hash": parent["canonical_content_hash"],
            "parent_parquet_sha256": parent["parquet_sha256"],
            "parent_parquet_size": parent["parquet_size"],
            "parent_descriptor_sha256": descriptor_hash(
                base.canonical_semantics()
            ),
            "parent_schema_fingerprint": schema_fingerprint(
                base.schema_version
            ),
            "transformation": {
                "name": descriptor.transformation["name"],
                "version": descriptor.transformation["version"],
                "timeframe_ms": descriptor.timeframe_ms,
            },
        }
        identity_evidence = {
            # Derivation input bytes stand where the source ZIP stood in 001.
            "source_sha256": parent["parquet_sha256"],
            "descriptor_sha256": descriptor_sha,
            "schema_fingerprint": fingerprint,
            "parser_version": PARSER_VERSION,
            "canonical_content_hash": content_hash,
            "quality_identity": report.identity(),
            "object_refs": object_refs,
            "derived_from": lineage,
        }
        # Closure: the commit address binds canonical content to the
        # authenticated lineage evidence.
        commit_address = derived_commit_identity(content_hash, lineage)
        identity_evidence["derived_commit_identity"] = commit_address

        # Idempotency is allowed only after full derived-graph authentication
        # (closure 2.6): renamed, misaddressed, or fabricated graphs are
        # rejected rather than honored or silently republished.
        pointer = derived_dir / "current.json"
        if pointer.exists():
            try:
                parsed_pointer = json.loads(
                    pointer.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise QuantaraError(
                    f"unreadable current.json: {exc}"
                ) from exc
            if not isinstance(parsed_pointer, dict):
                raise QuantaraError(
                    "current.json must be a JSON object"
                )
            pointer_commit_name = str(
                parsed_pointer.get("commit", "")
            ).lower()
            # A pointer whose target directory is missing or incomplete is a
            # LOST pointer: safe recovery proceeds below. Any graph that IS
            # present must pass full authentication or the run is rejected.
            pointer_target = derived_dir / "commits" / pointer_commit_name
            pointer_lost = not (pointer_target / "COMMITTED").is_file()
            if not pointer_lost:
                try:
                    verify_derived_current_graph(derived_dir, data)
                except QuantaraError as exc:
                    raise DerivedGraphVerificationFailed(str(exc)) from exc
                current_commit = parsed_pointer["commit"]
                existing_dir = derived_dir / "commits" / current_commit
                if existing_commit_matches(
                    data, existing_dir, identity_evidence,
                    keys=DERIVED_EVIDENCE_KEYS,
                ):
                    # Truthful milestones for THIS invocation: the retained
                    # graph was fully verified, but nothing was renamed or
                    # repointed by this run.
                    milestones["discovery_verified"] = True
                    _cleanup_attempt()
                    _write_attempt(
                        data,
                        root,
                        terminal_result="VERIFIED_NO_OP",
                        dispositions=_dispositions({
                            "normalized_parquet": "already_published",
                        }),
                        referenced_commit=current_commit,
                        diagnostics=[],
                    )
                    return EXIT_OK

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
                name: entry.state
                for name, entry in rights_record.operations.items()
            },
            environment=environment_evidence(root),
            derived_from=lineage,
        )
        manifest_bytes = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode()
        files = {
            "manifest.json": manifest_bytes,
            "quality.json": (
                json.dumps(_quality_payload(report), indent=2, sort_keys=True)
                + "\n"
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
            # Truthful milestone: only a successful atomic rename of THIS
            # invocation's staged commit counts as renamed.
            milestones["commit_renamed"] = True
        except QuantaraError:
            candidate = derived_dir / "commits" / commit_address
            if not (
                candidate.is_dir()
                and existing_commit_matches(
                    data, candidate, identity_evidence,
                    keys=DERIVED_EVIDENCE_KEYS,
                )
            ):
                raise QuantaraError(
                    "commit rename failed and no equivalent commit exists"
                ) from None
            commit_dir = candidate
            # The retained equivalent commit is reused as-is: no rename was
            # performed by this invocation, so commit_renamed stays False.
            # The retained commit is authoritative: pin the pointer to ITS
            # manifest bytes so digest and storage agree exactly.
            manifest_bytes = (commit_dir / "manifest.json").read_bytes()
        verify_commit_graph(data, commit_dir)
        write_current(derived_dir, commit_address, sha256_hex(manifest_bytes))
        milestones["pointer_replaced"] = True
        verify_derived_current_graph(derived_dir, data)
        milestones["discovery_verified"] = True
    except (QuantaraError, OSError) as exc:
        diagnostic = getattr(exc, "error_id", None) or (
            "os_error" if isinstance(exc, OSError) else "derivation_failure"
        )
        post_pointer = milestones["pointer_replaced"]
        extra = (
            {"post_pointer": "published_unverified"} if post_pointer else None
        )
        referenced = commit_address if post_pointer else None
        return _terminal_failure(diagnostic, referenced, extra, exc)

    _cleanup_attempt()
    _write_attempt(
        data,
        root,
        terminal_result="PUBLISHED",
        dispositions=_dispositions({"normalized_parquet": "published"}),
        referenced_commit=commit_address,
        diagnostics=[],
    )
    return EXIT_OK
