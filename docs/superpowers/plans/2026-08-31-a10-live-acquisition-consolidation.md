# A10 — Live acquisition consolidation and final source verdicts

**Status:** COMPLETE
**Scope:** A1–A9 acquisition feasibility only
**Important:** This document authoritatively supersedes conflicting semantic, gap, completeness, publication-lag, and rights claims in the earlier A1–A6 reports. It does not train a model or unseal 2025.

## Final matrix

### KEEP

- **A1 BTC settled funding:** KEEP. First-party monthly archive from 2020-01. Use settled records only after effective time; archive publication and real-time availability are separate concepts.
- **A2 BTC OI/ΔOI:** KEEP WITH CAVEATS from 2020-09-01. Prehistory null. Enumerate duplicates/gaps before ingestion; timestamp meaning remains conservatively eligible only after the snapshot boundary plus measured lag.
- **A3 BTC mark and index:** KEEP WITH CAVEATS. All 60 monthly objects exist, but sampled 2020-01 and 2020-12 files contain real minute gaps. Headerless row 0 is data, not a missing bar.
- **A4 Binance native premium index:** KEEP WITH CAVEATS. It is an impact-price premium index, not mark/index or mark/spot basis. Real sampled gaps remain null.
- **A7 ETH price/funding/native premium:** CANDIDATE KEEP. ETH OI is only PARTIAL KEEP from 2021-12-01. ETH enters no model without an incremental gate.
- **A8 BTCUSDT Binance spot:** KEEP WITH EXPLICIT GAPS. 60/60 files and checksums verified; 15 discontinuities and 2,325 missing minutes.
- **A9 Kraken XBT/USD:** KEEP WITH EXPLICIT GAPS for an optional second-venue family. 20 missing hourly intervals, no duplicates.

### DROP FROM PROTOCOL V1

- **A5 liquidations:** DROP. No complete auditable first-party 2020–2024 market tape. Historical public market REST, current private user history, and lossy WebSocket snapshots are distinct and none solves the requirement.
- **A6 Binance options:** DROP. Coverage begins in 2023, is regime-confounded, and the earlier report’s continuity claims are not supported by its file counts.

### DISTINCT DIAGNOSTICS, NOT SUBSTITUTES

- Native Binance premium index.
- Constructed `mark/index - 1`.
- Constructed `mark/spot - 1`.

These are related but not algebraically equivalent. Protocol v1 may freeze one primary native-premium feature and one separate spot/perpetual divergence family; it must not call them interchangeable.

## Corrections to earlier audits

### A1 funding

- Sixty filenames were listed, but only 15 monthly contents were sampled. Do not claim all 60 contents were row/gap/checksum verified.
- Ninety funding rows correspond to a 30-day month, not a 31-day month.
- Settlement-time economic availability and monthly-file publication are different timestamps.
- Do not claim universal append-only/finality or a universal ±0.75% cap without source-specific evidence.

### A2 OI

- 2020-09-01 through 2024-12-31 is 1,583 calendar days.
- Duplicate behavior observed in samples must not be generalized to every day without enumeration.
- A 287-row day beginning 00:00 and ending 23:55 has an interior missing bin.
- `create_time` semantics are not frozen as “bar open”; use conservative eligibility.

### A3 mark/index

Fresh correction probe:

- Script SHA-256: `14916bafb03150d119009c650a600120dcebbde4dc750a647ff410330f722bb1`
- Sidecar SHA-256: `d8ac8449e0fa58280cc8ecb0be8607277dc1ccc3968c2b1810eebcd8b4db1213`
- 60/60 monthly objects and checksum sidecars exist for 2020–2024.
- Pre-2022-11/12 transition files are headerless; physical row 0 is the valid 00:00 bar.
- 2020-01 mark/index: 44,611 rows and 29 missing bins.
- 2020-12 mark/index: 44,616 rows and 24 missing bins.
- These interior gaps are real; they cannot be “back-filled” from row 0.

### A4 premium and spot

- Native premium formula uses impact bid/ask relative to index; it is not `(mark-index)/index`.
- 2020-01 premium: 44,611 rows and 29 missing bins.
- 2020-12 premium: 44,534 rows and 106 missing bins across two gaps.
- Earlier spot counts discarded row 0. Correct full A8 enumeration replaces the sampled A4 gap summary.
- Positive premium alone does not mechanically prove the final funding transfer direction because funding includes other mechanics.

### A5 liquidations

- Historical public market `/allForceOrders` documentation used a recent 7-day query restriction.
- Current authenticated `/forceOrders` can expose up to 90 days of the requesting user’s own force orders; this is not market-wide history.
- Current public WebSocket documentation describes the largest liquidation snapshot per symbol per 1,000 ms. It remains incomplete.
- Do not claim every vendor necessarily inherits the public cap; vendor feed provenance is unknown until audited.

