"""D03 synthetic scalar contracts; no acquisition or real archive access."""

import hashlib
import json
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from quantara.hashing import CONTENT_HASH_DOMAIN as LEGACY_DOMAIN
from quantara.jcs import canonicalize
from quantara.series_canonical import (
    CONTENT_HASH_DOMAIN,
    PARQUET_SCHEMA,
    SCHEMA_VERSION,
    WRITER_CONFIG,
    ScalarCanonicalError,
    ScalarParquetFailure,
    ScalarReconciliationMismatch,
    build_scalar_rows,
    read_scalar_rows,
    reconcile_scalar_parquet,
    scalar_content_hash,
    scalar_schema_fingerprint,
    write_scalar_parquet,
)
from quantara.series_descriptor import SeriesArchive, SeriesDescriptor
from quantara.series_parsing import (
    FUNDING_HEADER,
    OI_HEADER,
    DuplicateConflict,
    FundingParseError,
    OpenInterestParseError,
    ScalarParseError,
    parse_scalar_rows,
)

FUNDING = 'calc_time,funding_interval_hours,last_funding_rate'
OI = ('create_time,symbol,sum_open_interest,sum_open_interest_value,'
      'count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,'
      'count_long_short_ratio,sum_taker_long_short_vol_ratio')
FUNDING_ROW = '1580486400002,8,-0.000123456789012345'
OI_ROW = '2021-12-01 00:55:00,BTCUSDT,12345.678901234567890123,456789.1234,1,2,3,4'
F = 1580486400002
OI_TS = 1638320100000
T = 1638320400000

# Independent literal schema, including family-specific nullable columns.
EXPECTED_COLUMNS = (
    ('provider', 'string', False),
    ('venue', 'string', False),
    ('market_type', 'string', False),
    ('instrument_id', 'string', False),
    ('provider_symbol', 'string', False),
    ('series_id', 'string', False),
    ('native_interval', 'string', False),
    ('source_file', 'string', False),
    ('source_sha256', 'string', False),
    ('event_ts', 'int64', False),
    ('interval_open_ts', 'int64', True),
    ('interval_close_ts', 'int64', True),
    ('settlement_or_snapshot_ts', 'int64', False),
    ('archive_publication_ts', 'int64', True),
    ('ingestion_ts', 'int64', True),
    ('eligibility_ts', 'int64', False),
    ('quality_flags', 'string', True),
    ('timestamp_role', 'string', False),
    ('funding_interval_hours', 'string', True),
    ('last_funding_rate', 'decimal128(38, 18)', True),
    ('sum_open_interest', 'decimal128(38, 18)', True),
    ('sum_open_interest_value', 'string', True),
)


def parse(tmp_path, rows=None, *, family='funding', symbol='BTC', raw=None):
    series = (f'{symbol.lower()}_settled_funding' if family == 'funding'
              else f'{symbol.lower()}_open_interest_5m')
    period = '2020-01' if family == 'funding' else '2021-12-01'
    header = FUNDING if family == 'funding' else OI
    default = FUNDING_ROW if family == 'funding' else OI_ROW.replace('BTCUSDT', symbol+'USDT')
    data = raw if raw is not None else (header+'\n'+'\n'.join(rows or [default])+'\n').encode()
    attempt = tmp_path / 'attempt.json'
    result = parse_scalar_rows(data, SeriesArchive(series, period), attempt_path=attempt)
    return result, json.loads(attempt.read_text()), data


@pytest.mark.parametrize('symbol', ['BTC', 'ETH'])
def test_funding_exact_settlement_jitter_and_evidence(tmp_path, symbol):
    result, attempt, data = parse(tmp_path, symbol=symbol)
    source = result.rows[0]
    assert FUNDING_HEADER == tuple(FUNDING.split(','))
    assert type(source.last_funding_rate) is Decimal
    assert source.last_funding_rate == Decimal('-0.000123456789012345')
    assert source.funding_interval_hours == '8'
    row, = build_scalar_rows(result)
    assert (row.event_ts, row.settlement_or_snapshot_ts, row.eligibility_ts) == (F, F, F+1)
    assert row.event_ts % 28_800_000 == 2
    assert row.native_interval == 'per_settlement_event'
    assert row.timestamp_role == 'settlement'
    assert row.instrument_id == f'binance:usd_m_futures:{symbol}USDT:perpetual'
    assert row.source_sha256 == hashlib.sha256(data).hexdigest()
    assert row.source_file == f'{symbol}USDT-fundingRate-2020-01.csv'
    assert row.archive_publication_ts is row.ingestion_ts is row.quality_flags is None
    assert row.interval_open_ts is row.interval_close_ts is None
    assert row.sum_open_interest is row.sum_open_interest_value is None
    assert attempt['status'] == 'PARSED'
    assert attempt['source_rows'] == attempt['distinct_rows'] == 1
    assert attempt['duplicate_rows'] == 0


