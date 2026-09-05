"""S02-A offline BTC open-interest contracts; all payload values are synthetic.

The real archive shape that motivates these tests was established by value-blind probes
against data.binance.vision:

  * 2020-09-01 through 2021-05-20 repeat every row twice, byte-identical
    (576 source rows for 288 distinct create_time values).
  * 2021-05-21 onward is single-rowed; the transition is a single flip, not an
    oscillation.
  * Some days are short (for example 2021-10-01 carries 287 snapshots), which is a
    daily-boundary warning rather than a grid failure.

The consequence the pipeline must enforce: a byte-identical repeat is a *warning*, a
same-key non-identical row is a *hard* conflict, and a warning-bearing period must not
publish without an approval record.
"""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from quantara import series_canonical as canonical
from quantara import series_parsing as parsing
from quantara.series_descriptor import SeriesArchive, SeriesDescriptorError, load_series_descriptor
from quantara.series_pipeline import run_series_pipeline
from quantara.series_quality import evaluate_series_quality, proposed_approval_payload

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml'
PERIOD = '2020-09-01'
SYMBOL = 'BTCUSDT'
STEP = 300_000
# 2020-09-01T00:00:00Z, the first frozen snapshot slot.
T0 = int(datetime(2020, 9, 1, tzinfo=UTC).timestamp() * 1000)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline open-interest tests must not use the network')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)


def stamp(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, UTC).strftime('%Y-%m-%d %H:%M:%S')


def row(ts_ms, oi='1.5', oi_value='2.25', symbol=SYMBOL,
        ratios=('0.5', '1.5', '0.75', '1.25')):
    return (stamp(ts_ms), symbol, oi, oi_value, *ratios)


def member(records, header=parsing.OI_HEADER):
    return (','.join(header) + '\n' + ''.join(
        ','.join(map(str, record)) + '\n' for record in records
    )).encode('ascii')


def parse(tmp_path, records, header=parsing.OI_HEADER, period=PERIOD, name='parse.json'):
    archive = load_series_descriptor(DESCRIPTOR).archive_for(period)
    return parsing.parse_scalar_rows(
        member(records, header), archive, attempt_path=tmp_path / name,
    )


def test_closed_daily_inventory_and_boundary_urls():
    descriptor = load_series_descriptor(DESCRIPTOR)
    periods = descriptor.object_periods
    # 2020-09-01 through 2024-12-31 inclusive.
    assert periods[0] == '2020-09-01' and periods[-1] == '2024-12-31'
    assert len(periods) == 1583
    assert len(set(periods)) == len(periods)
    assert list(periods) == sorted(periods)
    document = descriptor.to_dict()
    assert document['object_cadence'] == 'daily'
    assert document['observation_cadence'] == '5m'
    assert document['canonical_value'] == 'sum_open_interest'
    # v1.1 refuses to claim the provider stamp is a documented interval start.
    assert document['timestamp_role'] == 'UNRESOLVED_CONSERVATIVE'
    assert document['csv_header_policy'] == 'present'
    for period in (periods[0], periods[-1]):
        archive = descriptor.archive_for(period)
        assert archive.member == f'{SYMBOL}-metrics-{period}.csv'
        assert archive.archive_url == (
            'https://data.binance.vision/data/futures/um/daily/metrics/'
            f'{SYMBOL}/{SYMBOL}-metrics-{period}.zip'
        )
        assert archive.checksum_url == archive.archive_url + '.CHECKSUM'


def test_period_before_frozen_start_is_not_selectable():
    descriptor = load_series_descriptor(DESCRIPTOR)
    assert '2020-08-31' not in descriptor.object_periods
    with pytest.raises(SeriesDescriptorError):
        descriptor.archive_for('2020-08-31')


@pytest.mark.parametrize('text', [
    str(T0),                 # epoch milliseconds, the funding format
    '2020-09-01T00:00:00',   # ISO 8601 with a T separator
    '2020-09-01 00:00',      # missing seconds
    '2020-9-1 00:00:00',     # unpadded fields
    '2020-09-01 00:00:00Z',  # trailing zone designator
    '2020-02-30 00:00:00',   # impossible calendar date
])
def test_create_time_grammar_is_exact(tmp_path, text):
    records = [(text, SYMBOL, '1.5', '2.25', '0.5', '1.5', '0.75', '1.25')]
    with pytest.raises(parsing.OpenInterestParseError):
        parse(tmp_path, records)
    evidence = json.loads((tmp_path / 'parse.json').read_text())
    assert evidence['status'] == 'BLOCKED'
    assert evidence['counts_complete'] is False


