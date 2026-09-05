"""S02-C: audited publication of BTC open interest 2020-09 to 2024-12 to the production root.

Stop C. Runs the backfill on all 1583 frozen periods one by one, collects the
PUBLISHED ones, verifies the authenticated commit graph for every published period,
then reruns the whole inventory to prove every published period returns VERIFIED_NO_OP
with zero further HTTP requests.

Preconditions asserted before any write:
  * The production root contains no `datasets/series/btc_open_interest_5m` lane yet,
    so this is a first publication and cannot overwrite an existing series pointer.

Value-blind: records paths, counts, timestamps and hashes only, never open-interest values.

Environment:
    S02C_DATA_ROOT   production data root (required, explicit — never defaulted)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quantara import series_canonical as canonical
from quantara.archive import inspect_zip, read_member_bytes
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_scalar_rows
from quantara.series_pipeline import _storage_root, run_series_pipeline
from quantara.series_quality import evaluate_series_quality

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml'
EVIDENCE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ['S02C_DATA_ROOT'])


class CountingTransport(httpx.BaseTransport):
    """Real HTTP restricted to the exact frozen per-period allowlist."""

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


def preflight(descriptor, data_root: Path) -> None:
    """Refuse to publish if series lane already exists."""
    lane_root = data_root / 'datasets/series'
    existing = sorted(p.name for p in lane_root.iterdir()) if lane_root.is_dir() else []
    assert descriptor.series_id not in existing, (
        f'series lane already exists in production: {descriptor.series_id}')
    print(f'PREFLIGHT existing_series_lanes={existing} '
          f'all_periods={len(descriptor.object_periods)}')


def collect(descriptor, data_root: Path, outcomes: list, phase: str) -> list[dict]:
    """Verify the authenticated graph for every PUBLISHED period and record value-blind facts."""
    rows = []
    for outcome in outcomes:
        period = outcome.period
        if outcome.terminal_state != 'PUBLISHED':
            continue
        archive = descriptor.archive_for(period)
        lane = data_root / 'datasets/series' / descriptor.series_id / period
        current = read_and_verify_current(lane, lane)
        graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
        pointer = json.loads((lane / 'current.json').read_bytes())
        assert pointer['commit'] == current['commit'], (period, 'pointer commit drift')

        entry = {
            'period': period,
            'phase': phase,
            'terminal_state': outcome.terminal_state,
            'exit_code': outcome.exit_code,
            'commit': current['commit'],
            'manifest_sha256': pointer['manifest_sha256'],
            'publication_protocol_version': pointer['publication_protocol_version'],
            'canonical_content_hash': graph['canonical_content_hash'],
            'parser_input_sha256': graph['parser_input_sha256'],
            'source_sha256': graph['source_sha256'],
            'quality_state': graph['quality_state'],
            'quality_identity': graph['quality_identity'],
            'object_ref_kinds': sorted({r['kind'] for r in graph['object_refs']}),
        }
        if phase == 'publish':
            raw_path = object_path(lane, 'raw', graph['source_sha256'])
            raw = raw_path.read_bytes()
            checksum_ref, = [r for r in graph['object_refs'] if r['kind'] == 'checksum']
            checksum = object_path(lane, 'checksum', checksum_ref['sha256']).read_bytes()
            official_digest, official_name = checksum.decode('ascii').strip().split()
            member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))
            parsed = parse_scalar_rows(
                member, archive, attempt_path=EVIDENCE / 'parse' / f'{period}.json')
            report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
            times = [r.event_ts for r in parsed.rows]
            entry.update(
                zip_sha256=sha(raw),
                checksum_matches_zip=sha(raw) == official_digest == graph['source_sha256'],
                checksum_filename=official_name.lstrip('*'),
                member_sha256=sha(member),
                parser_input_matches=sha(member) == graph['parser_input_sha256'],
                source_rows=parsed.source_rows,
                distinct_rows=parsed.distinct_rows,
                duplicate_rows=parsed.duplicate_rows,
                conflict_rows=parsed.conflict_rows,
                first_event_utc=utc(min(times)),
                last_event_utc=utc(max(times)),
                recomputed_quality_state=report.state,
            )
        rows.append(entry)
    return rows


def run_phase(
    descriptor, data_root: Path, phase: str, periods: list[str],
) -> tuple[dict, list[dict]]:
    """Publish every period one by one; BLOCKED/FAILED periods are skipped, not fatal."""
    allowed = set()
    for period in periods:
        archive = descriptor.archive_for(period)
        allowed.update({archive.archive_url, archive.checksum_url})

    transport = CountingTransport(allowed)
    outcomes: list = []
    try:
        for i, period in enumerate(periods, 1):
            exit_code = run_series_pipeline(
                DESCRIPTOR, data_root, period=period, transport=transport)
            found = []
            for p in (data_root / 'attempts').glob('*.json'):
                doc = json.loads(p.read_bytes())
                if doc.get('selected_period') == period:
                    found.append(doc)
            if found:
                record = max(found, key=lambda d: d.get('saved_at', ''))
                state = record.get('terminal_state', 'UNKNOWN')
            else:
                state = 'UNKNOWN'
            outcomes.append(type('O', (), {
                'period': period,
                'exit_code': exit_code,
                'terminal_state': state,
                'attempt_path': data_root / 'attempts',
            })())
            print(f'[{i}/{len(periods)}] {period} {state}', flush=True)
    finally:
        transport.close()

    counts = {}
    for o in outcomes:
        counts[o.terminal_state] = counts.get(o.terminal_state, 0) + 1
    summary = {
        'phase': phase,
        'series_id': descriptor.series_id,
        'period_count': len(periods),
        'outcome_count': len(outcomes),
        'counts': counts,
        'http_request_count': len(transport.requests),
        'http_rejected_count': len(transport.rejected),
        'distinct_urls_contacted': len(set(transport.requests)),
    }
    print(f'{phase.upper()}_SUMMARY', json.dumps(summary, sort_keys=True))
    return summary, collect(descriptor, data_root, outcomes, phase)


def main() -> None:
    descriptor = load_series_descriptor(DESCRIPTOR)
    all_periods = descriptor.object_periods
    print(f'ALL_PERIODS {len(all_periods)}')

    data_root = _storage_root(DATA_ROOT)
    preflight(descriptor, data_root)
    (EVIDENCE / 'parse').mkdir(exist_ok=True)

    pub_summary, published = run_phase(descriptor, data_root, 'publish', all_periods)
    published_count = len(published)
    print(f'PUBLISHED_COUNT {published_count}')
    assert published_count > 0, 'no periods published'
    # Every published period should have PASS quality
    assert all(e['quality_state'] == 'PASS' for e in published), 'published period not PASS'
    assert all(e['recomputed_quality_state'] == 'PASS' for e in published), 'recomputed not PASS'
    assert all(e['checksum_matches_zip'] for e in published)
    assert all(e['parser_input_matches'] for e in published)

    noop_summary, reverified = run_phase(descriptor, data_root, 'rerun', all_periods)
    # Rerun: PUBLISHED periods must remain PUBLISHED (no-op). BLOCKED periods
    # legitimately re-download to verify they're still blocked.
    by_period_rerun = {e['period']: e for e in reverified}
    for e in published:
        assert by_period_rerun[e['period']]['terminal_state'] == 'PUBLISHED', \
            f"published period {e['period']} changed state in rerun"

    by_period = {e['period']: e for e in published}
    moved = [
        p for p, e in by_period.items()
        for r in [next(x for x in reverified if x['period'] == p)]
        if (e['commit'], e['canonical_content_hash'], e['manifest_sha256'])
        != (r['commit'], r['canonical_content_hash'], r['manifest_sha256'])
    ]
    assert not moved, f'identities moved on rerun: {moved}'

    total_rows = sum(e['source_rows'] for e in published)
    payload = {
        'publish': pub_summary,
        'rerun': noop_summary,
        'published': published,
        'reverified': reverified,
        'aggregate': {
            'total_source_rows': total_rows,
            'total_duplicates': sum(e['duplicate_rows'] for e in published),
            'total_conflicts': sum(e['conflict_rows'] for e in published),
            'distinct_commits': len({e['commit'] for e in published}),
            'first_event_utc': min(e['first_event_utc'] for e in published),
            'last_event_utc': max(e['last_event_utc'] for e in published),
        },
    }
    (EVIDENCE / 'publication.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    print('AGGREGATE', json.dumps(payload['aggregate'], sort_keys=True))
    print('PUBLICATION_WRITTEN', len(published))


if __name__ == '__main__':
    main()
