# btc_settled_funding — full inventory and provisional quality (S01-B)

**Status:** COMPLETE with one finding against shared acquisition robustness.
**Series:** `btc_settled_funding` (Binance USD-M futures, BTCUSDT settled funding rate)
**Descriptor:** `configs/series/binance-usdm-btcusdt-funding-settled-2020-2024.yaml`
**Inventory:** all 60 frozen monthly objects, `2020-01` through `2024-12`
**Date:** 2026-09-05
**Baseline:** `main` at `7dbbbb8af83cd57f2d9d289dd57a8581d98b55fb`

This is stop B of the uniform source-packet protocol: full inventory, every checksum
verified, every timestamp enumerated, and a **proposed** quality report. Nothing here is
an approval and no production pointer was moved. All 60 periods were acquired, parsed,
canonicalized and published into a temporary data root only.

## 1. Aggregate result

| Measure | Value |
| --- | --- |
| Periods in frozen inventory | 60 |
| Periods acquired and published | 60 |
| HTTP requests | 120 (2 per period: archive + adjacent `.CHECKSUM`) |
| Requests outside the exact allowlist | 0 |
| Provider checksum matches retained ZIP | 60 / 60 |
| Parser input hash matches published graph | 60 / 60 |
| Total settlement rows | 5481 |
| Distinct rows | 5481 |
| Duplicate rows | 0 |
| Same-key conflict rows | 0 |
| Source byte order strictly increasing | 60 / 60 |
| Observed `funding_interval_hours` | `8` for all 5481 rows |
| Quality state | PASS on all 60 periods |
| Non-`PASS` findings | none |
| First settlement | 2020-01-01T00:00:00Z |
| Last settlement | 2024-12-31T16:00:00Z |

Row count is independently consistent with the calendar: 1827 days across 2020–2024 at
three settlements per day = 5481, and every individual month equals its day count times
three. No month is short.

## 2. Cadence

Settlements are event-cadence, so no fixed grid was assumed. Consecutive deltas were
computed across the whole 60-month series in chronological order, spanning month
boundaries.

| Measure | Value |
| --- | --- |
| Deltas examined | 5480 |
| Negative or zero deltas | 0 |
| Deltas more than 60 s from 8 h | 0 |
| Distinct delta values | 70 |
| Delta spread around 8 h | -4 ms to +5 ms (in the ten most common) |

Ten most common deltas:

| Delta | Count |
| --- | --- |
| 28800000 ms | 2190 |
| 28800001 ms | 414 |
| 28799999 ms | 393 |
| 28799998 ms | 140 |
| 28800004 ms | 126 |
| 28800002 ms | 122 |
| 28800003 ms | 121 |
| 28799996 ms | 117 |
| 28800005 ms | 117 |
| 28799997 ms | 113 |

The cadence is a clean 8 hours everywhere, jittered by milliseconds. There are no gaps, no
missing settlements, and no out-of-order rows anywhere in five years.

## 3. Jitter

2403 of 5481 rows (43.8%) do not sit exactly on their own 8-hour grid. Offsets range from
1 ms to 47 ms. Per-period jitter counts range from 7 to 73 rows.

Jitter is **preserved exactly as the source states it** and is only ever reported as a
distance from each row's own interval grid. No timestamp was rounded, snapped, or filled.

## 4. Per-period inventory

Columns: source rows, distinct, duplicates, conflicts, ZIP sha256 prefix, provider
checksum match, member sha256 prefix, first and last settlement, observed interval with
count, jitter row count, jitter min/max ms, quality state.

