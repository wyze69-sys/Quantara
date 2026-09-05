"""D05 proposed series findings, with no publication or approval authority.

Consume D03/D04 evidence and canonical rows without reconstructing source bytes
or canonical values. Native-grid absence is reported, never filled. The D04
serializer hashes a gap manifest enumerated from the supplied canonical times.
An unclassified gap remains pending review; same-key conflicts are terminal.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass

from quantara.jcs import canonicalize
from quantara.series_canonical import (
    GAP_SCHEMA_VERSION,
    KlineCanonicalError,
    KlineCanonicalRow,
    ScalarCanonicalRow,
    gap_manifest_hash,
    gap_schema_fingerprint,
    validate_kline_row,
)
from quantara.series_descriptor import SERIES_REGISTRY, SeriesArchive
from quantara.series_parsing import KlineParseResult, ScalarParseResult, _bounds, kline_bounds

SCHEMA_VERSION = 'quantara.series-quality/v1'
IDENTITY_DOMAIN = 'quantara-series-quality-v1'
CHECK_IDS = (
    'funding_interval_valid', 'funding_settlement_grid', 'oi_snapshot_grid',
    'oi_daily_boundary', 'kline_grid_completeness', 'kline_interval_invariants',
    'duplicate_exact_bytes', 'conflict_same_key', 'source_order', 'kraken_derived_close',
)
EXCLUSION_REASONS = (
    'missing_native_interval', 'incomplete_feature_window', 'funding_cadence_incomplete',
    'oi_snapshot_gap', 'invalid_label_endpoint', 'buffer_bar_missing', 'pre_archive_period',
    'eth_oi_pre_2021_12_01', 'same_key_conflict',
)
PROPOSAL_SCHEMA = 'quantara.series-quality-approval-proposal/v1'
_HASH = re.compile(r'[0-9a-f]{64}')


class SeriesQualityError(ValueError):
    """Unsupported input, invalid evidence, or an attempt to approve a hard failure."""


def _digest(payload: dict) -> str:
    return hashlib.sha256(canonicalize(payload).encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class Finding:
    check_id: str
    outcome: str
    severity: str
    count: int
    evidence: dict

    def __post_init__(self) -> None:
        if (self.check_id not in CHECK_IDS or self.outcome not in ('pass', 'warn', 'fail')
                or self.severity not in ('hard', 'warning')
                or type(self.count) is not int or self.count < 0
                or type(self.evidence) is not dict):
            raise SeriesQualityError('finding violates the closed quality vocabulary')
        if self.check_id == 'conflict_same_key' and (
            self.severity != 'hard' or self.outcome != ('fail' if self.count else 'pass')
        ):
            raise SeriesQualityError('same-key conflicts are terminal hard failures')


@dataclass(frozen=True, slots=True)
class SeriesQualityReport:
    series_id: str
    source_sha256: tuple[str, ...]
    findings: tuple[Finding, ...]

    def __post_init__(self) -> None:
        if (self.series_id not in SERIES_REGISTRY or type(self.source_sha256) is not tuple
                or not self.source_sha256 or any(type(h) is not str or not _HASH.fullmatch(h)
                                                for h in self.source_sha256)
                or type(self.findings) is not tuple or not self.findings
                or any(type(f) is not Finding for f in self.findings)):
            raise SeriesQualityError('invalid proposed series report')
        checks = tuple(f.check_id for f in self.findings)
        if checks != tuple(check for check in CHECK_IDS if check in checks):
            raise SeriesQualityError('findings must be unique and in closed vocabulary order')

    @property
    def state(self) -> str:
        if any(f.outcome == 'fail' for f in self.findings):
            return 'FAIL'
        return 'WARN' if any(f.outcome == 'warn' for f in self.findings) else 'PASS'

    def identity(self) -> str:
        """Only the packet's JCS preimage; no operational timestamps or authority."""
        return _digest({'domain': IDENTITY_DOMAIN, 'schema_version': SCHEMA_VERSION,
                        'findings': [asdict(f) for f in self.findings]})