@pytest.mark.parametrize('symbol', ['BTC', 'ETH'])
def test_oi_payload_diagnostic_and_unresolved_timestamp(tmp_path, symbol):
    result, _, _ = parse(tmp_path, family='oi', symbol=symbol)
    assert OI_HEADER == tuple(OI.split(','))
    assert len(OI_HEADER) == 8
    source = result.rows[0]
    assert type(source.sum_open_interest) is Decimal
    assert type(source.sum_open_interest_value) is Decimal
    row, = build_scalar_rows(result)
    assert row.sum_open_interest == Decimal('12345.678901234567890123')
    assert row.sum_open_interest_value == '456789.123400000000000000'
    assert row.event_ts == row.settlement_or_snapshot_ts == OI_TS
    assert row.eligibility_ts == T == OI_TS+300_000
    assert row.native_interval == '5m'
    assert row.timestamp_role == 'UNRESOLVED_CONSERVATIVE'
    assert row.interval_open_ts is row.interval_close_ts is None
    assert row.last_funding_rate is row.funding_interval_hours is None
    forbidden = set(OI.split(',')[4:]) | {'symbol'}
    assert not forbidden.intersection(asdict(source))
    assert not forbidden.intersection(asdict(row))
    assert not forbidden.intersection(PARQUET_SCHEMA.names)
    assert all(name not in canonicalize(row.to_content_array()) for name in forbidden)


def test_latest_eligible_oi_is_previous_five_minute_timestamp(tmp_path):
    later = OI_ROW.replace('00:55:00', '01:00:00')
    result, _, _ = parse(tmp_path, [OI_ROW, later], family='oi')
    rows = build_scalar_rows(result)
    eligible = [r for r in rows if r.eligibility_ts < T+2]
    assert [r.event_ts for r in eligible] == [T-300_000]


@pytest.mark.parametrize('family', ['funding', 'oi'])
def test_exact_duplicate_counts_and_deterministic_order(tmp_path, family):
    first = FUNDING_ROW if family == 'funding' else OI_ROW
    later = (first.replace(str(F), str(F+1000)) if family == 'funding'
             else first.replace('00:55:00', '01:00:00'))
    result, attempt, _ = parse(tmp_path, [later, first, later, first], family=family)
    assert [r.event_ts for r in result.rows] == sorted(r.event_ts for r in result.rows)
    counts = tuple(attempt[key] for key in ('source_rows', 'distinct_rows', 'duplicate_rows'))
    assert counts == (4, 2, 2)
    assert attempt['source_ordered'] is False
    assert (result.source_rows, result.distinct_rows, result.duplicate_rows) == (4, 2, 2)


@pytest.mark.parametrize('family,change', [
    ('funding', lambda s: s.replace('-0.000123456789012345', '0.2')),
    ('funding', lambda s: s.replace(',8,', ',4,')),
    ('funding', lambda s: s.replace(',8,', ',08,')),
    ('oi', lambda s: s.replace('12345.678901234567890123', '1')),
    ('oi', lambda s: s.replace('456789.1234', '2')),
    ('oi', lambda s: s.replace(',1,2,3,4', ',2,2,3,4')),
])
def test_nonidentical_same_key_blocks_including_ignored_columns(tmp_path, family, change):
    row = FUNDING_ROW if family == 'funding' else OI_ROW
    with pytest.raises(DuplicateConflict):
        parse(tmp_path, [row, change(row)], family=family)
    evidence = json.loads((tmp_path/'attempt.json').read_text())
    assert evidence['status'] == 'BLOCKED'
    assert evidence['source_rows'] == 2
    assert evidence['distinct_rows'] == 1
    assert evidence['duplicate_rows'] == 0
    assert evidence['conflict_rows'] == 1
    assert evidence['counts_complete'] is False


