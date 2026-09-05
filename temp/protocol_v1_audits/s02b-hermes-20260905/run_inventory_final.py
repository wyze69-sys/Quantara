"""S02-B full BTC OI inventory; value-blind, resumable, no production writes.

Every frozen day runs through the real pipeline in a disposable root. WARN is expected
and does not stop the inventory. Evidence records counts, timestamps, hashes, and findings
only; never market values.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quantara import series_canonical as canonical
from quantara.archive import inspect_zip, read_member_bytes
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_scalar_rows
from quantara.series_pipeline import _storage_root, run_series_pipeline
from quantara.series_quality import evaluate_series_quality, proposed_approval_payload

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = Path(os.environ.get(
    'S02B_DESCRIPTOR',
    ROOT / 'configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml',
))
EVIDENCE = Path(__file__).resolve().parent
DATA_ROOT = _storage_root(Path(os.environ['S02B_DATA_ROOT']))
PROGRESS = EVIDENCE / 'inventory-progress-final.json'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace('+00:00', 'Z')


def _attempt_for(period: str) -> tuple[Path, dict]:
    found = []
    for path in (DATA_ROOT / 'attempts').glob('*.json'):
        doc = json.loads(path.read_bytes())
        if doc.get('selected_period') == period:
            found.append((path.stat().st_mtime_ns, path, doc))
    if not found:
        raise AssertionError(f'no attempt record for {period}')
    _, path, doc = max(found)
    return path, doc


def _source(record: dict, lane: Path):
    acquired = json.loads(Path(record['acquirer_evidence_path']).read_bytes())
    if record['terminal_state'] == 'PUBLISHED':
        current = read_and_verify_current(lane, lane)
        graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
        raw_path = object_path(lane, 'raw', graph['source_sha256'])
    else:
        graph = None
        raw_path_text = acquired.get('raw_path')
        raw_path = Path(raw_path_text) if raw_path_text else None
    return acquired, graph, raw_path


def inspect_period(descriptor, period: str) -> dict:
    archive = descriptor.archive_for(period)
    attempts_before = len(list((DATA_ROOT / 'attempts').glob('*.json')))
    exit_code = run_series_pipeline(DESCRIPTOR, DATA_ROOT, period=period)
    attempt_path, record = _attempt_for(period)
    attempts_after = len(list((DATA_ROOT / 'attempts').glob('*.json')))
    assert attempts_after >= attempts_before
    assert record['terminal_state'] in ('PUBLISHED', 'BLOCKED', 'FAILED')

    lane = DATA_ROOT / 'datasets/series' / descriptor.series_id / period
    acquired, graph, raw_path = _source(record, lane)
    if raw_path is None:
        raise httpx.TransportError(
            f'acquisition produced no source archive for {period}: '
            f'{record.get("error_type")}: {record.get("error_message")}'
        )
    raw = raw_path.read_bytes()
    member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))

    if record['terminal_state'] == 'FAILED':
        # Pipeline crashed; evidence from attempt record only
        return {
            'period': period,
            'attempt_path': str(attempt_path),
            'terminal_state': 'FAILED',
            'exit_code': exit_code,
            'error_type': record.get('error_type'),
            'error_message': record.get('error_message'),
            'zip_sha256': sha(raw),
            'official_digest': acquired['official_digest'],
            'checksum_matches_zip': (
                sha(raw) == acquired['official_digest'] == acquired['raw_sha256']
            ),
            'member_sha256': sha(member),
            'parser_input_matches': sha(member) == acquired['member_sha256'],
            'published': False,
            'pointer_written': False,
        }

    parse_path = EVIDENCE / 'parse' / f'{period}.json'
    parse_path.parent.mkdir(parents=True, exist_ok=True)
    if parse_path.exists():
        parse_path.unlink()
    parsed = parse_scalar_rows(member, archive, attempt_path=parse_path)
    rows = canonical.build_scalar_rows(parsed)
    report = evaluate_series_quality(parsed, rows)
    times = [row.event_ts for row in parsed.rows]
    nonpass = [
        {'check_id': f.check_id, 'outcome': f.outcome, 'severity': f.severity,
         'count': f.count, 'evidence': f.evidence}
        for f in report.findings if f.outcome != 'pass'
    ]
    official = acquired['official_digest']
    entry = {
        'period': period,
        'attempt_path': str(attempt_path),
        'terminal_state': record['terminal_state'],
        'exit_code': exit_code,
        'zip_sha256': sha(raw),
        'official_digest': official,
        'checksum_matches_zip': sha(raw) == official == acquired['raw_sha256'],
        'member_sha256': sha(member),
        'parser_input_matches': sha(member) == acquired['member_sha256'],
        'source_rows': parsed.source_rows,
        'distinct_rows': parsed.distinct_rows,
        'duplicate_rows': parsed.duplicate_rows,
        'duplicate_hash_count': len(parsed.duplicate_hashes),
        'conflict_rows': parsed.conflict_rows,
        'source_ordered': parsed.source_ordered,
        'first_event_ts': min(times),
        'first_event_utc': utc(min(times)),
        'last_event_ts': max(times),
        'last_event_utc': utc(max(times)),
        'off_grid_snapshots': sum(t % 300_000 != 0 for t in times),
        'eligibility_delay_ms': sorted({r.eligibility_ts - r.event_ts for r in rows}),
        'canonical_rows': len(rows),
        'canonical_content_hash': canonical.scalar_content_hash(rows),
        'quality_state': report.state,
        'quality_identity': report.identity(),
        'nonpass_findings': nonpass,
        'published': graph is not None,
        'pointer_written': (lane / 'current.json').exists(),
    }
    if graph is not None:
        entry.update(
            commit=graph['canonical_content_hash'],
            graph_source_matches=graph['source_sha256'] == sha(raw),
            graph_parser_input_matches=graph['parser_input_sha256'] == sha(member),
            graph_quality_matches=(graph['quality_state'] == report.state
                                   and graph['quality_identity'] == report.identity()),
        )
    if report.state == 'WARN':
        proposal = proposed_approval_payload(report)
        assert proposal['authorized'] is False and proposal['approver'] == 'PLACEHOLDER'
        entry['proposal'] = proposal
    return entry


def main() -> None:
    descriptor = load_series_descriptor(DESCRIPTOR)
    periods = descriptor.object_periods
    assert len(periods) == 1583
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    existing = []
    if PROGRESS.exists():
        existing = json.loads(PROGRESS.read_text(encoding='utf-8'))
    by_period = {entry['period']: entry for entry in existing}

    for index, period in enumerate(periods, 1):
        if period in by_period:
            continue
        for attempt in range(1, 4):
            try:
                entry = inspect_period(descriptor, period)
                break
            except (httpx.TransportError, AssertionError) as exc:
                if attempt == 3:
                    raise
                print(f'RETRY {period} {attempt} {type(exc).__name__}', flush=True)
                time.sleep(2**attempt)
        by_period[period] = entry
        ordered = [by_period[p] for p in periods if p in by_period]
        PROGRESS.write_text(json.dumps(ordered, indent=2, sort_keys=True), encoding='utf-8')
        source_rows = entry.get('source_rows', 'n/a')
        distinct_rows = entry.get('distinct_rows', 'n/a')
        duplicate_rows = entry.get('duplicate_rows', 'n/a')
        finding_ids = [f['check_id'] for f in entry.get('nonpass_findings', [])]
        print(
            f'[{index}/{len(periods)}] {period} {entry["terminal_state"]} '
            f'rows={source_rows} distinct={distinct_rows} dup={duplicate_rows} '
            f'findings={finding_ids}',
            flush=True,
        )

    inventory = [by_period[p] for p in periods]
    (EVIDENCE / 'inventory-final.json').write_text(
        json.dumps(inventory, indent=2, sort_keys=True), encoding='utf-8')
    assert all(e['checksum_matches_zip'] and e['parser_input_matches'] for e in inventory)
    assert all(e.get('conflict_rows', 0) == 0 for e in inventory)
    assert all(e.get('off_grid_snapshots', 0) == 0 for e in inventory)
    print(f'INVENTORY_COMPLETE {len(inventory)}', flush=True)


if __name__ == '__main__':
    main()
