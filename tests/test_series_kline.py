"""D04 synthetic contracts: no network, real archives, or sealed observations."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal, Inexact, Rounded, Subnormal, localcontext

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from quantara import hashing
from quantara import series_canonical as c
from quantara import series_parsing as p
from quantara.jcs import canonicalize
from quantara.series_descriptor import SERIES_REGISTRY, SeriesArchive

T = 1577836800000
HEADER = ('open_time,open,high,low,close,volume,close_time,quote_volume,count,'
          'taker_buy_volume,taker_buy_quote_volume,ignore')
SPOT = 'binance_btc_spot_ohlcv_1m'
KRAKEN = 'kraken_xbtusd_spot_ohlcv_1h'
SERIES = tuple(s for s, spec in SERIES_REGISTRY.items()
               if spec.canonical_value in ('ohlcv', 'ohlcvt'))
DERIVED = tuple(s for s in SERIES if 'price' in s or 'premium' in s)


def fields(t=T, *, kraken=False, price='1'):
    if kraken:
        return [str(t // 1000), price, price, price, price, '0', '2']
    return [str(t), price, price, price, price, '0', str(t + 59999),
            '0', '2', '0', '0', '0']


def parse(tmp_path, rows=None, *, series=SPOT, period=None, raw=None):
    archive = SeriesArchive(series, period or ('2020-2024' if series == KRAKEN else '2020-01'))
    if raw is None:
        rows = [fields(kraken=series == KRAKEN)] if rows is None else rows
        text = HEADER + '\n' if archive.csv_header == 'present' else ''
        raw = (text + ''.join(','.join(row) + '\n' for row in rows)).encode()
    attempt = tmp_path / f'attempt-{len(list(tmp_path.glob("attempt-*")))}.json'
    return p.parse_kline_rows(raw, archive, attempt_path=attempt)


@pytest.mark.parametrize('series', SERIES)
def test_all_frozen_families(tmp_path, series):
    result = parse(tmp_path, series=series)
    row, = c.build_kline_rows(result)
    step = 3600000 if series == KRAKEN else 60000
    assert row.event_ts == row.interval_open_ts == T
    assert row.interval_close_ts == T + step - 1
    assert row.eligibility_ts == T + step
    assert row.quality_flags is None
    assert row.settlement_or_snapshot_ts is None
    assert row.source_sha256 == result.source_sha256
    assert row.trade_count == (None if series in DERIVED else 2)
    assert row.source_count == 2
    assert row.volume_semantics == ('structural_zero' if series in DERIVED else 'traded')


@pytest.mark.parametrize('series,period,t', [
    ('btc_mark_price_1m', '2022-12', 1669852800000),
    ('ethusdt_perp_ohlcv_1m', '2022-01', 1640995200000),
])
def test_present_header(tmp_path, series, period, t):
    assert parse(tmp_path, [fields(t)], series=series, period=period).rows[0].event_ts == t


@pytest.mark.parametrize('mutation', [
    'missing', 'reordered', 'renamed', 'short', 'extra', 'quoted',
])
def test_bad_declared_present_header(tmp_path, mutation):
    header = HEADER.split(',')
    if mutation == 'reordered':
        header[1], header[2] = header[2], header[1]
    elif mutation == 'renamed':
        header[1] = 'OPEN'
    elif mutation == 'short':
        header.pop()
    elif mutation == 'extra':
        header.append('extra')
    elif mutation == 'quoted':
        header[1] = '"open"'
    raw = (('' if mutation == 'missing' else ','.join(header) + '\n')
           + ','.join(fields(1669852800000)) + '\n').encode()
    with pytest.raises(p.KlineParseError):
        parse(tmp_path, series='btc_mark_price_1m', period='2022-12', raw=raw)


@pytest.mark.parametrize('series', [SPOT, KRAKEN])
@pytest.mark.parametrize('mutation', ['header', 'short', 'extra', 'quoted', 'bom', 'blank',
                                    'cr', 'outside', 'unaligned', 'seconds_width'])
def test_bad_physical_records(tmp_path, series, mutation):
    row = fields(kraken=series == KRAKEN)
    if mutation == 'short':
        row.pop()
    elif mutation == 'extra':
        row.append('0')
    elif mutation == 'quoted':
        row[1] = '"1"'
    elif mutation == 'cr':
        row[1] = '1\r'
    elif mutation == 'outside':
        row[0] = '1546300800' if series == KRAKEN else '1580515200000'
    elif mutation == 'unaligned':
        row[0] = str(int(row[0]) + 1)
    elif mutation == 'seconds_width':
        row[0] += '0'
    raw = (','.join(row) + '\n').encode()
    if mutation == 'header':
        raw = HEADER.encode() + b'\n' + raw
    elif mutation == 'bom':
        raw = b'\xef\xbb\xbf' + raw
    elif mutation == 'blank':
        raw += b'\n'
    error = p.OhlcvtParseError if series == KRAKEN else p.KlineParseError
    with pytest.raises(error):
        parse(tmp_path, series=series, raw=raw)
    evidence = json.loads(next(tmp_path.glob('attempt-*')).read_text())
    assert evidence['status'] == 'BLOCKED'
    assert evidence['counts_complete'] is False


def test_bad_close_time(tmp_path):
    row = fields()
    row[6] = str(T + 60000)
    with pytest.raises(p.KlineParseError):
        parse(tmp_path, [row])


@pytest.mark.parametrize('series', [SPOT, KRAKEN])
@pytest.mark.parametrize('ending', [b'\n', b'\r\n'])
def test_duplicates_order_and_line_endings(tmp_path, series, ending):
    step = 3600000 if series == KRAKEN else 60000
    a = ','.join(fields(kraken=series == KRAKEN)).encode() + ending
    b = ','.join(fields(T + step, kraken=series == KRAKEN)).encode() + ending
    result = parse(tmp_path, series=series, raw=b + a + a)
    assert [r.event_ts for r in result.rows] == [T, T + step]
    assert (result.source_rows, result.distinct_rows, result.duplicate_rows) == (3, 2, 1)
    assert not result.source_ordered
    evidence = json.loads(next(tmp_path.glob('attempt-*')).read_text())
    assert evidence['duplicate_hashes'] == [hashlib.sha256(a).hexdigest()]
    assert result.source_sha256 == hashlib.sha256(b + a + a).hexdigest()


@pytest.mark.parametrize('change', ['decimal', 'ignore', 'ending'])
def test_any_byte_conflict(tmp_path, change):
    a = ','.join(fields()) + '\n'
    b = a.replace(',1,', ',1.0,', 1) if change == 'decimal' else a
    if change == 'ignore':
        b = a[:-2] + 'other\n'
    elif change == 'ending':
        b = a[:-1] + '\r\n'
    with pytest.raises(p.KlineDuplicateConflict):
        parse(tmp_path, raw=(a + b).encode())


@pytest.mark.parametrize('series', SERIES)
def test_signedness(tmp_path, series):
    rows = [fields(price='-0.0001', kraken=series == KRAKEN)]
    if series in DERIVED:
        row, = c.build_kline_rows(parse(tmp_path, rows, series=series))
        assert row.low == Decimal('-0.0001')
    else:
        with pytest.raises(p.KlineParseError):
            parse(tmp_path, rows, series=series)


@pytest.mark.parametrize('column', [5, 7, 9, 10])
@pytest.mark.parametrize('series', DERIVED)
def test_nonzero_structural_volume_blocks(tmp_path, column, series):
    row = fields()
    row[column] = '0.1'
    with pytest.raises(p.KlineParseError):
        parse(tmp_path, [row], series=series)


@pytest.mark.parametrize('ohlc', [('1', '2', '1.1', '1'), ('2', '1', '0', '2'),
                                 ('1', '0', '2', '1')])
def test_ohlc_invariants(tmp_path, ohlc):
    row = fields()
    row[1:5] = ohlc
    with pytest.raises(p.KlineParseError):
        parse(tmp_path, [row])


@pytest.mark.parametrize('bad', ['-1', '1.0', '9223372036854775808', ''])
def test_count_is_nonnegative_int64(tmp_path, bad):
    row = fields()
    row[8] = bad
    with pytest.raises(p.KlineParseError):
        parse(tmp_path, [row])


def test_ignore_is_verbatim_source_evidence(tmp_path):
    row = fields()
    row[-1] = 'source-only'
    assert c.build_kline_rows(parse(tmp_path, [row]))[0].source_ignore == 'source-only'


def test_attempt_exclusive_and_value_blind(tmp_path):
    path = tmp_path / 'evidence.json'
    path.write_bytes(b'preserve')
    with pytest.raises(FileExistsError):
        p.parse_kline_rows(b'', SeriesArchive(SPOT, '2020-01'), attempt_path=path)
    assert path.read_bytes() == b'preserve'
    bad = fields(price='SECRET_VALUE')
    with pytest.raises(p.KlineParseError) as caught:
        parse(tmp_path, [bad])
    assert 'SECRET_VALUE' not in str(caught.value)
    assert 'SECRET_VALUE' not in next(tmp_path.glob('attempt-*')).read_text()


@pytest.mark.parametrize('price,valid', [
    ('0.1234567890123456789', False),
    ('99999999999999999999.123456789012345678', True),
    ('100000000000000000000', False),
])
def test_q18_boundaries(tmp_path, price, valid):
    if not valid:
        with pytest.raises(p.KlineParseError):
            parse(tmp_path, [fields(price=price)])
    else:
        rows = c.build_kline_rows(parse(tmp_path, [fields(price=price)]))
        path = tmp_path / 'large.parquet'
        c.write_kline_parquet(rows, path)
        assert c.read_kline_rows(path) == rows


@pytest.mark.parametrize('price', ['0', '-0.000123456789012345', '-0'])
def test_hostile_decimal_context(tmp_path, price):
    rows = c.build_kline_rows(parse(tmp_path, [fields(price=price)], series=DERIVED[0]))
    baseline = c.kline_content_hash(rows)
    with localcontext() as context:
        context.prec = 1
        for signal in (Inexact, Rounded, Subnormal):
            context.traps[signal] = True
        other = c.build_kline_rows(parse(tmp_path, [fields(price=price)], series=DERIVED[0]))
        assert c.kline_content_hash(other) == baseline


@pytest.mark.parametrize('name,value', [
    ('provider', 'other'), ('venue', 'other'), ('market_type', 'perpetual'),
    ('instrument_id', 'other'), ('provider_symbol', 'ETHUSDT'),
    ('series_id', 'btc_settled_funding'), ('native_interval', '1h'),
    ('timestamp_role', 'settlement'), ('source_file', 'wrong.csv'),
    ('source_sha256', 'A' * 64), ('quality_flags', 'PASS'),
    ('eligibility_ts', T + 60001), ('interval_open_ts', T + 1),
    ('interval_close_ts', T + 60000), ('settlement_or_snapshot_ts', T),
    ('open', 1.0), ('volume', Decimal('-1')), ('trade_count', True),
    ('source_count', None), ('volume_semantics', 'structural_zero'),
])
def test_handset_drift_rejected(tmp_path, name, value):
    row, = c.build_kline_rows(parse(tmp_path))
    with pytest.raises(c.KlineCanonicalError):
        c.kline_content_hash([replace(row, **{name: value})])


def test_kraken_handset_eligibility_rejected(tmp_path):
    row, = c.build_kline_rows(parse(tmp_path, series=KRAKEN))
    with pytest.raises(c.KlineCanonicalError):
        c.kline_content_hash([replace(row, eligibility_ts=T + 60000)])


def test_schema_and_domain_separation(tmp_path):
    assert c.KLINE_SCHEMA_VERSION == 'quantara.kline-series/v1'
    assert c.KLINE_CONTENT_HASH_DOMAIN == 'quantara-kline-series-content-v1'
    fingerprint = c.kline_schema_fingerprint()
    assert len({fingerprint, hashing.schema_fingerprint(), c.scalar_schema_fingerprint()}) == 3
    assert fingerprint == '32048c4141735d7cc07e4a7d94bc317487db45a647e9396db4f8b7f9da1f8700'
    rows = c.build_kline_rows(parse(tmp_path))
    suffix = (fingerprint + '\n' + canonicalize(rows[0].to_content_array()) + '\n').encode()
    digest = c.kline_content_hash(rows)
    framed = c.KLINE_CONTENT_HASH_DOMAIN.encode() + b'\0' + suffix
    assert digest == hashlib.sha256(framed).hexdigest()
    for domain in (hashing.CONTENT_HASH_DOMAIN, c.CONTENT_HASH_DOMAIN):
        assert digest != hashlib.sha256(domain.encode() + b'\0' + suffix).hexdigest()


@pytest.mark.parametrize('series', [SPOT, KRAKEN, 'btc_native_premium_1m'])
def test_parquet_determinism_readback_and_reconciliation(tmp_path, series):
    step = 3600000 if series == KRAKEN else 60000
    price = '-0.1' if series in DERIVED else '1'
    source_rows = [fields(t, kraken=series == KRAKEN, price=price)
                   for t in (T, T + 2 * step)]
    rows = c.build_kline_rows(parse(tmp_path, source_rows, series=series))
    a, b = tmp_path / 'a.parquet', tmp_path / 'b.parquet'
    c.write_kline_parquet(rows, a)
    c.write_kline_parquet(rows, b)
    assert a.read_bytes() == b.read_bytes()
    assert c.read_kline_rows(a) == rows
    assert [row.event_ts for row in c.read_kline_rows(a)] == [T, T + 2 * step]
    with pytest.raises(c.KlineReconciliationMismatch):
        c.reconcile_kline_parquet(rows[:1], a)
    with pytest.raises(c.KlineReconciliationMismatch):
        c.reconcile_kline_parquet([replace(rows[0], ingestion_ts=T), rows[1]], a)
    for invalid in ([rows[1], rows[0]], [rows[0], rows[0]]):
        with pytest.raises(c.KlineCanonicalError):
            c.kline_content_hash(invalid)
    table = pq.read_table(a)
    pq.write_table(table.replace_schema_metadata(None), b)
    with pytest.raises(c.KlineParquetFailure):
        c.read_kline_rows(b)
    pq.write_table(pa.table({'foreign': [1]}), b)
    with pytest.raises(c.KlineParquetFailure):
        c.read_kline_rows(b)


@pytest.mark.parametrize('series,slots,step', [(SPOT, 44640, 60000), (KRAKEN, 43848, 3600000)])
@pytest.mark.parametrize('holes', [(), (0,), (10,), (-1,), (0, 7, 18, -1)])
def test_gap_grid_manifest_and_no_fabrication(tmp_path, series, slots, step, holes):
    omitted = {i % slots for i in holes}
    source = [fields(T + i * step, kraken=series == KRAKEN)
              for i in range(slots) if i not in omitted]
    parsed = parse(tmp_path, source, series=series)
    manifest = c.build_gap_manifest(parsed)
    assert manifest['expected_slots'] == slots
    assert manifest['present_slots'] == slots - len(omitted)
    expected_starts = [T + i * step for i in sorted(omitted)]
    assert [g['interval_open_ts'] for g in manifest['gaps']] == expected_starts
    for gap in manifest['gaps']:
        assert gap['interval_close_ts'] == gap['interval_open_ts'] + step - 1
        assert gap['series_id'] == series
        assert gap['enumeration_basis'] == 'descriptor_period_native_grid'
        assert gap['exclusion_reason'] is None  # no candidate/lookback has been assessed
    encoded = c.gap_manifest_bytes(manifest)
    assert encoded == c.gap_manifest_bytes(c.build_gap_manifest(parsed))
    assert c.gap_manifest_hash(manifest) == c.gap_manifest_hash(c.build_gap_manifest(parsed))
    assert not any(token in encoded for token in (b'approval', b'quality', b'PASS', b'designed'))
    assert len(c.build_kline_rows(parsed)) == slots - len(omitted)


def test_gap_schema_identity_and_tampering(tmp_path):
    manifest = c.build_gap_manifest(parse(tmp_path))
    assert c.GAP_SCHEMA_VERSION == 'quantara.kline-gap-manifest/v1'
    assert c.GAP_HASH_DOMAIN == 'quantara-kline-gap-manifest-content-v1'
    assert c.gap_schema_fingerprint() == (
        '9625517b83b52bd02c3349b26fff7bb801cf7424bb9ce0468bdcd2f0dc58b52b'
    )
    assert len({c.gap_schema_fingerprint(), c.kline_schema_fingerprint(),
                c.scalar_schema_fingerprint(), hashing.schema_fingerprint()}) == 4
    manifest['gaps'].pop()
    with pytest.raises(c.KlineCanonicalError):
        c.gap_manifest_bytes(manifest)


def test_legacy_identities_unchanged():
    assert hashing.schema_fingerprint() == (
        'feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8'
    )
    assert hashing.CONTENT_HASH_DOMAIN == 'quantara-canonical-content-v1'
    assert c.SCHEMA_VERSION == 'quantara.scalar-series/v1'
    assert c.CONTENT_HASH_DOMAIN == 'quantara-scalar-series-content-v1'
    assert c.scalar_schema_fingerprint().startswith('a2819e59231eb81a')
    with pytest.raises(p.MalformedNumeric):
        p.parse_numeric('-0.1')
