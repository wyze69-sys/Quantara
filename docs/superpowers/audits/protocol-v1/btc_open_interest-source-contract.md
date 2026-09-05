# btc_open_interest_5m — source contract and boundary acceptance (S02-A)

**Status:** COMPLETE
**Correction D10:** F-S02A-1 is CLOSED. Exact-byte repeats for this reviewed series
are preserved as counted and hashed informational evidence but no longer block deterministic
deduplication. Missing native slots and all hard failures remain blocking. See
`docs/superpowers/plans/2026-09-05-protocol-v1-d10-btc-oi-exact-duplicate-disposition.md`.
**Series:** `btc_open_interest_5m` (Binance USD-M futures BTCUSDT metrics, 5-minute open-interest snapshots)
**Descriptor:** `configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml`
**Frozen window:** 2020-09-01 … 2024-12-31, 1583 daily objects
**Packet:** S02-A, Stage 2 stop S02, Protocol v1
**Date:** 2026-09-05

## Scope

S02-A establishes the source contract for the second frozen series and accepts it against
real archives at the boundaries. It does not publish the series to the production data
root; that is S02-C, and it cannot start until the finding below is dispositioned.

No open-interest value appears in this document, in the committed tests, or in any
evidence file. Row counts, timestamps, hashes, finding identifiers and terminal states
only.

## What the source actually looks like

The archive shape was established by value-blind probes against
`data.binance.vision`, not assumed from the funding series:

| Fact | Value |
| --- | --- |
| Object cadence | daily ZIP, one CSV member |
| Observation cadence | 5 minutes, 288 slots per full day |
| CSV header | present, exact ordered 8-column metrics family header |
| Canonical value | `sum_open_interest` |
| Timestamp column | `create_time`, `YYYY-MM-DD HH:MM:SS`, interpreted UTC |
| Timestamp role | `UNRESOLVED_CONSERVATIVE` |
| Provider integrity | adjacent `.CHECKSUM` file, `binance_adjacent_checksum` |

The `create_time` stamp is a snapshot label. Binance does not document whether it marks
the open or the close of the 5-minute window it summarises, so the descriptor refuses to
relabel it: `interval_open_ts` and `interval_close_ts` stay null and eligibility is
deferred by one full snapshot interval (300000 ms), never by the +1 ms used for a settled
funding event. A negative control pins this arithmetic — `event_ts + 1`, `event_ts`, and a
tampered snapshot stamp are all rejected by `validate_scalar_row`.

## Finding F-S02A-1 — the early archive repeats every row

**Severity at S02-A:** warning (`WARN`), **State:** CLOSED by D10,
**Disposition:** exact-byte repeats are informational for `btc_open_interest_5m` only

Between 2020-09-01 and 2021-05-20 the provider CSV contains every row twice,
byte-for-byte identical: 576 source rows carrying 288 distinct `create_time` values. From
2021-05-21 the archive is single-rowed. A value-blind binary search over the frozen window
located that transition exactly; 2021-05-21 is the only mixed day (292 rows, 284 distinct)
and the flip does not oscillate afterwards.

Two properties make this a warning rather than a hard failure:

- Duplicates are byte-identical, so no row disagrees with another. `conflict_rows` is 0 on
  every probed day. A same-key row with any different byte — including `1.50` where `1.5`
  was seen, which is numerically equal but textually distinct — raises
  `OpenInterestDuplicateConflict` and can never be proposed for approval.
- Every retained stamp is on the native 5-minute grid, so deduplication recovers exactly
  288 canonical rows for a full doubled day with no interpolation.

The S02-A pipeline therefore stopped rather than publishing, which was the designed
behaviour before a disposition existed. D10 closes that finding narrowly: exact-byte
repetition is now informational for this series after deterministic deduplication. Days
with missing native slots still stop on `oi_daily_boundary`; same-key different-byte rows
remain hard failures.

A second, unrelated shape also warns: some days carry fewer than 288 snapshots
(2021-10-01 has 287). The missing slot is enumerated exactly and never filled.

## Boundary acceptance against real archives

Five periods were chosen from the probe results rather than guessed: the first frozen day,
the last fully doubled day, the transition day, a short day, and the last frozen day. Each
ran the frozen pipeline end to end over real HTTP with a fail-closed two-URL allowlist.