def test_create_time_is_interpreted_as_utc(tmp_path):
    parsed = parse(tmp_path, [row(T0), row(T0 + STEP)])
    assert tuple(r.event_ts for r in parsed.rows) == (T0, T0 + STEP)


@pytest.mark.parametrize('header', [
    parsing.OI_HEADER[:-1],
    parsing.OI_HEADER[::-1],
    (*parsing.OI_HEADER, 'extra'),
    ('create_time', 'symbol', 'sum_open_interest_value', 'sum_open_interest',
     *parsing.OI_HEADER[4:]),
])
def test_exact_ordered_header_required(tmp_path, header):
    with pytest.raises(parsing.OpenInterestParseError, match='exact ordered family header'):
        parse(tmp_path, [row(T0)], header)
    assert json.loads((tmp_path / 'parse.json').read_text())['status'] == 'BLOCKED'


def test_symbol_column_must_match_frozen_descriptor(tmp_path):
    with pytest.raises(parsing.OpenInterestParseError, match='OI symbol'):
        parse(tmp_path, [row(T0, symbol='ETHUSDT')])


def test_byte_identical_repeat_deduplicates_and_is_hashed(tmp_path):
    """The real pre-2021-05-21 shape: every row present exactly twice."""
    records = [row(T0), row(T0), row(T0 + STEP), row(T0 + STEP)]
    parsed = parse(tmp_path, records)
    assert (parsed.source_rows, parsed.distinct_rows, parsed.duplicate_rows) == (4, 2, 2)
    assert parsed.conflict_rows == 0
    assert len(canonical.build_scalar_rows(parsed)) == 2
    raw = ','.join(map(str, row(T0))).encode() + b'\n'
    assert hashlib.sha256(raw).hexdigest() in parsed.duplicate_hashes
    assert len(parsed.duplicate_hashes) == parsed.duplicate_rows


@pytest.mark.parametrize('different', [
    row(T0, oi='1.50'),        # same numeric value, different bytes
    row(T0, oi='1.6'),
    row(T0, oi_value='2.250'),
    row(T0, ratios=('0.5', '1.5', '0.75', '1.26')),
])
def test_same_timestamp_with_different_bytes_is_a_hard_conflict(tmp_path, different):
    with pytest.raises(parsing.OpenInterestDuplicateConflict):
        parse(tmp_path, [row(T0), different])
    assert json.loads((tmp_path / 'parse.json').read_text())['conflict_rows'] == 1


def test_conservative_eligibility_delay_is_one_snapshot_interval(tmp_path):
    parsed = parse(tmp_path, [row(T0), row(T0 + STEP)])
    rows = canonical.build_scalar_rows(parsed)
    assert all(r.eligibility_ts == r.event_ts + STEP for r in rows)
    assert all(r.timestamp_role == 'UNRESOLVED_CONSERVATIVE' for r in rows)
    # The snapshot stamp is never relabelled as an interval open or close.
    assert all(r.interval_open_ts is None and r.interval_close_ts is None for r in rows)
    assert all(r.settlement_or_snapshot_ts == r.event_ts for r in rows)
    assert all(r.funding_interval_hours is None for r in rows)
    assert all(r.last_funding_rate is None for r in rows)


def test_eligibility_arithmetic_has_a_negative_control(tmp_path):
    from dataclasses import replace

    rows = canonical.build_scalar_rows(parse(tmp_path, [row(T0)]))
    for wrong in (replace(rows[0], eligibility_ts=rows[0].event_ts + 1),
                  replace(rows[0], eligibility_ts=rows[0].event_ts),
                  replace(rows[0], settlement_or_snapshot_ts=rows[0].event_ts + 1)):
        with pytest.raises(canonical.ScalarCanonicalError, match='eligibility mismatch'):
            canonical.validate_scalar_row(wrong)