@pytest.mark.parametrize('family,error', [
    ('funding', FundingParseError), ('oi', OpenInterestParseError),
])
@pytest.mark.parametrize('kind', ['unknown', 'missing', 'order', 'bom', 'utf8', 'empty', 'extra'])
def test_invalid_headers_are_family_typed(tmp_path, family, error, kind):
    header = FUNDING if family == 'funding' else OI
    cols = header.split(',')
    raw = {
        'unknown': header.replace(cols[0], 'unknown').encode()+b'\n',
        'missing': ','.join(cols[:-1]).encode()+b'\n',
        'order': ','.join(reversed(cols)).encode()+b'\n',
        'bom': b'\xef\xbb\xbf'+header.encode()+b'\n',
        'utf8': b'\xff\n', 'empty': b'', 'extra': (header+',extra\n').encode(),
    }[kind]
    with pytest.raises(error):
        parse(tmp_path, family=family, raw=raw)


@pytest.mark.parametrize('family,error', [
    ('funding', FundingParseError), ('oi', OpenInterestParseError),
])
@pytest.mark.parametrize('value', ['', 'NaN', 'Infinity', '1e-3', ' 1', '1_000', '+1', 'bad',
                                  '0.0000000000000000001', '100000000000000000000'])
def test_malformed_or_unrepresentable_payload(tmp_path, family, error, value):
    cols = (FUNDING_ROW if family == 'funding' else OI_ROW).split(',')
    cols[2] = value
    with pytest.raises(error):
        parse(tmp_path, [','.join(cols)], family=family)


@pytest.mark.parametrize('family,error,bad', [
    ('funding', FundingParseError, '1.5'), ('funding', FundingParseError, '-1'),
    ('funding', FundingParseError, '1e12'), ('funding', FundingParseError, '9'*25),
    ('funding', FundingParseError, '1577836799999'),
    ('oi', OpenInterestParseError, '2021-02-30 00:00:00'),
    ('oi', OpenInterestParseError, '2021-12-01T00:55:00Z'),
    ('oi', OpenInterestParseError, '1638320100000'),
    ('oi', OpenInterestParseError, '2021-11-30 23:55:00'),
])
def test_timestamp_grammar_and_archive_membership(tmp_path, family, error, bad):
    cols = (FUNDING_ROW if family == 'funding' else OI_ROW).split(',')
    cols[0] = bad
    with pytest.raises(error):
        parse(tmp_path, [','.join(cols)], family=family)


@pytest.mark.parametrize('column,value', [(1, 'ETHUSDT'), (3, ''), (3, '-1'),
                                          (4, 'NaN'), (5, 'bad'), (6, '1e2'), (7, '-1')])
def test_oi_symbol_diagnostic_and_ratio_structure(tmp_path, column, value):
    cols = OI_ROW.split(',')
    cols[column] = value
    with pytest.raises(OpenInterestParseError):
        parse(tmp_path, [','.join(cols)], family='oi')


def test_missing_ratio_cells_are_preserved_only_in_raw_source(tmp_path):
    result, _, _ = parse(tmp_path, [','.join(OI_ROW.split(',')[:4])+',,,,'], family='oi')
    assert build_scalar_rows(result)[0].sum_open_interest == Decimal('12345.678901234567890123')


@pytest.mark.parametrize('family,error', [
    ('funding', FundingParseError), ('oi', OpenInterestParseError),
])
@pytest.mark.parametrize('suffix', [',extra', '\n', ','])
def test_bad_row_width_or_blank_record(tmp_path, family, error, suffix):
    row = FUNDING_ROW if family == 'funding' else OI_ROW
    with pytest.raises(error):
        parse(tmp_path, [row+suffix], family=family)


def test_attempt_records_are_exclusive_and_no_quality_approval(tmp_path):
    parse(tmp_path)
    original = (tmp_path/'attempt.json').read_bytes()
    with pytest.raises(FileExistsError):
        parse(tmp_path)
    assert (tmp_path/'attempt.json').read_bytes() == original
    assert 'PASS' not in original.decode()


def test_non_scalar_descriptor_and_nonbytes_input_rejected(tmp_path):
    with pytest.raises(ScalarParseError):
        parse_scalar_rows(b'', SeriesArchive('btc_mark_price_1m', '2020-01'),
                          attempt_path=tmp_path/'unsupported.json')
    with pytest.raises(FundingParseError):
        parse(tmp_path, raw=1.0)


def test_normalization_rights_gate_blocks_before_rows(tmp_path, monkeypatch):
    class Denied:
        def permits(self, operation):
            assert operation == 'normalize_internal'
            return False

    monkeypatch.setattr(SeriesDescriptor, 'load_rights', lambda *args, **kwargs: Denied())
    with pytest.raises(ScalarParseError, match='rights'):
        parse(tmp_path)
    assert json.loads((tmp_path/'attempt.json').read_text())['status'] == 'BLOCKED'


