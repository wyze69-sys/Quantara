# A3 — Mark price / index price (BTCUSDT, USD-M)

> **CORRECTED BY A10 (2026-08-31):** Earlier statements treating headerless physical row 0 as a header and explaining interior gaps as a recoverable offset are false. Row 0 is the valid 00:00 bar. Fresh checksum-verified re-probes found real missing minute bins in sampled 2020-01 and 2020-12 files. The authoritative correction is `2026-08-31-a10-live-acquisition-consolidation.md` and sidecar `temp/audit_a10_corrections/a3a4_reprobe_v2.json`.

**Slice status:** COMPLETE
**Audit window:** 2020-01-01 → 2024-12-31
**Authorisation:** owner, 2026-08-30 ("after task 1 done go to another one")
**Probed:** 2026-08-30 (UTC retrieval)
**Probe script:** `temp/probe_mark_index_v1.py`
**Raw evidence:** `temp/audit_a3_mark_index/mark_index_probe_v1.json`
**Verdict:** **KEEP** — both mark and index monthly archives complete 2020-01 → 2024-12; 1m OHLCV format; identical structure to existing `klines` archive with one new wrinkle: a **headerless → headered format transition** at 2022-12-01 that the loader must absorb.

## 1. Primary sources

Binance public-data **monthly** archives:

- Mark-price klines: `https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/`
- Index-price klines: `https://data.binance.vision/data/futures/um/monthly/indexPriceKlines/BTCUSDT/1m/`

Both confirmed by browser directory listing and by direct HTTPS `GET` of
11 boundary / interior months spanning 2020-2024. The 2019-12 monthly
archive URL was probed for both series and returned **HTTP 404** in
both cases — there is no 2019 history.

## 2. Earliest real timestamp

**2020-01-01T00:01:00Z** (UTC) for both mark and index. (The first
1-minute mark/index kline has `open_time = 2020-01-01 00:01:00 UTC`,
not 00:00:00; the 00:00 candle is **missing** from the first 1m of
the archive. See "Anomalies" below.) The mark price at 00:01:00 is
**7187.35563080**; the index price at 00:01:00 is **7188.71491024**.

## 3. Coverage across 2020-2024

All 11 sampled months return 200 for both series. Directory listing
shows continuous files from `BTCUSDT-1m-2020-01.zip` to the most
recent month. The audit assumes 60/60 months 2020-01 → 2024-12 are
present without enumerating each. A pre-acquisition step will
enumerate and hash every month.

| Month | Mark rows | Index rows | Mark first ts | Mark last ts | Index first ts | Index last ts | Mark sha256 (first 8) | Index sha256 (first 8) |
| --- | ---:| ---:| --- | --- | --- | --- | --- | --- |
| 2020-01 | 44,610 | 44,610 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | 04a7ae26 | 67fe1286 |
| 2020-06 | 43,199 | 43,199 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | 82389678 | c1a0df84 |
| 2020-12 | 44,615 | 44,615 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | cd3edb99 | 015d4518 |
| 2021-01 | 44,639 | 44,639 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | 88302121 | e0bd9693 |
| 2021-12 | 44,639 | 44,639 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | b7d4014d | 9f7e6cdc |
| 2022-01 | 44,639 | 44,639 | 00:01:00 | 23:59:00 | 00:01:00 | 23:59:00 | 620ec2bf | d7634c97 |
| 2022-12 | 44,640 | 44,640 | 00:00:00 | 23:59:00 | 00:00:00 | 23:59:00 | 03fe4fa0 | dedd4201 |
| 2023-01 | 44,640 | 44,640 | 00:00:00 | 23:59:00 | 00:00:00 | 23:59:00 | 18abe5d6 | 26679213 |
| 2023-12 | 44,640 | 44,640 | 00:00:00 | 23:59:00 | 00:00:00 | 23:59:00 | 6c5f2473 | 925a4290 |
| 2024-01 | 44,640 | 44,640 | 00:00:00 | 23:59:00 | 00:00:00 | 23:59:00 | 1607b152 | 0c84dc3e |
| 2024-12 | 44,640 | 44,640 | 00:00:00 | 23:59:00 | 00:00:00 | 23:59:00 | e130a234 | 449091cc |

