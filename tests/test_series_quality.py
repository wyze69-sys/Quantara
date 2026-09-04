"""D05 synthetic quality/evidence contracts; no external or sealed data."""

import hashlib
import importlib
import json
from dataclasses import FrozenInstanceError, asdict, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from quantara import series_canonical as c
from quantara import series_parsing as p
from quantara.jcs import canonicalize
from quantara.quality_approval import QualityApprovalError, load_approval_record
from quantara.series_descriptor import SERIES_REGISTRY, SeriesArchive

T = 1577836800000
OI_START = 1638316800000
SPOT = 'binance_btc_spot_ohlcv_1m'
KRAKEN = 'kraken_xbtusd_spot_ohlcv_1h'
CHECKS = (
    'funding_interval_valid', 'funding_settlement_grid', 'oi_snapshot_grid',
    'oi_daily_boundary', 'kline_grid_completeness', 'kline_interval_invariants',
    'duplicate_exact_bytes', 'conflict_same_key', 'source_order', 'kraken_derived_close',
)
REASONS = (
    'missing_native_interval', 'incomplete_feature_window', 'funding_cadence_incomplete',
    'oi_snapshot_gap', 'invalid_label_endpoint', 'buffer_bar_missing', 'pre_archive_period',
    'eth_oi_pre_2021_12_01', 'same_key_conflict',
)


@pytest.fixture
def q():
    # Import per case so the pre-implementation transcript records every case.
    return importlib.import_module('quantara.series_quality')


