"""S01-A real boundary artifacts only; evidence excludes all market values."""

import hashlib
import json
import os
from pathlib import Path

import httpx
import pytest

from quantara import series_canonical as canonical
from quantara.archive import inspect_zip, read_member_bytes
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_scalar_rows
from quantara.series_pipeline import _storage_root, run_series_pipeline
from quantara.series_quality import evaluate_series_quality

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-funding-settled-2020-2024.yaml'


class BoundaryTransport(httpx.BaseTransport):
    """Real HTTP transport; fail closed before any unapproved URL is contacted."""

    def __init__(self, archive):
        self.allowed = {archive.archive_url, archive.checksum_url}
        self.requests = []
        self.real = httpx.HTTPTransport()

    def handle_request(self, request):
        url = str(request.url)
        assert url in self.allowed, 'boundary acquisition URL outside exact allowlist'
        self.requests.append(url)
        response = self.real.handle_request(request)
        assert response.status_code == 200, 'unexpected source status; no challenge bypass'
        assert 'text/html' not in response.headers.get('content-type', '').lower()
        return response

    def close(self):
        self.real.close()


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('period', ['2020-01', '2024-12'])
def test_boundary_archive_acquire_parse_publish_and_verified_no_op(tmp_path, period):
    descriptor = load_series_descriptor(DESCRIPTOR)
    archive = descriptor.archive_for(period)
    data_root = _storage_root(tmp_path / 'data')
    lane = data_root / 'datasets/series' / descriptor.series_id / period
    transport = BoundaryTransport(archive)
    try:
        exit_code = run_series_pipeline(
            DESCRIPTOR, data_root, period=period, transport=transport,
        )
    finally:
        transport.close()
    assert exit_code == 0, 'frozen live pipeline failed; inspect value-blind attempt evidence'
    assert set(transport.requests) == {archive.archive_url, archive.checksum_url}
    record = json.loads(next((data_root / 'attempts').glob('*.json')).read_bytes())
    assert record['terminal_state'] == 'PUBLISHED'
    assert record['selected_period'] == period
    acquired = json.loads(Path(record['acquirer_evidence_path']).read_bytes())
    current = read_and_verify_current(lane, lane)
    graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
    assert graph['quality_state'] == current['quality_state'] == 'PASS'
    raw_path = object_path(lane, 'raw', graph['source_sha256'])
    raw = raw_path.read_bytes()
    checksum_ref, = [ref for ref in graph['object_refs'] if ref['kind'] == 'checksum']
    checksum = object_path(lane, 'checksum', checksum_ref['sha256']).read_bytes()
    # The provider sidecar authenticates the ZIP, not a nonexistent descriptor member pin.
    official_digest, official_filename = checksum.decode('ascii').strip().split()
    assert official_filename.lstrip('*') == archive.member[:-4] + '.zip'
    assert sha(raw) == official_digest == graph['source_sha256']
    assert sha(checksum) == checksum_ref['sha256']
    member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))
    assert sha(member) == graph['parser_input_sha256'] == record['parser_input_sha256']
    assert acquired['integrity_basis'] == 'binance_adjacent_checksum'
    assert acquired['official_digest'] == official_digest
    assert acquired['member_sha256'] == sha(member)
    parsed = parse_scalar_rows(member, archive, attempt_path=data_root / 'independent-parse.json')
    assert parsed.source_sha256 == sha(member)
    assert (parsed.source_rows, parsed.distinct_rows, parsed.duplicate_rows,
            parsed.conflict_rows) == (93, 93, 0, 0)
    assert parsed.source_ordered
    rows = canonical.build_scalar_rows(parsed)
    parquet = object_path(lane, 'normalized', graph['artifacts']['canonical_parquet'])
    canonical.reconcile_scalar_parquet(rows, parquet)
    restored = canonical.read_scalar_rows(parquet)
    assert canonical.scalar_content_hash(restored) == graph['canonical_content_hash']
    # Boolean comparisons prevent a failing assertion from disclosing source values.
    assert all(a.last_funding_rate == b.last_funding_rate
               for a, b in zip(parsed.rows, restored, strict=True)), 'exact Decimal mismatch'
    assert all(a.event_ts == b.event_ts == b.settlement_or_snapshot_ts
               and b.eligibility_ts == a.event_ts + 1
               and a.funding_interval_hours == b.funding_interval_hours
               for a, b in zip(parsed.rows, restored, strict=True))
    quality = evaluate_series_quality(parsed, rows)
    assert quality.state == 'PASS'
    assert quality.identity() == graph['quality_identity']
    parse_record = json.loads(Path(record['parse_attempt_path']).read_bytes())
    assert parse_record['status'] == 'PARSED' and parse_record['counts_complete']
    assert parse_record['source_rows'] == len(rows)
    pointer_before = (lane / 'current.json').read_bytes()
    commits_before = sorted(p.name for p in (lane / 'commits').iterdir())
    no_op_calls = []

    def forbidden(request):
        no_op_calls.append(str(request.url))
        pytest.fail('verified no-op must not acquire')

    assert run_series_pipeline(
        DESCRIPTOR, data_root, period=period, transport=httpx.MockTransport(forbidden),
    ) == 0
    assert no_op_calls == []
    assert (lane / 'current.json').read_bytes() == pointer_before
    assert sorted(p.name for p in (lane / 'commits').iterdir()) == commits_before
    attempts = [json.loads(p.read_bytes()) for p in (data_root / 'attempts').glob('*.json')]
    assert sorted(a['terminal_state'] for a in attempts) == ['PUBLISHED', 'VERIFIED_NO_OP']
    timestamps = [r.event_ts for r in parsed.rows]
    # Report distance from the observed row's interval grid, never alter the timestamp.
    jitter = [{'event_ts': r.event_ts,
               'offset_ms': r.event_ts % (int(r.funding_interval_hours) * 3_600_000)}
              for r in parsed.rows if r.event_ts % (int(r.funding_interval_hours) * 3_600_000)]
    facts = {
        'period': period, 'series_id': descriptor.series_id, 'requests': transport.requests,
        'data_root': str(data_root), 'zip_sha256': sha(raw), 'official_digest': official_digest,
        'member_sha256': sha(member), 'checksum_sha256': sha(checksum),
        'source_rows': parsed.source_rows, 'distinct_rows': parsed.distinct_rows,
        'duplicate_rows': parsed.duplicate_rows, 'conflict_rows': parsed.conflict_rows,
        'first_event_ts': min(timestamps), 'last_event_ts': max(timestamps),
        'observed_interval_hours': sorted({r.funding_interval_hours for r in parsed.rows}),
        'jitter_count': len(jitter), 'jitter_examples': jitter[:5],
        'quality_state': quality.state, 'quality_identity': quality.identity(),
        'canonical_content_hash': graph['canonical_content_hash'],
        'pipeline_attempt_path': str(next((data_root / 'attempts').glob('*.json'))),
        'acquisition_evidence_path': record['acquirer_evidence_path'],
        'publication_verified': True, 'exact_reconciliation': True,
        'verified_no_op': True, 'no_op_acquisition_count': len(no_op_calls),
    }
    evidence_dir = os.environ.get('QUANTARA_S01A_EVIDENCE_DIR')
    if evidence_dir:
        destination = Path(evidence_dir).resolve()
        assert destination.is_relative_to(ROOT / 'temp/protocol_v1_audits/btc_settled_funding')
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f'boundary-facts-{period}.json'
        with path.open('x', encoding='utf-8') as output:
            json.dump(facts, output, indent=2, sort_keys=True)
    print('S01A_VALUE_BLIND ' + json.dumps(facts, sort_keys=True))
