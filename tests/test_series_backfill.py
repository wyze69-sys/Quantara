"""D07: synthetic sources, real publication, bounded scheduling and honest linkage."""

import importlib
import json
from dataclasses import asdict
from pathlib import Path
from threading import Barrier, Event

import httpx
import pytest
import yaml

import test_series_acquisition as acquisition_tests
from quantara import series_pipeline as pipeline
from quantara.manifests import attempt_id_now, write_json
from quantara.series_descriptor import SeriesDescriptor
from test_series_pipeline import BTC, KRAKEN, ROOT, descriptor_file, funding, transport_for

PERIODS = ('2020-01', '2020-02', '2020-03', '2020-04')


@pytest.fixture(autouse=True)
def no_local_archive(monkeypatch):
    monkeypatch.delenv('QUANTARA_KRAKEN_ARCHIVE', raising=False)


@pytest.fixture
def backfill():
    return importlib.import_module('quantara.series_backfill')


@pytest.fixture
def small_inventory(monkeypatch):
    # Narrow only the test inventory; archive_for still enforces the real registry.
    monkeypatch.setattr(SeriesDescriptor, 'object_periods', property(lambda _: PERIODS))
    return PERIODS


def source(*, calls=None, blocked=None, failed=None):
    transports = {
        p: transport_for(period=p, member=funding(p, duplicate=(p == blocked)))
        for p in SeriesDescriptor(BTC).object_periods
    }

    def handle(request):
        period = next(p for p in transports if p in request.url.path)
        if calls is not None:
            calls.append(period)
        if period == failed:
            return httpx.Response(404, content=b'synthetic-market-secret')
        return transports[period].handle_request(request)

    return httpx.MockTransport(handle)


def no_contact(calls):
    def handle(request):
        calls.append(str(request.url))
        pytest.fail('unexpected acquisition')
    return httpx.MockTransport(handle)


def checked(result):
    assert sum(result.counts.values()) == len(result.outcomes)
    assert len(result.outcomes) + len(result.not_attempted) == len(result.periods)
    ran = tuple(o.period for o in result.outcomes)
    assert ran == tuple(p for p in result.periods if p not in result.not_attempted)
    assert len(set(ran)) == len(ran)
    for outcome in result.outcomes:
        manifest = json.loads(Path(outcome.attempt_path).read_bytes())
        assert manifest['attempt_id'] == outcome.attempt_id
        assert manifest['exit_code'] == outcome.exit_code
        assert manifest['terminal_state'] == outcome.terminal_state
        assert manifest['selected_period'] == outcome.manifest_selected_period
        assert outcome.manifest_selected_period in (None, outcome.period)
        if outcome.manifest_selected_period is None:
            assert outcome.terminal_state in ('BLOCKED', 'FAILED')
    return result


def invoke(backfill, tmp_path, **kwargs):
    kwargs.setdefault('transport', source())
    kwargs.setdefault('sleeper', lambda _: None)
    return checked(backfill.run_series_backfill(
        descriptor_file(tmp_path), tmp_path / 'data', **kwargs,
    ))


def test_full_serial_publish_and_resume(backfill, tmp_path, small_inventory):
    first = invoke(backfill, tmp_path)
    assert first.periods == PERIODS
    assert first.counts == {'PUBLISHED': 4}
    assert first.exit_code == 0 and first.stopped_at is None and first.preflight is None
    assert first.not_attempted == ()
    commits = {p: p.read_bytes() for p in (tmp_path / 'data').rglob('COMMITTED')}
    pointers = {p: p.read_bytes() for p in (tmp_path / 'data').rglob('current.json')}
    assert len(commits) == len(pointers) == 4
    calls = []
    second = invoke(backfill, tmp_path, transport=no_contact(calls))
    assert second.counts == {'VERIFIED_NO_OP': 4}
    assert calls == [] and second.exit_code == 0
    assert {p: p.read_bytes() for p in (tmp_path / 'data').rglob('COMMITTED')} == commits
    assert {p: p.read_bytes() for p in (tmp_path / 'data').rglob('current.json')} == pointers
    assert {o.attempt_id for o in first.outcomes}.isdisjoint(
        {o.attempt_id for o in second.outcomes},
    )
    assert len(list((tmp_path / 'data/attempts').glob('*.json'))) == 8


@pytest.mark.parametrize(('start', 'end', 'expected'), [
    ('2020-02', '2020-03', PERIODS[1:3]),
    (None, '2020-02', PERIODS[:2]),
    ('2020-03', None, PERIODS[2:]),
    (None, None, PERIODS),
])
def test_inclusive_range_defaults(backfill, tmp_path, small_inventory, start, end, expected):
    calls = []
    result = invoke(backfill, tmp_path, start=start, end=end, transport=source(calls=calls))
    assert result.periods == tuple(o.period for o in result.outcomes) == expected
    assert set(calls) == set(expected)