| Period | Rows | Distinct | Dup | Conf | ZIP | Checksum | Member | First | Last | Interval | Jitter | Min/Max ms | State |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2020-01 | 93 | 93 | 0 | 0 | 7f81b2f3694d | yes | b566eea750ed | 2020-01-01T00:00:00Z | 2020-01-31T16:00:00Z | 8x93 | 14 | 1/2 | PASS |
| 2020-02 | 87 | 87 | 0 | 0 | 6599466d108d | yes | e1ff46ee6c1d | 2020-02-01T00:00:00Z | 2020-02-29T16:00:00Z | 8x87 | 15 | 1/15 | PASS |
| 2020-03 | 93 | 93 | 0 | 0 | eee845fde633 | yes | 1ca0430f06cd | 2020-03-01T00:00:00Z | 2020-03-31T16:00:00.001000Z | 8x93 | 23 | 1/6 | PASS |
| 2020-04 | 90 | 90 | 0 | 0 | d009ce034d08 | yes | f9f9f1d211c4 | 2020-04-01T00:00:00.002000Z | 2020-04-30T16:00:00Z | 8x90 | 14 | 1/6 | PASS |
| 2020-05 | 93 | 93 | 0 | 0 | 3f2b56dd6b9a | yes | 51e9d27a9c57 | 2020-05-01T00:00:00Z | 2020-05-31T16:00:00Z | 8x93 | 17 | 1/11 | PASS |
| 2020-06 | 90 | 90 | 0 | 0 | 30b3470ff985 | yes | 6ad618ae28a1 | 2020-06-01T00:00:00Z | 2020-06-30T16:00:00.002000Z | 8x90 | 39 | 1/9 | PASS |
| 2020-07 | 93 | 93 | 0 | 0 | 18dae7b11075 | yes | da2268dcb243 | 2020-07-01T00:00:00.002000Z | 2020-07-31T16:00:00Z | 8x93 | 28 | 1/6 | PASS |
| 2020-08 | 93 | 93 | 0 | 0 | e6f6d1749f67 | yes | 78de37294fb2 | 2020-08-01T00:00:00.005000Z | 2020-08-31T16:00:00.001000Z | 8x93 | 30 | 1/17 | PASS |
| 2020-09 | 90 | 90 | 0 | 0 | 7ae9a3b6afb2 | yes | b92ada45ee14 | 2020-09-01T00:00:00Z | 2020-09-30T16:00:00Z | 8x90 | 48 | 1/45 | PASS |
| 2020-10 | 93 | 93 | 0 | 0 | 4c55b191c101 | yes | 77b1a0826243 | 2020-10-01T00:00:00Z | 2020-10-31T16:00:00Z | 8x93 | 43 | 1/15 | PASS |
| 2020-11 | 90 | 90 | 0 | 0 | 676356a2d075 | yes | 474c0b124cc9 | 2020-11-01T00:00:00Z | 2020-11-30T16:00:00Z | 8x90 | 53 | 1/17 | PASS |
| 2020-12 | 93 | 93 | 0 | 0 | d7390f90edf5 | yes | 6450a5b509fb | 2020-12-01T00:00:00Z | 2020-12-31T16:00:00.010000Z | 8x93 | 48 | 1/33 | PASS |
| 2021-01 | 93 | 93 | 0 | 0 | cff916dc4b63 | yes | 5be276b08532 | 2021-01-01T00:00:00.002000Z | 2021-01-31T16:00:00Z | 8x93 | 47 | 1/20 | PASS |
| 2021-02 | 84 | 84 | 0 | 0 | 819a7b107443 | yes | d163ae55143b | 2021-02-01T00:00:00.001000Z | 2021-02-28T16:00:00Z | 8x84 | 53 | 1/25 | PASS |
| 2021-03 | 93 | 93 | 0 | 0 | 2125fd300848 | yes | 1e1bf39fe6f6 | 2021-03-01T00:00:00Z | 2021-03-31T16:00:00Z | 8x93 | 47 | 1/30 | PASS |
| 2021-04 | 90 | 90 | 0 | 0 | 9cd888e3b0a1 | yes | fa2d4f4af93e | 2021-04-01T00:00:00.025000Z | 2021-04-30T16:00:00.003000Z | 8x90 | 60 | 1/25 | PASS |
| 2021-05 | 93 | 93 | 0 | 0 | ed934afb9cf8 | yes | 7bef9fb0da55 | 2021-05-01T00:00:00.002000Z | 2021-05-31T16:00:00Z | 8x93 | 66 | 1/43 | PASS |
| 2021-06 | 90 | 90 | 0 | 0 | 7b8d9bfb8816 | yes | 838c3a004e80 | 2021-06-01T00:00:00.001000Z | 2021-06-30T16:00:00.005000Z | 8x90 | 65 | 1/44 | PASS |
| 2021-07 | 93 | 93 | 0 | 0 | 8ab3df641d3b | yes | 58dbb17f8eca | 2021-07-01T00:00:00Z | 2021-07-31T16:00:00.003000Z | 8x93 | 65 | 1/46 | PASS |
| 2021-08 | 93 | 93 | 0 | 0 | 7eb681cc45b9 | yes | d90f25a13bb7 | 2021-08-01T00:00:00.005000Z | 2021-08-31T16:00:00.003000Z | 8x93 | 58 | 1/21 | PASS |
| 2021-09 | 90 | 90 | 0 | 0 | 03f25a7c25ee | yes | 5245309395b0 | 2021-09-01T00:00:00Z | 2021-09-30T16:00:00.005000Z | 8x90 | 62 | 1/47 | PASS |
| 2021-10 | 93 | 93 | 0 | 0 | f25820d6add6 | yes | 3665c1f20956 | 2021-10-01T00:00:00.012000Z | 2021-10-31T16:00:00.001000Z | 8x93 | 72 | 1/22 | PASS |
| 2021-11 | 90 | 90 | 0 | 0 | e2e6b2d72186 | yes | 007948d31914 | 2021-11-01T00:00:00.009000Z | 2021-11-30T16:00:00Z | 8x90 | 60 | 1/19 | PASS |
| 2021-12 | 93 | 93 | 0 | 0 | bf3ce484faf4 | yes | dc76057b5a7e | 2021-12-01T00:00:00Z | 2021-12-31T16:00:00Z | 8x93 | 64 | 1/31 | PASS |
| 2022-01 | 93 | 93 | 0 | 0 | 22ee19079b62 | yes | 58ef13e02a06 | 2022-01-01T00:00:00.006000Z | 2022-01-31T16:00:00Z | 8x93 | 59 | 1/28 | PASS |
| 2022-02 | 84 | 84 | 0 | 0 | fa95088258a9 | yes | 673deb571d8d | 2022-02-01T00:00:00.010000Z | 2022-02-28T16:00:00.002000Z | 8x84 | 61 | 1/23 | PASS |
| 2022-03 | 93 | 93 | 0 | 0 | 4cf0883bc07f | yes | 91ad72b00344 | 2022-03-01T00:00:00.002000Z | 2022-03-31T16:00:00.015000Z | 8x93 | 63 | 1/28 | PASS |
| 2022-04 | 90 | 90 | 0 | 0 | 57e2776cc68b | yes | 17fb657620aa | 2022-04-01T00:00:00Z | 2022-04-30T16:00:00.015000Z | 8x90 | 59 | 1/31 | PASS |
| 2022-05 | 93 | 93 | 0 | 0 | bced8a5013d0 | yes | 6e45c571be54 | 2022-05-01T00:00:00Z | 2022-05-31T16:00:00Z | 8x93 | 65 | 1/25 | PASS |
| 2022-06 | 90 | 90 | 0 | 0 | 0cd0708f8903 | yes | e4bf4d198700 | 2022-06-01T00:00:00Z | 2022-06-30T16:00:00Z | 8x90 | 61 | 1/25 | PASS |
| 2022-07 | 93 | 93 | 0 | 0 | 29d58cce0cd4 | yes | 3a078bd60b69 | 2022-07-01T00:00:00.001000Z | 2022-07-31T16:00:00.019000Z | 8x93 | 62 | 1/22 | PASS |
| 2022-08 | 93 | 93 | 0 | 0 | 6f4f0c6c84c0 | yes | 7a5fd83b9046 | 2022-08-01T00:00:00.010000Z | 2022-08-31T16:00:00.013000Z | 8x93 | 63 | 1/21 | PASS |
| 2022-09 | 90 | 90 | 0 | 0 | d62cd4e13009 | yes | 8bba85a3aaae | 2022-09-01T00:00:00.012000Z | 2022-09-30T16:00:00.007000Z | 8x90 | 58 | 1/28 | PASS |
| 2022-10 | 93 | 93 | 0 | 0 | ad9efed10d4c | yes | 4f513a5a6416 | 2022-10-01T00:00:00.008000Z | 2022-10-31T16:00:00.010000Z | 8x93 | 64 | 1/27 | PASS |
| 2022-11 | 90 | 90 | 0 | 0 | 8febe5bec1a0 | yes | 98b0632629a7 | 2022-11-01T00:00:00Z | 2022-11-30T16:00:00.015000Z | 8x90 | 57 | 1/27 | PASS |
| 2022-12 | 93 | 93 | 0 | 0 | 4218c78331bc | yes | a7527621060c | 2022-12-01T00:00:00.001000Z | 2022-12-31T16:00:00Z | 8x93 | 65 | 1/27 | PASS |
| 2023-01 | 93 | 93 | 0 | 0 | 05e3df32f28d | yes | b83a5af33157 | 2023-01-01T00:00:00Z | 2023-01-31T16:00:00.007000Z | 8x93 | 60 | 1/23 | PASS |
| 2023-02 | 84 | 84 | 0 | 0 | 5227accd9aaa | yes | c346990315d8 | 2023-02-01T00:00:00.013000Z | 2023-02-28T16:00:00.005000Z | 8x84 | 69 | 1/23 | PASS |
| 2023-03 | 93 | 93 | 0 | 0 | ab022adff9b8 | yes | d776e94a48c8 | 2023-03-01T00:00:00.016000Z | 2023-03-31T16:00:00.011000Z | 8x93 | 71 | 1/27 | PASS |
| 2023-04 | 90 | 90 | 0 | 0 | 2931039d2681 | yes | 1c2b6f3e55fb | 2023-04-01T00:00:00Z | 2023-04-30T16:00:00.010000Z | 8x90 | 73 | 1/27 | PASS |
| 2023-05 | 93 | 93 | 0 | 0 | 5d026fece46d | yes | a979797e9509 | 2023-05-01T00:00:00.004000Z | 2023-05-31T16:00:00Z | 8x93 | 62 | 1/29 | PASS |
| 2023-06 | 90 | 90 | 0 | 0 | 3ffdde6f1dc9 | yes | 1d076e090a53 | 2023-06-01T00:00:00.008000Z | 2023-06-30T16:00:00.001000Z | 8x90 | 16 | 1/16 | PASS |
| 2023-07 | 93 | 93 | 0 | 0 | 0304baed9fd4 | yes | 65c6e99359aa | 2023-07-01T00:00:00Z | 2023-07-31T16:00:00.001000Z | 8x93 | 9 | 1/1 | PASS |
| 2023-08 | 93 | 93 | 0 | 0 | 516a8f50631c | yes | e92d6c334b66 | 2023-08-01T00:00:00Z | 2023-08-31T16:00:00Z | 8x93 | 10 | 1/5 | PASS |
| 2023-09 | 90 | 90 | 0 | 0 | 3fd9df6fd1ee | yes | f7ad0d9e9039 | 2023-09-01T00:00:00Z | 2023-09-30T16:00:00Z | 8x90 | 7 | 1/1 | PASS |
| 2023-10 | 93 | 93 | 0 | 0 | 03105cc14015 | yes | 01d36bd8eccb | 2023-10-01T00:00:00Z | 2023-10-31T16:00:00Z | 8x93 | 10 | 1/5 | PASS |
| 2023-11 | 90 | 90 | 0 | 0 | 8015d2997f8d | yes | bde8bb8a6a7f | 2023-11-01T00:00:00Z | 2023-11-30T16:00:00Z | 8x90 | 11 | 1/1 | PASS |
| 2023-12 | 93 | 93 | 0 | 0 | 8f02fdd2a2da | yes | 00a808892d8c | 2023-12-01T00:00:00Z | 2023-12-31T16:00:00Z | 8x93 | 7 | 1/1 | PASS |
| 2024-01 | 93 | 93 | 0 | 0 | 3e0d30870672 | yes | 232a13d92487 | 2024-01-01T00:00:00Z | 2024-01-31T16:00:00Z | 8x93 | 15 | 1/3 | PASS |
| 2024-02 | 87 | 87 | 0 | 0 | daf1e4901e3d | yes | e08c820f5019 | 2024-02-01T00:00:00Z | 2024-02-29T16:00:00Z | 8x87 | 11 | 1/4 | PASS |
| 2024-03 | 93 | 93 | 0 | 0 | 711dcaf2a341 | yes | 1ac0fa4862ab | 2024-03-01T00:00:00Z | 2024-03-31T16:00:00.001000Z | 8x93 | 11 | 1/4 | PASS |
| 2024-04 | 90 | 90 | 0 | 0 | 6d220b8e2815 | yes | a7dfc9321f21 | 2024-04-01T00:00:00Z | 2024-04-30T16:00:00Z | 8x90 | 16 | 1/15 | PASS |
| 2024-05 | 93 | 93 | 0 | 0 | aef8c5fdce14 | yes | a34fabae463d | 2024-05-01T00:00:00Z | 2024-05-31T16:00:00Z | 8x93 | 7 | 1/4 | PASS |
| 2024-06 | 90 | 90 | 0 | 0 | 43fc4473820d | yes | 7c470eeee314 | 2024-06-01T00:00:00Z | 2024-06-30T16:00:00Z | 8x90 | 13 | 1/8 | PASS |
| 2024-07 | 93 | 93 | 0 | 0 | acab0593c145 | yes | 60d8e545d103 | 2024-07-01T00:00:00Z | 2024-07-31T16:00:00Z | 8x93 | 13 | 1/4 | PASS |
| 2024-08 | 93 | 93 | 0 | 0 | 7003d29a43dd | yes | 5031f1d1dde9 | 2024-08-01T00:00:00Z | 2024-08-31T16:00:00Z | 8x93 | 15 | 1/8 | PASS |
| 2024-09 | 90 | 90 | 0 | 0 | 6ef23b02392b | yes | 5ba49e01519e | 2024-09-01T00:00:00Z | 2024-09-30T16:00:00Z | 8x90 | 22 | 1/5 | PASS |
| 2024-10 | 93 | 93 | 0 | 0 | 26db65ac8020 | yes | c20b8d0f1239 | 2024-10-01T00:00:00Z | 2024-10-31T16:00:00Z | 8x93 | 14 | 1/13 | PASS |
| 2024-11 | 90 | 90 | 0 | 0 | e1b19cccfe2c | yes | 56722e25782b | 2024-11-01T00:00:00Z | 2024-11-30T16:00:00Z | 8x90 | 15 | 1/10 | PASS |
| 2024-12 | 93 | 93 | 0 | 0 | 069409f525eb | yes | 46bd01d8e090 | 2024-12-01T00:00:00Z | 2024-12-31T16:00:00Z | 8x93 | 18 | 1/14 | PASS |

