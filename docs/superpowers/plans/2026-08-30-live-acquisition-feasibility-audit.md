# Live historical-data acquisition feasibility audit

**Project:** Quantara (`D:\PROJECT\Quantara`)
**Window:** 2020-01-01 → 2024-12-31 (2025 deliberately excluded — sealed final canary)
**Date opened:** 2026-08-30
**Status:** **A1–A10 COMPLETE** — consolidated corrections and final verdicts are in `2026-08-31-a10-live-acquisition-consolidation.md`.
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
| A1 | BTCUSDT USD-M funding rate | **COMPLETE** | `2026-08-30-a1-funding-rate.md` | KEEP; 60 filenames listed, 15 contents sampled; settlement and archive publication are separate timestamps |
| A2 | OI / ΔOI | **COMPLETE** | `2026-08-30-a2-open-interest.md` | KEEP WITH CAVEATS from 2020-09-01; prehistory null; enumerate duplicates/gaps before publication |
| A3 | Mark / index | **COMPLETE — CORRECTED** | A3 report + A10 correction sidecar | KEEP WITH CAVEATS; row 0 is data and sampled 2020 files contain real minute gaps |
| A4 | Native premium + spot diagnostics | **COMPLETE — CORRECTED** | A4 report + A8 + A10 | KEEP native impact-price premium WITH CAVEATS; it is not mark/index or mark/spot; real gaps remain null |
| A5 | Liquidations | **COMPLETE — CORRECTED** | `2026-08-30-a5-liquidations.md` | DROP; no complete auditable first-party market tape; distinguish historical public REST, private user history, and lossy WebSocket |
| A6 | Options IV / skew / OI | **COMPLETE — CORRECTED** | A6 report + A10 | DROP FROM PROTOCOL V1; partial 2023+ coverage and prior continuity claims unsupported by file counts |
| A7 | ETHUSDT perpetual | **COMPLETE** | `2026-08-31-a7-ethusdt-perpetual.md` | KEEP WITH RESTRICTIONS; ETH OI starts 2021-12-01; model inclusion still gated |
| A8 | BTCUSDT spot | **COMPLETE** | `2026-08-31-a8-btcusdt-spot.md` | KEEP WITH EXPLICIT GAPS; 60/60 checksums, 15 discontinuities, 2,325 missing minutes |
| A9 | Second BTC venue | **COMPLETE** | `2026-08-31-a9-second-btc-venue-kraken.md` | Select Kraken XBT/USD; 20 missing hours, internal-use rights posture |
| A10 | Final matrix | **COMPLETE** | `2026-08-31-a10-live-acquisition-consolidation.md` | Final source, fallback, rights, hash, missing-data, and publication contract |

## Authorisation policy

The owner directed the audit to run unattended, one slice per run, advancing
automatically. **No model training is permitted in this audit, and 2025 evidence
must not be referenced.** Target and protocol freeze is the next workstream
**after** A10 closes.
