# Live historical-data acquisition feasibility audit

**Project:** Quantara (`D:\PROJECT\Quantara`)
**Window:** 2020-01-01 → 2024-12-31 (2025 deliberately excluded — sealed final canary)
**Date opened:** 2026-08-30
**Status:** A1 complete; A2–A10 queued
**Owner authorization:** "do we can breack task to small i dont want you to stuck on my screen , just after task 1 done go to another one" (2026-08-30)

## Scope and method

For each candidate feature family we verify — through real archive downloads, primary
documentation, or endpoint probes — and record the following evidence. Anything not
directly observed is labelled **inference**; the audit never describes unavailable
history as available.

1. earliest real timestamp
2. complete monthly coverage across 2020-2024 and exact gaps
3. timestamp/settlement semantics
4. realistic publication delay
5. pagination and rate limits
6. revision behavior
7. licensing and retention/redistribution rights
8. reproducibility and SHA-256 sample hashes
9. fallback source if unavailable

Order is fixed: A1 funding, A2 OI / ΔOI, A3 mark/index, A4 basis, A5 liquidations,
A6 options IV/skew/OI, A7 ETHUSDT perp, A8 BTCUSDT spot, A9 second BTC venue,
A10 consolidate.

## Status tracker

| ID | Series | Status | Evidence artifact | Verdict |
| --- | --- | --- | --- | --- |
| A1 | BTCUSDT USD-M funding rate | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a1-funding-rate.md` + `temp/audit_a1_funding/funding_probe_v1.json` | KEEP — primary archive complete 2020-01 → 2024-12, 8h settlement, ±33 ms jitter, `.CHECKSUM` matches every probed month |
| A2 | OI / ΔOI | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a2-open-interest.md` + `temp/audit_a2_oi/oi_probe_v1.json` + `temp/audit_a2_oi/oi_probe_v2.json` | KEEP with caveats — `metrics` archive 2020-09-01 → 2024-12-31 at 5-min; 2020-01 → 2020-08 is a real gap on Binance public archives; dedup the 2×288 anomaly in 2020-09 → 2021-01 |
| A3 | Mark / index | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a3-mark-index.md` + `temp/audit_a3_mark_index/mark_index_probe_v1.json` | KEEP — both `markPriceKlines` and `indexPriceKlines` monthly archives 2020-01 → 2024-12, 1m OHLCV; **same headerless→headered format transition on 2022-12-01 as the base klines** — apply existing `csv_header: absent` allowlist path to the two new dataset ids |
| A4 | Perp-spot basis | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a4-basis.md` + `temp/audit_a4_basis/basis_probe_v1.json` | KEEP — `premiumIndexKlines` archive is Binance's native TWA perp-vs-index basis 1m OHLCV (decimal fraction), 2020-01 → 2024-12; spot 1m archive extends back to 2017-08 for any future fallback; same headerless→headered transition on 2022-12-01 |
| A5 | Liquidations | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a5-liquidations.md` + `temp/audit_a5_liquidations/liquidation_probe_v1.json` | DROP — no Binance public liquidation archive (6/6 paths 404); live `/fapi/v1/allForceOrders` retains only 7 days; `@forceOrder` WS throttled to 1/sec/symbol since 2021-04-27; vendor archives inherit the cap and are not auditable to first-party source |
| A6 | Options IV / skew / OI | **COMPLETE** | `docs/superpowers/plans/2026-08-30-a6-options.md` + `temp/audit_a6_options/options_probe_v1.json` | PARTIAL KEEP with severe gap — BVOL index 2023-06-20 → 2026-08-29 (1,141 days, one 1-day gap 2024-06-30); EOH summary 2023-05-18 → 2023-10-23 (147 days only); 2020-01-01 → 2023-05-17 has **zero** first-party options history |
| A7 | ETHUSDT perpetual | pending | — | — |
| A8 | BTCUSDT spot | pending | — | — |
| A9 | Second BTC venue | pending | — | — |
| A10 | Final matrix | pending | — | — |

## Authorisation policy

The owner directed the audit to run unattended, one slice per run, advancing
automatically. **No model training is permitted in this audit, and 2025 evidence
must not be referenced.** Target and protocol freeze is the next workstream
**after** A10 closes.