@pytest.mark.parametrize('endpoint', ['start', 'end'])
@pytest.mark.parametrize('value', ['2025-01', '1999-01', 'bogus', 42])
def test_nonmember_before_execution(backfill, tmp_path, endpoint, value):
    calls = []
    with pytest.raises(backfill.BackfillRangeError):
        invoke(backfill, tmp_path, transport=no_contact(calls), **{endpoint: value})
    assert calls == [] and not (tmp_path / 'data').exists()


def test_inverted_range(backfill, tmp_path):
    calls = []
    with pytest.raises(backfill.BackfillRangeError):
        invoke(backfill, tmp_path, start='2020-02', end='2020-01', transport=no_contact(calls))
    assert calls == [] and not (tmp_path / 'data').exists()


def test_empty_inventory(backfill, tmp_path, monkeypatch):
    monkeypatch.setattr(SeriesDescriptor, 'object_periods', property(lambda _: ()))
    calls = []
    with pytest.raises(backfill.BackfillRangeError):
        invoke(backfill, tmp_path, transport=no_contact(calls))
    assert calls == [] and not (tmp_path / 'data').exists()


@pytest.mark.parametrize('workers', [0, 5, -1, 2.5, True, '2'])
def test_workers_before_execution(backfill, tmp_path, workers):
    calls = []
    with pytest.raises(backfill.BackfillWorkersError):
        invoke(backfill, tmp_path, workers=workers, transport=no_contact(calls))
    assert calls == [] and not (tmp_path / 'data').exists()


def test_descriptor_order_not_lexical_order(backfill, tmp_path, monkeypatch):
    inventory = ('2020-03', '2020-01', '2020-02')
    monkeypatch.setattr(SeriesDescriptor, 'object_periods', property(lambda _: inventory))
    result = invoke(backfill, tmp_path, start='2020-03', end='2020-02')
    assert result.periods == tuple(o.period for o in result.outcomes) == inventory


def test_workers_four_staggered_real_pipeline_order(
    backfill, tmp_path, small_inventory, monkeypatch,
):
    serial_root = tmp_path / 'serial'
    serial_root.mkdir()
    serial = invoke(backfill, serial_root)
    original = backfill.run_series_pipeline
    barrier = Barrier(4)
    finished = {p: Event() for p in PERIODS}
    completion = []

    def staggered(*args, period, **kwargs):
        barrier.wait(timeout=30)
        code = original(*args, period=period, **kwargs)
        index = PERIODS.index(period)
        if index < 3:
            assert finished[PERIODS[index + 1]].wait(30)
        completion.append(period)
        finished[period].set()
        return code

    monkeypatch.setattr(backfill, 'run_series_pipeline', staggered)
    parallel = invoke(backfill, tmp_path, workers=4)
    assert completion == list(reversed(PERIODS))

    def ordering_bytes(result):
        # IDs and paths identify distinct invocations; all ordered semantic fields match.
        return json.dumps([
            {k: v for k, v in asdict(o).items() if k not in ('attempt_id', 'attempt_path')}
            for o in result.outcomes
        ], sort_keys=True).encode()

    assert ordering_bytes(parallel) == ordering_bytes(serial)
    assert parallel.counts == serial.counts == {'PUBLISHED': 4}


@pytest.mark.parametrize(('blocked', 'failed', 'state', 'code'), [
    ('2020-02', None, 'BLOCKED', 2),
    (None, '2020-02', 'FAILED', 3),
])
def test_serial_stop(backfill, tmp_path, small_inventory, blocked, failed, state, code):
    calls = []
    result = invoke(backfill, tmp_path, transport=source(
        calls=calls, blocked=blocked, failed=failed,
    ))
    assert tuple(o.period for o in result.outcomes) == PERIODS[:2]
    assert result.not_attempted == PERIODS[2:]
    assert result.stopped_at == '2020-02' and result.exit_code == code
    assert result.counts == {'PUBLISHED': 1, state: 1}
    assert set(calls) == set(PERIODS[:2])


