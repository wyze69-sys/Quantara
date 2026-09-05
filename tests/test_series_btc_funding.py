"""S01-A offline BTC funding contracts; all payload values are synthetic."""

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from quantara import series_canonical as canonical
from quantara import series_parsing as parsing
from quantara.series_descriptor import SeriesArchive, SeriesDescriptorError, load_series_descriptor
from quantara.series_pipeline import run_series_pipeline

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTOR = ROOT / 'configs/series/binance-usdm-btcusdt-funding-settled-2020-2024.yaml'
T = 1577836800000


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('offline funding tests must not use the network')

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)


def member(records, header=parsing.FUNDING_HEADER):
    return (','.join(header) + '\n' + ''.join(
        ','.join(map(str, row)) + '\n' for row in records
    )).encode('ascii')


def parse(tmp_path, records, header=parsing.FUNDING_HEADER):
    archive = load_series_descriptor(DESCRIPTOR).archive_for('2020-01')
    return parsing.parse_scalar_rows(
        member(records, header), archive, attempt_path=tmp_path / 'parse.json',
    )


def test_closed_descriptor_inventory_and_boundary_urls():
    descriptor = load_series_descriptor(DESCRIPTOR)
    expected = tuple(f'{year}-{month:02d}' for year in range(2020, 2025)
                     for month in range(1, 13))
    assert descriptor.object_periods == expected
    assert len(expected) == 60
    symbol = descriptor.to_dict()['provider_symbol']
    for period in (expected[0], expected[-1]):
        archive = descriptor.archive_for(period)
        assert archive.member == f'{symbol}-fundingRate-{period}.csv'
        assert archive.archive_url == (
            'https://data.binance.vision/data/futures/um/monthly/fundingRate/'
            f'{symbol}/{symbol}-fundingRate-{period}.zip'
        )
        assert archive.checksum_url == archive.archive_url + '.CHECKSUM'


def test_funding_quoting_remains_forbidden(tmp_path):
    archive = load_series_descriptor(DESCRIPTOR).archive_for('2020-01')
    data = (','.join(parsing.FUNDING_HEADER) + f'\n{T},8,"-0.125"\n').encode('ascii')
    with pytest.raises(parsing.FundingParseError, match='quoting'):
        parsing.parse_scalar_rows(data, archive, attempt_path=tmp_path / 'parse.json')


def test_exact_millisecond_jitter_and_strict_eligibility_round_trip(tmp_path):
    timestamps = (T + 1, T + 28_800_000 - 1, T + 57_600_000 + 3)
    parsed = parse(tmp_path, [(ts, 8, '-0.125') for ts in timestamps])
    assert tuple(row.event_ts for row in parsed.rows) == timestamps
    rows = canonical.build_scalar_rows(parsed)
    path = tmp_path / 'canonical.parquet'
    canonical.write_scalar_parquet(rows, path)
    restored = canonical.read_scalar_rows(path)
    assert tuple(row.event_ts for row in restored) == timestamps
    assert tuple(row.settlement_or_snapshot_ts for row in restored) == timestamps
    assert tuple(row.eligibility_ts for row in restored) == tuple(ts + 1 for ts in timestamps)
    assert all(row.archive_publication_ts is None for row in restored)
    assert canonical.scalar_content_hash(restored) == canonical.scalar_content_hash(rows)
    # A clean-grid or non-strict temporal envelope is a meaningful negative control.
    for wrong in (replace(rows[0], event_ts=T), replace(rows[0], eligibility_ts=T + 1)):
        with pytest.raises(canonical.ScalarCanonicalError, match='eligibility mismatch'):
            canonical.validate_scalar_row(wrong)


@pytest.mark.parametrize('interval', ['1', '4', '8', '24', '0004', '9223372036854775807'])
def test_observed_interval_preserved_without_universal_cap(tmp_path, interval):
    parsed = parse(tmp_path, [(T, interval, '0')])
    assert parsed.rows[0].funding_interval_hours == interval
    rows = canonical.build_scalar_rows(parsed)
    canonical.write_scalar_parquet(rows, tmp_path / 'canonical.parquet')
    assert canonical.read_scalar_rows(tmp_path / 'canonical.parquet')[0].funding_interval_hours == (
        interval
    )


