"""Lineage-bound research-table orchestration (data slice 003b).

Mirrors the slice 002 derivation pipeline: research descriptor validation plus
the ``analyze_internal`` gate on the v2 rights record, full authentication of
the parent derived graph (pointer protocol, lineage-bound address equation,
manifest digest pinning, Parquet byte hashes, decoded-row canonical-content
identity, authenticated PASS quality evidence), exact decimal feature/label
engines with single-rounding Q18 storage quantization, PASS-only research
quality gating, staged Parquet write/read-back/reconciliation, a domain-
separated lineage-bound commit address, immutable publication through the
unchanged protocol with idempotent VERIFIED_NO_OP detection over extended
evidence keys, and attempt manifests carrying truthful milestones.
Exit codes: 0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from quantara.aggregation import rows_from_persisted
from quantara.canonical import WRITER_CONFIG, read_canonical_rows
from quantara.derive_pipeline import verify_derived_current_graph
from quantara.derive_quality import evaluate_derived_quality
from quantara.descriptor import load_rights_record
from quantara.errors import QuantaraError
from quantara.features import build_research_rows
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    quality_identity,
    render_decimal_18,
    research_content_hash,
    research_schema_fingerprint,
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
    stage_commit,
    store_object,
    verify_commit_graph,
    write_current,
)
from quantara.research_descriptor import (
    UndersizedBaseDataset,
    load_research_descriptor,
)
from quantara.research_quality import (
    QUALITY_POLICY_VERSION,
    designed_null_budgets,
    evaluate_research_quality,
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3

# Idempotency evidence = slice 001/002 key set extended with the research
# lineage block and the lineage-bound commit identity binding them together.
RESEARCH_EVIDENCE_KEYS = (
    "source_sha256",
    "descriptor_sha256",
    "schema_fingerprint",
    "parser_version",
    "canonical_content_hash",
    "quality_identity",
    "object_refs",
    "research_from",
    "research_commit_identity",
)


@dataclass(frozen=True)
class _ParentQualityView:
    """Temporal surface evaluate_derived_quality needs for the parent."""

    timeframe_ms: int
    start_utc_open_ms: int


def research_commit_identity(content_hash: str, lineage: dict) -> str:
    """Deterministic research commit address (design §3.9).

    Domain-separated SHA-256 over JCS of ``{domain, canonical_content_hash,
    research_from}``: the logical research-table content bound to the
    authenticated parent lineage evidence. Changed parameters ⇒ changed
    address ⇒ a new immutable commit; parents are never mutated.
    """
    payload = {
        "domain": "quantara-research-commit-identity-v1",
        "canonical_content_hash": content_hash.lower(),
        "research_from": lineage,
    }
    return sha256_hex(canonicalize(payload).encode("utf-8"))


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def epoch_ms(moment: datetime) -> int:
    """Exact UTC epoch milliseconds via integer division — never a float."""
    return (moment - EPOCH) // timedelta(milliseconds=1)


def _dataset_dir(data_root: Path, symbol: str, interval: str, start) -> Path:
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


def _parent_klines_dir(data_root: Path, symbol: str, interval: str, start) -> Path:
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


class ResearchParquetFailure(QuantaraError):
    error_id = "failed_parquet_write_or_read_back"


class ReconciliationMismatch(QuantaraError):
    error_id = "reconciliation_mismatch"


class ResearchGraphVerificationFailed(QuantaraError):
    error_id = "research_current_verification_failed"


# The seven-column physical Parquet schema (design §5), fixed order, stored
# with the established writer configuration.
RESEARCH_PARQUET_SCHEMA = pa.schema(
    [
        pa.field("open_time_ms", pa.int64(), nullable=False),
        pa.field("f_ret_1", pa.decimal128(38, 18)),
        pa.field("f_roc_60", pa.decimal128(38, 18)),
        pa.field("f_rvol_20", pa.decimal128(38, 18)),
        pa.field("f_volratio_20", pa.decimal128(38, 18)),
        pa.field("l_fwdret_24", pa.decimal128(38, 18)),
        pa.field("l_fwddir_24", pa.int8()),
    ]
)


def write_research_parquet(rows: list[tuple], path: Path) -> None:
    try:
        arrays = [
            pa.array([row[i] for row in rows], type=field.type)
            for i, field in enumerate(RESEARCH_PARQUET_SCHEMA)
        ]
        table = pa.Table.from_arrays(arrays, schema=RESEARCH_PARQUET_SCHEMA)
        with pq.ParquetWriter(path, RESEARCH_PARQUET_SCHEMA, **WRITER_CONFIG) as writer:
            writer.write_table(table)
    except Exception as exc:
        raise ResearchParquetFailure(f"research Parquet write failed for {path}: {exc}") from exc


def read_research_rows(path: Path) -> list[tuple]:
    """Read back through the approved explicit schema; decimals arrive as
    decimal.Decimal, timestamps as epoch-ms ints, labels as int|None."""
    try:
        table = pq.read_table(Path(path))
    except Exception as exc:
        raise ResearchParquetFailure(
            f"research Parquet read-back failed for {path}: {exc}"
        ) from exc
    if table.schema != RESEARCH_PARQUET_SCHEMA:
        raise ResearchParquetFailure("read-back schema differs from the approved research schema")
    columns = [table.column(i).to_pylist() for i in range(len(RESEARCH_PARQUET_SCHEMA))]
    return list(zip(*columns, strict=True))


def reconcile_research_rows(computed_rows: list[tuple], persisted_rows: list[tuple]) -> None:
    """Exact field-by-field reconciliation — never a tolerance."""
    if len(computed_rows) != len(persisted_rows):
        raise ReconciliationMismatch(
            f"row count mismatch: {len(computed_rows)} computed vs {len(persisted_rows)} persisted"
        )
    for position, (computed, persisted) in enumerate(
        zip(computed_rows, persisted_rows, strict=True)
    ):
        if computed[0] != persisted[0] or computed[6] != persisted[6]:
            raise ReconciliationMismatch(f"row {position} differs in open_time_ms or l_fwddir_24")
        for i in range(1, 6):
            expected, actual = computed[i], persisted[i]
            if (expected is None) != (actual is None):
                raise ReconciliationMismatch(f"row {position} column {i} nullability differs")
            if expected is not None and expected != actual:
                raise ReconciliationMismatch(f"row {position} column {i}: {expected} != {actual}")


def render_content_rows(rows: list[tuple]) -> list[list[object]]:
    """Hash-contract arrays: epoch-ms int, Q18 decimal strings, sign int."""
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
    """Record one attempt manifest; a fault here is reported to stderr and
    never allowed to mask the pipeline's primary terminal result."""
    try:
        attempt = new_attempt_manifest(
            terminal_result=terminal_result,
            artifact_dispositions=dispositions,
            retry_evidence=[],
            http_statuses=[],
            referenced_commit=referenced_commit,
            diagnostics=diagnostics,
            repo_root=repo_root,
        )
        write_json(
            Path(data_root) / "attempts" / f"{attempt['attempt_id']}.json",
            attempt,
        )
    except (OSError, QuantaraError) as exc:
        print(f"failed to record attempt manifest: {exc}", file=sys.stderr)


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