def test_concurrent_failure_drains_batch_and_stops(backfill, tmp_path, monkeypatch):
    original = backfill.run_series_pipeline
    barrier = Barrier(4)
    began = []
    finished = []

    def together(*args, period, **kwargs):
        began.append(period)
        barrier.wait(timeout=30)
        code = original(*args, period=period, **kwargs)
        finished.append(period)
        return code

    monkeypatch.setattr(backfill, 'run_series_pipeline', together)
    result = invoke(backfill, tmp_path, end='2020-08', workers=4,
                    transport=source(blocked='2020-02', failed='2020-03'))
    assert set(began) == set(finished) == set(PERIODS)
    assert result.not_attempted == ('2020-05', '2020-06', '2020-07', '2020-08')
    assert result.counts == {'PUBLISHED': 2, 'BLOCKED': 1, 'FAILED': 1}
    assert result.exit_code == 3 and result.stopped_at in ('2020-02', '2020-03')
    assert len(list((tmp_path / 'data/attempts').glob('*.json'))) == 4


@pytest.mark.parametrize('workers', [1, 2, 3, 4])
def test_dry_run_no_publication(backfill, tmp_path, small_inventory, workers):
    calls = []
    result = invoke(backfill, tmp_path, workers=workers, dry_run=True,
                    transport=no_contact(calls))
    assert result.counts == {'VERIFIED_NO_OP': 4} and result.exit_code == 0
    assert calls == [] and not (tmp_path / 'data/datasets').exists()
    assert all(json.loads(Path(o.attempt_path).read_bytes())['dry_run'] for o in result.outcomes)


def test_value_blind_result_and_logs(backfill, tmp_path, small_inventory, capsys):
    result = invoke(backfill, tmp_path, transport=source(failed='2020-03'))
    output = capsys.readouterr()
    serialized = json.dumps(asdict(result), default=str)
    for secret in ('-0.000123456789012345', 'synthetic-market-secret'):
        assert secret not in serialized + repr(result) + output.out + output.err


def test_kraken_single_period_real_synthetic_pipeline(backfill, tmp_path, monkeypatch):
    member = b''.join(f'{t},12.3,13.4,11.2,12.4,19.8,2\n'.encode()
                      for t in range(1577836800, 1735689600, 3600))
    monkeypatch.setattr(acquisition_tests, 'PAYLOAD', member)
    _, _, calls, handler = acquisition_tests.kraken_source.__wrapped__(monkeypatch)
    result = checked(backfill.run_series_backfill(
        descriptor_file(tmp_path, KRAKEN), tmp_path / 'data',
        transport=httpx.MockTransport(handler), sleeper=lambda _: None,
    ))
    assert result.periods == ('2020-2024',) and result.counts == {'PUBLISHED': 1}
    assert result.exit_code == 0 and calls


def rights_repo(tmp_path, denied):
    name = SeriesDescriptor(BTC).legal_record + '.yaml'
    record = yaml.safe_load((ROOT / 'configs/legal' / name).read_text())
    for operation in denied:
        record['operations'][operation]['state'] = 'PROHIBITED'
    legal = tmp_path / 'repo/configs/legal'
    legal.mkdir(parents=True)
    (legal / name).write_text(yaml.safe_dump(record), encoding='utf-8')
    return tmp_path / 'repo'


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('denied', [('acquire_internal',), pipeline._OPERATIONS])
def test_rights_preflight_no_attempts(backfill, tmp_path, small_inventory, monkeypatch,
                                    workers, denied):
    root = rights_repo(tmp_path, denied)
    calls = []
    monkeypatch.setattr(backfill, 'run_series_pipeline',
                        lambda *a, **kw: pytest.fail('preflight must not attempt a period'))
    result = invoke(backfill, tmp_path, repo_root=root, workers=workers,
                    transport=no_contact(calls))
    assert result.outcomes == () and result.not_attempted == PERIODS
    assert result.counts == {} and result.stopped_at is None and result.exit_code == 2
    assert result.preflight['gate'] == 'rights'
    assert result.preflight['denied'] == denied
    assert set(result.preflight['states']) == set(pipeline._OPERATIONS)
    assert all(result.preflight['states'][op] == 'PROHIBITED' for op in denied)
    assert calls == [] and not (tmp_path / 'data').exists()


def test_real_frozen_rights_are_permitted(backfill, tmp_path, small_inventory):
    rights = SeriesDescriptor(BTC).load_rights(ROOT)
    assert all(rights.operations[op].state == 'OWNER_APPROVED_PENDING_COUNSEL'
               and rights.permits(op) for op in pipeline._OPERATIONS)
    result = invoke(backfill, tmp_path)
    assert result.preflight is None and result.counts == {'PUBLISHED': 4}
    assert backfill._OPERATIONS is pipeline._OPERATIONS