All 60 canonical content hashes are distinct, as expected for 60 distinct months.

## 5. Proposed quality report

Every period evaluated to `PASS` through the frozen `evaluate_series_quality`. No period
produced a `warn` or `fail` finding, so:

- No approval proposal is required or generated for any period.
- No `authorized: true` record exists anywhere in this stop.
- Four distinct quality identities appear across the 60 periods, corresponding to the four
  distinct settlement counts (84, 87, 90, 93) that make up the interval-count evidence.

Stop C therefore needs no designed-gap or duplicate approval for this source. That is a
result of the data being clean, not of any check being skipped.

## 6. Finding F-S01B-1 — dropped connections are not retried

**Severity:** robustness defect in shared acquisition. Not a data-integrity problem. No
incorrect data was produced or published at any point.

The first full-inventory run used the frozen D07 driver with `workers=4`. Three of the
first four periods failed with `DownloadFailed`, and the driver correctly halted the whole
source rather than hiding it:

- `2020-01`, `2020-02`, `2020-04` — `FAILED`, exit 3
- `2020-03` — `PUBLISHED`
- remaining 56 periods — `not_attempted`

The acquisition evidence shows the cause: the `.CHECKSUM` request returned 200, then the
ZIP request recorded `"transport_error": "RemoteProtocolError"` with `received_bytes: 0`
and, critically, `"retry_evidence": []` — **zero retry attempts**.

