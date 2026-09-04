"""D06 composition gates: synthetic sources, real persistence and discovery."""

import hashlib
import importlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import yaml

import test_series_acquisition as acquisition_tests
from quantara import series_acquisition as acquisition
from quantara import series_canonical as canonical
from quantara import series_parsing as parsing
from quantara.cli import main
from quantara.publication import object_path, read_and_verify_current, verify_commit_graph
from quantara.series_descriptor import SeriesDescriptor
from test_pipeline import (
    build_zip,
    dataset_dir_for,
    fake_transport,
)
from test_pipeline import (
    env as legacy_env,  # noqa: F401 -- pytest fixture
)
from test_series_acquisition import good_handler

ROOT = Path(__file__).resolve().parents[1]
BTC = 'btc_settled_funding'
SPOT = 'binance_btc_spot_ohlcv_1m'
KRAKEN = 'kraken_xbtusd_spot_ohlcv_1h'
T = 1577836800000


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture(autouse=True)
def no_local_archive(monkeypatch):
    monkeypatch.delenv('QUANTARA_KRAKEN_ARCHIVE', raising=False)


@pytest.fixture
def pipeline():
    # Each test records a real import failure before the implementation exists.
    return importlib.import_module('quantara.series_pipeline')


def descriptor_file(tmp_path, series=BTC):
    path = tmp_path / f'{series}.yaml'
    path.write_text(yaml.safe_dump(SeriesDescriptor(series).to_dict()), encoding='utf-8')
    return path


def funding(period='2020-01', duplicate=False):
    ts = int(datetime.fromisoformat(period + '-01').replace(tzinfo=UTC).timestamp()) * 1000
    row = f'{ts},8,-0.000123456789012345\n'.encode()
    return ','.join(parsing.FUNDING_HEADER).encode() + b'\n' + row * (2 if duplicate else 1)


def transport_for(series=BTC, period='2020-01', member=None, calls=None):
    archive = SeriesDescriptor(series).archive_for(period)
    if member is None and series == KRAKEN:
        member = b''  # injected local acquisition never uses this transport
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
        info = zipfile.ZipInfo(archive.member, date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, funding(period) if member is None else member)
    payload = buffer.getvalue()
    checksum = f'{sha(payload)}  {archive.member[:-4]}.zip\n'.encode()

    def handler(request):
        if calls is not None:
            calls.append(str(request.url))
        return good_handler(payload, checksum)(request)

    return httpx.MockTransport(handler)


def lane(root, series=BTC, period='2020-01'):
    return root / 'datasets/series' / series / period


def attempts(root):
    return [json.loads(p.read_text()) for p in sorted((root / 'attempts').glob('*.json'))]


def run(pipeline, tmp_path, *, period='2020-01', series=BTC, member=None, **kwargs):
    return pipeline.run_series_pipeline(
        descriptor_file(tmp_path, series), tmp_path / 'data', period=period,
        transport=transport_for(series, period, member), sleeper=lambda _: None, **kwargs,
    )


def no_publication(root):
    assert not list(root.rglob('current.json'))
    assert not list(root.rglob('COMMITTED'))


def test_scalar_publish_and_verified_no_op(pipeline, tmp_path):
    assert run(pipeline, tmp_path) == 0
    root = tmp_path / 'data'
    target = lane(root)
    current = read_and_verify_current(target, target)
    assert verify_commit_graph(target, target / 'commits' / current['commit'])
    assert current['quality_state'] == 'PASS'
    pointer = (target / 'current.json').read_bytes()
    commits = sorted(p.name for p in (target / 'commits').iterdir())
    staging = sorted(str(p) for p in target.rglob('staging/*'))

    def forbidden(_):
        pytest.fail('verified no-op must not acquire')

    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path), root, period='2020-01',
        transport=httpx.MockTransport(forbidden),
    ) == 0
    assert (target / 'current.json').read_bytes() == pointer
    assert sorted(p.name for p in (target / 'commits').iterdir()) == commits
    assert sorted(str(p) for p in target.rglob('staging/*')) == staging
    assert sorted(a['terminal_state'] for a in attempts(root)) == ['PUBLISHED', 'VERIFIED_NO_OP']
    assert not (root / 'objects').exists()


