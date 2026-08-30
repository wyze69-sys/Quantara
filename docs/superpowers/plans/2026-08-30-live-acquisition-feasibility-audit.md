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
| A3 | Mark / index | pending | — | — |
| A4 | Perp-spot basis | pending | — | — |
| A5 | Liquidations | pending | — | — |
| A6 | Options IV / skew / OI | pending | — | — |
| A7 | ETHUSDT perpetual | pending | — | — |
| A8 | BTCUSDT spot | pending | — | — |
| A9 | Second BTC venue | pending | — | — |
| A10 | Final matrix | pending | — | — |

## Authorisation policy

The owner directed the audit to run unattended, one slice per run, advancing
automatically. **No model training is permitted in this audit, and 2025 evidence
must not be referenced.** Target and protocol freeze is the next workstream
**after** A10 closes.
