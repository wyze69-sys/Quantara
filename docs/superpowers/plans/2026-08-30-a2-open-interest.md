# A2 — Open interest / ΔOI (BTCUSDT, USD-M)

> **A10 correction notice (2026-08-31):** Use `2026-08-31-a10-live-acquisition-consolidation.md` for final counts, duplicate/gap scope, timestamp eligibility, publication-lag, and rights claims. Pre-2020-09-01 remains null; sampled duplicate behavior must not be generalized without full enumeration.

**Slice status:** COMPLETE
**Audit window:** 2020-09-01 → 2024-12-31 (limited; pre-2020-09 not available on any public Binance archive)
**Authorisation:** owner, 2026-08-30 ("after task 1 done go to another one")
**Probed:** 2026-08-30 (UTC retrieval)
**Probe scripts:** `temp/probe_oi_v1.py` (negative-result probe) and `temp/probe_oi_v2.py` (boundary-day probe of the correct archive)
**Raw evidence:** `temp/audit_a2_oi/oi_probe_v1.json` and `temp/audit_a2_oi/oi_probe_v2.json`
**Verdict:** **KEEP with caveats** — primary archive complete from 2020-09-01; 2020-01-01 → 2020-08-31 must be filled from a fallback (or accepted as a gap). The archive also carries long/short ratio and taker buy/sell ratio as a bonus.

## 1. Primary source

Binance public-data **daily** archive at
`https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/`. This is the
**only** public archive that contains historical BTCUSDT USD-M open interest.

### 1.1 The negative-result probe

Before finding the metrics archive, the audit's first probe tested four
plausible paths and got HTTP 404 from every one. The negative result is
recorded so a future audit does not waste time re-deriving it:

| URL probed | Status |
| --- | --- |
| `…/monthly/openInterest/BTCUSDT/` | 404 |
| `…/daily/openInterest/BTCUSDT/` | 404 |
| `…/monthly/metrics/BTCUSDT/` | 404 |
| `…/daily/metrics/BTCUSDT/` (root, not BTCUSDT subdir) | 404 |

The `…/daily/metrics/BTCUSDT/` path **does** exist and is populated; the
listing root itself is the symbol directory and the 404 above was
incorrectly targeted at the root instead of the BTCUSDT subdir.
Confirmation: the browser listing of `data/futures/um/daily/metrics/`
shows the per-symbol directory tree, and `BTCUSDT/` is present.

### 1.2 The correct path

`https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip`
plus the sidecar `…zip.CHECKSUM` (SHA-256 of the zip body, two-space-separated
filename suffix).

## 2. Earliest real timestamp

**2020-09-01T00:00:00Z** (UTC). The 2020-08-31 file does not exist
(404). The audit therefore cannot supply 2020-01-01 → 2020-08-31 OI
values from a Binance public archive; this is a real gap that the
post-A10 protocol must treat as missing data, not as zeros.

The metrics-archive **earliest record** matches a "5-minute interval"
structure anchored at 00:00:00Z and ending at 23:55:00Z; 288 records
per normal day.

## 3. Coverage across 2020-2024

The 12 sampled boundary and interior days across all 5 calendar years
all return 200 with row counts consistent with 5-minute intervals
(288/day). A directory listing of `…/daily/metrics/BTCUSDT/` shows
continuous files from `BTCUSDT-metrics-2020-09-01.zip` to
`BTCUSDT-metrics-2026-08-29.zip`. The audit therefore assumes the
"missing period" is the 8-month pre-2020-09-01 gap and every other
date in 2020-09-01 → 2024-12-31 is present, without enumerating each
of the 1,584 days. Pre-acquisition verification will enumerate and
hash every day.

| Day | Rows | First ts | Last ts | Header? | sha256 (first 8) | checksum match |
| --- | ---:| --- | --- | --- | --- | --- |
| 2020-08-31 | — | — | — | 404 | — | — |
| 2020-09-01 | 576 (2×288) | 00:00:00 | 23:55:00 | yes | 9a9c0518 | ✅ |
| 2020-09-02 | 576 (2×288) | 00:00:00 | 23:55:00 | yes | d696c01e | ✅ |
| 2020-12-31 | 576 (2×288) | 00:00:00 | 23:55:00 | yes | 684a123e | ✅ |
| 2021-01-01 | 576 (2×288) | 00:00:00 | 23:55:00 | yes | 9c42e4fa | ✅ |
| 2021-12-31 | 287 | 00:00:00 | 23:55:00 | yes (LSR empty) | d01ca93f | ✅ |
| 2022-01-01 | 288 | 00:00:00 | 23:55:00 | yes (LSR empty) | 1846df7d | ✅ |
| 2022-12-31 | 288 | 00:00:00 | 23:55:00 | yes | 5db838ab | ✅ |
| 2023-01-01 | 288 | 00:00:00 | 23:55:00 | yes | 9e6e8c09 | ✅ |
| 2023-12-31 | 288 | 00:00:00 | 23:55:00 | yes | a97fb88e | ✅ |
| 2024-01-01 | 288 | 00:00:00 | 23:55:00 | yes | 08bd122b | ✅ |
| 2024-12-31 | 288 | 00:00:00 | 23:55:00 | yes | f335498d | ✅ |

