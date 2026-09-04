"""D06 single-period composition over frozen D02–D05 and publication primitives.

Only raw PASS is publishable. Acquisition, staging and objects belong to the
selected series lane; attempts are value-blind and survive every terminal path.
"""

from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from quantara import series_acquisition as acquisition
from quantara import series_canonical as canonical
from quantara.acquisition import ChecksumMismatch
from quantara.archive import inspect_zip, read_member_bytes
from quantara.hashing import sha256_hex
from quantara.manifests import attempt_id_now, write_json
from quantara.publication import (
    PublicationError,
    existing_commit_matches,
    publish_commit,
    put_object,
    read_and_verify_current,
    stage_commit,
    verify_commit_graph,
    write_current,
)
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_kline_rows, parse_scalar_rows
from quantara.series_quality import evaluate_series_quality

_ROOT = Path(__file__).resolve().parents[2]
_HASH = re.compile(r'[0-9a-f]{64}')
_OPERATIONS = ('acquire_internal', 'retain_raw_internal', 'normalize_internal')


class SeriesPipelineError(ValueError):
    """Unsupported retained format or inconsistent series publication evidence."""


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + '\n').encode('utf-8')


def _lane(data: Path, series_id: str, period: str) -> Path:
    return data / 'datasets' / 'series' / series_id / period


def _storage_root(path) -> Path:
    """Keep frozen file primitives usable beyond Windows' legacy MAX_PATH."""
    data = Path(path)
    if sys.platform == 'win32':
        absolute = str(data.absolute())
        if not absolute.startswith('\\\\?\\'):
            absolute = ('\\\\?\\UNC\\' + absolute[2:] if absolute.startswith('\\\\')
                        else '\\\\?\\' + absolute)
        data = Path(absolute)
    return data


def _verified(lane: Path, series_id: str, period: str, descriptor_sha: str) -> dict | None:
    """Treat malformed/lost discovery as absent, never follow unchecked paths.

    The legacy graph verifier authenticates object references. Bind its returned
    content to the pointer's manifest digest and this descriptor/period as well.
    """
    try:
        pointer = json.loads((lane / 'current.json').read_bytes())
        if not isinstance(pointer, dict):
            return None
        commit = pointer.get('commit')
        if type(commit) is not str or not _HASH.fullmatch(commit):
            return None
        current = read_and_verify_current(lane, lane)
        directory = lane / 'commits' / commit
        content = verify_commit_graph(lane, directory)
        manifest = (directory / 'manifest.json').read_bytes()
        if (sha256_hex(manifest) != pointer.get('manifest_sha256')
                or json.loads(manifest) != content
                or content.get('series_id') != series_id
                or content.get('period') != period
                or content.get('descriptor_sha256') != descriptor_sha
                or content.get('canonical_content_hash') != commit
                or content.get('quality_state') != 'PASS'):
            return None
        return current
    except (OSError, ValueError, TypeError, PublicationError):
        return None


def _member_bytes(evidence, archive) -> bytes:
    raw = evidence.raw_path.read_bytes()
    if len(raw) != evidence.raw_size or sha256_hex(raw) != evidence.raw_sha256:
        raise ChecksumMismatch('retained series bytes differ from acquisition evidence')
    if evidence.raw_format == 'zip':
        member = read_member_bytes(
            evidence.raw_path, inspect_zip(evidence.raw_path, archive.member_pattern),
        )
        if sha256_hex(member) != evidence.member_sha256:
            raise ChecksumMismatch('Binance member differs from acquisition evidence')
        return member
    if evidence.raw_format == 'csv_2020_2024':
        return raw
    if evidence.raw_format == 'zip_raw_deflate_member':
        buffer = io.BytesIO()
        acquisition._verify_deflate(
            [raw], acquisition._KRAKEN, sink=acquisition._KrakenWindow(buffer),
        )
        member = buffer.getvalue()
        if not member:
            raise SeriesPipelineError('empty frozen-window Kraken selection')
        return member
    raise SeriesPipelineError('unsupported retained series format')


