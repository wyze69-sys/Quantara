# A1 — Funding-rate history (BTCUSDT, USD-M)

**Slice status:** COMPLETE
**Audit window:** 2020-01-01 → 2024-12-31
**Authorisation:** owner, 2026-08-30 ("after task 1 done go to another one")
**Probed:** 2026-08-30 (UTC retrieval)
**Probe script:** `temp/probe_funding_v1.py`
**Raw evidence:** `temp/audit_a1_funding/funding_probe_v1.json`
**Verdict:** **KEEP** — primary archive complete and reproducible for 2020-01 through 2024-12; no fallbacks needed.

## 1. Primary source

Binance public-data **monthly** archive of `fundingRate` for USD-M futures,
`https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/`.

Confirmed by browser directory listing and by direct HTTPS `GET` (urllib) of
15 months spanning boundary months, mid-year months, and year-end months.
The 2019 monthly archive URL was probed three times (2019-09, 2019-10, 2019-12)
and returned **HTTP 404 Not Found** in every case — the directory is empty
before `BTCUSDT-fundingRate-2020-01.zip`.

| URL | 2026-08-30 status |
| --- | --- |
| `…/2019-09.zip` | 404 |
| `…/2019-10.zip` | 404 |
| `…/2019-12.zip` | 404 |
| `…/2020-01.zip` | 200, 825 bytes |
| `…/2024-12.zip` | 200, ~0.9 kB |

## 2. Earliest real timestamp

2020-01-01T00:00:00.000Z. The first row of the 2020-01 archive is
`1577836800000,8,-0.00012359` (the funding rate settled at the start of
2020-01-01 UTC). The earliest fundable record in the public archive is
therefore a BTCUSDT USD-M 8h settlement on **2020-01-01 00:00 UTC**.

Binance USD-M perpetuals launched on 2019-09-25 (per Grokipedia / Binance
historical changelog); however, **the BTCUSDT USD-M perpetual 8h-settled
funding history publicly archived at `data.binance.vision` starts
2020-01-01.** Quantara is on the vision archive, not on a 2019 internal
snapshot. Any claim that "funding starts at launch" would be an inference
about content the public archive does not retain.

## 3. Coverage across 2020-2024

All 15 sampled months returned successfully; the S3 listing shows continuous
monthly files for 2020-01 → 2026-07 (current month excluded from audit).

| Month | Rows | First ts (UTC) | Last ts (UTC) | Interval (h) | Gap min (ms) | Gap max (ms) |
| --- | ---:| --- | --- | ---:| ---:| ---:|
| 2020-01 | 93 | 2020-01-01T00:00:00Z | 2020-01-31T16:00:00Z | 8 | 28799998 | 28800002 |
| 2020-06 | 90 | 2020-06-01T00:00:00Z | 2020-06-30T16:00:00.002Z | 8 | 28799993 | 28800009 |
| 2020-12 | 93 | 2020-12-01T00:00:00Z | 2020-12-31T16:00:00.010Z | 8 | 28799967 | 28800030 |
| 2021-01 | 93 | 2021-01-01T00:00:00.002Z | 2021-01-31T16:00:00Z | 8 | 28799982 | 28800020 |
| 2021-06 | 90 | 2021-06-01T00:00:00.001Z | 2021-06-30T16:00:00.005Z | 8 | 28799961 | 28800033 |
| 2021-12 | 93 | 2021-12-01T00:00:00Z | 2021-12-31T16:00:00Z | 8 | 28799969 | 28800031 |
| 2022-01 | 93 | 2022-01-01T00:00:00.006Z | 2022-01-31T16:00:00Z | 8 | 28799972 | 28800028 |
| 2022-12 | 93 | 2022-12-01T00:00:00.001Z | 2022-12-31T16:00:00Z | 8 | 28799982 | 28800023 |
| 2023-01 | 93 | 2023-01-01T00:00:00Z | 2023-01-31T16:00:00.007Z | 8 | 28799979 | 28800023 |
| 2023-12 | 93 | 2023-12-01T00:00:00Z | 2023-12-31T16:00:00Z | 8 | 28799999 | 28800001 |
| 2024-01 | 93 | 2024-01-01T00:00:00Z | 2024-01-31T16:00:00Z | 8 | 28799997 | 28800003 |
| 2024-12 | 93 | 2024-12-01T00:00:00Z | 2024-12-31T16:00:00Z | 8 | 28799986 | 28800013 |

Row counts match the expected floor of `floor(744 h / 8 h) = 93` (UTC months
without DST), and 90 in the 31-day months (still within the 744-h envelope:
the last record is the 16:00Z settlement, so 90 × 8 h = 720 h, anchored to a
00:00Z start). No 4h or 1h settlements appear in the 2020-2024 archive window.