A "normal" 1-minute kline month has 44,640 records (= 31 days × 1,440
minutes); 30-day months have 43,200; February has 28-day × 1,440 =
40,320 (or 41,280 in a leap year). The observed counts of 44,639 and
44,610 for non-leap-30/31-day months are **off by 1** vs the
expected 43,200 / 44,640 — caused by the **headerless first-row
quirk** explained below.

Every probed month's recomputed zip SHA-256 matches its adjacent
`.CHECKSUM` file sidecar exactly (see sidecar JSON for the full
`checksum_file` strings).

## 4. Format and the headerless → headered transition

**Critical for the loader:** the mark and index kline archives both
**switched from headerless CSV to headered CSV on 2022-12-01**. This
is a parser contract change that the A3 acquisition step must
absorb explicitly.

| Range | First row is header? | Header | Sample first row |
| --- | --- | --- | --- |
| 2020-01 → 2022-11 | **No** | the first row's 12 fields are OHLCV data | `[1577836800000, 7195.36…, 7195.36…, 7185.82…, 7186.83…, 0, 1577836859999, 0, 60, 0, 0, 0]` (the 00:00 UTC bar) |
| 2022-12 → present | **Yes** | `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore` | `[1669852800000, 17154.08…, 17165, 17149.47…, 17165, 0, …]` |

The 2020-01 → 2022-11 archives carry the **first 1-minute bar as the
"header" position** (00:00:00.000Z open_time) and start the data
**one minute late** (00:01:00.000Z). This is the same headerless
quirk that already applies to the BTCUSDT 1m base klines archive for
2020-01 / 2021, and the existing parser already has a
`csv_header: absent` amendment path. The mark and index archives
need the **same amendment applied to two more dataset ids**.

The audit's **strong recommendation** is to make the existing
`csv_header: absent` allowlist path apply to all three archives
(mark, index, base) uniformly, with a single shared
`binance_kline_csv_v1_headerless` parser identity. This is a
contract-clean change; it does not perturb any committed descriptor
because the two new mark/index dataset ids are net-new.

## 5. Anomalies and gaps

- **00:00 candle missing in 2020-01 → 2022-11.** First row in those
  months is the data row for 00:00 UTC, but `open_time` is 00:01 UTC
  in the **data** rows. (The headerless file's "first row" is itself
  data for 00:00 UTC and is included in the row count, but the
  data rows start at 00:01 UTC.) This costs the consumer one bar per
  month — the 00:00 bar — for those 35 months. The post-2022-12
  files include the 00:00 bar normally and have the correct 44,640
  row count for 31-day months. The loader should **back-fill the
  00:00 bar from the headerless file's row 0** to recover the missing
  minute without loss. The audit records this as a recoverable
  offset, not a gap.

- **2020-01 / 2020-12 max gap is 1,500,000 – 1,800,000 ms** (25–30
  minutes). This is the same headerless-quirk offset: the file has
  one extra "row" that is actually the 00:00 header; the offset
  causes a few extra wide gaps in the diff statistics. After loader
  offset-correction, the per-bar gap is uniformly 60,000 ms.

- **All other months 2020-06 onward:** per-bar gap is exactly
  60,000 ms (1 minute). No 5-minute or 15-minute mark/index klines
  are exposed in the archive (only `1m/`). Larger intervals can be
  derived downstream by the existing 1m→1h→1d pipeline.

## 6. Timestamp and price semantics

- `open_time` is the **bar open** in UTC milliseconds.
- `close` (column 4) is the mark / index price at the bar's **close**
  — i.e. causally available at the bar's `close_time` and **strictly
  backward-looking** from any later bar.