def test_schema_and_writer_config_are_frozen():
    assert SCHEMA_VERSION == 'quantara.scalar-series/v1'
    assert tuple((f.name, str(f.type), f.nullable) for f in PARQUET_SCHEMA) == EXPECTED_COLUMNS
    assert PARQUET_SCHEMA.metadata == {b'schema_version': b'quantara.scalar-series/v1'}
    assert WRITER_CONFIG == {'compression': 'zstd', 'version': '2.6',
                             'data_page_version': '2.0', 'store_schema': True}
    columns = [{'index': i, 'name': n, 'type': t, 'nullable': null}
               for i, (n, t, null) in enumerate(EXPECTED_COLUMNS)]
    expected = hashlib.sha256(canonicalize({'domain': 'quantara-scalar-series-schema-v1',
                                           'schema_version': SCHEMA_VERSION,
                                           'columns': columns}).encode()).hexdigest()
    assert scalar_schema_fingerprint() == expected


def test_q18_and_decimal_context_independence(tmp_path):
    result, _, _ = parse(tmp_path, ['1580486400002,8,-99999999999999999999.123456789012345678'])
    row, = build_scalar_rows(result)
    with localcontext() as ctx:
        ctx.prec = 3
        content = row.to_content_array()
    assert content[19] == '-99999999999999999999.123456789012345678'


@pytest.mark.parametrize('bad', [0.1, True, '0.1', Decimal('NaN'), Decimal('Infinity'),
                               Decimal('1E-19'), Decimal('1E20')])
def test_direct_canonical_payload_cannot_bypass_decimal_policy(tmp_path, bad):
    result, _, _ = parse(tmp_path)
    row, = build_scalar_rows(result)
    with pytest.raises(ScalarCanonicalError):
        replace(row, last_funding_rate=bad).to_content_array()


def test_hash_domain_and_literal_row_framing(tmp_path):
    result, _, _ = parse(tmp_path)
    rows = build_scalar_rows(result)
    fingerprint = scalar_schema_fingerprint()
    framed = (fingerprint+'\n'+canonicalize(rows[0].to_content_array())+'\n').encode()
    assert CONTENT_HASH_DOMAIN == 'quantara-scalar-series-content-v1'
    expected = hashlib.sha256(b'quantara-scalar-series-content-v1\0'+framed).hexdigest()
    assert scalar_content_hash(rows) == scalar_content_hash(tuple(rows)) == expected
    assert expected != hashlib.sha256(LEGACY_DOMAIN.encode()+b'\0'+framed).hexdigest()


@pytest.mark.parametrize('family,changes', [
    ('funding', {'last_funding_rate': Decimal('0.125')}),
    ('funding', {'funding_interval_hours': '4'}),
    ('funding', {'source_sha256': 'f'*64}),
    ('funding', {'ingestion_ts': F+100}),
    ('funding', {'archive_publication_ts': F+200}),
    ('funding', {'event_ts': F+1, 'settlement_or_snapshot_ts': F+1, 'eligibility_ts': F+2}),
    ('oi', {'sum_open_interest': Decimal('2')}),
    ('oi', {'sum_open_interest_value': '2.000000000000000000'}),
])
def test_hash_binds_payload_and_each_applicable_evidence(tmp_path, family, changes):
    result, _, _ = parse(tmp_path, family=family)
    row, = build_scalar_rows(result)
    assert scalar_content_hash([replace(row, **changes)]) != scalar_content_hash([row])


def test_ratio_values_never_reach_content_except_whole_source_digest(tmp_path):
    (tmp_path/'a').mkdir()
    (tmp_path/'b').mkdir()
    first, _, _ = parse(tmp_path/'a', family='oi')
    second, _, _ = parse(tmp_path/'b', [OI_ROW.replace(',1,2,3,4', ',5,6,7,8')], family='oi')
    a, = build_scalar_rows(first)
    b, = build_scalar_rows(second)
    assert a.source_sha256 != b.source_sha256  # Required immutable source provenance.
    assert a.to_content_array() == replace(b, source_sha256=a.source_sha256).to_content_array()


