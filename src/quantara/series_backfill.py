"""Bounded frozen-range orchestration over the unchanged single-period pipeline.

Only attempt manifests are inspected here. Verified-pointer resume, rights
rechecks, acquisition and publication remain entirely owned by the pipeline.
"""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from quantara.series_descriptor import load_series_descriptor
from quantara.series_pipeline import _OPERATIONS, _storage_root, run_series_pipeline

_ROOT = Path(__file__).resolve().parents[2]
_TERMINAL_CODES = {'PUBLISHED': 0, 'VERIFIED_NO_OP': 0, 'BLOCKED': 2, 'FAILED': 3}


class BackfillError(ValueError):
    """The backfill request or its invocation evidence is invalid."""


class BackfillRangeError(BackfillError):
    """Endpoints do not select a nonempty contiguous frozen inventory slice."""


class BackfillWorkersError(BackfillError):
    """Worker count is not an integer in the closed interval 1..4."""


class BackfillManifestError(BackfillError):
    """New attempt evidence is missing, inconsistent or ambiguously attributed."""


@dataclass(frozen=True)
class PeriodOutcome:
    period: str
    exit_code: int
    terminal_state: str
    attempt_id: str
    attempt_path: Path
    manifest_selected_period: str | None


@dataclass(frozen=True)
class BackfillResult:
    series_id: str
    periods: tuple[str, ...]
    outcomes: tuple[PeriodOutcome, ...]
    counts: dict[str, int]
    stopped_at: str | None
    not_attempted: tuple[str, ...]
    exit_code: int
    preflight: dict | None = None


def _select(inventory, start, end):
    if not inventory:
        raise BackfillRangeError('empty frozen inventory')
    start = inventory[0] if start is None else start
    end = inventory[-1] if end is None else end
    if (type(start) is not str or type(end) is not str
            or start not in inventory or end not in inventory):
        raise BackfillRangeError('endpoints must belong to the frozen inventory')
    first, last = inventory.index(start), inventory.index(end)
    if first > last:
        raise BackfillRangeError('start follows end in descriptor order')
    return inventory[first:last + 1]


def _snapshot(directory):
    try:
        return {p.name for p in directory.iterdir() if p.is_file()}
    except FileNotFoundError:
        return set()
    except OSError:
        raise BackfillManifestError('attempt directory cannot be inspected') from None


def _outcomes(directory, before, codes, series_id):
    """Attribute only newly created files; do not use names as chronology."""
    names = _snapshot(directory) - before
    if len(names) != len(codes):
        raise BackfillManifestError('expected one new manifest per invocation')
    by_period = {}
    unselected = []
    for name in sorted(names):
        path = directory / name
        try:
            record = json.loads(path.read_bytes())
            state = record['terminal_state']
            code = record['exit_code']
            selected = record['selected_period']
            identity = record['attempt_id']
            valid = (
                record['schema'] == 'quantara.series-pipeline-attempt/v1'
                and record['series_id'] == series_id
                and type(identity) is str and identity == path.stem and path.suffix == '.json'
                and type(code) is int and code == _TERMINAL_CODES[state]
                and (selected is None or type(selected) is str)
            )
        except (OSError, ValueError, KeyError, TypeError):
            raise BackfillManifestError('invalid new attempt manifest') from None
        if not valid:
            raise BackfillManifestError('inconsistent new attempt manifest')
        evidence = (path, record)
        if selected is None:
            if state not in ('BLOCKED', 'FAILED'):
                raise BackfillManifestError('success cannot precede period selection')
            unselected.append(evidence)
        elif selected not in codes or selected in by_period:
            raise BackfillManifestError('new manifest period attribution is not unique')
        else:
            by_period[selected] = evidence

    # Correction 1 permits one null-selection manifest. There is then exactly
    # one unmatched invocation; two nulls have no defensible period mapping.
    missing = tuple(p for p in codes if p not in by_period)
    if unselected:
        unselected.sort(key=lambda item: item[1]['attempt_id'])
        if len(unselected) != 1 or len(missing) != 1:
            raise BackfillManifestError('ambiguous pre-selection batch manifests')
        by_period[missing[0]] = unselected[0]
    if set(by_period) != set(codes):
        raise BackfillManifestError('invocation is missing its attempt manifest')

    result = []
    for period, code in codes.items():
        path, record = by_period[period]
        if type(code) is not int or record['exit_code'] != code:
            raise BackfillManifestError('pipeline exit differs from its manifest')
        result.append(PeriodOutcome(
            period, code, record['terminal_state'], record['attempt_id'], path,
            record['selected_period'],
        ))
    return tuple(result)


def run_series_backfill(
    descriptor_path, data_root, *, start=None, end=None, workers=1,
    transport=None, sleeper=None, repo_root=None, dry_run=False,
) -> BackfillResult:
    """Run a closed inventory slice, draining a failing batch without refilling it.

    Rights denial is a series preflight result with no attempted periods. Every
    executed call still performs its own pipeline rights check. Concurrent calls
    use batches of at most four and one attempt-directory snapshot per batch.
    Outcomes always follow descriptor order; stopped_at is the first observed
    nonzero pipeline return. Missing or ambiguous evidence raises a typed error
    after in-flight calls finish, never a fabricated aggregate result.
    """
    if type(workers) is not int or not 1 <= workers <= 4:
        raise BackfillWorkersError('workers must be an integer from 1 through 4')
    root = _ROOT if repo_root is None else Path(repo_root)
    descriptor = load_series_descriptor(descriptor_path, repo_root=root)
    rights = descriptor.load_rights(root)
    denied = tuple(op for op in _OPERATIONS if not rights.permits(op))
    periods = _select(descriptor.object_periods, start, end)
    if denied:
        return BackfillResult(descriptor.series_id, periods, (), {}, None, periods, 2, {
            'gate': 'rights', 'denied': denied,
            'states': {op: rights.operations[op].state for op in _OPERATIONS},
        })

    directory = _storage_root(data_root) / 'attempts'
    outcomes = []
    stopped_at = None

    def run(period):
        # archive_for validation remains inside the frozen pipeline invocation.
        return run_series_pipeline(
            descriptor_path, data_root, period=period, dry_run=dry_run,
            transport=transport, sleeper=sleeper, repo_root=root,
        )

    def batch(selected, executor=None):
        nonlocal stopped_at
        before = _snapshot(directory)
        codes = {}
        if executor is None:
            period = selected[0]
            codes[period] = run(period)
            if codes[period] in (2, 3):
                stopped_at = period
        else:
            futures = {}
            for period in selected:
                # Do not keep submitting if a fast failure is already visible.
                if any(f.done() and f.result() in (2, 3) for f in futures):
                    break
                futures[executor.submit(run, period)] = period
            for future in as_completed(futures):
                period = futures[future]
                codes[period] = future.result()
                if stopped_at is None and codes[period] in (2, 3):
                    stopped_at = period
        ordered_codes = {p: codes[p] for p in selected if p in codes}
        return _outcomes(directory, before, ordered_codes, descriptor.series_id)

    if workers == 1:
        for period in periods:
            outcomes.extend(batch((period,)))
            if stopped_at is not None:
                break
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for offset in range(0, len(periods), workers):
                outcomes.extend(batch(periods[offset:offset + workers], executor))
                if stopped_at is not None:
                    break

    attempted = {o.period for o in outcomes}
    return BackfillResult(
        descriptor.series_id, periods, tuple(outcomes),
        dict(Counter(o.terminal_state for o in outcomes)), stopped_at,
        tuple(p for p in periods if p not in attempted),
        max((o.exit_code for o in outcomes), default=0),
    )