Root cause in `src/quantara/acquisition.py`:

```python
_ELIGIBLE_TIMEOUTS = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout)

def _is_connection_reset(exc):
    return isinstance(exc, httpx.TransportError) and "reset" in str(exc).lower()
```

Retry eligibility for a transport error is decided by **substring-matching the exception
message**. When a server drops the connection, httpx raises
`RemoteProtocolError("Server disconnected without sending a response.")`. That is a
`TransportError` subclass, but its message contains no "reset", so it falls through to
`raise DownloadFailed(...)` immediately with no backoff and no second attempt.

Reproduced offline with synthetic transports in
`temp/protocol_v1_audits/btc_settled_funding/s01b/probe_retry_classification.py`:

```text
MAX_ATTEMPTS = 3
1 call(s)  retries=0  DownloadFailed  bare dropped connection (observed on Binance under 4 workers)
3 call(s)  retries=5  DownloadFailed  same class, message contains "reset"
3 call(s)  retries=5  DownloadFailed  connect timeout
3 call(s)  retries=5  DownloadFailed  read timeout
CONFIRMED: identical exception class, retry behaviour decided by message text.
```

The same exception class gets one attempt or three depending purely on wording.

**Confirmation it is transient, not a source problem:** rerunning the identical inventory
serially (`workers=1`) published all 60 periods with 120 requests and exit 0. The three
periods that failed under concurrency are byte-identical and clean when acquired
sequentially. All evidence in this document comes from that serial run.

