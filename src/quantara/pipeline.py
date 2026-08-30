"""22-step pipeline orchestration.

Executes the approved processing flow in order: descriptor/rights validation,
verified acquisition, safe archive inspection, exact parsing, canonical
assembly and quality evaluation, Parquet write/read-back/reconciliation,
hashing, immutable publication through the content-addressed protocol,
discovery verification via current.json, and idempotent VERIFIED_NO_OP
detection. Exit codes: 0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED,
4 QUARANTINED (spec §10, plan Task 10).
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

from quantara.acquisition import Acquirer, ChecksumMismatch
from quantara.archive import inspect_zip, read_member_bytes
from quantara.canonical import (
    assemble_canonical_rows,
    reconcile_parquet,
    write_canonical_parquet,
)
from quantara.descriptor import (
    V2_SCHEMA,
    DatasetDescriptor,
    load_descriptor,
    load_rights_record,
)
from quantara.errors import QuantaraError
from quantara.hashing import (
    canonical_content_hash,
    descriptor_hash,
    schema_fingerprint,
    sha256_hex,
)
from quantara.jcs import canonicalize
from quantara.manifests import (
    attempt_id_now,
    build_dataset_manifest,
    environment_evidence,
    new_attempt_manifest,
    parser_version_for,
    write_json,
)
from quantara.parsing import decode_member, parse_rows
from quantara.publication import (
    existing_commit_matches,
    publish_commit,
    put_object,
    read_and_verify_current,
    stage_commit,
    verify_commit_graph,
    write_current,
)
from quantara.quality import QualityReport, evaluate_quality
from quantara.quality_approval import (
    EffectiveQualityDecision,
    QualityApprovalRecord,
    evaluate_effective_quality,
    load_approval_record,
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3
EXIT_QUARANTINED = 4


class MultiMonthInvariantViolation(QuantaraError):
    error_id = "multi_month_invariant_violation"


def _dataset_dir(data_root: Path, descriptor: DatasetDescriptor) -> Path:
    start = descriptor.start_utc
    return (
        Path(data_root)
        / "datasets"
        / "binance"
        / "usdm"
        / "klines"
        / descriptor.provider_symbol
        / descriptor.interval
        / f"year={start:%Y}"
        / f"month={start:%m}"
    )


def _write_attempt(
    data_root: Path,
    repo_root: Path,
    *,
    terminal_result: str,
    dispositions: dict[str, str],
    retry_evidence: list[dict],
    http_statuses: list[int],
    referenced_commit: str | None,
    diagnostics: list[str],
) -> None:
    """Record one attempt manifest; a fault here is reported to stderr and
    never allowed to mask the pipeline's terminal result."""
    try:
        attempt = new_attempt_manifest(
            terminal_result=terminal_result,
            artifact_dispositions=dispositions,
            retry_evidence=retry_evidence,
            http_statuses=http_statuses,
            referenced_commit=referenced_commit,
            diagnostics=diagnostics,
            repo_root=repo_root,
        )
        write_json(Path(data_root) / "attempts" / f"{attempt['attempt_id']}.json", attempt)
    except (OSError, QuantaraError) as exc:
        print(f"failed to record attempt manifest: {exc}", file=sys.stderr)


def _quality_payload(report: QualityReport) -> dict:
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