@pytest.mark.parametrize('oi', ['0', '1.5', '12345.678901234567890123', '1E-18'])
def test_exact_decimal_open_interest_round_trip(tmp_path, oi):
    parsed = parse(tmp_path, [row(T0, oi=oi)])
    assert parsed.rows[0].sum_open_interest == Decimal(oi)
    rows = canonical.build_scalar_rows(parsed)
    path = tmp_path / 'canonical.parquet'
    canonical.write_scalar_parquet(rows, path)
    restored = canonical.read_scalar_rows(path)
    assert type(restored[0].sum_open_interest) is Decimal
    assert restored[0].sum_open_interest == Decimal(oi)
    # The notional value is diagnostic and stored as an exact 18dp string.
    assert restored[0].sum_open_interest_value == '2.250000000000000000'
    assert canonical.scalar_content_hash(restored) == canonical.scalar_content_hash(rows)


@pytest.mark.parametrize('bad', ['-1', '-0.000000000000000001', 'abc', '', 'nan', 'Infinity'])
def test_invalid_or_negative_open_interest_is_blocked(tmp_path, bad):
    with pytest.raises((parsing.OpenInterestParseError, canonical.ScalarCanonicalError)):
        canonical.build_scalar_rows(parse(tmp_path, [row(T0, oi=bad)]))


def test_incidental_ratio_columns_are_validated_but_never_canonical(tmp_path):
    parsed = parse(tmp_path, [row(T0, ratios=('0.5', '1.5', '0.75', '1.25'))])
    rows = canonical.build_scalar_rows(parsed)
    assert len(rows) == 1
    # Ratios exist in the immutable raw object but are not canonical columns.
    names = {name for name, _type, _null in canonical.SCALAR_COLUMNS}
    assert not names & {
        'count_toptrader_long_short_ratio', 'sum_toptrader_long_short_ratio',
        'count_long_short_ratio', 'sum_taker_long_short_vol_ratio',
    }
    with pytest.raises(parsing.OpenInterestParseError):
        parse(tmp_path, [row(T0, ratios=('0.5', '1.5', '0.75', 'abc'))], name='bad.json')


@pytest.mark.parametrize('offset', [-1, 86_400_000])
def test_timestamp_outside_selected_day_rejected_before_payload(tmp_path, offset):
    records = [(stamp(T0 + offset), SYMBOL, 'not-a-number', 'x', '', '', '', '')]
    with pytest.raises(parsing.OpenInterestParseError,
                       match='outside the selected archive period'):
        parse(tmp_path, records)


def test_off_grid_snapshot_is_a_hard_grid_failure(tmp_path):
    """A stamp inside the day but off the 5-minute grid must fail hard, not warn."""
    parsed = parse(tmp_path, [row(T0), row(T0 + 60_000)])
    report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
    grid, = [f for f in report.findings if f.check_id == 'oi_snapshot_grid']
    assert grid.outcome == 'fail' and grid.severity == 'hard' and grid.count == 1
    assert report.state == 'FAIL'


def test_short_day_is_a_boundary_warning_not_a_grid_failure(tmp_path):
    """The real 2021-10-01 shape: fewer than 288 snapshots, all on-grid."""
    parsed = parse(tmp_path, [row(T0 + index * STEP) for index in range(287)])
    report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
    grid, = [f for f in report.findings if f.check_id == 'oi_snapshot_grid']
    boundary, = [f for f in report.findings if f.check_id == 'oi_daily_boundary']
    assert grid.outcome == 'pass'
    assert boundary.outcome == 'warn' and boundary.severity == 'warning'
    assert boundary.count == 1
    assert boundary.evidence['expected_slots'] == 288
    assert boundary.evidence['present_slots'] == 287
    assert report.state == 'WARN'


def test_full_clean_day_passes_with_no_findings(tmp_path):
    parsed = parse(tmp_path, [row(T0 + index * STEP) for index in range(288)])
    report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
    assert report.state == 'PASS'
    assert [f.check_id for f in report.findings if f.outcome != 'pass'] == []


def test_warning_bearing_period_proposes_but_never_authorizes(tmp_path):
    """A doubled day warns; the proposal carries no approval authority."""
    parsed = parse(tmp_path, [row(T0), row(T0)] + [
        row(T0 + index * STEP) for index in range(1, 288)])
    report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
    assert report.state == 'WARN'
    duplicate, = [f for f in report.findings if f.check_id == 'duplicate_exact_bytes']
    assert duplicate.outcome == 'warn' and duplicate.count == 1
    proposal = proposed_approval_payload(report)
    assert proposal['authorized'] is False
    assert proposal['approver'] == 'PLACEHOLDER'
    assert proposal['quality_identity_sha256'] == report.identity()