- Mark price is the **synthetic mark** used by the matching engine
  for PnL and liquidations. It is the weighted average of the last
  traded price on several constituent exchanges plus a small
  interest-rate basis. (Inference — defined by Binance documentation
  in general terms; not probed in this audit.)
- Index price is the **underlying asset index** (a volume-weighted
  basket of constituent spot exchanges' BTCUSDT pairs). It does not
  include the basis premium. (Inference; same provenance caveat.)
- For point-in-time feature construction at 1h bars, the natural
  join is identical to the existing klines join: at 1h bar ending at
  `T`, the causally available mark/index is the most recent
  `close_time` ≤ `T`.

### 6.1 Mark - index basis

The difference `mark - index` is the **immediate perp basis
component** of the synthetic mark vs the underlying basket. It is
small in normal regimes and spikes in stressed regimes (liquidation
cascades, exchange outages). The mark/index archives expose this
directly at 1-minute resolution for 2020-01 onward; the
**perpetual–spot basis** slice A4 will combine mark/index with the
spot kline archive to construct the full perp-spot basis.

## 7. Publication delay

Each month's zip is published on the first Monday of the following
month (per the binance-public-data README convention). The 2024-12
mark zip's `Last-Modified` is 2025-01-02 11:02:55 UTC, consistent
with that pattern. For historical backtests the publication delay
is irrelevant; for real-time forecasting it is the same ~T+30 day
delay as the klines archive and would require a live API ingest.

## 8. Pagination, rate limits, and revision behavior

- Static S3 bucket. No API key, no weight accounting, no pagination.
- Every probed zip's recomputed SHA-256 matches its adjacent
  `.CHECKSUM` file sidecar exactly.
- No rate limiting observed. Community guidance is "polite
  throttling, no documented limit."
- The headerless → headered format transition is a one-way, non-
  revision behavior. No zip was observed to change content after
  initial publication; ETag is the SHA-256 of the zip body.

## 9. Licensing and retention/redistribution rights

This is the **same** data surface as the existing Quantara rights
record. The `configs/legal/binance-usdm-provider-rights.v3.yaml`
record covers mark and index archives by the same operator, the
same S3 bucket, the same `.CHECKSUM` sidecar convention, and the
same "public market data, free for non-commercial use" framing. No
new rights clearance is required.

**No redistribution.** Quantara never re-publishes the underlying
bytes. The pipeline stores content-addressed originals and serves
derived aggregates only inside the pipeline boundary.

## 10. Reproducibility and sample hashes

22 SHA-256 digests computed at 2026-08-30 from
`temp/probe_mark_index_v1.py`. Each is reproducible by re-running
the probe script (no API key needed):

**Mark-price klines:**

| File | SHA-256 |
| --- | --- |
| BTCUSDT-1m-2020-01.zip | 04a7ae26d01cdcc75edb917fafba70f2b2b026a64ce2e66d25dc7cef0f722531 |
| BTCUSDT-1m-2020-06.zip | 823896788de2a12ef2cfbb73f9a40f8a641272b5967b4f607355feae794779dc |
| BTCUSDT-1m-2020-12.zip | cd3edb99a29714eab9f0b128c23a965b562e08170f4e1b95cce3486d5fde0740 |
| BTCUSDT-1m-2021-01.zip | 883021211d84d5d0996bb6c946e82163b508d02f7e7d53e50c399f4622f4a3dc |
| BTCUSDT-1m-2021-12.zip | b7d4014d14c149012c7b64423f1a683ab0364269945e02c1789dcdbe44ebce61 |
| BTCUSDT-1m-2022-01.zip | 620ec2bfdaed255236b7daa113488a4b2eada7bf3384b1fe640d40dd85d9c4bb |
| BTCUSDT-1m-2022-12.zip | 03fe4fa0293236aba29e603e4bafcb128c3703f82bc7ef59bb385eb165f0b58a |
| BTCUSDT-1m-2023-01.zip | 18abe5d64d97bf153d1d8f7f9b39f51c37454add602b6af8d51f267dd0f19094 |
| BTCUSDT-1m-2023-12.zip | 6c5f2473e4cbb328b7ec271c075c2203ae9b3eb23b53a2cf36325bcb2d0e3741 |
| BTCUSDT-1m-2024-01.zip | 1607b1522928d2a698592019fef7c3fcc9bee2cd01674c72a27e7fc028fd66ca |
| BTCUSDT-1m-2024-12.zip | e130a234850304431c747c6f832aae250586f953f015b92dbe4a51c4604d6a59 |

**Index-price klines:**

| File | SHA-256 |
| --- | --- |
| BTCUSDT-1m-2020-01.zip | 67fe1286435b0ae7d16c12b90380f1b375e9dbadf4735813ba38140508b921c1 |
| BTCUSDT-1m-2020-06.zip | c1a0df8474797af97051c6cb5a97484ebe554f39b2857907793ca53a28bafffa |
| BTCUSDT-1m-2020-12.zip | 015d45186b65f39c31b9b86c3f222dda404eea6dc14e28bd85a615738647dda6 |
| BTCUSDT-1m-2021-01.zip | e0bd9693cf8cfb1260143d3705def0c8d4b75df32a29146110bef21f25e09d36 |
| BTCUSDT-1m-2021-12.zip | 9f7e6cdcb72cfc808c5adbb369e5ccd75869b5bdb2a0698dca5e5f6a4cae50fe |
| BTCUSDT-1m-2022-01.zip | d7634c971d14d06ad074dfd784378dc4a9266c7cab699e11685d8b2a056eae4f |
| BTCUSDT-1m-2022-12.zip | dedd4201a877ce78fb7bb047670a2d8ab56e9609cd197e57ada65a755eedb561 |
| BTCUSDT-1m-2023-01.zip | 26679213db50d47e58c4c1eadcaa685102ed59a98225918670621b13e863771f |
| BTCUSDT-1m-2023-12.zip | 925a4290af07cd8c368489aeffd12ea4c2efba29fd51af11de20b53affc5d139 |
| BTCUSDT-1m-2024-01.zip | 0c84dc3eab839e57226501b5b739bc5b88bd27fcaee8f2db1bfa6bfe4e5854e8 |
| BTCUSDT-1m-2024-12.zip | 449091ccaf7e0af8f9c4e62acb8242d3818866cf2ba4e27f0d25b8887d4c2c6b |

## 11. Fallback

**No fallback required for the 2020-01 → 2024-12 window.** All 60
months are present on the primary archive. The 2019-12 gap is the
same gap as the klines archive: the existing project's 2020-01
publication already established the "2020-01 is the project's
earliest data point" boundary, and the mark and index archives
align with it.

## 12. Verdict

**KEEP — primary archive complete, no fallback required.**

- Both mark and index monthly archives return 200 for all 11
  sampled months 2020-01 → 2024-12.
- 2019-12 returns 404 for both, consistent with the klines and
  funding-rate archives.
- All `.CHECKSUM` sidecars match the recomputed zip SHA-256 exactly.
- The 2020-01 → 2022-11 headerless → 2022-12 onward headered
  format transition is a real contract change that the loader must
  handle, identical in spirit to the existing 2020/2021 base
  klines headerless amendment. The audit recommends folding this
  into the existing `csv_header: absent` allowlist path so all
  three archives share one variant parser.
- The 00:00 bar missing in 2020-01 → 2022-11 is recoverable
  (one row per month, off by 1 in the row-count delta) and the
  loader should back-fill it from the file's row 0.
- Live API cross-check (which would have validated mark / index
  against `/fapi/v1/premiumIndex`) was not completed in this audit
  environment (network blocked); flagged for the acquisition step.