def _resolve_rights(descriptor_path: Path, legal_record: str) -> Path:
    target = descriptor_path.resolve().parent
    rights_path = target / legal_record
    while not rights_path.exists() and target != target.parent:
        target = target.parent
        rights_path = target / legal_record
    return rights_path


def _verify_parent(parent_dir: Path, data_root: Path, base) -> dict:
    """Full parent authentication before any computation.

    The research parent is a derived dataset commit, so authentication uses
    the slice 002 closure (pointer protocol, lineage-bound address equation,
    manifest digest pinning, manifest/content agreement, object hashes,
    authenticated PASS quality evidence), then additionally verifies the
    retained Parquet bytes, decodes every row through the approved reader,
    recomputes the canonical content identity from those rows, and freshly
    re-evaluates parent quality against its authenticated committed identity.
    """
    pointer_path = parent_dir / "current.json"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"unreadable current.json: {exc}") from exc
    if not isinstance(pointer, dict):
        raise QuantaraError("parent current.json must be a JSON object")
    expected_pointer_keys = {
        "publication_protocol_version",
        "commit",
        "manifest_sha256",
    }
    if set(pointer) != expected_pointer_keys:
        raise QuantaraError(
            "parent current.json keys must be exactly "
            f"{sorted(expected_pointer_keys)}, got {sorted(pointer)}"
        )
    if pointer["publication_protocol_version"] != PUBLICATION_PROTOCOL_VERSION:
        raise QuantaraError("unsupported publication protocol version")

    # COMMITTED marker, content.json, object hashes, address equation,
    # manifest digest pinning, manifest/content agreement, quality auth+PASS.
    graph = verify_derived_current_graph(parent_dir, data_root)

    commit_dir = parent_dir / "commits" / graph["commit"]
    try:
        manifest = json.loads((commit_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QuantaraError(f"parent manifest unreadable: {exc}") from exc

    if manifest.get("dataset_id") != base.dataset_id:
        raise QuantaraError(
            f"parent dataset_id {manifest.get('dataset_id')!r} does not "
            f"match the approved base {base.dataset_id!r}"
        )
    if manifest.get("schema_version") != base.schema_version:
        raise QuantaraError(
            f"parent schema_version {manifest.get('schema_version')!r} does "
            f"not match the approved base {base.schema_version!r}"
        )
    expected_fingerprint = schema_fingerprint(base.schema_version)
    if manifest.get("schema_fingerprint") != expected_fingerprint:
        raise QuantaraError(
            "parent schema_fingerprint does not match the approved base "
            "descriptor's logical schema fingerprint"
        )

    normalized_refs = [
        ref for ref in graph.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if len(normalized_refs) != 1:
        raise QuantaraError("parent commit must reference exactly one object")
    stored_sha = normalized_refs[0]["sha256"]
    object_path = data_root / "objects" / "normalized" / "sha256" / stored_sha
    parquet_bytes = object_path.read_bytes()
    if sha256_hex(parquet_bytes) != stored_sha:
        raise QuantaraError("parent Parquet object bytes fail their own digest")
    if manifest.get("parquet_size") != len(parquet_bytes):
        raise QuantaraError(
            f"parent Parquet size {len(parquet_bytes)} disagrees with the "
            f"committed manifest value {manifest.get('parquet_size')}"
        )

    # Closure: authenticate the ACTUAL retained rows — decode through the
    # approved reader and recompute the canonical content identity.
    decoded_rows = rows_from_persisted(read_canonical_rows(object_path))
    fingerprint = schema_fingerprint(base.schema_version)
    recomputed_cch = canonical_content_hash(
        fingerprint, [row.to_content_array() for row in decoded_rows]
    )
    if recomputed_cch != manifest.get("canonical_content_hash"):
        raise QuantaraError(
            "parent canonical content identity does not match its retained "
            f"rows: recomputed {recomputed_cch!r} but evidence claims "
            f"{manifest.get('canonical_content_hash')!r}"
        )

    # Fresh independent evaluation of the retained parent rows.
    view = _ParentQualityView(
        timeframe_ms=base.timeframe_ms,
        start_utc_open_ms=epoch_ms(base.start_utc),
    )
    fresh_report = evaluate_derived_quality(
        decoded_rows, view, expected_count=base.expected_row_count
    )
    if fresh_report.state != "PASS":
        raise QuantaraError(
            f"fresh parent evaluation is {fresh_report.state}; a less-than-"
            "PASS parent is never a research input"
        )
    committed_identity = graph.get("quality_identity")
    if fresh_report.identity() != committed_identity:
        raise QuantaraError(
            "freshly evaluated parent quality identity drifts from the "
            "authenticated committed quality evidence"
        )

    return {
        "commit": graph["commit"],
        "canonical_content_hash": manifest["canonical_content_hash"],
        "parquet_sha256": stored_sha,
        "parquet_size": len(parquet_bytes),
        "parquet_path": object_path,
        "row_count": len(decoded_rows),
        "quality_identity": committed_identity,
    }


def _authenticate_research_quality_document(commit_dir: Path, manifest: dict) -> dict:
    """Load, shape-check, and authenticate a committed research quality.json."""
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
    finding_keys = {"check_id", "outcome", "severity", "count", "evidence"}
    for position, finding in enumerate(committed_findings):
        if not isinstance(finding, dict) or set(finding) != finding_keys:
            raise QuantaraError(
                f"quality finding {position} must carry exactly {sorted(finding_keys)}"
            )
    authenticated_identity = quality_identity(committed_findings)
    if quality_doc["identity"] != authenticated_identity:
        raise QuantaraError("quality identity disagrees with its committed findings")
    if manifest.get("quality_state") != quality_doc["state"]:
        raise QuantaraError("manifest quality state disagrees with quality.json")
    if str(manifest.get("quality_policy_version")) != str(quality_doc["policy_version"]):
        raise QuantaraError("manifest quality policy version disagrees with quality.json")
    if manifest.get("quality_identity") != authenticated_identity:
        raise QuantaraError(
            "manifest quality identity disagrees with the authenticated committed quality evidence"
        )
    return quality_doc


def verify_research_current_graph(dataset_dir: Path, data_root: Path) -> dict:
    """Full authentication of a research current graph: strict pointer
    structure, the lineage-bound address equation ``pointer commit ==
    research_commit_identity(content hash, lineage)``, commit-directory/
    content/manifest agreement, Parquet ref agreement, and authenticated
    PASS quality evidence. VERIFIED_NO_OP may only follow this verification."""
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
        raise QuantaraError("manifest bytes disagree with current.json manifest_sha256")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ValueError as exc:
        raise QuantaraError(f"manifest not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise QuantaraError("manifest.json must be a JSON object")

    lineage = content.get("research_from")
    content_hash = content.get("canonical_content_hash")
    recorded_address = content.get("research_commit_identity")
    if lineage is None or content_hash is None or recorded_address is None:
        raise QuantaraError("content.json lacks lineage/canonical/commit identity evidence")
    recomputed_address = research_commit_identity(content_hash, lineage)
    if recomputed_address != address or recorded_address != address:
        raise ResearchGraphVerificationFailed(
            f"address binding mismatch: recomputed {recomputed_address!r}, "
            f"recorded {recorded_address!r}, pointer/commit {address!r}"
        )
    for key in (
        "schema_fingerprint",
        "parser_version",
        "canonical_content_hash",
        "quality_identity",
        "object_refs",
        "research_from",
    ):
        if manifest.get(key) != content.get(key):
            raise QuantaraError(f"manifest/content disagreement on {key!r}")
    if manifest.get("commit_identity") != address:
        raise QuantaraError("manifest commit_identity disagrees with the commit address")
    normalized_refs = [
        ref for ref in content.get("object_refs", []) if ref.get("kind") == "normalized"
    ]
    if (
        len(normalized_refs) != 1
        or manifest.get("parquet_sha256") != (normalized_refs[0]["sha256"])
    ):
        raise QuantaraError("manifest Parquet SHA-256 disagrees with the object ref")

    quality_doc = _authenticate_research_quality_document(commit_dir, manifest)
    # PASS-only policy: an authenticated graph whose committed quality state
    # is anything other than exactly PASS is never a NO_OP candidate.
    if quality_doc["state"] != "PASS" or manifest.get("quality_state") != "PASS":
        raise ResearchGraphVerificationFailed(
            "research quality state is not PASS; a less-than-verified "
            "research graph is never honored"
        )
    return {**content, "commit": address}


def run_research_pipeline(
    descriptor_path: str | Path,
    data_root: str | Path,
    dry_run: bool = False,
    repo_root: str | Path | None = None,
) -> int:
    root = Path(repo_root) if repo_root else Path.cwd()
    data = Path(data_root)
    descriptor_file = Path(descriptor_path)

    # Step 1: load + validate the research descriptor; gate analyze_internal.
    try:
        descriptor = load_research_descriptor(descriptor_file)
    except UndersizedBaseDataset as exc:
        print(f"undersized_base_dataset: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"normalized_parquet": "not_written"},
            referenced_commit=None,
            diagnostics=["undersized_base_dataset"],
        )
        return EXIT_BLOCKED
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
    if not rights_record.permits("analyze_internal"):
        # Publishing labels IS analysis; the v2 amendment gates exactly this
        # operation and grants nothing toward model_train_internal.
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

    base = descriptor.base_descriptor
    parent_dir = _parent_klines_dir(data, base.provider_symbol, base.interval, base.start_utc)
    research_dir = _dataset_dir(data, base.provider_symbol, base.interval, descriptor.start_utc)

    # Step 2: the parent must resolve and fully verify — BLOCKED otherwise.
    try:
        parent = _verify_parent(parent_dir, data, base)
    except (QuantaraError, OSError, ValueError, KeyError) as exc:
        diagnostic = getattr(exc, "error_id", None) or "parent_dataset_unavailable"
        print(f"parent_dataset_unavailable: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"normalized_parquet": "not_written"},
            referenced_commit=None,
            diagnostics=[diagnostic],
        )
        return EXIT_BLOCKED

    if dry_run:
        # Steps 1–2 verification only; no mutation of any dataset directory.
        return EXIT_OK

    # Recovery/cleanup re-armed per attempt: no dot-prefixed staging residue
    # may survive any terminal path.
    attempt_id = attempt_id_now()
    staging = data / "staging" / attempt_id
    research_dot_staging = research_dir / "commits" / f".staging-{attempt_id}"
    milestones = {
        "attempt_staged": False,
        "object_written": False,
        "commit_renamed": False,
        "pointer_replaced": False,
        "discovery_verified": False,
    }
    parquet_state = "not_written"
    cleanup_state = {"staging": "pending"}
    commit_address: str | None = None

    def _cleanup_attempt() -> None:
        ok = True
        for directory in (staging, research_dot_staging):
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
        print(f"research pipeline failed: {detail}", file=sys.stderr)
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
        for stale in (research_dir / "commits").glob(".staging-*"):
            shutil.rmtree(stale, ignore_errors=True)

        staging.mkdir(parents=True, exist_ok=True)
        milestones["attempt_staged"] = True

        # Compute from the authenticated retained parent rows only.
        parent_rows = read_canonical_rows(parent["parquet_path"])
        computed_rows = build_research_rows(parent_rows, descriptor.parameters)

        parquet_path = staging / "research.parquet"
        write_research_parquet(computed_rows, parquet_path)
        persisted_rows = read_research_rows(parquet_path)
        # Independent cell-level reconciliation feeds the evaluator.
        reconcile_research_rows(computed_rows, persisted_rows)

        report = evaluate_research_quality(
            persisted_rows,
            [row[10] for row in parent_rows],
            descriptor.parameters,
            reconciliation_ok=True,
        )
        parquet_state = "staged_not_published"

        # PASS-only policy: exactly PASS publishes.
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

        fingerprint = research_schema_fingerprint(descriptor.schema_version)
        descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
        content_hash = research_content_hash(fingerprint, render_content_rows(persisted_rows))
        parquet_bytes = parquet_path.read_bytes()
        parquet_sha = sha256_hex(parquet_bytes)

        lineage = {
            "base_dataset_id": base.dataset_id,
            "base_commit_address": parent["commit"],
            "base_canonical_content_hash": parent["canonical_content_hash"],
            "base_parquet_sha256": parent["parquet_sha256"],
            "base_parquet_size": parent["parquet_size"],
            "feature_set_name": descriptor.feature_set["name"],
            "feature_set_version": descriptor.feature_set["version"],
            "parameters": dict(descriptor.parameters),
            "label_horizon": descriptor.parameters["label_horizon"],
        }
        commit_address = research_commit_identity(content_hash, lineage)

        stored_normalized = store_object(data, "normalized", parquet_bytes)
        normalized_ref = stored_normalized.sha256
        # Truthful milestone: only an object this invocation actually created
        # counts as written; a deduplicated identical object is left untouched.
        milestones["object_written"] = stored_normalized.created
        parquet_state = "object_written" if stored_normalized.created else "object_reused"

        object_refs = [{"kind": "normalized", "sha256": normalized_ref}]
        identity_evidence = {
            # The authenticated parent Parquet stands where the source ZIP
            # stood in slice 001.
            "source_sha256": parent["parquet_sha256"],
            "descriptor_sha256": descriptor_sha,
            "schema_fingerprint": fingerprint,
            "parser_version": PARSER_VERSION,
            "canonical_content_hash": content_hash,
            "quality_identity": report.identity(),
            "object_refs": object_refs,
            "research_from": lineage,
        }
        identity_evidence["research_commit_identity"] = commit_address

        # Idempotency is allowed only after full research-graph authentication.
        pointer = research_dir / "current.json"
        if pointer.exists():
            try:
                parsed_pointer = json.loads(pointer.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise QuantaraError(f"unreadable current.json: {exc}") from exc
            if not isinstance(parsed_pointer, dict):
                raise QuantaraError("current.json must be a JSON object")
            pointer_commit_name = str(parsed_pointer.get("commit", "")).lower()
            pointer_target = research_dir / "commits" / pointer_commit_name
            # A LOST pointer (missing/incomplete target) falls through to safe
            # recovery below; any present graph must fully authenticate.
            pointer_lost = not (pointer_target / "COMMITTED").is_file()
            if not pointer_lost:
                verify_research_current_graph(research_dir, data)
                existing_dir = research_dir / "commits" / parsed_pointer["commit"]
                if existing_commit_matches(
                    data,
                    existing_dir,
                    identity_evidence,
                    keys=RESEARCH_EVIDENCE_KEYS,
                ):
                    # Truthful milestones: nothing renamed/repointed by THIS run.
                    milestones["discovery_verified"] = True
                    _cleanup_attempt()
                    _write_attempt(
                        data,
                        root,
                        terminal_result="VERIFIED_NO_OP",
                        dispositions=_dispositions({"normalized_parquet": "already_published"}),
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
            source_row_count=len(parent_rows),
            canonical_row_count=len(computed_rows),
            canonical_content_hash=content_hash,
            commit_identity=commit_address,
            parquet_sha256=parquet_sha,
            parquet_size=len(parquet_bytes),
            object_refs=object_refs,
            legal_record_id=rights_record.record_id,
            legal_states={name: entry.state for name, entry in rights_record.operations.items()},
            environment=environment_evidence(root),
            research_from=lineage,
            feature_set=dict(descriptor.feature_set),
            parameters=dict(descriptor.parameters),
            designed_null_budgets=designed_null_budgets(len(computed_rows), descriptor.parameters),
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
        staged_commit = stage_commit(research_dir, attempt_id, files)
        try:
            commit_dir = publish_commit(staged_commit, research_dir / "commits", commit_address)
            # Truthful milestone: only a successful atomic rename of THIS
            # invocation's staged commit counts as renamed.
            milestones["commit_renamed"] = True
        except QuantaraError:
            candidate = research_dir / "commits" / commit_address
            if not (
                candidate.is_dir()
                and existing_commit_matches(
                    data,
                    candidate,
                    identity_evidence,
                    keys=RESEARCH_EVIDENCE_KEYS,
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
        write_current(research_dir, commit_address, sha256_hex(manifest_bytes))
        milestones["pointer_replaced"] = True
        verify_research_current_graph(research_dir, data)
        milestones["discovery_verified"] = True
    except (QuantaraError, OSError) as exc:
        diagnostic = getattr(exc, "error_id", None) or (
            "os_error" if isinstance(exc, OSError) else "research_failure"
        )
        post_pointer = milestones["pointer_replaced"]
        extra = {"post_pointer": "published_unverified"} if post_pointer else None
        # Slice 002 closure contract: a replaced pointer means the graph IS
        # published (discoverable, verification pending) regardless of whether
        # this invocation renamed its own staging commit or reused a retained
        # equivalent. The FAILED evidence must therefore reference the
        # published commit whenever the pointer was replaced.
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