def _quality_payload_v2(
    report: QualityReport,
    effective_decision: EffectiveQualityDecision,
    approval_record: QualityApprovalRecord | None,
) -> dict:
    payload = {
        "state": effective_decision.effective_state,
        "raw_state": effective_decision.raw_state,
        "policy_version": "2",
        "identity": report.identity(),
        "identity_sha256": effective_decision.raw_identity_sha256,
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
    if approval_record is not None:
        payload["approval_record_id"] = approval_record.record_id
        payload["approval_record_sha256"] = approval_record.record_sha256
    return payload


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    return start, end


def _segment_descriptor(
    descriptor: DatasetDescriptor, position: int
) -> DatasetDescriptor:
    month = descriptor.months[position]
    start, end = _month_bounds(month)
    return replace(
        descriptor,
        start_utc=start,
        end_utc=end,
        archive_url=descriptor.archive_urls[position],
        checksum_url=descriptor.checksum_urls[position],
        member_pattern=descriptor.member_patterns[position],
        months=(month,),
        archive_urls=(descriptor.archive_urls[position],),
        checksum_urls=(descriptor.checksum_urls[position],),
        member_patterns=(descriptor.member_patterns[position],),
    )


def _validate_range_segments(segment_rows, descriptor: DatasetDescriptor) -> None:
    if len(segment_rows) != len(descriptor.months):
        raise MultiMonthInvariantViolation(
            "segment accounting differs from the descriptor month count"
        )
    combined = [row for rows in segment_rows for row in rows]
    times = [row.open_time for row in combined]
    if len(set(times)) != len(times):
        raise MultiMonthInvariantViolation(
            "concatenated months contain duplicate open times"
        )
    if any(
        current <= previous
        for previous, current in zip(times, times[1:], strict=False)
    ):
        raise MultiMonthInvariantViolation(
            "concatenated months are not strictly chronological"
        )
    if any(
        current - previous != 60_000
        for previous, current in zip(times, times[1:], strict=False)
    ):
        raise MultiMonthInvariantViolation(
            "concatenated months are not continuous at one-minute cadence"
        )
    for position, rows in enumerate(segment_rows):
        expected = _segment_descriptor(descriptor, position).expected_row_count
        if len(rows) != expected:
            raise MultiMonthInvariantViolation(
                f"month {descriptor.months[position]} parsed {len(rows)} rows; "
                f"expected {expected}"
            )
    if len(combined) != descriptor.expected_row_count:
        raise MultiMonthInvariantViolation(
            f"concatenated rows {len(combined)} differ from expected "
            f"{descriptor.expected_row_count}"
        )


def _retry_payload(acquirers: list[Acquirer]) -> list[dict]:
    return [asdict(item) for acquirer in acquirers for item in acquirer.retry_evidence]


def _http_statuses(acquirers: list[Acquirer]) -> list[int]:
    return [status for acquirer in acquirers for status in acquirer.http_statuses]


def run_pipeline(  # noqa: C901, PLR0915 - one explicit linear flow per spec §10
    descriptor_path: str | Path,
    data_root: str | Path,
    dry_run: bool = False,
    transport=None,
    sleeper=None,
    repo_root: str | Path | None = None,
) -> int:
    root = Path(repo_root) if repo_root else Path.cwd()
    data = Path(data_root)

    # Steps 1–2: load and validate descriptor and legal state.
    try:
        descriptor = load_descriptor(Path(descriptor_path))
    except (QuantaraError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"invalid descriptor: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"zip": "not_downloaded", "checksum": "not_downloaded"},
            retry_evidence=[],
            http_statuses=[],
            referenced_commit=None,
            diagnostics=["invalid_descriptor"],
        )
        return EXIT_FAILED

    # Resolve the legal record relative to the nearest ancestor that contains
    # it (descriptor files may live at any directory depth).
    legal_target = Path(descriptor_path).resolve().parent
    rights_path = legal_target / descriptor.legal_record
    while not rights_path.exists() and legal_target != legal_target.parent:
        legal_target = legal_target.parent
        rights_path = legal_target / descriptor.legal_record
    try:
        rights_record = load_rights_record(rights_path)
    except (QuantaraError, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"rights record unavailable: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"zip": "not_downloaded", "checksum": "not_downloaded"},
            retry_evidence=[],
            http_statuses=[],
            referenced_commit=None,
            diagnostics=["rights_record_unavailable"],
        )
        return EXIT_FAILED
    blocked_ops = [
        op_name
        for op_name in ("acquire_internal", "retain_raw_internal", "normalize_internal")
        if not rights_record.permits(op_name)
    ]
    if blocked_ops:
        print(f"legal gate blocks operations: {blocked_ops}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={op: "blocked" for op in blocked_ops},
            retry_evidence=[],
            http_statuses=[],
            referenced_commit=None,
            diagnostics=["legal_gate_blocked"],
        )
        return EXIT_BLOCKED

    dataset_directory = _dataset_dir(data, descriptor)
    pointer = dataset_directory / "current.json"

    if dry_run:
        # Descriptor/rights/existing-commit verification only.
        if pointer.exists():
            try:
                read_and_verify_current(dataset_directory, data)
            except QuantaraError as exc:
                print(f"dry-run discovery verification failed: {exc}", file=sys.stderr)
                return EXIT_FAILED
        return EXIT_OK

    # Recovery: stale staging directories are safe orphans; discard them.
    for stale in (dataset_directory / "commits").glob(".staging-*"):
        shutil.rmtree(stale, ignore_errors=True)

    # Steps 3–8 (+12.3 reuse): verified acquisition into staging and objects.
    attempt_id = attempt_id_now()
    segment_descriptors = [
        _segment_descriptor(descriptor, position)
        for position in range(len(descriptor.months))
    ]
    acquirers: list[Acquirer] = []
    evidences = []
    try:
        for segment in segment_descriptors:
            acquirer = Acquirer(
                segment,
                data,
                attempt_id,
                transport=transport,
                sleeper=sleeper,
            )
            acquirers.append(acquirer)
            evidences.append(acquirer.acquire())
    except ChecksumMismatch as exc:
        print(f"quarantined: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="QUARANTINED",
            dispositions={"zip": "quarantined", "checksum": "downloaded"},
            retry_evidence=_retry_payload(acquirers),
            http_statuses=_http_statuses(acquirers),
            referenced_commit=None,
            diagnostics=[ChecksumMismatch.error_id],
        )
        shutil.rmtree(data / "staging" / attempt_id, ignore_errors=True)
        return EXIT_QUARANTINED
    except QuantaraError as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"zip": "not_published", "checksum": "downloaded"},
            retry_evidence=_retry_payload(acquirers),
            http_statuses=_http_statuses(acquirers),
            referenced_commit=None,
            diagnostics=["download_failed"],
        )
        shutil.rmtree(data / "staging" / attempt_id, ignore_errors=True)
        return EXIT_FAILED

    # Steps 9–17: archive inspection, parsing, canonical assembly, quality,
    # Parquet write/read-back, reconciliation.
    try:
        specs = []
        members = []
        member_shas = []
        segment_rows = []
        for segment, evidence in zip(
            segment_descriptors, evidences, strict=True
        ):
            spec = inspect_zip(evidence.zip_path, segment.member_pattern)
            member_bytes = read_member_bytes(evidence.zip_path, spec)
            rows = parse_rows(decode_member(member_bytes), segment)
            specs.append(spec)
            members.append(member_bytes)
            member_shas.append(sha256_hex(member_bytes))
            segment_rows.append(rows)
        if descriptor.schema == V2_SCHEMA:
            _validate_range_segments(segment_rows, descriptor)
        source_rows = [row for rows in segment_rows for row in rows]
        assembled, order_ok = assemble_canonical_rows(source_rows, descriptor)
        report = evaluate_quality(
            assembled,
            descriptor,
            source_order_valid=order_ok,
            expected_count=descriptor.expected_row_count,
        )

        fingerprint = schema_fingerprint(
            months=descriptor.months if descriptor.schema == V2_SCHEMA else None
        )
        descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
        content_hash = canonical_content_hash(
            fingerprint, (row.to_content_array() for row in assembled)
        )
        source_digests = (
            [evidence.zip_sha256 for evidence in evidences]
            if descriptor.schema == V2_SCHEMA
            else [evidences[0].zip_sha256]
        )

        approval_record: QualityApprovalRecord | None = None
        if descriptor.quality_policy_version == "2":
            if descriptor.quality_approval is not None:
                approval_record = load_approval_record(
                    descriptor.quality_approval, repo_root=root
                )
            effective_decision = evaluate_effective_quality(
                raw_report=report,
                quality_policy_version="2",
                approval_record=approval_record,
                dataset_id=descriptor.dataset_id,
                canonical_content_hash=content_hash,
                schema_fingerprint=fingerprint,
                source_sha256=source_digests,
            )
        else:
            effective_decision = evaluate_effective_quality(
                raw_report=report,
                quality_policy_version="1",
            )

        if effective_decision.effective_state not in ("PASS", "WARN_APPROVED"):
            print(
                f"quality state {effective_decision.effective_state} blocks publication",
                file=sys.stderr,
            )
            _write_attempt(
                data,
                root,
                terminal_result=(
                    "BLOCKED"
                    if effective_decision.effective_state != "FAIL"
                    else "FAILED"
                ),
                dispositions={"zip": "retained", "normalized_parquet": "not_written"},
                retry_evidence=[],
                http_statuses=_http_statuses(acquirers),
                referenced_commit=None,
                diagnostics=[
                    f.check_id for f in report.findings if f.outcome != "pass"
                ]
                or [f"quality_state_{effective_decision.effective_state}"],
            )
            shutil.rmtree(data / "staging" / attempt_id, ignore_errors=True)
            return (
                EXIT_BLOCKED
                if effective_decision.effective_state != "FAIL"
                else EXIT_FAILED
            )

        staging = data / "staging" / attempt_id
        parquet_path = staging / "canonical.parquet"
        write_canonical_parquet(assembled, parquet_path)
        reconcile_parquet(assembled, parquet_path)
    except MultiMonthInvariantViolation as exc:
        print(f"range invariant blocks publication: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="BLOCKED",
            dispositions={"zip": "retained", "normalized_parquet": "not_written"},
            retry_evidence=_retry_payload(acquirers),
            http_statuses=_http_statuses(acquirers),
            referenced_commit=None,
            diagnostics=[exc.error_id],
        )
        shutil.rmtree(data / "staging" / attempt_id, ignore_errors=True)
        return EXIT_BLOCKED
    except QuantaraError as exc:
        print(f"normalization failed: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"zip": "retained", "normalized_parquet": "not_written"},
            retry_evidence=_retry_payload(acquirers),
            http_statuses=_http_statuses(acquirers),
            referenced_commit=None,
            diagnostics=[exc.error_id],
        )
        shutil.rmtree(data / "staging" / attempt_id, ignore_errors=True)
        return EXIT_FAILED

    # Step 18: content identities.
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data, "normalized", parquet_bytes)

    object_refs = []
    for evidence in evidences:
        object_refs.extend(
            [
                {"kind": "raw", "sha256": evidence.zip_sha256},
                {
                    "kind": "checksum",
                    "sha256": evidence.checksum_document_sha256,
                },
            ]
        )
    object_refs.append({"kind": "normalized", "sha256": normalized_ref})
    identity_evidence = {
        "source_sha256": (
            evidences[0].zip_sha256
            if descriptor.schema != V2_SCHEMA
            else [evidence.zip_sha256 for evidence in evidences]
        ),
        "descriptor_sha256": descriptor_sha,
        "schema_fingerprint": fingerprint,
        "parser_version": parser_version_for(descriptor),
        "canonical_content_hash": content_hash,
        "quality_identity": report.identity(),
        "object_refs": object_refs,
    }
    if descriptor.schema == V2_SCHEMA:
        identity_evidence["months"] = list(descriptor.months)
    if descriptor.quality_policy_version == "2" and approval_record is not None:
        identity_evidence.update(
            {
                "quality_state": effective_decision.effective_state,
                "quality_raw_state": effective_decision.raw_state,
                "quality_identity_sha256": effective_decision.raw_identity_sha256,
                "quality_approval_record_id": approval_record.record_id,
                "quality_approval_record_sha256": approval_record.record_sha256,
            }
        )

    # Steps 12.3/§16: idempotent rerun — verify the existing commit instead of
    # publishing an identical one. A malformed or non-object pointer behaves
    # as a lost pointer: recovery proceeds through the normal publication path.
    if pointer.exists():
        try:
            parsed_pointer = json.loads(pointer.read_text(encoding="utf-8"))
        except ValueError:
            parsed_pointer = None
        current_commit = ""
        if isinstance(parsed_pointer, dict):
            current_commit = str(parsed_pointer.get("commit", ""))
        commit_dir = dataset_directory / "commits" / current_commit
        evidence_keys = tuple(identity_evidence.keys())
        matches = bool(
            current_commit
            and existing_commit_matches(
                data, commit_dir, identity_evidence, keys=evidence_keys
            )
        )
        if (
            matches
            and descriptor.quality_policy_version == "2"
            and approval_record is not None
        ):
            approval_file = commit_dir / "quality-approval.json"
            if not approval_file.exists():
                matches = False
            else:
                try:
                    committed_approval = json.loads(
                        approval_file.read_text(encoding="utf-8")
                    )
                    committed_sha = sha256_hex(
                        canonicalize(committed_approval).encode("utf-8")
                    )
                    if committed_sha != approval_record.record_sha256:
                        matches = False
                except Exception:
                    matches = False

        if matches:
            _write_attempt(
                data,
                root,
                terminal_result="VERIFIED_NO_OP",
                dispositions={
                    "zip": "reused",
                    "checksum": "downloaded",
                    "normalized_parquet": "already_published",
                },
                retry_evidence=_retry_payload(acquirers),
                http_statuses=_http_statuses(acquirers),
                referenced_commit=current_commit,
                diagnostics=[],
            )
            shutil.rmtree(staging, ignore_errors=True)
            return EXIT_OK

    # Steps 19–21: staged evidence, atomic commit publication, pointer.
    manifest_kwargs = dict(
        dataset_id=descriptor.dataset_id,
        instrument_id=descriptor.instrument_id,
        archive_url=(
            descriptor.archive_url
            if descriptor.schema != V2_SCHEMA
            else list(descriptor.archive_urls)
        ),
        checksum_url=(
            descriptor.checksum_url
            if descriptor.schema != V2_SCHEMA
            else list(descriptor.checksum_urls)
        ),
        official_checksum_sha256=(
            evidences[0].official_digest
            if descriptor.schema != V2_SCHEMA
            else [evidence.official_digest for evidence in evidences]
        ),
        checksum_document_sha256=(
            evidences[0].checksum_document_sha256
            if descriptor.schema != V2_SCHEMA
            else [evidence.checksum_document_sha256 for evidence in evidences]
        ),
        local_zip_sha256=(
            evidences[0].zip_sha256
            if descriptor.schema != V2_SCHEMA
            else [evidence.zip_sha256 for evidence in evidences]
        ),
        local_zip_size=(
            evidences[0].zip_size
            if descriptor.schema != V2_SCHEMA
            else [evidence.zip_size for evidence in evidences]
        ),
        member_name=(
            specs[0].name
            if descriptor.schema != V2_SCHEMA
            else [spec.name for spec in specs]
        ),
        member_size=(
            specs[0].uncompressed_size
            if descriptor.schema != V2_SCHEMA
            else [spec.uncompressed_size for spec in specs]
        ),
        member_sha256=(
            member_shas[0]
            if descriptor.schema != V2_SCHEMA
            else member_shas
        ),
        # Amendment 2026-08-30: under the headerless variant the member's
        # first line is a data row, so publishing it as header evidence
        # would be a fabricated field. Record the declared absence instead.
        source_header=(
            None
            if descriptor.csv_header_absent
            else list(decode_member(members[0]).splitlines()[0].split(","))
        ),
        parser_version=parser_version_for(descriptor),
        schema_version=descriptor.schema_version,
        schema_fingerprint=fingerprint,
        timestamp_semantics=descriptor.timestamp_semantics,
        quality_policy_version=descriptor.quality_policy_version,
        quality_identity=report.identity(),
        quality_state=(
            effective_decision.effective_state
            if descriptor.quality_policy_version == "2"
            else report.state
        ),
        source_row_count=len(assembled),
        canonical_row_count=len(assembled),
        source_order_state="ordered" if order_ok else "sorted_from_unordered",
        canonical_content_hash=content_hash,
        parquet_sha256=parquet_sha,
        parquet_size=len(parquet_bytes),
        object_refs=object_refs,
        legal_record_id=rights_record.record_id,
        legal_states={
            name: entry.state for name, entry in rights_record.operations.items()
        },
        environment=environment_evidence(root),
    )
    if descriptor.quality_policy_version == "2" and approval_record is not None:
        manifest_kwargs.update(
            quality_raw_state=effective_decision.raw_state,
            quality_identity_sha256=effective_decision.raw_identity_sha256,
            quality_approval_record_id=approval_record.record_id,
            quality_approval_record_sha256=approval_record.record_sha256,
        )
    manifest = build_dataset_manifest(**manifest_kwargs)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    files = {
        "manifest.json": manifest_bytes,
        "quality.json": (
            json.dumps(
                _quality_payload(report)
                if descriptor.quality_policy_version == "1"
                else _quality_payload_v2(report, effective_decision, approval_record),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode(),
        "content.json": (
            json.dumps(identity_evidence, indent=2, sort_keys=True) + "\n"
        ).encode(),
    }
    if descriptor.quality_policy_version == "2" and approval_record is not None:
        files["quality-approval.json"] = (
            json.dumps(
                approval_record.canonical_semantics(), indent=2, sort_keys=True
            )
            + "\n"
        ).encode()

    staged_commit = stage_commit(dataset_directory, attempt_id, files)
    published_manifest_bytes = manifest_bytes
    try:
        commit_dir = publish_commit(
            staged_commit, dataset_directory / "commits", content_hash
        )
    except QuantaraError:
        # Recovery: an equivalent commit already exists (e.g., pointer loss).
        candidate = dataset_directory / "commits" / content_hash
        evidence_keys = tuple(identity_evidence.keys())
        if not (
            candidate.is_dir()
            and existing_commit_matches(
                data, candidate, identity_evidence, keys=evidence_keys
            )
        ):
            print(
                "publication failed: existing commit differs from current evidence",
                file=sys.stderr,
            )
            return EXIT_FAILED
        if (
            descriptor.quality_policy_version == "2"
            and approval_record is not None
        ):
            app_file = candidate / "quality-approval.json"
            if not app_file.exists():
                print(
                    "publication failed: existing commit missing quality-approval.json",
                    file=sys.stderr,
                )
                return EXIT_FAILED
            try:
                cand_app = json.loads(app_file.read_text(encoding="utf-8"))
                if (
                    sha256_hex(canonicalize(cand_app).encode("utf-8"))
                    != approval_record.record_sha256
                ):
                    print(
                        "publication failed: existing quality-approval.json hash mismatch",
                        file=sys.stderr,
                    )
                    return EXIT_FAILED
            except Exception:
                return EXIT_FAILED
        commit_dir = candidate
        published_manifest_bytes = (candidate / "manifest.json").read_bytes()

    # Step 21: verify the committed directory independently before pointing.
    verify_commit_graph(data, commit_dir)
    write_current(
        dataset_directory,
        content_hash,
        manifest_digest=sha256_hex(published_manifest_bytes),
    )

    # Step 22: reopen discovery through current.json and verify the graph.
    read_and_verify_current(dataset_directory, data)

    shutil.rmtree(staging, ignore_errors=True)
    _write_attempt(
        data,
        root,
        terminal_result="PUBLISHED",
        dispositions={
            "zip": "retained" if evidence.reused_zip else "downloaded",
            "checksum": "reused" if evidence.reused_checksum else "downloaded",
            "normalized_parquet": "published",
        },
        retry_evidence=_retry_payload(acquirers),
        http_statuses=_http_statuses(acquirers),
        referenced_commit=content_hash,
        diagnostics=[],
    )
    return EXIT_OK