**Not fixed here.** Stop B has no production-code allowance. This needs a D-series
correction packet that classifies dropped connections as retry-eligible by exception type
rather than message text, with a synthetic test proving a `RemoteProtocolError` is retried
`MAX_ATTEMPTS` times.

**Operational note until then:** run multi-period backfills for this source with
`workers=1`. Concurrency does not corrupt anything — the driver stops the source on the
first failure, which is the designed behavior — but it wastes the run.

## 7. Verification

| Check | Result |
| --- | --- |
| Full inventory, `workers=1` | 60 PUBLISHED, exit 0, 120 requests, 0 rejected |
| Full inventory, `workers=4` | 1 PUBLISHED, 3 FAILED, 56 not attempted, exit 3 (F-S01B-1) |
| Provider checksum verification | 60 / 60 |
| Commit graph verified per period | 60 / 60 |
| Quality state | 60 PASS |
| Retry-classification probe | reproduced offline, no network |
| `ruff check src tests benchmarks` | clean |
| Focused `test_series_btc_funding` + `test_series_pipeline` | 63 passed |
| Full suite `pytest -n 4` | 2097 passed, 1 skipped (unchanged; stop B adds no tests) |
| `uv sync --locked` | no drift |

## 8. Scope and limits

- No production `data/` root was written. Both runs used isolated temporary roots.
- No 2025 acquisition. The frozen inventory ends at `2024-12`.
- No funding-rate value appears in this document or in any evidence JSON. Counts,
  timestamps, hashes, interval strings and state names only.
- No approval record, no approver, no decision time, no `authorized: true`.
- Not verified: whether other sources hit F-S01B-1, since only this series was acquired.
- Not verified by before/after pointer comparison: no pre-run production-pointer snapshot
  was taken. The claim is that no production root was ever passed to the pipeline.

## 9. Next

1. A D-series correction for F-S01B-1 before any source relies on concurrent backfill.
2. S01-C: audited approval and publication. No designed-gap or duplicate approval is
   needed for this source, since all 60 periods are `PASS`.