def test_snapshot_ignores_older_lexically_newer_attempt(backfill, tmp_path, monkeypatch):
    ids = iter(('99999999T235959Z-older', '00000000T000000Z-newer'))
    monkeypatch.setattr(pipeline, 'attempt_id_now', lambda: next(ids))
    first = invoke(backfill, tmp_path, start='2020-01', end='2020-01')
    second = invoke(backfill, tmp_path, start='2020-01', end='2020-01')
    assert first.outcomes[0].attempt_id == '99999999T235959Z-older'
    assert second.outcomes[0].attempt_id == '00000000T000000Z-newer'
    assert second.counts == {'VERIFIED_NO_OP': 1}


@pytest.mark.parametrize('workers', [1, 4])
def test_rights_change_after_preflight_preserves_null(backfill, tmp_path, monkeypatch, workers):
    root = rights_repo(tmp_path, ())
    original = backfill.run_series_pipeline

    def revoke(*args, **kwargs):
        name = SeriesDescriptor(BTC).legal_record + '.yaml'
        path = root / 'configs/legal' / name
        record = yaml.safe_load(path.read_text())
        record['operations']['acquire_internal']['state'] = 'PROHIBITED'
        path.write_text(yaml.safe_dump(record), encoding='utf-8')
        return original(*args, **kwargs)

    monkeypatch.setattr(backfill, 'run_series_pipeline', revoke)
    calls = []
    result = invoke(backfill, tmp_path, repo_root=root, workers=workers,
                    start='2020-01', end='2020-01', transport=no_contact(calls))
    assert result.preflight is None and result.exit_code == 2
    assert result.stopped_at == '2020-01' and result.counts == {'BLOCKED': 1}
    assert result.outcomes[0].manifest_selected_period is None and calls == []


def synthetic_attempt(root, period, *, state='FAILED', code=3, **changes):
    identity = attempt_id_now()
    record = dict(schema='quantara.series-pipeline-attempt/v1', series_id=BTC,
                  selected_period=period, terminal_state=state, exit_code=code,
                  attempt_id=identity)
    record.update(changes)
    write_json(Path(root) / 'attempts' / f'{identity}.json', record)


@pytest.mark.parametrize('number', [0, 2])
def test_snapshot_requires_exactly_one_manifest(backfill, tmp_path, monkeypatch, number):
    def broken(descriptor_path, data_root, *, period, **kwargs):
        for _ in range(number):
            synthetic_attempt(data_root, period)
        return 3

    monkeypatch.setattr(backfill, 'run_series_pipeline', broken)
    with pytest.raises(backfill.BackfillManifestError):
        invoke(backfill, tmp_path, end='2020-01')


@pytest.mark.parametrize('change', [
    {'selected_period': '2020-02'},
    {'selected_period': None, 'terminal_state': 'PUBLISHED', 'exit_code': 0},
    {'attempt_id': 'wrong-file'},
    {'exit_code': 2},
    {'series_id': 'eth_settled_funding'},
])
def test_invalid_manifest_is_not_misattributed(backfill, tmp_path, monkeypatch, change):
    def broken(descriptor_path, data_root, *, period, **kwargs):
        synthetic_attempt(data_root, period, **change)
        return 3

    monkeypatch.setattr(backfill, 'run_series_pipeline', broken)
    with pytest.raises(backfill.BackfillManifestError):
        invoke(backfill, tmp_path, end='2020-01')


def test_two_null_manifests_in_batch_raise(backfill, tmp_path, monkeypatch):
    barrier = Barrier(2)

    def broken(descriptor_path, data_root, *, period, **kwargs):
        barrier.wait(timeout=30)
        synthetic_attempt(data_root, None)
        return 3

    monkeypatch.setattr(backfill, 'run_series_pipeline', broken)
    with pytest.raises(backfill.BackfillManifestError):
        invoke(backfill, tmp_path, end='2020-02', workers=2)
    assert len(list((tmp_path / 'data/attempts').glob('*.json'))) == 2


def test_single_null_manifest_in_mixed_batch(backfill, tmp_path, monkeypatch):
    original = backfill.run_series_pipeline
    barrier = Barrier(4)

    def early_failure(descriptor_path, data_root, *, period, **kwargs):
        barrier.wait(timeout=30)
        if period == '2020-02':
            synthetic_attempt(data_root, None)
            return 3
        return original(descriptor_path, data_root, period=period, **kwargs)

    monkeypatch.setattr(backfill, 'run_series_pipeline', early_failure)
    result = invoke(backfill, tmp_path, end='2020-06', workers=4)
    assert result.counts == {'PUBLISHED': 3, 'FAILED': 1}
    assert result.outcomes[1].manifest_selected_period is None
    assert result.stopped_at == '2020-02' and result.not_attempted == ('2020-05', '2020-06')