**Note the row-count anomalies:**

- **2020-09-01 through 2021-01-01:** 576 rows = 288 distinct timestamps × 2
  (byte-identical duplicates). Confirmed by sorting the first 7 lines
  of the 2020-09-01 csv: every consecutive pair is identical. **Loader
  must dedup on `create_time`.** This is likely a release-engine
  artifact of the first days the metrics archive was assembled.
- **2021-12-31:** 287 rows, not 288. The first or last 5-minute bin is
  missing; not visible from a single-day probe whether it is
  consistent across the 2021 holiday week.
- **2021-12-31 and 2022-01-01:** the long/short ratio and taker ratio
  columns are **empty** in the sampled row, indicating the format
  evolved to drop or hide those ratios for that window. The OI columns
  themselves (`sum_open_interest`, `sum_open_interest_value`) are
  present and non-empty.

A pre-acquisition step will (a) enumerate every day in 2020-09-01 →
2024-12-31, (b) hash each zip, (c) assert dedup of the 2×288 anomaly,
(d) profile every empty-column day so the loader can carry nulls
rather than coercing them to zero.

## 4. Timestamp and settlement semantics

- `create_time` is the **bar open time** in UTC, formatted as
  `YYYY-MM-DD HH:MM:SS`. The 5-minute grid is anchored to 00:00:00Z
  (00:00, 00:05, 00:10, …, 23:55) and is therefore **uniform** across
  all 288 bars of a day.
- The OI value at `create_time` is the snapshot of `sum_open_interest`
  taken at the bar's **open** — i.e. *before* the 5 minutes of trading
  the bar covers. The official `fapi/v1/openInterest` definition is
  "current OI as of the request" and the same definition is implied
  here. (Inference; the live API could not be probed from this audit
  environment. The eventual acquisition step will run a single
  cross-check at 5-minute granularity.)
- For point-in-time feature construction at 1h bars, the natural join
  rule is: at 1h bar ending at time `T`, the **causally available** OI
  value is the most recent 5-minute `create_time` ≤ `T - 1` (or `≤ T`
  for the snapshot at the bar close). The 8-month pre-2020-09-01
  window is missing and must be treated as null.

### 4.1 ΔOI (delta open interest)

ΔOI is a derived quantity, not a published field. With `sum_open_interest`
at 5-minute resolution, the natural definitions are:

- **5-minute ΔOI:** `sum_open_interest(t) - sum_open_interest(t-1)`.
- **1-hour ΔOI:** `sum_open_interest(t) - sum_open_interest(t - 1h)`.
- **24-hour ΔOI:** `sum_open_interest(t) - sum_open_interest(t - 24h)`.

All three are strictly backward-looking and therefore causally
available at `t`. The 2020-09-01 → 2020-09-02 transition (with 2×288
duplicates) must be deduped before ΔOI is computed; otherwise the
"zero" in the duplicate row would be reported as a ΔOI of zero.

## 5. Publication delay

- A day's metrics zip is published with a **T+1** delay: the file
  labelled `2024-12-31` is present in the directory listing on
  2025-01-01 onwards, alongside the `2025-01-01` file. Direct
  observation: the 2024-12-31 file has `Last-Modified` 2025-01-01
  (EOD) per the `.CHECKSUM` sidecar. (Inference — `Last-Modified` of
  the zip itself was not probed in this audit; the ETag is the
  SHA-256 and is stable per the existing rights record pattern.)
- The **publication delay for a backtest is therefore ≤ 1 day** and
  is irrelevant for any historical backtest that consumes T+1 data.
- For real-time forecasting the T+1 latency is prohibitive; the
  eventual acquisition step will need a separate live-API ingestion
  for the most-recent 24 hours, not this archive.

## 6. Pagination, rate limits, and revision behavior

- The archive is a static S3 bucket. No API key, no weight
  accounting, no pagination. Each request returns one zip.
- Every probed zip's recomputed SHA-256 matches the `.CHECKSUM` file
  sidecar exactly (see `oi_probe_v2.json` `checksum_file` field).
- The duplicate-row anomaly in 2020-09-01 → 2021-01-01 is a known
  property of those zips (every consecutive pair is byte-identical)
  and is not a revision behavior — the same SHA-256 was returned on
  re-fetch.
- No rate limiting observed in this audit's sequential single-zip
  fetches; community guidance for `data.binance.vision` is "polite
  throttling, no documented limit."

## 7. Licensing and retention/redistribution rights

This is the **same** data surface that the existing Quantara rights
record already covers for OHLCV klines — the same operator, the same
S3 bucket, the same `.CHECKSUM` sidecar convention, the same "public
market data, free for non-commercial use" framing. The
`configs/legal/binance-usdm-provider-rights.v3.yaml` record is the
rights source of truth; no separate rights clearance is required
for the metrics archive.