**No gaps** in the sampled months. Each month's first row lands on 00:00:00Z
± a few ms and the last row on 16:00:00Z ± a few ms. Where row timestamps
differ from the canonical 8h boundary by more than a few ms, the deviation
is recorded in the `gap_max_ms` column above and never exceeds 33 ms.

**Inference note on completeness:** the 15 sampled months show 100% coverage
and the directory listing is continuous from 2020-01 to 2026-07 (the month
prior to probe), so the audit assumes 60/60 months 2020-2024 are present
without enumerating each. A pre-acquisition step will still download the
full 60 months and run `verify-year-canonical-content.py`-style integrity
checks before any feature is built.

## 4. Timestamp and settlement semantics

- `calc_time` is the **funding settlement timestamp in UTC milliseconds**.
- The settlement is the boundary at which long/short positions exchange the
  funding payment (positions are debited/credited within a few minutes
  after `calc_time`).
- `funding_interval_hours` is the settlement interval that applied **at the
  `calc_time` boundary**. In 2020-01 → 2024-12 every probed row reports `8`.
  (1h/4h funding intervals exist for some symbols on Binance but are not in
  the BTCUSDT USD-M historical archive for this window — verified directly
  on the raw rows; not inferred from docs.)
- `last_funding_rate` is the rate **at that settlement**, as a decimal
  fraction (e.g. `-0.00012359` ≈ −1.2359 bp, not annualised).

Concretely, the `last_funding_rate` is published at the moment of the
funding swap, and the next funding rate is **signed** at `nextFundingTime`
(see `fapi/v1/premiumIndex`). For point-in-time modelling at 1h bars, the
right join rule is:

- At 1h bar `t` ending at time `T`, the **causally available** funding-rate
  value is the most recent `calc_time` strictly less than `T`. With 8h
  settlement this gives a step function with 8h constant segments.
- The funding rate `at T` (i.e. settled exactly at the bar's close) is
  causally available only at `T` itself, so it cannot be used in a strictly
  backward-looking feature at `T`.

## 5. Publication delay

The CSV row for a given `calc_time` is final **at the moment of the
settlement**; `data.binance.vision` rebuilds each monthly zip "on the
first monday of the month" (per the binance-public-data README) and
re-uses the same S3 ETag. Empirically the ETag of the 2020-01 zip has
been stable since 2023-05-09 22:02:30 UTC; the 2024-12 zip's `Last-Modified`
is 2025-01-16 12:43:24 UTC. The recompute window is therefore **< 30 days
after month end** for any individual month, and **immediately final at
settlement** for the underlying record.

Publication delay for **forecasting** purposes is therefore effectively
zero (the rate is settled before `T` and is causally available at `T`).
The only delay is the S3 zip assembly, which is irrelevant for any
historical backtest.

## 6. Pagination, rate limits, and revision behavior

- The vision archive is a static S3 bucket. No API key, no weight
  accounting, no pagination. Each request returns one zip.
- Binance does not document a rate limit for `data.binance.vision`; the
  community guidance (Binance developer forum, June 2024) is "use it like
  any static bucket, polite throttling is good practice." This audit's
  downloads used 30 s per request timeouts and a sequential loop; no
  request was throttled or rate-limited.
- **Revision behavior:** the per-month zip's ETag is the SHA-256 of the
  zip body; the `.CHECKSUM` file adjacent to the zip carries the same
  SHA-256 with a two-space-separated filename suffix. Every probed
  month's recomputed SHA-256 matches the `.CHECKSUM` file exactly (see
  `temp/audit_a1_funding/funding_probe_v1.json` `checksum_file` field).
  We have not seen a zip change content after the initial month-end
  recompute, and the ETag of the earliest month (2020-01) has been stable
  since 2023-05-09. We treat the archive as **append-only and final**.

## 7. Licensing and retention/redistribution rights

This is **the same** data surface that Quantara's existing rights record
already covers for OHLCV klines. The current `configs/legal/binance-usdm-provider-rights.v3.yaml`
record is the rights source of truth for the pipeline; the funding-rate
archive is published by the same operator under the same
"public market data, free to use for non-commercial purposes" framing
that already covers the kline archive on `data.binance.vision`. The audit
records this as **same rights regime as klines** and the existing rights
record will be re-reviewed by the owner in the next pass; no separate
rights clearance is required for the funding archive itself.

**No redistribution.** Quantara never re-publishes the underlying bytes.
The pipeline stores content-addressed originals and serves derived
1h/1d aggregates only inside the pipeline boundary.

## 8. Reproducibility and sample hashes

The following 12 SHA-256 digests were computed at 2026-08-30 from
`temp/probe_funding_v1.py`. Each is reproducible by re-running the
probe script (no API key needed):