def test_warn_is_blocked_with_identity(pipeline, tmp_path):
    assert run(pipeline, tmp_path, member=funding(duplicate=True)) == 2
    record = attempts(tmp_path / 'data')[0]
    assert record['terminal_state'] == 'BLOCKED' and record['exit_code'] == 2
    assert len(record['quality_identity']) == 64
    assert 'duplicate_exact_bytes' in record['finding_ids']
    no_publication(tmp_path / 'data')


def test_fail_quality_never_publishes(pipeline, tmp_path, monkeypatch):
    original = pipeline.evaluate_series_quality

    def tampered(parsed, rows):
        # Actual D05 evaluation of a conflicting parse result returns FAIL.
        return original(replace(parsed, conflict_rows=1), rows)

    monkeypatch.setattr(pipeline, 'evaluate_series_quality', tampered)
    assert run(pipeline, tmp_path) == 3
    record = attempts(tmp_path / 'data')[0]
    assert record['quality_state'] == 'FAIL' and record['exit_code'] == 3
    no_publication(tmp_path / 'data')


@pytest.mark.parametrize('operation', [
    'acquire_internal', 'retain_raw_internal', 'normalize_internal',
])
def test_rights_before_acquisition(pipeline, tmp_path, operation):
    name = SeriesDescriptor(BTC).legal_record + '.yaml'
    record = yaml.safe_load((ROOT / 'configs/legal' / name).read_text())
    record['operations'][operation]['state'] = 'PROHIBITED'
    legal = tmp_path / 'repo/configs/legal'
    legal.mkdir(parents=True)
    (legal / name).write_text(yaml.safe_dump(record))
    calls = []
    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path), tmp_path / 'data', period='2020-01',
        repo_root=tmp_path / 'repo', transport=transport_for(calls=calls),
    ) == 2
    assert calls == []
    attempt = attempts(tmp_path / 'data')[0]
    assert attempt['rights_states'][operation] == 'PROHIBITED'
    assert not list((tmp_path / 'data').rglob('objects'))


@pytest.fixture(scope='module')
def spot_member():
    return b''.join(
        f'{t},12.3,13.4,11.2,12.4,19.8,{t + 59999},0,2,0,0,0\n'.encode()
        for t in range(T, T + 2678400000, 60000)
    )


def test_complete_kline_publishes_frozen_gap_object(pipeline, tmp_path, spot_member):
    assert run(pipeline, tmp_path, series=SPOT, member=spot_member) == 0
    root = tmp_path / 'data'
    target = lane(root, SPOT)
    content = read_and_verify_current(target, target)
    gap_path = object_path(target, 'normalized', content['artifacts']['gap_manifest'])
    gap = json.loads(gap_path.read_bytes())
    parsed = parsing.parse_kline_rows(
        spot_member, SeriesDescriptor(SPOT).archive_for('2020-01'),
        attempt_path=tmp_path / 'expected-parse.json',
    )
    assert gap == canonical.build_gap_manifest(parsed)
    assert content['gap_manifest_hash'] == canonical.gap_manifest_hash(gap)
    assert gap['gap_count'] == 0
    assert all(g['exclusion_reason'] is None for g in gap['gaps'])


def test_kline_hole_stays_unclassified_and_blocked(pipeline, tmp_path, spot_member):
    member = b'\n'.join(spot_member.split(b'\n')[1:])
    assert run(pipeline, tmp_path, series=SPOT, member=member) == 2
    target = lane(tmp_path / 'data', SPOT)
    gap = json.loads(next(target.glob('staging/*/gaps.json')).read_bytes())
    assert gap['gaps'][0]['exclusion_reason'] is None
    assert gap['gap_count'] == 1
    no_publication(tmp_path / 'data')