### A6 options

Earlier counts contradict continuity claims:

- 2023-06-20 through 2026-08-29 spans 1,167 dates; 1,141 BVOL files imply 26 absent dates, not one.
- 2023-05-18 through 2023-10-23 spans 159 dates; 147 EOH files imply 12 absent dates.
- BVOL’s first sampled files begin after midnight and EOH samples do not establish 24 observations per contract/day.
- Treat coverage as partial/unresolved and DROP options from Protocol v1.

## Missing-data policy

1. Missing means null, never zero by default.
2. Never interpolate price, premium, mark, index, or venue gaps.
3. A feature is invalid if any required lookback crosses a gap unless the frozen feature definition explicitly tolerates sparse state observations.
4. A label is invalid if its required price path or endpoints are unavailable.
5. Known pre-archive periods remain null; no backward fill.
6. As-of joins are backward on `eligibility_ts`; nearest and forward joins are forbidden.
7. Duplicate rows must be byte-compared. Exact duplicates may be deterministically deduplicated with evidence; conflicts block publication.

## Point-in-time and publication contract

Every source record must preserve:

- `event_ts`
- `interval_open_ts`
- `interval_close_ts`
- `settlement_or_snapshot_ts`
- `archive_publication_ts`
- `ingestion_ts`
- `eligibility_ts`

Rules:

- `eligibility_ts < prediction_ts` for Protocol v1.
- Completed bars: eligible after close plus measured/conservative ingestion delay.
- Settled funding: eligible after settlement plus delay.
- OI snapshots: eligible only after the snapshot boundary plus delay.
- Monthly/daily archive publication is ex-post acquisition evidence; it is not automatically the real-time eligibility time of underlying observations.
- Production operation requires live-source replay with measured latency. Do not invent fixed 5-second/5-minute constants without measurement.

## Rights matrix

- **Binance USD-M archives:** internal research only under `OWNER_APPROVED_PENDING_COUNSEL`; confirm the rights record covers every new family.
- **Binance spot:** rights-record amendment/review required; internal research posture only.
- **Binance options:** separate options-terms review required; excluded from Protocol v1.
- **Kraken OHLCVT:** internal research/backtesting posture only; no raw redistribution or customer-facing reconstructable feed without written permission/data agreement.
- **Third-party liquidation/options vendors:** separate vendor-specific provenance, license, retention, and redistribution audit required before use.

No audit here grants commercial display or redistribution rights.

## Fallbacks

- Funding/OI/mark/index/premium: no unverified fallback. Missing first-party intervals remain null.
- Binance spot: no interpolation; optional first-party trade reconstruction requires a separate verified pipeline.
- Kraken missing candles: remain null unless Kraken time-and-sales proves a frozen zero-trade/reconstruction rule.
- Liquidations: no Protocol-v1 fallback.
- Options: no Protocol-v1 fallback.

## Reproducibility anchors

- A7/A8 probe: `2e06c9d74d3535eaf6f36887c8d638e778efba79979e4f8a65346fe505aa0f79`
- A7 sidecar: `42ceb787835603c83c1b8c69c0628b616c943274e4f9d890f57971b83585fbad`
- A8 sidecar: `68136566f8352c37a80446db3a63db9e1d1b0a803e7c7162108c2b3aa4c8c54f`
- A9 probe: `54af490a94023b458b0627acb09d0422c7865b879720071787338cc5e434182c`
- A9 sidecar: `d90cadf07b59c113656518523c6dc257e5971c17ed50546e91d25a6c55a55f33`
- Kraken XBTUSD hourly member: `b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297`
- A3/A4 correction probe: `14916bafb03150d119009c650a600120dcebbde4dc750a647ff410330f722bb1`
- A3/A4 correction sidecar: `d8ac8449e0fa58280cc8ecb0be8607277dc1ccc3968c2b1810eebcd8b4db1213`

Older A1–A6 per-file hashes remain in their sidecars, subject to this correction register’s interpretation.

## Final acquisition verdict

A7–A10 are complete. Quantara has enough defensible first-party data to proceed to a separate **protocol-freeze** step using:

- BTC volatility baseline inputs;
- BTC settled funding;
- BTC OI from 2020-09-01;
- Binance native premium index;
- Binance spot/perpetual divergence with validity masks;
- optional ETH family with OI only from 2021-12-01;
- optional Kraken XBT/USD hourly family.

Liquidations and options are excluded. No model training or 2025 outcome inspection occurred during these audits.