@pytest.mark.parametrize('interval', ['0', '-1', '4.5', 'abc', '', '9223372036854775808'])
def test_invalid_interval_is_blocked(tmp_path, interval):
    with pytest.raises(parsing.FundingParseError, match='positive integer'):
        parse(tmp_path, [(T, interval, '0')])
    evidence = json.loads((tmp_path / 'parse.json').read_text())
    assert evidence['status'] == 'BLOCKED'
    assert evidence['counts_complete'] is False


@pytest.mark.parametrize('header', [
    parsing.FUNDING_HEADER[:-1], parsing.FUNDING_HEADER[::-1],
    (*parsing.FUNDING_HEADER, 'extra'),
])
def test_exact_header_rejects_missing_reordered_extra_columns(tmp_path, header):
    with pytest.raises(parsing.FundingParseError, match='exact ordered family header'):
        parse(tmp_path, [(T, 8, '0')], header)
    assert json.loads((tmp_path / 'parse.json').read_text())['status'] == 'BLOCKED'


@pytest.mark.parametrize('numeric', ['-0.125', '1.25E-8', '-2.5e-9'])
def test_synthetic_exact_decimal_and_scientific_notation_round_trip(tmp_path, numeric):
    from decimal import Decimal

    parsed = parse(tmp_path, [(T, 4, numeric)])
    rows = canonical.build_scalar_rows(parsed)
    canonical.write_scalar_parquet(rows, tmp_path / 'canonical.parquet')
    actual = canonical.read_scalar_rows(tmp_path / 'canonical.parquet')[0].last_funding_rate
    assert type(actual) is Decimal
    assert actual == Decimal(numeric)


def test_identical_source_bytes_deduplicate_without_filling(tmp_path):
    parsed = parse(tmp_path, [(T, 8, '0'), (T, 8, '0')])
    assert (parsed.source_rows, parsed.distinct_rows, parsed.duplicate_rows) == (2, 1, 1)
    assert len(canonical.build_scalar_rows(parsed)) == 1
    assert parsed.duplicate_hashes == (hashlib.sha256(f'{T},8,0\n'.encode()).hexdigest(),)


@pytest.mark.parametrize('different', [(T, 4, '0'), (T, 8, '0.0')])
def test_nonidentical_duplicate_blocks_even_when_numeric_value_matches(tmp_path, different):
    with pytest.raises(parsing.FundingDuplicateConflict):
        parse(tmp_path, [(T, 8, '0'), different])
    assert json.loads((tmp_path / 'parse.json').read_text())['conflict_rows'] == 1


@pytest.mark.parametrize('timestamp', [T - 1, 1580515200000])
def test_outside_selected_month_rejected_before_payload(tmp_path, timestamp):
    with pytest.raises(parsing.FundingParseError, match='outside the selected archive period'):
        parse(tmp_path, [(timestamp, 8, 'not-a-number')])


def test_2025_selection_rejected_with_zero_acquisition(tmp_path):
    descriptor = load_series_descriptor(DESCRIPTOR)
    with pytest.raises(SeriesDescriptorError):
        descriptor.archive_for('2025-01')
    with pytest.raises(SeriesDescriptorError):
        SeriesArchive(descriptor.series_id, '2025-01')
    calls = []

    def forbidden(request):
        calls.append(str(request.url))
        pytest.fail('out-of-window selection must not acquire')

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period='2025-01', transport=httpx.MockTransport(forbidden),
    ) == 3
    assert calls == []
    assert not list(tmp_path.rglob('current.json'))
    assert not (tmp_path / 'datasets').exists()
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['error_type'] == 'SeriesDescriptorError'
    assert record['acquirer_evidence_path'] is None


def test_provider_checksum_corruption_prevents_parse_and_publication(tmp_path):
    archive = load_series_descriptor(DESCRIPTOR).archive_for('2020-01')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(archive.member, member([(T, 8, '0')]))
    payload = buffer.getvalue()
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        assert url in (archive.archive_url, archive.checksum_url)
        body = (f'{"0" * 64}  {archive.member[:-4]}.zip\n'.encode()
                if url == archive.checksum_url else payload)
        return httpx.Response(200, content=body)

    assert run_series_pipeline(
        DESCRIPTOR, tmp_path, period='2020-01', transport=httpx.MockTransport(handler),
        sleeper=lambda _: None,
    ) == 3
    assert calls
    record = json.loads(next((tmp_path / 'attempts').glob('*.json')).read_text())
    assert record['error_type'] == 'ChecksumMismatch'
    assert record['parse_attempt_path'] is None
    assert not list(tmp_path.rglob('current.json'))
    assert not list(tmp_path.rglob('COMMITTED'))
