"""S02-A real boundary artifacts only; evidence excludes all market values."""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from quantara import series_canonical as canonical
from quantara.archive import inspect_zip, read_member_bytes
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import load_series_descriptor
from quantara.series_parsing import parse_scalar_rows
from quantara.series_pipeline import _storage_root, run_series_pipeline
from quantara.series_quality import evaluate_series_quality, proposed_approval_payload

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml'
STEP = 300_000


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


def acquire(tmp_path, period):
    descriptor = load_series_descriptor(DESCRIPTOR)
    archive = descriptor.archive_for(period)
    data_root = _storage_root(tmp_path / 'data')
    transport = BoundaryTransport(archive)
    try:
        exit_code = run_series_pipeline(
            DESCRIPTOR, data_root, period=period, transport=transport,
        )
    finally:
        transport.close()
    assert set(transport.requests) == {archive.archive_url, archive.checksum_url}
    record = json.loads(next((data_root / 'attempts').glob('*.json')).read_bytes())
    return descriptor, archive, data_root, exit_code, record


def reparse(archive, data_root, descriptor, period, tmp_path, graph):
    lane = data_root / 'datasets/series' / descriptor.series_id / period
    raw_path = object_path(lane, 'raw', graph['source_sha256'])
    member = read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))
    parsed = parse_scalar_rows(member, archive, attempt_path=tmp_path / 'reparse.json')
    return member, parsed


def test_last_frozen_day_publishes_and_reruns_to_verified_no_op(tmp_path):
    """2024-12-31: clean 288-snapshot day, the only shape that may publish unattended."""
    period = '2024-12-31'
    descriptor, archive, data_root, exit_code, record = acquire(tmp_path, period)
    assert exit_code == 0, 'clean boundary day failed; inspect value-blind attempt evidence'
    assert record['terminal_state'] == 'PUBLISHED'
    assert record['selected_period'] == period

    lane = data_root / 'datasets/series' / descriptor.series_id / period
    current = read_and_verify_current(lane, lane)
    graph = verify_commit_graph(lane, lane / 'commits' / current['commit'])
    assert graph['quality_state'] == 'PASS'

    raw_path = object_path(lane, 'raw', graph['source_sha256'])
    raw = raw_path.read_bytes()
    checksum_ref, = [ref for ref in graph['object_refs'] if ref['kind'] == 'checksum']
    checksum = object_path(lane, 'checksum', checksum_ref['sha256']).read_bytes()
    official_digest, official_filename = checksum.decode('ascii').strip().split()
    assert official_filename.lstrip('*') == archive.member[:-4] + '.zip'
    assert sha(raw) == official_digest == graph['source_sha256']
    assert sha(checksum) == checksum_ref['sha256']

    member, parsed = reparse(archive, data_root, descriptor, period, tmp_path, graph)
    assert sha(member) == graph['parser_input_sha256']
    assert parsed.source_rows == parsed.distinct_rows == 288
    assert parsed.duplicate_rows == 0
    assert parsed.conflict_rows == 0
    assert parsed.source_ordered

    rows = canonical.build_scalar_rows(parsed)
    assert len(rows) == 288
    # Every snapshot sits exactly on the native 5-minute grid.
    assert all(row.event_ts % STEP == 0 for row in rows)
    # Conservative eligibility: one full snapshot interval, never +1 ms.
    assert all(row.eligibility_ts == row.event_ts + STEP for row in rows)
    assert all(row.timestamp_role == 'UNRESOLVED_CONSERVATIVE' for row in rows)
    assert all(row.interval_open_ts is None and row.interval_close_ts is None for row in rows)
    assert all(row.last_funding_rate is None for row in rows)

    report = evaluate_series_quality(parsed, rows)
    assert report.state == 'PASS'
    assert report.identity() == graph['quality_identity']

    # Rerun must be a verified no-op with no further network use.
    transport = BoundaryTransport(archive)
    try:
        assert run_series_pipeline(
            DESCRIPTOR, data_root, period=period, transport=transport,
        ) == 0
    finally:
        transport.close()
    assert transport.requests == [], 'a verified no-op must not re-download'
    states = sorted(
        json.loads(path.read_bytes())['terminal_state']
        for path in (data_root / 'attempts').glob('*.json')
    )
    assert states == ['PUBLISHED', 'VERIFIED_NO_OP']
    after = read_and_verify_current(lane, lane)
    assert after['commit'] == current['commit']


