"""S03-B: full 60-month inventory for BTC mark-price klines.

Runs the frozen pipeline on all 60 monthly periods, records terminal state
and value-blind evidence for each. Identifies PASS/BLOCKED/FAILED periods.

Environment:
    S03B_DATA_ROOT   disposable data root (required, explicit)
    S03B_WORKERS     backfill workers, default 1
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quantara.archive import inspect_zip, read_member_bytes
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_kline_rows
from quantara.series_pipeline import _storage_root, run_series_pipeline
from quantara.series_quality import evaluate_series_quality

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-mark-1m-2020-2024.yaml'
EVIDENCE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ['S03B_DATA_ROOT'])
WORKERS = int(os.environ.get('S03B_WORKERS', '1'))


class CountingTransport(httpx.BaseTransport):
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed
        self.requests: list[str] = []
        self.rejected: list[str] = []
        self.real = httpx.HTTPTransport()

    def handle_request(self, request):
        url = str(request.url)
        if url not in self.allowed:
            self.rejected.append(url)
            raise AssertionError(f'URL outside allowlist: {url}')
        self.requests.append(url)
        response = self.real.handle_request(request)
        assert response.status_code == 200, f'status {response.status_code} for {url}'
        assert 'text/html' not in response.headers.get('content-type', '').lower()
        return response

    def close(self):
        self.real.close()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace('+00:00', 'Z')


def main() -> None:
    descriptor = load_series_descriptor(DESCRIPTOR)
    all_periods = descriptor.object_periods
    print(f'ALL_PERIODS {len(all_periods)}')

    data_root = _storage_root(DATA_ROOT)
    (EVIDENCE / 'parse').mkdir(exist_ok=True)

    allowed = set()
    for period in all_periods:
        archive = descriptor.archive_for(period)
        allowed.update({archive.archive_url, archive.checksum_url})

    transport = CountingTransport(allowed)
    results = []
    try:
        for i, period in enumerate(all_periods, 1):
            archive = descriptor.archive_for(period)
            lane = data_root / 'datasets/series' / descriptor.series_id / period
            exit_code = run_series_pipeline(
                DESCRIPTOR, data_root, period=period, transport=transport)

            attempts = sorted((data_root / 'attempts').glob('*.json'),
                              key=lambda p: p.stat().st_mtime)
            record = json.loads(attempts[-1].read_bytes())

            entry = {
                'period': period,
                'exit_code': exit_code,
                'terminal_state': record['terminal_state'],
                'error_type': record.get('error_type'),
            }

            if record['terminal_state'] == 'PUBLISHED':
                current = read_and_verify_current(lane, lane)
                graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
                raw_path = object_path(lane, 'raw', graph['source_sha256'])
                checksum_ref, = [r for r in graph['object_refs'] if r['kind'] == 'checksum']
                checksum = object_path(lane, 'checksum', checksum_ref['sha256']).read_bytes()
                official_digest, official_name = checksum.decode('ascii').strip().split()
                member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))
                parsed = parse_kline_rows(member, archive, attempt_path=EVIDENCE / 'parse' / f'{period}.json')
                times = [r.event_ts for r in parsed.rows]
                entry.update(
                    zip_sha256=sha(raw_path.read_bytes()),
                    checksum_matches=sha(raw_path.read_bytes()) == official_digest,
                    member_sha256=sha(member),
                    parser_input_matches=sha(member) == graph['parser_input_sha256'],
                    source_rows=parsed.source_rows,
                    distinct_rows=parsed.distinct_rows,
                    duplicate_rows=parsed.duplicate_rows,
                    conflict_rows=parsed.conflict_rows,
                    first_event_utc=utc(min(times)),
                    last_event_utc=utc(max(times)),
                    commit=current['commit'],
                    quality_state=graph['quality_state'],
                )
            elif record['terminal_state'] == 'BLOCKED':
                acquired = json.loads(Path(record['acquirer_evidence_path']).read_bytes())
                raw_path = Path(acquired['raw_path'])
                official_digest = acquired['official_digest']
                member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))
                parsed = parse_kline_rows(member, archive, attempt_path=EVIDENCE / 'parse' / f'{period}.json')
                times = [r.event_ts for r in parsed.rows]
                entry.update(
                    zip_sha256=sha(raw_path.read_bytes()),
                    checksum_matches=sha(raw_path.read_bytes()) == official_digest,
                    member_sha256=sha(member),
                    source_rows=parsed.source_rows,
                    distinct_rows=parsed.distinct_rows,
                    duplicate_rows=parsed.duplicate_rows,
                    conflict_rows=parsed.conflict_rows,
                    first_event_utc=utc(min(times)),
                    last_event_utc=utc(max(times)),
                )

            results.append(entry)
            print(f'[{i}/{len(all_periods)}] {period} {record["terminal_state"]}', flush=True)
    finally:
        transport.close()

    counts = {}
    for r in results:
        counts[r['terminal_state']] = counts.get(r['terminal_state'], 0) + 1

    payload = {
        'period_count': len(all_periods),
        'counts': counts,
        'http_request_count': len(transport.requests),
        'http_rejected_count': len(transport.rejected),
        'results': results,
    }
    (EVIDENCE / 'inventory.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    print(f'INVENTORY_WRITTEN {counts}')


if __name__ == '__main__':
    main()