def _inputs(parsed, canonical_rows):
    if type(parsed) not in (ScalarParseResult, KlineParseResult):
        raise SeriesQualityError('expected a D03/D04 parse result')
    if type(parsed.archive) is not SeriesArchive or parsed.archive.series_id not in SERIES_REGISTRY:
        raise SeriesQualityError('unsupported source series')
    spec = SERIES_REGISTRY[parsed.archive.series_id]
    scalar = spec.source_family in ('fundingRate', 'metrics')
    if type(parsed) is not (ScalarParseResult if scalar else KlineParseResult):
        raise SeriesQualityError('parse result family differs from registered series')
    if (type(parsed.source_sha256) is not str or not _HASH.fullmatch(parsed.source_sha256)
            or any(type(n) is not int or n < 0 for n in (
                parsed.source_rows, parsed.distinct_rows,
                parsed.duplicate_rows, parsed.conflict_rows))
            or type(parsed.source_ordered) is not bool
            or type(parsed.duplicate_hashes) is not tuple
            or len(parsed.duplicate_hashes) != parsed.duplicate_rows
            or any(type(h) is not str or not _HASH.fullmatch(h) for h in parsed.duplicate_hashes)
            or parsed.source_rows != parsed.distinct_rows + parsed.duplicate_rows
            or parsed.distinct_rows != len(parsed.rows)):
        raise SeriesQualityError('parse evidence is incomplete or inconsistent')
    try:
        rows = tuple(canonical_rows)
    except TypeError:
        raise SeriesQualityError('expected canonical rows') from None
    if len(rows) != parsed.distinct_rows:
        raise SeriesQualityError('canonical row count differs from parse evidence')
    for row in rows:
        if type(row) is not (ScalarCanonicalRow if scalar else KlineCanonicalRow):
            raise SeriesQualityError('canonical row type differs from series family')
        if (row.series_id != parsed.archive.series_id or row.source_sha256 != parsed.source_sha256
                or row.source_file != parsed.archive.member):
            raise SeriesQualityError('canonical provenance differs from parse evidence')
        if type(row.event_ts) is not int:
            raise SeriesQualityError('canonical event timestamp must be integer milliseconds')
    return spec, rows


def _sequence_failures(times: tuple[int, ...], start: int, end: int, step=None) -> int:
    return sum(not start <= t < end or (step is not None and t % step != 0)
               or (i > 0 and t <= times[i - 1]) for i, t in enumerate(times))


def _kline_gaps(parsed: KlineParseResult, times: tuple[int, ...]) -> dict:
    # Only timestamp enumeration here: no rebuilding or hashing canonical rows.
    start, end, step = kline_bounds(parsed.archive)
    present = {t for t in times if start <= t < end and t % step == 0}
    gaps = [
        {'series_id': parsed.archive.series_id, 'interval_open_ts': t,
         'interval_close_ts': t + step - 1, 'enumeration_basis': 'descriptor_period_native_grid',
         'exclusion_reason': None}
        for t in range(start, end, step) if t not in present
    ]
    return {
        'schema_version': GAP_SCHEMA_VERSION, 'schema_fingerprint': gap_schema_fingerprint(),
        'series_id': parsed.archive.series_id, 'period': parsed.archive.period,
        'source_file': parsed.archive.member, 'source_sha256': parsed.source_sha256,
        'period_start_ts': start, 'period_end_ts': end, 'native_step_ms': step,
        'expected_slots': (end - start) // step, 'present_slots': len(present),
        'gap_count': len(gaps), 'gaps': gaps,
    }