def test_first_frozen_day_is_doubled_and_blocks_without_approval(tmp_path):
    """2020-09-01: every row appears twice byte-identically, so quality is WARN."""
    period = '2020-09-01'
    descriptor, archive, data_root, exit_code, record = acquire(tmp_path, period)
    # A warning-bearing period is a deliberate stop, not a failure.
    assert exit_code == 2
    assert record['terminal_state'] == 'BLOCKED'
    assert record['quality_state'] == 'WARN'
    assert record['finding_ids'] == ['duplicate_exact_bytes']
    # A quality stop is not an error: no exception type is recorded.
    assert 'error_type' not in record
    # Nothing was published and no pointer exists.
    assert not list(data_root.rglob('current.json'))
    assert not list(data_root.rglob('COMMITTED'))

    # The staged parse evidence still proves the exact duplicate shape.
    parsed = parse_scalar_rows(
        _staged_member(record, archive), archive, attempt_path=tmp_path / 'reparse.json')
    assert parsed.source_rows == 576
    assert parsed.distinct_rows == 288
    assert parsed.duplicate_rows == 288
    assert parsed.conflict_rows == 0
    assert len(parsed.duplicate_hashes) == 288
    assert parsed.source_ordered

    rows = canonical.build_scalar_rows(parsed)
    assert len(rows) == 288
    assert all(row.event_ts % STEP == 0 for row in rows)

    report = evaluate_series_quality(parsed, rows)
    assert report.state == 'WARN'
    duplicate, = [f for f in report.findings if f.check_id == 'duplicate_exact_bytes']
    assert duplicate.outcome == 'warn' and duplicate.count == 288
    grid, = [f for f in report.findings if f.check_id == 'oi_snapshot_grid']
    boundary, = [f for f in report.findings if f.check_id == 'oi_daily_boundary']
    assert grid.outcome == 'pass', 'a doubled day is still fully on-grid'
    assert boundary.outcome == 'pass', 'all 288 slots are present'

    proposal = proposed_approval_payload(report)
    assert proposal['authorized'] is False
    assert proposal['approver'] == 'PLACEHOLDER'
    assert proposal['quality_identity_sha256'] == report.identity()


def _staged_member(record, archive):
    """Read the retained raw object from the blocked attempt's staging directory."""
    acquired = json.loads(Path(record['acquirer_evidence_path']).read_bytes())
    raw_path = Path(acquired['raw_path'])
    return read_member_bytes(raw_path, inspect_zip(raw_path, archive.member_pattern))


def test_short_day_warns_on_the_daily_boundary_only(tmp_path):
    """2021-10-01 carries 287 on-grid snapshots: boundary warning, no grid failure."""
    period = '2021-10-01'
    descriptor, archive, data_root, exit_code, record = acquire(tmp_path, period)
    assert exit_code == 2
    assert record['terminal_state'] == 'BLOCKED'
    assert record['quality_state'] == 'WARN'
    assert record['finding_ids'] == ['oi_daily_boundary']
    assert not list(data_root.rglob('current.json'))

    parsed = parse_scalar_rows(
        _staged_member(record, archive), archive, attempt_path=tmp_path / 'reparse.json')
    assert parsed.duplicate_rows == 0
    assert parsed.conflict_rows == 0
    assert parsed.distinct_rows == 287

    rows = canonical.build_scalar_rows(parsed)
    assert all(row.event_ts % STEP == 0 for row in rows)
    report = evaluate_series_quality(parsed, rows)
    grid, = [f for f in report.findings if f.check_id == 'oi_snapshot_grid']
    boundary, = [f for f in report.findings if f.check_id == 'oi_daily_boundary']
    assert grid.outcome == 'pass'
    assert boundary.outcome == 'warn'
    assert boundary.evidence['expected_slots'] == 288
    assert boundary.evidence['present_slots'] == 287
    assert boundary.evidence['gap_count'] == 1
    # The missing slot is enumerated exactly, never filled.
    assert len(boundary.evidence['gap_interval_open_ts']) == 1
    assert boundary.evidence['gap_interval_open_ts'][0] % STEP == 0