def run_series_pipeline(
    descriptor_path, data_root, *, period=None, dry_run=False,
    transport=None, sleeper=None, repo_root=None,
) -> int:
    """Publish one explicit or first-unpublished closed period; return 0/2/3.

    Dry-run performs selection and descriptor/rights validation only. Its
    VERIFIED_NO_OP attempt is marked dry_run and never claims a publication.
    Failure messages retain types only, never source payloads or market values.
    """
    data = _storage_root(data_root)
    root = _ROOT if repo_root is None else Path(repo_root)
    attempt_id = attempt_id_now()
    record = {
        'schema': 'quantara.series-pipeline-attempt/v1', 'attempt_id': attempt_id,
        'series_id': None, 'period': None, 'selected_period': None,
        'selection_mode': 'first_unpublished' if period is None else 'explicit',
        'descriptor_source': {'path': str(Path(descriptor_path)), 'sha256': None},
        'acquirer_evidence_path': None, 'parse_attempt_path': None,
        'canonical_content_hash': None, 'gap_manifest_hash': None,
        'quality_identity': None, 'quality_state': None, 'finding_ids': [],
        'parser_input_sha256': None, 'raw_format': None, 'dry_run': dry_run,
        'terminal_state': 'FAILED', 'exit_code': 3,
    }

    def finish(state, code):
        record.update(terminal_state=state, exit_code=code)
        try:
            write_json(data / 'attempts' / f'{attempt_id}.json', record)
        except OSError as exc:
            print(f'series attempt write failed: {type(exc).__name__}', file=sys.stderr)
            return 3
        print(f'{state}: series={record["series_id"]} period={record["selected_period"]}')
        return code

    try:
        descriptor = load_series_descriptor(descriptor_path, repo_root=root)
        descriptor_sha = sha256_hex(Path(descriptor_path).read_bytes())
        record['descriptor_source']['sha256'] = descriptor_sha
        record['series_id'] = descriptor.series_id
        rights = descriptor.load_rights(root)
        record['rights_states'] = {op: rights.operations[op].state for op in _OPERATIONS}
        if not all(rights.permits(op) for op in _OPERATIONS):
            return finish('BLOCKED', 2)

        current = None
        if period is not None:
            archive = descriptor.archive_for(period)  # closed type and frozen-window guard
            selected = archive.period
            lane = _lane(data, descriptor.series_id, selected)
            current = _verified(lane, descriptor.series_id, selected, descriptor_sha)
        else:
            for selected in descriptor.object_periods:
                lane = _lane(data, descriptor.series_id, selected)
                current = _verified(lane, descriptor.series_id, selected, descriptor_sha)
                if current is None:
                    break
            archive = descriptor.archive_for(selected)
        record.update(period=selected, selected_period=selected)
        if current is not None:
            for key in ('canonical_content_hash', 'gap_manifest_hash', 'quality_identity',
                        'quality_state', 'parser_input_sha256', 'raw_format',
                        'full_member_verification', 'member_sha256'):
                if key in current:
                    record[key] = current[key]
            return finish('VERIFIED_NO_OP', 0)
        if dry_run:
            return finish('VERIFIED_NO_OP', 0)

        # The frozen acquirer roots both objects and staging at its data_root.
        # Supplying this lane prevents any write to another series or legacy lane.
        acquirer = acquisition.SeriesAcquirer(
            descriptor, selected, lane, transport=transport, sleeper=sleeper, repo_root=root,
        )
        record['acquirer_evidence_path'] = str(
            lane / 'staging' / acquirer.attempt_id / 'attempt.json',
        )
        evidence = acquirer.acquire()
        record.update(acquirer_evidence_path=str(evidence.evidence_path),
                      raw_format=evidence.raw_format)
        if descriptor.to_dict()['provider'] == 'kraken':
            record.update(full_member_verification='acquirer_provenance',
                          member_sha256=evidence.member_sha256)
        member = _member_bytes(evidence, archive)
        record['parser_input_sha256'] = sha256_hex(member)
        staging = lane / 'staging' / attempt_id
        staging.mkdir(parents=True, exist_ok=False)
        parse_path = staging / 'parse-attempt.json'
        record['parse_attempt_path'] = str(parse_path)
        scalar = descriptor.to_dict()['canonical_value'] in (
            'last_funding_rate', 'sum_open_interest',
        )
        parsed = (parse_scalar_rows if scalar else parse_kline_rows)(
            member, archive, attempt_path=parse_path, repo_root=root,
        )
        rows = (canonical.build_scalar_rows if scalar else canonical.build_kline_rows)(parsed)
        hash_rows = canonical.scalar_content_hash if scalar else canonical.kline_content_hash
        content_hash = hash_rows(rows)
        record['canonical_content_hash'] = content_hash
        gap = None
        if not scalar:
            gap = canonical.build_gap_manifest(parsed)
            record['gap_manifest_hash'] = canonical.gap_manifest_hash(gap)
            (staging / 'gaps.json').write_bytes(canonical.gap_manifest_bytes(gap))
        parquet = staging / 'canonical.parquet'
        (canonical.write_scalar_parquet if scalar else canonical.write_kline_parquet)(rows, parquet)
        (canonical.reconcile_scalar_parquet if scalar else canonical.reconcile_kline_parquet)(
            rows, parquet,
        )
        report = evaluate_series_quality(parsed, rows)
        quality = {
            'state': report.state, 'identity': report.identity(),
            'findings': [asdict(finding) for finding in report.findings],
        }
        record.update(quality_state=report.state, quality_identity=report.identity(),
                      finding_ids=[f.check_id for f in report.findings if f.outcome != 'pass'])
        if report.state != 'PASS':
            return finish('BLOCKED' if report.state == 'WARN' else 'FAILED',
                          2 if report.state == 'WARN' else 3)

        # All publication objects, including the hash value itself, use the
        # frozen write-once content-addressed primitive with computed addresses.
        artifacts = {}
        refs = [{'kind': 'raw', 'sha256': evidence.raw_sha256}]
        # Acquirer normally retained this object; reusing the primitive also
        # authenticates and deduplicates it before committing its reference.
        put_object(lane, 'raw', evidence.raw_path.read_bytes())
        if evidence.checksum_path is not None:
            checksum = evidence.checksum_path.read_bytes()
            if sha256_hex(checksum) != evidence.checksum_sha256:
                raise ChecksumMismatch('retained checksum differs from acquisition evidence')
            refs.append({'kind': 'checksum', 'sha256': put_object(lane, 'checksum', checksum)})
        payloads = {
            'canonical_parquet': parquet.read_bytes(),
            'canonical_content_hash': (content_hash + '\n').encode('ascii'),
            'quality_report': _json_bytes(quality), 'parse_attempt': parse_path.read_bytes(),
        }
        if gap is not None:
            payloads['gap_manifest'] = canonical.gap_manifest_bytes(gap)
        for name, payload in payloads.items():
            digest = put_object(lane, 'normalized', payload)
            artifacts[name] = digest
            refs.append({'kind': 'normalized', 'sha256': digest})
        content = {
            'schema': 'quantara.series-publication/v1', 'series_id': descriptor.series_id,
            'period': selected, 'descriptor_sha256': descriptor_sha,
            'canonical_content_hash': content_hash,
            'gap_manifest_hash': record['gap_manifest_hash'],
            'quality_identity': report.identity(), 'quality_state': report.state,
            'parser_input_sha256': record['parser_input_sha256'], 'raw_format': evidence.raw_format,
            'source_sha256': evidence.raw_sha256, 'artifacts': artifacts, 'object_refs': refs,
        }
        if 'full_member_verification' in record:
            content.update(full_member_verification=record['full_member_verification'],
                           member_sha256=evidence.member_sha256)
        manifest = _json_bytes(content)
        candidate = lane / 'commits' / content_hash
        if candidate.exists():
            if (not existing_commit_matches(lane, candidate, content, keys=tuple(content))
                    or (candidate / 'manifest.json').read_bytes() != manifest):
                raise PublicationError('existing series commit differs from current evidence')
        else:
            staged = stage_commit(lane, attempt_id, {'manifest.json': manifest,
                                                    'content.json': manifest})
            candidate = publish_commit(staged, lane / 'commits', content_hash)
        verify_commit_graph(lane, candidate)
        write_current(lane, content_hash, sha256_hex(manifest))
        discovered = _verified(lane, descriptor.series_id, selected, descriptor_sha)
        if discovered is None or discovered['commit'] != content_hash:
            raise PublicationError('series discovery verification failed')
        return finish('PUBLISHED', 0)
    except Exception as exc:
        record['error_type'] = type(exc).__name__
        return finish('FAILED', 3)