def test_legacy_lane_isolation(pipeline, request, tmp_path):
    from quantara.pipeline import run_pipeline

    descriptor, root = request.getfixturevalue('legacy_env')
    archive, digest = build_zip(tmp_path)
    transport = fake_transport(archive, f'{digest}  BTCUSDT-1m-2024-01.zip\n')
    assert run_pipeline(descriptor, root, repo_root=tmp_path, transport=transport) == 0
    legacy = dataset_dir_for(root)
    before = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob('*') if p.is_file()}
    assert run(pipeline, tmp_path) == 0
    after = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob('*') if p.is_file()}
    assert after == before


@pytest.mark.parametrize('garbage', [b'{', b'null', b'{"commit":123}', b'{"commit":"../escape"}'])
def test_malformed_pointer_recovers_existing_commit(pipeline, tmp_path, garbage):
    assert run(pipeline, tmp_path) == 0
    target = lane(tmp_path / 'data')
    original = (target / 'current.json').read_bytes()
    (target / 'current.json').write_bytes(garbage)
    assert run(pipeline, tmp_path) == 0
    assert (target / 'current.json').read_bytes() == original
    assert len(list((target / 'commits').glob('[0-9a-f]*'))) == 1


def test_attempt_schema_and_value_blindness(pipeline, tmp_path):
    assert run(pipeline, tmp_path) == 0
    record = attempts(tmp_path / 'data')[0]
    assert record['schema'] == 'quantara.series-pipeline-attempt/v1'
    assert {
        'attempt_id', 'series_id', 'period', 'descriptor_source', 'acquirer_evidence_path',
        'parse_attempt_path', 'canonical_content_hash', 'gap_manifest_hash', 'quality_identity',
        'terminal_state', 'exit_code', 'selected_period', 'selection_mode',
        'parser_input_sha256', 'raw_format',
    } <= record.keys()
    assert record['descriptor_source']['sha256'] == sha(descriptor_file(tmp_path).read_bytes())
    assert record['selection_mode'] == 'explicit' and record['selected_period'] == '2020-01'
    assert '-0.000123456789012345' not in json.dumps(record)
    assert record['parser_input_sha256'] == sha(funding())
    assert Path(record['acquirer_evidence_path']).is_file()
    assert Path(record['parse_attempt_path']).is_file()


@pytest.mark.parametrize('exit_code', [0, 2, 3])
def test_cli_dispatch_period_and_exit_code(pipeline, tmp_path, monkeypatch, exit_code):
    calls = []

    def dispatched(**kwargs):
        calls.append(kwargs)
        return exit_code

    monkeypatch.setattr(pipeline, 'run_series_pipeline', dispatched)
    path = descriptor_file(tmp_path)
    assert main(['--descriptor', str(path), '--data-root', str(tmp_path / 'data'),
                 '--period', '2020-01', '--dry-run']) == exit_code
    assert calls == [dict(descriptor_path=str(path), data_root=str(tmp_path / 'data'),
                          period='2020-01', dry_run=True)]
    path.write_text('schema: unknown\n')
    assert main(['--descriptor', str(path), '--data-root', str(tmp_path / 'data')]) == 3


def test_dry_run_validates_without_acquisition(pipeline, tmp_path):
    calls = []
    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path), tmp_path / 'data', period='2020-01', dry_run=True,
        transport=transport_for(calls=calls),
    ) == 0
    assert calls == []
    assert attempts(tmp_path / 'data')[0]['dry_run'] is True
    assert not list((tmp_path / 'data').rglob('objects'))
    no_publication(tmp_path / 'data')


def test_object_collision_is_hard_failure(pipeline, tmp_path, monkeypatch):
    original = pipeline.put_object

    def collide(root, kind, payload, *args, **kwargs):
        target = object_path(root, kind, sha(payload))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'pre-existing different bytes')
        return original(root, kind, payload, *args, **kwargs)

    monkeypatch.setattr(pipeline, 'put_object', collide)
    assert run(pipeline, tmp_path) == 3
    assert attempts(tmp_path / 'data')[0]['error_type'] == 'ObjectCollision'
    no_publication(tmp_path / 'data')