def evaluate_series_quality(parse_result, canonical_rows, *, ingestion_ts=None,
                            archive_publication_ts=None) -> SeriesQualityReport:
    """Produce value-blind findings, never an effective publication decision.

    Non-eight-hour funding intervals are warning notes, without an invented cap.
    OI absence is a warning in daily boundary evidence, separate from grid failure.
    Operational timestamps are accepted but never enter findings or identity.
    A successful parser result has zero conflicts; positive counts supplied in a
    tampered result still produce a terminal finding and can never be proposed
    for approval. Failed parse attempts themselves are not successful results.
    """
    parsed = parse_result
    spec, rows = _inputs(parsed, canonical_rows)
    times = tuple(row.event_ts for row in rows)
    findings = []

    def record(check, count=0, *, warning=False, **evidence):
        findings.append(Finding(check, ('warn' if warning else 'fail') if count else 'pass',
                                'warning' if warning else 'hard', count, evidence))

    if spec.source_family == 'fundingRate':
        intervals = [row.funding_interval_hours for row in rows]
        if any(type(v) is not str or not re.fullmatch(r'[0-9]{1,19}', v)
               or not 0 < int(v) < 2**63 for v in intervals):
            raise SeriesQualityError('structurally invalid funding interval evidence')
        counts = dict(sorted(Counter(intervals).items()))
        record('funding_interval_valid', sum(n for v, n in counts.items() if v != '8'),
               warning=True, observed_counts=counts)
        start, end = _bounds(parsed.archive)
        record('funding_settlement_grid', _sequence_failures(times, start, end),
               observed_settlements=len(times))
    elif spec.source_family == 'metrics':
        start, end = _bounds(parsed.archive)
        record('oi_snapshot_grid', _sequence_failures(times, start, end, 300000),
               native_step_ms=300000, observed_snapshots=len(times))
        present = {t for t in times if start <= t < end and t % 300000 == 0}
        gaps = [t for t in range(start, end, 300000) if t not in present]
        record('oi_daily_boundary', len(gaps), warning=True,
               first_snapshot_ts=min(times, default=None),
               last_snapshot_ts=max(times, default=None),
               expected_slots=(end - start) // 300000, present_slots=len(present),
               gap_count=len(gaps), gap_interval_open_ts=gaps)
    else:
        manifest = _kline_gaps(parsed, times)
        record('kline_grid_completeness', manifest['gap_count'], warning=True,
               expected_slots=manifest['expected_slots'], present_slots=manifest['present_slots'],
               gap_count=manifest['gap_count'], gap_manifest_hash=gap_manifest_hash(manifest),
               gap_interval_open_ts=[g['interval_open_ts'] for g in manifest['gaps']])
        start, end, step = kline_bounds(parsed.archive)
        invalid = 0
        for i, row in enumerate(rows):
            try:
                validate_kline_row(row)
                valid = start <= row.event_ts < end and (i == 0 or row.event_ts > times[i - 1])
            except KlineCanonicalError:
                valid = False
            invalid += not valid
        record('kline_interval_invariants', invalid, checked_rows=len(rows), native_step_ms=step)

    # D10: BTC OI provider archives before 2021-05-21 repeat whole rows
    # byte-for-byte. Parsing already deduplicates only exact bytes; any differing
    # same-key row remains a hard conflict above. Preserve the duplicate count and
    # hashes as audited evidence without turning information-neutral repetition
    # into a publication warning for this one reviewed series. Do not generalise
    # the disposition to another series without its own source audit.
    if parsed.archive.series_id == 'btc_open_interest_5m':
        findings.append(Finding(
            'duplicate_exact_bytes', 'pass', 'warning', parsed.duplicate_rows,
            {'source_rows': parsed.source_rows, 'distinct_rows': parsed.distinct_rows,
             'duplicate_rows': parsed.duplicate_rows,
             'duplicate_hash_count': len(parsed.duplicate_hashes)},
        ))
    else:
        record('duplicate_exact_bytes', parsed.duplicate_rows, warning=True,
               source_rows=parsed.source_rows, distinct_rows=parsed.distinct_rows,
               duplicate_rows=parsed.duplicate_rows,
               duplicate_hash_count=len(parsed.duplicate_hashes))
    record('conflict_same_key', parsed.conflict_rows, conflict_rows=parsed.conflict_rows)
    record('source_order', 0, warning=True,
           source_ordered=parsed.source_ordered)
    if spec.source_family == 'kraken':
        record('kraken_derived_close', sum(
            type(row.interval_open_ts) is not int or type(row.interval_close_ts) is not int
            or row.interval_close_ts != row.interval_open_ts + 3600000 - 1 for row in rows),
            checked_rows=len(rows), native_step_ms=3600000, close_is_source_observed=False)
    return SeriesQualityReport(parsed.archive.series_id, (parsed.source_sha256,), tuple(findings))


def gap_disposition(gap_manifest) -> dict:
    """Propose supplied reasons; bare D04 gaps remain unclassified pending review.

    No lookback or feature-window context is inferred from a native gap alone.
    A same-key conflict rejects the entire proposal: no approval disposition is
    returned for it, and no extra authorization field is added to the two-column
    table. These entries carry no approval authority, even for known reasons.
    """
    if type(gap_manifest) is not dict or type(gap_manifest.get('gaps')) is not list:
        raise SeriesQualityError('expected a gap manifest')
    dispositions = []
    previous = -1
    for gap in gap_manifest['gaps']:
        if type(gap) is not dict:
            raise SeriesQualityError('invalid gap entry')
        t = gap.get('interval_open_ts')
        if type(t) is not int or not previous < t < 2**63:
            raise SeriesQualityError('gap times must be nonnegative and strictly increasing')
        previous = t
        reason = gap.get('exclusion_reason')
        if reason == 'same_key_conflict':
            raise SeriesQualityError('same-key conflicts have no approval disposition')
        dispositions.append({'interval_open_ts': t,
                             'reason': reason if reason in EXCLUSION_REASONS
                             else 'unclassified_pending_review'})
    return {'gaps': dispositions}


def proposed_approval_payload(report, *, reviewer_placeholder=True) -> dict:
    """Return an explicitly unauthorized proposal, never a legacy approval record."""
    if type(report) is not SeriesQualityReport or reviewer_placeholder is not True:
        raise SeriesQualityError('proposals require a series report and reviewer placeholders')
    if report.state == 'FAIL':
        raise SeriesQualityError('hard failures have no approval proposal')
    payload = {
        'schema': PROPOSAL_SCHEMA, 'series_id': report.series_id,
        'source_sha256': list(report.source_sha256), 'quality_identity_sha256': report.identity(),
        'proposed_findings': [
            {'check_id': f.check_id, 'count': f.count, 'finding_sha256': _digest(asdict(f))}
            for f in report.findings if f.outcome == 'warn'
        ],
        'approver': 'PLACEHOLDER', 'decision_time_utc': 'PLACEHOLDER', 'authorized': False,
    }
    return {**payload, 'record_sha256': _digest(payload)}