def test_same_key_conflict_can_never_be_proposed_for_approval(tmp_path):
    from quantara.series_quality import SeriesQualityError

    parsed = parse(tmp_path, [row(T0)])
    report = evaluate_series_quality(parsed, canonical.build_scalar_rows(parsed))
    tampered = type(report)(report.series_id, report.source_sha256, tuple(
        type(f)('conflict_same_key', 'fail', 'hard', 1, {'conflict_rows': 1})
        if f.check_id == 'conflict_same_key' else f for f in report.findings))
    assert tampered.state == 'FAIL'
    with pytest.raises(SeriesQualityError):
        proposed_approval_payload(tampered)


def test_2025_selection_rejected_with_zero_acquisition(tmp_path):
    descriptor = load_series_descriptor(DESCRIPTOR)
    with pytest.raises(SeriesDescriptorError):
        descriptor.archive_for('2025-01-01')
    with pytest.raises(SeriesDescriptorError):
        SeriesArchive(descriptor.series_id, '2025-01-01')
    calls = []

    def forbidden(request):
        calls.append(str(request.url))
        pytest.fail('out-of-window selection must not acquire')

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period='2025-01-01',
        transport=httpx.MockTransport(forbidden),
    ) == 3
    assert calls == []
    assert not list(tmp_path.rglob('current.json'))
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['error_type'] == 'SeriesDescriptorError'
    assert record['acquirer_evidence_path'] is None


def zip_bytes(archive, records, header=parsing.OI_HEADER):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(archive.member, member(records, header))
    return buffer.getvalue()


def test_provider_checksum_corruption_prevents_parse_and_publication(tmp_path):
    archive = load_series_descriptor(DESCRIPTOR).archive_for(PERIOD)
    payload = zip_bytes(archive, [row(T0)])

    def handler(request):
        url = str(request.url)
        assert url in (archive.archive_url, archive.checksum_url)
        body = (f'{"0" * 64}  {archive.member[:-4]}.zip\n'.encode()
                if url == archive.checksum_url else payload)
        return httpx.Response(200, content=body)

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period=PERIOD, transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) == 3
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['error_type'] == 'ChecksumMismatch'
    assert record['parse_attempt_path'] is None
    assert not list(tmp_path.rglob('current.json'))
    assert not list(tmp_path.rglob('COMMITTED'))


def test_warning_bearing_day_blocks_publication_without_approval(tmp_path):
    """The S02 headline: a doubled day is WARN, so the pipeline must not publish it."""
    archive = load_series_descriptor(DESCRIPTOR).archive_for(PERIOD)
    doubled = []
    for index in range(288):
        record = row(T0 + index * STEP)
        doubled += [record, record]
    payload = zip_bytes(archive, doubled)
    digest = hashlib.sha256(payload).hexdigest()

    def handler(request):
        url = str(request.url)
        body = (f'{digest}  {archive.member[:-4]}.zip\n'.encode()
                if url == archive.checksum_url else payload)
        return httpx.Response(200, content=body)

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period=PERIOD, transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) == 2
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['terminal_state'] == 'BLOCKED'
    assert record['quality_state'] == 'WARN'
    assert record['finding_ids'] == ['duplicate_exact_bytes']
    # Nothing was published and no pointer was written.
    assert not list(tmp_path.rglob('current.json'))
    assert not list(tmp_path.rglob('COMMITTED'))


def test_clean_day_publishes_and_reruns_to_verified_no_op(tmp_path):
    archive = load_series_descriptor(DESCRIPTOR).archive_for(PERIOD)
    payload = zip_bytes(archive, [row(T0 + index * STEP) for index in range(288)])
    digest = hashlib.sha256(payload).hexdigest()
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        body = (f'{digest}  {archive.member[:-4]}.zip\n'.encode()
                if url == archive.checksum_url else payload)
        return httpx.Response(200, content=body)

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period=PERIOD, transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) == 0
    first = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert first['terminal_state'] == 'PUBLISHED'
    assert first['quality_state'] == 'PASS'
    contacted = len(calls)

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period=PERIOD, transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) == 0
    states = sorted(
        json.loads(path.read_text())['terminal_state']
        for path in (tmp_path / 'attempts').glob('*.json')
    )
    assert states == ['PUBLISHED', 'VERIFIED_NO_OP']
    assert len(calls) == contacted, 'a verified no-op must not re-download'