def test_parse_failure_retains_attempt(pipeline, tmp_path):
    assert run(pipeline, tmp_path, member=funding() + b'corrupt,market-secret\n') == 3
    record = attempts(tmp_path / 'data')[0]
    parse = json.loads(Path(record['parse_attempt_path']).read_text())
    assert parse['status'] == 'BLOCKED'
    assert 'market-secret' not in json.dumps(record)
    no_publication(tmp_path / 'data')


@pytest.mark.parametrize('period', ['2025-01', '2019-12', '2020-01-01', '../2020-01', 42])
def test_invalid_period_fails_before_acquisition(pipeline, tmp_path, period):
    calls = []
    assert pipeline.run_series_pipeline(descriptor_file(tmp_path), tmp_path / 'data',
                                        period=period, transport=transport_for(calls=calls)) == 3
    assert calls == []
    assert attempts(tmp_path / 'data')[0]['error_type'] == 'SeriesDescriptorError'


def test_first_unpublished_and_all_published(pipeline, tmp_path):
    descriptor = descriptor_file(tmp_path)
    root = tmp_path / 'data'
    periods = SeriesDescriptor(BTC).object_periods
    for selected in periods:
        before = {p: p.read_bytes() for p in root.rglob('current.json')}
        assert pipeline.run_series_pipeline(descriptor, root,
                                            transport=transport_for(period=selected)) == 0
        assert (lane(root, period=selected) / 'current.json').is_file()
        assert all(p.read_bytes() == value for p, value in before.items())
    records = attempts(root)
    assert {r['selected_period'] for r in records} == set(periods)
    assert {r['selection_mode'] for r in records} == {'first_unpublished'}
    assert pipeline.run_series_pipeline(
        descriptor, root, transport=httpx.MockTransport(lambda _: pytest.fail('caught up')),
    ) == 0
    last = next(r for r in attempts(root) if r['terminal_state'] == 'VERIFIED_NO_OP')
    assert last['selected_period'] == periods[-1]


@pytest.fixture(scope='module')
def kraken_member():
    return b''.join(f'{t},12.3,13.4,11.2,12.4,19.8,2\n'.encode()
                    for t in range(1577836800, 1735689600, 3600))


def test_remote_kraken_uses_only_windowed_parser_input(
    pipeline, tmp_path, monkeypatch, kraken_member,
):
    full = b'1546300800,outside-window-must-not-parse\n' + kraken_member
    monkeypatch.setattr(acquisition_tests, 'PAYLOAD', full)
    _, anchor, calls, handler = acquisition_tests.kraken_source.__wrapped__(monkeypatch)
    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path, KRAKEN), tmp_path / 'data', period='2020-2024',
        transport=httpx.MockTransport(handler), sleeper=lambda _: None,
    ) == 0
    record = attempts(tmp_path / 'data')[0]
    assert calls and record['parser_input_sha256'] == sha(kraken_member)
    assert record['member_sha256'] == anchor.member_sha256 != sha(kraken_member)
    assert record['full_member_verification'] == 'acquirer_provenance'
    assert record['raw_format'] == 'zip_raw_deflate_member'
    acquired = json.loads(Path(record['acquirer_evidence_path']).read_text())
    assert sha(Path(acquired['raw_path']).read_bytes()) == acquired['raw_sha256']
    assert 'outside-window' not in json.dumps(record)
    assert not any('equal' in key for key in record)


def injected_local(pipeline, monkeypatch, member, *, change=None):
    def acquire(self):
        staging = self.data_root / 'staging' / self.attempt_id
        staging.mkdir(parents=True)
        raw = staging / 'selected.csv'
        raw.write_bytes(member)
        evidence_path = staging / 'acquisition.json'
        evidence_path.write_text('{}')
        result = acquisition.SeriesAcquisitionEvidence(
            KRAKEN, '2020-2024', self.attempt_id, raw, sha(member), len(member),
            'csv_2020_2024', self.archive.member, 'a' * 64, len(member) + 100,
            '12345678', None, None, None, False, 'kraken_frozen_a9_member_hash', evidence_path,
        )
        return replace(result, **(change or {}))

    monkeypatch.setattr(acquisition.SeriesAcquirer, 'acquire', acquire)