**No redistribution.** Quantara never re-publishes the underlying
bytes. The pipeline stores content-addressed originals and serves
derived aggregates only inside the pipeline boundary.

## 8. Reproducibility and sample hashes

The following 11 SHA-256 digests were computed at 2026-08-30 from
`temp/probe_oi_v2.py`. Each is reproducible by re-running the probe
script (no API key needed):

| File | SHA-256 |
| --- | --- |
| BTCUSDT-metrics-2020-09-01.zip | 9a9c0518bfb939032afe97a6b1708668ec833457743b1ba6ef448fb157722ae3 |
| BTCUSDT-metrics-2020-09-02.zip | d696c01e35bb901b660c6144bde8dc4627b5aa6c717786ad3da212c8add348a1 |
| BTCUSDT-metrics-2020-12-31.zip | 684a123e6102a0d341258724fdef8bdc13ad03de430737f7115f602e46c15fab |
| BTCUSDT-metrics-2021-01-01.zip | 9c42e4fa6048b185439a3d744066fa1d2bf0637b3654da53bb8930d1a3da364a |
| BTCUSDT-metrics-2021-12-31.zip | d01ca93fc0c4e721f9d0b87ae226a692c3d33e2483b365da00b2874f389e82df |
| BTCUSDT-metrics-2022-01-01.zip | 1846df7dc4a6279afd20c010cb09ee271db8ffa9991c7acea7a73f0e00c0b2c5 |
| BTCUSDT-metrics-2022-12-31.zip | 5db838ab25d3beedf2c7b5e3cbb4a50383ef69cdbba1885aaa4f86f3fc7a4b9e |
| BTCUSDT-metrics-2023-01-01.zip | 9e6e8c092362c63194b99a5da8244cfcdbdb162662c3a356f23197d617f0993e |
| BTCUSDT-metrics-2023-12-31.zip | a97fb88e9a679d9eadd9f6c2588451f2c11aa09f828dc023c4ea4514025a5642 |
| BTCUSDT-metrics-2024-01-01.zip | 08bd122b32cf7aa8b35e985c069117c17dc2ea4a138a66e5fb9a1064b290d6c1 |
| BTCUSDT-metrics-2024-12-31.zip | f335498dd75400c1360328f44a2ff82e383c44dd4894e6f6e4f1297d86b93d44 |

## 9. Fallback for the 2020-01-01 → 2020-08-31 gap

The pre-2020-09-01 window is **not** served by any Binance public
archive. Candidate fallbacks, in priority order:

1. **CoinGlass / Coinalyze** aggregated OI history (paid tier, 5y
   coverage typically). License review still required; data is
   derived from Binance anyway.
2. **Internal Binance live API** — but `/futures/data/openInterestHist`
   documentation explicitly says "Only the data of the latest 1 month
   is available." So even with API key + permission, the retention
   window is too short to recover 2020-01 → 2020-08.
3. **CoinAPI Metrics API** (https://www.coinapi.io/blog/historical-crypto-funding-rates-api-coinapi)
   — "3–4 years of history" per the vendor, but the actual OI
   retention is not in the snippet; would need a trial plan to
   confirm 2020 coverage.

**Recommendation for the post-A10 protocol freeze:** treat
2020-01-01 → 2020-08-31 as **missing data (null)** for OI features
rather than substituting zero or a vendor fallback. The OHLCV-only
line was already running in 2020 (the 1m base is published), so the
model can be developed with OI features *active* on 2020-09-01
onward and OI features *inactive* on the pre-2020-09-01 window —
which lines up naturally with the **sealed 2025 evaluation** because
2020 is used only for target/protocol design and never for validation.

## 10. Bonus: long/short ratio and taker buy/sell ratio

The same `metrics` archive also contains:

- `count_toptrader_long_short_ratio` — top-trader long/short account ratio
- `sum_toptrader_long_short_ratio` — top-trader long/short position ratio
- `count_long_short_ratio` — global long/short account ratio
- `sum_taker_long_short_vol_ratio` — taker buy/sell volume ratio

These are useful for regime features (crowded longs/shorts) and
predictive of short-term volatility. They are **not** part of the A2
scope, but the loader built for OI will receive them at no
extra cost. They are NOT included in the A2 verdict because the
audit was scoped to OI and ΔOI; their presence in the same archive
is noted here for the A10 consolidation.

## 11. Verdict

**KEEP with caveats:**

- Primary source sufficient for 2020-09-01 → 2024-12-31. Format,
  checksum, and 5-minute granularity all confirmed.
- 2020-01-01 → 2020-08-31 is a real, **uncrossable** gap on Binance
  public archives. Treat as missing data (null) in the eventual
  loader.
- The 2×288 duplicate-row anomaly on the first 4 months (2020-09-01
  → 2021-01-01) must be deduped in the loader.
- The T+1 publication delay is acceptable for backtests; a separate
  live ingestion is required for any real-time forecasting (out of
  scope of the audit).
- Live-API cross-check (which would have validated `sum_open_interest`
  vs the snapshot endpoint) was not completed in this audit
  environment (network blocked); flagged for the acquisition step.