def sample(tmp_path, series='btc_settled_funding', *, times=None, interval='8',
           duplicate=False, ending=b'\n'):
    spec = SERIES_REGISTRY[series]
    scalar = spec.source_family in ('fundingRate', 'metrics')
    oi = spec.source_family == 'metrics'
    kraken = series == KRAKEN
    archive = SeriesArchive(series, '2021-12-01' if oi else
                            '2020-2024' if kraken else '2020-01')
    times = [OI_START if oi else T] if times is None else times
    records = []
    for t in times:
        if spec.source_family == 'fundingRate':
            row = [str(t), interval, '-0.000123456789012345']
        elif oi:
            row = [datetime.fromtimestamp(t / 1000, UTC).strftime('%Y-%m-%d %H:%M:%S'),
                   spec.provider_symbol, '12345.67890123456789', '987654.321', '', '', '', '']
        elif kraken:
            row = [str(t // 1000), '12.3', '13.4', '11.2', '12.4', '19.8', '2']
        else:
            derived = spec.source_family in p.DERIVED_PRICE_FAMILIES
            row = [str(t), '12.3', '13.4', '11.2', '12.4', '0' if derived else '19.8',
                   str(t + 59999), '0', '2', '0', '0', '0']
        records.append(','.join(row).encode() + ending)
    if duplicate:
        records.append(records[0])
    header = p.OI_HEADER if oi else p.FUNDING_HEADER if scalar else p.KLINE_HEADER
    raw = (','.join(header).encode() + ending if archive.csv_header == 'present' else b'')
    raw += b''.join(records)
    path = tmp_path / f'attempt-{len(list(tmp_path.glob("attempt-*")))}.json'
    parsed = (p.parse_scalar_rows if scalar else p.parse_kline_rows)(
        raw, archive, attempt_path=path,
    )
    canonical = (c.build_scalar_rows if scalar else c.build_kline_rows)(parsed)
    return parsed, canonical, json.loads(path.read_text()), records


def finding(report, check):
    return next(f for f in report.findings if f.check_id == check)


@pytest.mark.parametrize('series', ['btc_settled_funding', 'eth_settled_funding'])
def test_clean_funding_identity(q, tmp_path, series):
    parsed, rows, _, _ = sample(tmp_path, series, times=[T + 2, T + 28800003])
    first = q.evaluate_series_quality(parsed, rows)
    second = q.evaluate_series_quality(parsed, rows)
    assert first.state == 'PASS'
    assert first.identity() == second.identity()
    assert q.SCHEMA_VERSION == 'quantara.series-quality/v1'
    assert q.IDENTITY_DOMAIN == 'quantara-series-quality-v1'
    expected = {'domain': 'quantara-series-quality-v1',
                'schema_version': 'quantara.series-quality/v1',
                'findings': [asdict(f) for f in first.findings]}
    assert first.identity() == hashlib.sha256(canonicalize(expected).encode()).hexdigest()


@pytest.mark.parametrize('interval,outcome', [('8', 'pass'), ('4', 'warn'),
                                             ('1', 'warn'), ('12', 'warn')])
def test_funding_interval_census(q, tmp_path, interval, outcome):
    parsed, rows, _, _ = sample(tmp_path, interval=interval)
    f = finding(q.evaluate_series_quality(parsed, rows), 'funding_interval_valid')
    assert f.outcome == outcome
    assert f.evidence['observed_counts'] == {interval: 1}
    assert f.severity == 'warning'


@pytest.mark.parametrize('family', ['btc_settled_funding', 'btc_open_interest_5m'])
def test_duplicate_distinct_timestamp_fails(q, tmp_path, family):
    parsed, rows, _, _ = sample(tmp_path, family)
    parsed = replace(parsed, rows=parsed.rows * 2, source_rows=2, distinct_rows=2)
    report = q.evaluate_series_quality(parsed, rows * 2)
    check = 'oi_snapshot_grid' if 'interest' in family else 'funding_settlement_grid'
    assert finding(report, check).outcome == 'fail'
    assert report.state == 'FAIL'


@pytest.mark.parametrize('times,outcome', [([OI_START, OI_START + 300000], 'pass'),
                                         ([OI_START, OI_START + 301000], 'fail'),
                                         ([OI_START, OI_START + 600000], 'pass')])
def test_oi_grid_and_gaps(q, tmp_path, times, outcome):
    parsed, rows, _, _ = sample(tmp_path, 'btc_open_interest_5m', times=times)
    report = q.evaluate_series_quality(parsed, rows)
    assert finding(report, 'oi_snapshot_grid').outcome == outcome
    boundary = finding(report, 'oi_daily_boundary')
    assert boundary.evidence['first_snapshot_ts'] == times[0]
    assert boundary.evidence['last_snapshot_ts'] == times[-1]
    assert boundary.evidence['expected_slots'] == 288
    if outcome == 'pass':
        assert boundary.outcome == 'warn'
        assert boundary.evidence['gap_count'] == 286
        assert report.state == 'WARN'


def test_full_oi_day_passes(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, 'eth_open_interest_5m',
                                times=range(OI_START, OI_START + 86400000, 300000))
    assert q.evaluate_series_quality(parsed, rows).state == 'PASS'


def test_kline_gap_manifest_identity_echo(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, SPOT, times=[T, T + 120000])
    manifest = c.build_gap_manifest(parsed)
    f = finding(q.evaluate_series_quality(parsed, rows), 'kline_grid_completeness')
    assert f.outcome == 'warn'
    assert f.count == 44638
    assert f.evidence == {
        'expected_slots': 44640, 'present_slots': 2, 'gap_count': 44638,
        'gap_manifest_hash': c.gap_manifest_hash(manifest),
        'gap_interval_open_ts': [T + 60000] + list(range(T + 180000, T + 2678400000, 60000)),
    }


def test_complete_kline_month(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, SPOT, times=range(T, T + 2678400000, 60000))
    assert q.evaluate_series_quality(parsed, rows).state == 'PASS'


@pytest.mark.parametrize('change', [{'open': Decimal('99')}, {'interval_close_ts': T + 60000},
                                  {'eligibility_ts': T + 60001}])
def test_tampered_kline_invariants(q, tmp_path, change):
    parsed, rows, _, _ = sample(tmp_path, SPOT)
    report = q.evaluate_series_quality(parsed, (replace(rows[0], **change),))
    assert finding(report, 'kline_interval_invariants').outcome == 'fail'
    assert report.state == 'FAIL'


@pytest.mark.parametrize('series', ['btc_settled_funding', 'btc_open_interest_5m', SPOT, KRAKEN])
def test_duplicate_evidence_warns(q, tmp_path, series):
    parsed, rows, _, _ = sample(tmp_path, series, duplicate=True)
    report = q.evaluate_series_quality(parsed, rows)
    f = finding(report, 'duplicate_exact_bytes')
    assert (f.outcome, f.severity, f.count) == ('warn', 'warning', 1)
    assert f.evidence == {'source_rows': 2, 'distinct_rows': 1,
                          'duplicate_rows': 1, 'duplicate_hash_count': 1}
    assert report.state == 'WARN'


@pytest.mark.parametrize('series', ['btc_settled_funding', SPOT])
def test_conflict_is_terminal(q, tmp_path, series):
    parsed, rows, _, _ = sample(tmp_path, series)
    report = q.evaluate_series_quality(replace(parsed, conflict_rows=1), rows)
    f = finding(report, 'conflict_same_key')
    assert (f.outcome, f.severity, f.count, report.state) == ('fail', 'hard', 1, 'FAIL')
    with pytest.raises(q.SeriesQualityError):
        q.proposed_approval_payload(report)
    with pytest.raises(q.SeriesQualityError):
        q.gap_disposition({'gaps': [
            {'interval_open_ts': T, 'exclusion_reason': 'same_key_conflict'},
        ]})


def test_source_order_warning(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, times=[T + 28800000, T])
    f = finding(q.evaluate_series_quality(parsed, rows), 'source_order')
    assert (f.outcome, f.severity, f.count) == ('warn', 'warning', 1)


@pytest.mark.parametrize('tampered', [False, True])
def test_kraken_derived_close(q, tmp_path, tampered):
    parsed, rows, _, _ = sample(tmp_path, KRAKEN)
    if tampered:
        rows = (replace(rows[0], interval_close_ts=T + 3600000),)
    f = finding(q.evaluate_series_quality(parsed, rows), 'kraken_derived_close')
    assert f.outcome == ('fail' if tampered else 'pass')
    assert f.evidence['close_is_source_observed'] is False
    assert f.evidence['native_step_ms'] == 3600000


@pytest.mark.parametrize('reason', REASONS[:-1] + (None, 'unknown'))
def test_gap_dispositions_closed(q, reason):
    manifest = {'gaps': [{'interval_open_ts': T, 'exclusion_reason': reason}]}
    assert q.gap_disposition(manifest) == {'gaps': [
        {'interval_open_ts': T, 'reason': reason if reason in REASONS
         else 'unclassified_pending_review'},
    ]}
    assert manifest['gaps'][0]['exclusion_reason'] == reason


def test_proposal_is_not_an_approval(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, duplicate=True)
    report = q.evaluate_series_quality(parsed, rows)
    proposed = q.proposed_approval_payload(report)
    assert proposed['authorized'] is False
    assert proposed['approver'] == proposed['decision_time_utc'] == 'PLACEHOLDER'
    assert proposed['series_id'] == parsed.archive.series_id
    assert proposed['source_sha256'] == [parsed.source_sha256]
    assert proposed['quality_identity_sha256'] == report.identity()
    assert proposed['proposed_findings'] == [
        {'check_id': 'duplicate_exact_bytes', 'count': 1,
         'finding_sha256': hashlib.sha256(canonicalize(
             asdict(finding(report, 'duplicate_exact_bytes'))).encode()).hexdigest()},
    ]
    semantics = {k: v for k, v in proposed.items() if k != 'record_sha256'}
    assert proposed['record_sha256'] == hashlib.sha256(canonicalize(semantics).encode()).hexdigest()
    record_dir = tmp_path / 'configs' / 'quality_approvals'
    record_dir.mkdir(parents=True)
    path = record_dir / 'proposal.yaml'
    path.write_text(json.dumps(proposed), encoding='utf-8')
    with pytest.raises(QualityApprovalError):
        load_approval_record(path, repo_root=tmp_path)
    with pytest.raises(q.SeriesQualityError):
        q.proposed_approval_payload(report, reviewer_placeholder=False)


def test_identity_excludes_operational_times(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path)
    a = q.evaluate_series_quality(parsed, rows, ingestion_ts=1, archive_publication_ts=2)
    b = q.evaluate_series_quality(parsed, (replace(rows[0], ingestion_ts=3,
                                    archive_publication_ts=4),), ingestion_ts=3,
                                    archive_publication_ts=4)
    assert a.identity() == b.identity()


def test_identity_changed_count_and_own_finding(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path)
    report = q.evaluate_series_quality(parsed, rows)
    changed = replace(report, findings=(replace(report.findings[0], count=1),)
                      + report.findings[1:])
    assert changed.identity() != report.identity()
    assert type(report.findings[0]).__module__ == 'quantara.series_quality'


def test_exhaustive_check_vocabulary_and_order(q, tmp_path):
    observed = set()
    assert q.CHECK_IDS == CHECKS
    for series in SERIES_REGISTRY:
        parsed, rows, _, _ = sample(tmp_path, series)
        report = q.evaluate_series_quality(parsed, rows)
        checks = [f.check_id for f in report.findings]
        assert checks == [check for check in CHECKS if check in checks]
        observed.update(checks)
    assert observed == set(CHECKS)


def test_unsupported_input_typed_error(q):
    parsed = SimpleNamespace(archive=SimpleNamespace(series_id='research_dataset'))
    with pytest.raises(q.SeriesQualityError):
        q.evaluate_series_quality(parsed, ())


@pytest.mark.parametrize('series', ['btc_settled_funding', 'btc_open_interest_5m', SPOT, KRAKEN])
def test_all_evidence_value_blind(q, tmp_path, series):
    parsed, rows, _, _ = sample(tmp_path, series)
    report = q.evaluate_series_quality(parsed, rows)
    text = json.dumps([asdict(f) for f in report.findings])
    for value in ('-0.000123456789012345', '12345.67890123456789', '987654.321',
                  '12.3', '13.4', '11.2', '12.4', '19.8'):
        assert value not in text


@pytest.mark.parametrize('series', ['btc_settled_funding', 'btc_open_interest_5m', SPOT, KRAKEN])
@pytest.mark.parametrize('ending', [b'\n', b'\r\n'])
def test_part_a_duplicate_evidence_and_immutable_results(tmp_path, series, ending):
    parsed, _, attempt, records = sample(tmp_path, series, duplicate=True, ending=ending)
    digest = hashlib.sha256(records[0]).hexdigest()
    assert parsed.duplicate_hashes == (digest,)
    assert parsed.duplicate_rows == 1
    assert parsed.conflict_rows == 0
    assert attempt['duplicate_hashes'] == [digest]
    assert [f.name for f in fields(parsed)][-2:] == ['duplicate_hashes', 'conflict_rows']
    assert not hasattr(parsed, '__dict__')
    with pytest.raises(FrozenInstanceError):
        parsed.conflict_rows = 1


@pytest.mark.parametrize('series', ['btc_settled_funding', SPOT])
def test_conflict_parser_still_raises_and_preserves_evidence(tmp_path, series):
    parsed, _, _, records = sample(tmp_path, series)
    raw = records[0] + records[0] + records[0].replace(b'\n', b'\r\n')
    if series != SPOT:
        raw = ','.join(p.FUNDING_HEADER).encode() + b'\n' + raw
    path = tmp_path / 'conflict.json'
    parser = p.parse_kline_rows if series == SPOT else p.parse_scalar_rows
    error = p.KlineDuplicateConflict if series == SPOT else p.FundingDuplicateConflict
    with pytest.raises(error):
        parser(raw, parsed.archive, attempt_path=path)
    evidence = json.loads(path.read_text())
    assert evidence['status'] == 'BLOCKED'
    assert evidence['conflict_rows'] == 1
    assert evidence['duplicate_hashes'] == [hashlib.sha256(records[0]).hexdigest()]


def test_malformed_duplicate_evidence_rejected(q, tmp_path):
    parsed, rows, _, _ = sample(tmp_path, duplicate=True)
    with pytest.raises(q.SeriesQualityError):
        q.evaluate_series_quality(replace(parsed, duplicate_hashes=()), rows)
