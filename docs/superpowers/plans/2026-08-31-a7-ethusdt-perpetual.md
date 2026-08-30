# A7 — ETHUSDT perpetual feasibility audit

**Status:** COMPLETE
**Audit window:** 2020-01-01 through 2024-12-31
**Verdict:** **KEEP WITH RESTRICTIONS** — ETH traded price, funding, mark, index, and native premium archives are usable candidate inputs. ETH OI begins only on 2021-12-01 and is not a full-window feature. ETH remains optional and must later beat the BTC-only model under the frozen incremental gate.

## Evidence and reproducibility

- Probe: `temp/probe_a7_a8_v1.py`
- Raw sidecar: `temp/audit_a7_a8/a7_ethusdt_probe_v1.json`
- Fresh execution: 2026-08-31, exit 0
- Probe SHA-256: `2e06c9d74d3535eaf6f36887c8d638e778efba79979e4f8a65346fe505aa0f79`
- Sidecar SHA-256: `42ceb787835603c83c1b8c69c0628b616c943274e4f9d890f57971b83585fbad`
- All sampled ZIP SHA-256 values matched Binance `.CHECKSUM` sidecars.

Primary source: `https://data.binance.vision/` under `data/futures/um/`.

## Coverage result

- ETHUSDT traded 1m klines: 60/60 monthly objects, 2020-01 through 2024-12.
- Funding-rate history: 60/60 monthly objects, 2020-01 through 2024-12.
- Mark-price 1m klines: 60/60 monthly objects.
- Index-price 1m klines: 60/60 monthly objects.
- Premium-index 1m klines: 60/60 monthly objects.
- Daily metrics/OI: first archived date `2021-12-01`; 1,127/1,127 daily files through 2024-12-31, with no missing filenames or missing checksum sidecars after the first date.
- `2019-12` monthly objects are absent for the five monthly futures families. This is an honest boundary, not a value to reconstruct.

“60/60” proves archive-object coverage. It does not by itself prove every minute in every ZIP. Eleven boundary/regime months per monthly family were content-parsed and checksum-verified; full ingestion must enumerate every timestamp before publication.

## Sample findings

### Traded price

The sampled traded-price months had complete 60-second grids. Representative anchors:

- 2020-01: SHA-256 `a3e4f209b53ba03eb5adbb9560faf88431cd268b1cc7890fce488fb7674f385e`, 44,640 rows, `00:00` through `23:59`.
- 2024-12: SHA-256 `82018947075e35e5ac0a771bb97a22118008db2c6fb6a94f8c1a2c4ebb34d12b`, 44,640 rows.

### Funding

Sampled files contained 8-hour settled records with millisecond-scale timestamp jitter. Representative anchors:

- 2020-01: SHA-256 `0ce8da3b2ee7eceb6616efa215a2a1b1aab7b5b04becebe73634a95ec0abfa90`, 93 rows.
- 2024-12: SHA-256 `11a0847e8aacb32eeb725611fda4fe6a8419c03eb0c16e14dfc3b9287e78ecc9`, 93 rows.

Use settled funding only at or after its effective timestamp. A currently predicted funding rate is a different, revisable variable and is outside this audit.

### Mark, index, and native premium

Headerless files must parse physical row 0 as data. The format becomes headered by 2022-12. Samples revealed real historical gaps:

- 2020-01 mark/index/premium: 44,611 rows; one 30-minute timestamp jump, meaning 29 missing minute bins.
- 2020-12 mark/index: 44,616 rows; one 25-minute jump, meaning 24 missing bins.
- 2020-12 premium: 44,534 rows; two gaps, maximum 83 minutes, 106 missing bins total.

These are not recoverable “header offsets.” Missing bins remain null and any derived feature window crossing them must be invalidated.

Representative 2024-12 hashes:

- mark: `19b9ceda7d035adf49e05736ef09b2c68ede9a30f69d1ef57d31d853788c6174`
- index: `e6cf22aeb9bdb5e2ea8a84fabd2f77a9f38ff512388ecba82818cda9c8d01f4c`
- premium: `49fe9e8b31b539f74d639f59bfb16f924d2077ef19c4a661c43db8c8c6fc56bd`

The native premium index is Binance’s impact-price premium series. It is not algebraically equal to `mark/index - 1` or `mark/spot - 1`.

### OI/metrics

- No ETH metrics archive exists before 2021-12-01.
- The 2021-12-31 sample has 287 distinct rows/timestamps rather than 288, so one interior 5-minute observation is absent.
- Sampled 2022–2024 boundary files have 288 distinct rows and timestamps.
- No backward fill, zero fill, or synthetic prehistory is allowed.

Representative hashes:

- 2021-12-31: `a6f6fed7161cf90aa826f060ced26e8f50f6514b5d1eaafca5b0c022e2aeb206`
- 2024-12-31: `cb2d7c934662c0f0cc6160649465bfa437f3d6862a454eceb70cfca4b5b5cf57`

## Point-in-time rules

Preserve `event_ts`, `interval_open_ts`, `interval_close_ts`, settlement/publication timestamp, ingestion timestamp, and `eligibility_ts`.

- Completed bars become eligible only after interval close plus a conservative measured ingestion delay.
- Settled funding becomes eligible at/after the settlement timestamp plus ingestion delay.
- Metrics/OI uses backward as-of joins only after its snapshot/publication boundary plus ingestion delay.
- Monthly archive publication is ex-post acquisition evidence, not the real-time availability timestamp of each underlying observation.
- No nearest/forward joins and no unfinished bars.

## Rights

Use is approved only for Quantara internal research under the existing owner-approved-pending-counsel posture. Commercial display, raw redistribution, and customer-facing data delivery remain unresolved. This audit does not grant those rights.

## Final A7 decision

- ETH price/volatility: **candidate KEEP**.
- ETH settled funding: **candidate KEEP**.
- ETH native premium: **candidate KEEP**.
- ETH OI/ΔOI: **PARTIAL KEEP from 2021-12-01 only**.
- ETH family in final model: **NOT YET ACCEPTED**; retain only if it beats the identical BTC-only model under the frozen incremental Brier/calibration gate.