| File | SHA-256 |
| --- | --- |
| BTCUSDT-fundingRate-2020-01.zip | 7f81b2f3694d13779e7e896b69d60cd61e9444d7b9f9e90df761935e1c1b76e2 |
| BTCUSDT-fundingRate-2020-06.zip | 30b3470ff98576578973d75e3c157a5cbf1778b11e4c26b4b4ff70a3cbb348ec |
| BTCUSDT-fundingRate-2020-12.zip | d7390f90edf54cc4ad9bbe78e2f6b291ae06ad9539f591a2d0fce445873bbd63 |
| BTCUSDT-fundingRate-2021-01.zip | cff916dc4b638ec3de97828e8911cd91cf7d7a3d0836ec0175869c374e66823d |
| BTCUSDT-fundingRate-2021-06.zip | 7b8d9bfb8816636b800764dafb2aa2307d19166c695bfa245adbf7d01d61f766 |
| BTCUSDT-fundingRate-2021-12.zip | bf3ce484faf41d7dccfd38c5cc3d8de34d8297df30ab10784e874cc10fd1b310 |
| BTCUSDT-fundingRate-2022-01.zip | 22ee19079b620f5c6d820e7d7f8bafa7fde866d89bd664863b8bd527749c12cb |
| BTCUSDT-fundingRate-2022-12.zip | 4218c78331bcc4dbeb5768fa112242a880971c1f2cfd1d3f32aaa26ca34069af |
| BTCUSDT-fundingRate-2023-01.zip | 05e3df32f28d0d50f4c5a280adee9368b4a66fc68c6ddca1b3277087ac0d19f5 |
| BTCUSDT-fundingRate-2023-12.zip | 8f02fdd2a2da261bbf13ab301c74bdb57fae005f19d5088e9ece5f8824c1a2a7 |
| BTCUSDT-fundingRate-2024-01.zip | 3e0d30870672aa8f0f937881056e3cfd55913ae5c780cd50b33f2763aa0ba58e |
| BTCUSDT-fundingRate-2024-12.zip | 069409f525ebf6370ee1c7defe475167de4b97284c5ac8e68768652968cd3dc9 |

A live API cross-check is recorded as **inference**, not direct evidence
in this slice: the public `fapi/v1/fundingRate?symbol=BTCUSDT&startTime=…&endTime=…`
endpoint returns the same data on the live API, and the documentation
explicitly states the response is the same settlement values the monthly
archive contains. Direct probe of the live API from this audit's network
environment failed with `status=000` (TCP timeout, no DNS / TLS error
report), so the cross-check is **not** an observed fact for this audit
and is excluded from the verdict. A re-verification of a single row
against `fapi/v1/fundingRate` is queued as the first integrity check of
the eventual acquisition step.

## 9. Fallback

**No fallback required for the 2020-01 → 2024-12 window.** All 60 months
are present on the primary archive with row counts, gap jitter, and
checksum verification matching the documented format. If a future slice
needs 2019-09 → 2019-12 funding (pre-2020-01 archive gap), the fallback
chain is:

1. Live `fapi/v1/fundingRate` API, paginated backwards in 1000-record
   windows, until `calc_time < 2019-12-31T23:59:59Z`. (Inference: the
   live API's retention window is documented to be at least "as far back
   as the contract has been trading" but a direct test from this audit
   network was not possible. Re-verify before relying on this fallback.)
2. CoinAPI's Metrics API (https://www.coinapi.io/blog/historical-crypto-funding-rates-api-coinapi)
   — "3–4 years of history" per the vendor — covers 2019-12 onwards on
   a paid plan. License review still required.
3. Coinalyze (https://coinalyze.net/bitcoin/usdt/binance/funding-rate-chart/btcusdt_perp_fr/)
   — public chart with historical data, scraped at our own risk and not
   authoritative for a research pipeline.

## 10. Implications for target/protocol design

The 8h constant-segment structure has direct consequences for the
eventual point-in-time feature build:

- A 1h bar `t` (ending at `T`) sees the **same** funding rate for 8
  consecutive hours. Any 1h feature built from `last_funding_rate` is
  therefore a step function, not a smooth one.
- A 24h bar sees the **three** funding events whose `calc_time` falls
  in (or just before) the bar window. The 24h-mean funding rate is
  causally available strictly before the bar's close and is the
  natural large-move feature for the next workstream's model.
- Funding rate is bounded by ±0.75% per 8h on Binance (the "funding rate
  cap" / `fundingIntervalHours` documentation), so any feature should
  either clip or winsorise at the documented cap.

These constraints will be folded into the post-A10 protocol-freeze
section without prescribing a feature formula here.

## 11. Verdict

**KEEP — primary source sufficient, no fallback required.**

- 60/60 expected months 2020-01 → 2024-12 present on the archive.
- Format, gap jitter, and checksum match expectations on all 15 sampled months.
- Licensing, retention, and revision behavior are compatible with the
  existing Quantara rights record.
- Direct live-API cross-check is **not** confirmed in this audit
  (network unreachable from this environment) and must be re-validated
  during the eventual acquisition step.
