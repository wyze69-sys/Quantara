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
from dataclasses import asdict
from pathlib import Path

from quantara.acquisition import Acquirer, ChecksumMismatch
from quantara.archive import inspect_zip, read_member_bytes
from quantara.canonical import (
    assemble_canonical_rows,
    read_canonical_rows,
    reconcile_rows,
    write_canonical_parquet,
)
from quantara.descriptor import DatasetDescriptor, load_descriptor, load_rights_record
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
from quantara.quality import evaluate_quality

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_FAILED = 3
EXIT_QUARANTINED = 4


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
    except QuantaraError as exc:
        print(f"invalid descriptor: {exc}", file=sys.stderr)
        return EXIT_FAILED

    # Resolve the legal record relative to the nearest ancestor that contains
    # it (descriptor files may live at any directory depth).
    legal_target = Path(descriptor_path).resolve().parent
    rights_path = legal_target / descriptor.legal_record
    while not rights_path.exists() and legal_target != legal_target.parent:
        legal_target = legal_target.parent
        rights_path = legal_target / descriptor.legal_record
    rights_record = load_rights_record(rights_path)
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
    acquirer = Acquirer(
        descriptor,
        data,
        attempt_id,
        transport=transport,
        sleeper=sleeper,
    )
    try:
        evidence = acquirer.acquire()
    except ChecksumMismatch as exc:
        print(f"quarantined: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="QUARANTINED",
            dispositions={"zip": "quarantined", "checksum": "downloaded"},
            retry_evidence=[asdict(r) for r in acquirer.retry_evidence],
            http_statuses=list(acquirer.http_statuses),
            referenced_commit=None,
            diagnostics=[ChecksumMismatch.error_id],
        )
        return EXIT_QUARANTINED
    except QuantaraError as exc:
        print(f"acquisition failed: {exc}", file=sys.stderr)
        _write_attempt(
            data,
            root,
            terminal_result="FAILED",
            dispositions={"zip": "not_published", "checksum": "downloaded"},
            retry_evidence=[asdict(r) for r in acquirer.retry_evidence],
            http_statuses=list(acquirer.http_statuses),
            referenced_commit=None,
            diagnostics=["download_failed"],
        )
        return EXIT_FAILED

    # Steps 9–17: archive inspection, parsing, canonical assembly, quality,
    # Parquet write/read-back, reconciliation.
    try:
        spec = inspect_zip(evidence.zip_path, descriptor.member_pattern)
        member_bytes = read_member_bytes(evidence.zip_path, spec)
        member_sha = sha256_hex(member_bytes)
        source_rows = parse_rows(decode_member(member_bytes), descriptor)
        assembled, order_ok = assemble_canonical_rows(source_rows, descriptor)
        report = evaluate_quality(
            assembled,
            descriptor,
            source_order_valid=order_ok,
            expected_count=descriptor.expected_row_count,
        )
        if report.state != "PASS":
            print(f"quality state {report.state} blocks publication", file=sys.stderr)
            _write_attempt(
                data,
                root,
                terminal_result="BLOCKED",
                dispositions={"zip": "retained", "normalized_parquet": "not_written"},
                retry_evidence=[],
                http_statuses=list(acquirer.http_statuses),
                referenced_commit=None,
                diagnostics=[
                    f.check_id for f in report.findings if f.outcome != "pass"
                ]
                or [f"quality_state_{report.state}"],
            )
            return EXIT_BLOCKED

        staging = data / "staging" / attempt_id
        parquet_path = staging / "canonical.parquet"
        write_canonical_parquet(assembled, parquet_path)
        persisted_rows = read_canonical_rows(parquet_path)
        reconcile_rows(assembled, persisted_rows)
    except ChecksumMismatch as exc:
        print(f"quarantined: {exc}", file=sys.stderr)
        return EXIT_QUARANTINED
    except QuantaraError as exc:
        print(f"normalization failed: {exc}", file=sys.stderr)
        return EXIT_FAILED

    # Step 18: content identities.
    fingerprint = schema_fingerprint()
    descriptor_sha = descriptor_hash(descriptor.canonical_semantics())
    content_hash = canonical_content_hash(
        fingerprint, [row.to_content_array() for row in assembled]
    )
    parquet_bytes = parquet_path.read_bytes()
    parquet_sha = sha256_hex(parquet_bytes)
    normalized_ref = put_object(data, "normalized", parquet_bytes)

    object_refs = [
        {"kind": "raw", "sha256": evidence.zip_sha256},
        {"kind": "checksum", "sha256": evidence.checksum_document_sha256},
        {"kind": "normalized", "sha256": normalized_ref},
    ]
    identity_evidence = {
        "source_sha256": evidence.zip_sha256,
        "descriptor_sha256": descriptor_sha,
        "schema_fingerprint": fingerprint,
        "parser_version": PARSER_VERSION,
        "canonical_content_hash": content_hash,
        "quality_identity": report.identity(),
        "object_refs": object_refs,
    }

    # Steps 12.3/§16: idempotent rerun — verify the existing commit instead of
    # publishing an identical one.
    if pointer.exists():
        current_commit = (
            json.loads(pointer.read_text(encoding="utf-8")).get("commit", "")
        )
        commit_dir = dataset_directory / "commits" / current_commit
        if existing_commit_matches(data, commit_dir, identity_evidence):
            _write_attempt(
                data,
                root,
                terminal_result="VERIFIED_NO_OP",
                dispositions={
                    "zip": "reused",
                    "checksum": "downloaded",
                    "normalized_parquet": "already_published",
                },
                retry_evidence=[asdict(r) for r in acquirer.retry_evidence],
                http_statuses=list(acquirer.http_statuses),
                referenced_commit=current_commit,
                diagnostics=[],
            )
            shutil.rmtree(staging, ignore_errors=True)
            return EXIT_OK

    # Steps 19–21: staged evidence, atomic commit publication, pointer.
    manifest = build_dataset_manifest(
        dataset_id=descriptor.dataset_id,
        instrument_id=descriptor.instrument_id,
        archive_url=descriptor.archive_url,
        checksum_url=descriptor.checksum_url,
        official_checksum_sha256=evidence.official_digest,
        checksum_document_sha256=evidence.checksum_document_sha256,
        local_zip_sha256=evidence.zip_sha256,
        local_zip_size=evidence.zip_size,
        member_name=spec.name,
        member_size=spec.uncompressed_size,
        member_sha256=member_sha,
        source_header=list(decode_member(member_bytes).splitlines()[0].split(",")),
        parser_version=PARSER_VERSION,
        schema_version=descriptor.schema_version,
        schema_fingerprint=fingerprint,
        timestamp_semantics=descriptor.timestamp_semantics,
        quality_policy_version="1",
        quality_identity=report.identity(),
        quality_state=report.state,
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
    staged_commit = stage_commit(dataset_directory, attempt_id, files)
    try:
        commit_dir = publish_commit(
            staged_commit, dataset_directory / "commits", content_hash
        )
    except QuantaraError:
        # Recovery: an equivalent commit already exists (e.g., pointer loss).
        candidate = dataset_directory / "commits" / content_hash
        if not (
            candidate.is_dir()
            and existing_commit_matches(data, candidate, identity_evidence)
        ):
            print(
                "publication failed: existing commit differs from current evidence",
                file=sys.stderr,
            )
            return EXIT_FAILED
        commit_dir = candidate

    # Step 21: verify the committed directory independently before pointing.
    verify_commit_graph(data, commit_dir)
    write_current(
        dataset_directory,
        content_hash,
        manifest_digest=sha256_hex(manifest_bytes),
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
        retry_evidence=[asdict(r) for r in acquirer.retry_evidence],
        http_statuses=list(acquirer.http_statuses),
        referenced_commit=content_hash,
        diagnostics=[],
    )
    return EXIT_OK