| Period | Terminal state | Exit | Source rows | Distinct | Duplicates | Conflicts | Off-grid | Non-pass findings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020-09-01 | BLOCKED | 2 | 576 | 288 | 288 | 0 | 0 | `duplicate_exact_bytes` |
| 2021-05-20 | BLOCKED | 2 | 576 | 288 | 288 | 0 | 0 | `duplicate_exact_bytes` |
| 2021-05-21 | BLOCKED | 2 | 292 | 284 | 8 | 0 | 0 | `duplicate_exact_bytes`, `oi_daily_boundary` |
| 2021-10-01 | BLOCKED | 2 | 287 | 287 | 0 | 0 | 0 | `oi_daily_boundary` |
| 2024-12-31 | PUBLISHED | 0 | 288 | 288 | 0 | 0 | 0 | none |

Verified across all five: provider CHECKSUM matched the stored ZIP 5/5; every snapshot
on-grid 5/5; conflicts 0 5/5; eligibility delay exactly 300000 ms 5/5; timestamp role
`UNRESOLVED_CONSERVATIVE` 5/5. For the four blocked periods: no pointer was written, and
the approval proposal carries `authorized: false` with approver `PLACEHOLDER` 4/4. For the
published period: parser-input hash, source hash and recomputed quality identity all
matched the authenticated commit graph, and the rerun was a `VERIFIED_NO_OP` with zero
further requests.

Requests stayed inside the exact two-URL allowlist for every period, and no challenge or
anti-bot response was encountered or bypassed.

## Tests

- `tests/test_series_btc_oi.py` — 43 offline contract tests, synthetic payloads, network
  disabled by an autouse fixture that fails the test if any real transport is used.
- `tests/test_integration_series_btc_oi.py` — 3 real-archive acceptance tests behind the
  `integration` marker, which the default `addopts` deselects.

Coverage worth naming: exact ordered header (4 rejected permutations), `create_time`
grammar (6 rejected forms including an impossible calendar date), symbol mismatch,
byte-identical repeat versus same-key conflict (4 conflict variants), exact-decimal
round-trip through Parquet at 18 dp, negative and non-numeric values, out-of-day stamps
rejected before payload parsing, off-grid as hard failure versus short day as warning,
provider checksum corruption, warning-bearing day blocked without approval, and a clean
day publishing then rerunning to `VERIFIED_NO_OP`.

### The tests were proven capable of failing

A suite that passes on first write is unproven. Five mutation probes each rebound one
frozen behaviour to a plausible wrong variant while keeping every public symbol in place —
deleting a module would only prove an `ImportError`, which says nothing about behaviour.

| Mutation | Expected detector | Result |
| --- | --- | --- |
| Byte-identical repeat raises a conflict | duplicate handling | RED |
| Eligibility delay relaxed to +1 ms | conservative eligibility | RED |
| Off-grid stamps snapped onto the grid | hard grid check | RED |
| WARN findings stripped so the period publishes | publication gate | RED |
| Symbol column no longer checked | symbol validation | RED |

All five turned the suite red; the restored suite returned 43 passed. Generated plugins are
deleted in a `finally` block so no scaffolding survives in the tree.

## Verification

| Gate | Result |
| --- | --- |
| `ruff check src tests benchmarks` | clean |
| Offline contract tests | 43 passed |
| Real-archive acceptance tests | 3 passed |
| Full suite | 2150 passed, 1 skipped, exit 0 |
| Mutation probes | 5/5 detected, restored suite green |
| Frozen production code and descriptors | unchanged, empty diff |
| Production `data/` | untouched; probes used disposable roots outside the repo |

The full suite moved from 2107 to 2150 (+43 offline tests; the 3 integration tests are
deselected by default). The single warning is pre-existing, from a ZIP fixture in
`tests/test_archive.py`.

## What S02-A does not establish

- The series is not published. Only the throwaway boundary roots hold objects.
- Only 5 of 1583 days were acquired. A full inventory remains S02-B; it must enumerate
  every missing native slot and any additional source variants without changing this narrow
  exact-duplicate disposition.
- F-S02A-1 is closed by D10 for exact-byte repeats only. This is a reviewed quality
  disposition, not an approval record and not a wildcard for other findings.
- Whether other Binance metrics series share the doubling is untested; each frozen series
  gets its own probe rather than an assumption inherited from this one.