def test_local_kraken_separate_hash_domains(pipeline, tmp_path, monkeypatch, kraken_member):
    injected_local(pipeline, monkeypatch, kraken_member)
    assert run(pipeline, tmp_path, period='2020-2024', series=KRAKEN) == 0
    record = attempts(tmp_path / 'data')[0]
    assert record['parser_input_sha256'] == sha(kraken_member) != record['member_sha256']
    assert record['full_member_verification'] == 'acquirer_provenance'


@pytest.mark.parametrize('change', [{'raw_sha256': '0' * 64}, {'raw_size': 1},
                                   {'raw_format': 'unknown'}])
def test_retained_integrity_and_format_before_parsing(pipeline, tmp_path, monkeypatch, change):
    injected_local(pipeline, monkeypatch, b'1577836800,12,13,11,12,1,2\n', change=change)
    monkeypatch.setattr(pipeline, 'parse_kline_rows', lambda *a, **kw: pytest.fail('parsed'))
    assert run(pipeline, tmp_path, period='2020-2024', series=KRAKEN) == 3
    assert attempts(tmp_path / 'data')[0]['error_type']
    no_publication(tmp_path / 'data')


def test_binance_member_hash_gate(pipeline, tmp_path, monkeypatch):
    original = acquisition.SeriesAcquirer.acquire

    def altered(self):
        return replace(original(self), member_sha256='0' * 64)

    monkeypatch.setattr(acquisition.SeriesAcquirer, 'acquire', altered)
    monkeypatch.setattr(pipeline, 'parse_scalar_rows', lambda *a, **kw: pytest.fail('parsed'))
    assert run(pipeline, tmp_path) == 3
    no_publication(tmp_path / 'data')


def test_acquisition_failure_keeps_value_blind_evidence(pipeline, tmp_path):
    calls = []

    def fail(request):
        calls.append(str(request.url))
        return httpx.Response(404, content=b'synthetic-market-secret')

    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path), tmp_path / 'data', period='2020-01',
        transport=httpx.MockTransport(fail), sleeper=lambda _: None,
    ) == 3
    record = attempts(tmp_path / 'data')[0]
    assert len(calls) == 1 and record['error_type'] == 'DownloadFailed'
    assert Path(record['acquirer_evidence_path']).is_file()
    assert 'synthetic-market-secret' not in json.dumps(record)
    no_publication(tmp_path / 'data')


def test_discovery_failure_is_recorded(pipeline, tmp_path, monkeypatch):
    from quantara.publication import PublicationError

    def lost(*args):
        raise PublicationError('synthetic discovery failure')

    monkeypatch.setattr(pipeline, 'read_and_verify_current', lost)
    assert run(pipeline, tmp_path) == 3
    record = attempts(tmp_path / 'data')[0]
    assert record['terminal_state'] == 'FAILED' and record['error_type'] == 'PublicationError'


def test_remote_kraken_empty_selection_fails(pipeline, tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition_tests, 'PAYLOAD', b'1546300800,outside-window\n')
    _, _, _, handler = acquisition_tests.kraken_source.__wrapped__(monkeypatch)
    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path, KRAKEN), tmp_path / 'data', period='2020-2024',
        transport=httpx.MockTransport(handler), sleeper=lambda _: None,
    ) == 3
    record = attempts(tmp_path / 'data')[0]
    assert record['error_type'] == 'SeriesPipelineError'
    assert record['parse_attempt_path'] is None
    no_publication(tmp_path / 'data')


def test_deep_data_root_publishes(pipeline, tmp_path):
    # xdist adds another directory level; frozen object-store temporary names
    # can exceed Windows MAX_PATH even when the final object name fits.
    deep_root = tmp_path / ('nested-' + 'x' * 100) / 'data'
    calls = []
    assert pipeline.run_series_pipeline(
        descriptor_file(tmp_path), deep_root, period='2020-01',
        transport=transport_for(calls=calls), sleeper=lambda _: None,
    ) == 0
    assert len(calls) == 2