@pytest.mark.parametrize('family', ['funding', 'oi'])
def test_real_parquet_roundtrip_and_reconciliation(tmp_path, family):
    result, _, _ = parse(tmp_path, family=family)
    rows = build_scalar_rows(result, ingestion_ts=T+1000, archive_publication_ts=T+500)
    path = tmp_path/'scalar.parquet'
    write_scalar_parquet(rows, path)
    actual = read_scalar_rows(path)
    assert actual == rows
    value = actual[0].last_funding_rate if family == 'funding' else actual[0].sum_open_interest
    assert type(value) is Decimal
    assert pq.read_schema(path).equals(PARQUET_SCHEMA, check_metadata=True)
    assert pq.ParquetFile(path).metadata.row_group(0).column(19).compression == 'ZSTD'
    reconcile_scalar_parquet(rows, path)
    assert scalar_content_hash(actual) == scalar_content_hash(rows)


@pytest.mark.parametrize('tamper', ['value', 'diagnostic', 'row_count', 'schema', 'byte'])
def test_tampered_parquet_fails_closed(tmp_path, tamper):
    result, _, _ = parse(tmp_path, family='oi')
    rows = build_scalar_rows(result)
    path = tmp_path/'scalar.parquet'
    write_scalar_parquet(rows, path)
    if tamper == 'byte':
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
    else:
        table = pq.read_table(path)
        data = table.to_pylist()
        if tamper == 'value':
            data[0]['sum_open_interest'] = Decimal('1')
        elif tamper == 'diagnostic':
            data[0]['sum_open_interest_value'] = '1.000000000000000000'
        elif tamper == 'row_count':
            data = []
        table = pa.Table.from_pylist(data, schema=PARQUET_SCHEMA)
        if tamper == 'schema':
            table = table.append_column('unapproved', pa.array([1]))
        pq.write_table(table, path, **WRITER_CONFIG)
    with pytest.raises((ScalarReconciliationMismatch, ScalarParquetFailure)):
        reconcile_scalar_parquet(rows, path)


def test_hash_and_writer_reject_duplicate_or_unsorted_canonical_rows(tmp_path):
    result, _, _ = parse(tmp_path, [FUNDING_ROW, FUNDING_ROW.replace(str(F), str(F+1))])
    rows = build_scalar_rows(result)
    for invalid in (rows[::-1], (rows[0], rows[0])):
        with pytest.raises(ScalarCanonicalError):
            scalar_content_hash(invalid)
        with pytest.raises(ScalarCanonicalError):
            write_scalar_parquet(invalid, tmp_path/'invalid.parquet')


def test_header_only_means_no_observations_not_fabricated_zeros(tmp_path):
    result, record, _ = parse(tmp_path, raw=(FUNDING+'\n').encode())
    assert result.rows == ()
    assert record['source_rows'] == record['distinct_rows'] == record['duplicate_rows'] == 0
    rows = build_scalar_rows(result)
    path = tmp_path/'empty.parquet'
    write_scalar_parquet(rows, path)
    assert read_scalar_rows(path) == ()
    reconcile_scalar_parquet(rows, path)


@pytest.mark.parametrize('changes', [
    {'series_id': 'unknown'}, {'series_id': 'btc_mark_price_1m'},
    {'provider': 'unapproved'}, {'provider_symbol': 'ETHUSDT'},
    {'instrument_id': 'invented'}, {'native_interval': '1h'},
    {'timestamp_role': 'interval_start'}, {'event_ts': True},
    {'eligibility_ts': F}, {'settlement_or_snapshot_ts': F+1},
    {'interval_open_ts': F}, {'quality_flags': 'PASS'},
    {'source_sha256': 'x'*64}, {'source_file': 'other.csv'},
    {'last_funding_rate': None}, {'funding_interval_hours': '0'},
    {'ingestion_ts': 1.0}, {'archive_publication_ts': -1},
])
def test_direct_row_identity_and_temporal_shape_cannot_bypass_validation(tmp_path, changes):
    result, _, _ = parse(tmp_path)
    row, = build_scalar_rows(result)
    with pytest.raises(ScalarCanonicalError):
        scalar_content_hash([replace(row, **changes)])


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_byte_identical_duplicates_with_each_line_ending(tmp_path, newline):
    raw = (FUNDING+newline+FUNDING_ROW+newline+FUNDING_ROW+newline).encode()
    result, record, _ = parse(tmp_path, raw=raw)
    assert len(result.rows) == record['duplicate_rows'] == 1


def test_nonidentical_record_terminators_block(tmp_path):
    raw = (FUNDING+'\n'+FUNDING_ROW+'\n'+FUNDING_ROW+'\r\n').encode()
    with pytest.raises(DuplicateConflict):
        parse(tmp_path, raw=raw)
