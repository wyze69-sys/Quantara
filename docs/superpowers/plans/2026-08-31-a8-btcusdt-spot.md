# A8 — BTCUSDT Binance spot feasibility audit

**Status:** COMPLETE
**Audit window:** 2020-01-01 through 2024-12-31
**Verdict:** **KEEP WITH EXPLICIT GAPS** — all 60 monthly 1m ZIPs and checksum sidecars exist and verify, but the minute tape contains 15 real discontinuities totaling 2,325 missing minute bins. Never interpolate or forward-fill them.

## Evidence and reproducibility

- Primary source: `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/`
- Probe: `temp/probe_a7_a8_v1.py`
- Raw sidecar: `temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json`
- Fresh execution: 2026-08-31, exit 0
- Probe SHA-256: `2e06c9d74d3535eaf6f36887c8d638e778efba79979e4f8a65346fe505aa0f79`
- Sidecar SHA-256: `68136566f8352c37a80446db3a63db9e1d1b0a803e7c7162108c2b3aa4c8c54f`

Every 2020-01 through 2024-12 ZIP was downloaded, parsed, hashed, and compared with its adjacent Binance `.CHECKSUM`: **60 verified, 0 missing, 0 checksum failures, 0 parse failures**.

## Timestamp and format semantics

- Each row is a 1-minute kline identified by interval open time.
- The 2020–2024 spot files are headerless; physical row 0 is the valid `00:00` bar and must not be discarded.
- A completed bar is causally usable only after its close time and measured/conservative ingestion delay.
- The monthly archive is an ex-post transport artifact; its file publication time is not the real-time event availability of the underlying bar.

## Complete gap manifest

Each pair gives last good minute, next good minute, and missing bins:

- 2020-02-09 01:59Z → 03:00Z: 60
- 2020-02-19 11:35Z → 17:30Z: 354
- 2020-03-04 09:21Z → 11:30Z: 128
- 2020-04-25 01:59Z → 04:30Z: 150
- 2020-06-28 01:59Z → 05:30Z: 210
- 2020-11-30 05:59Z → 07:00Z: 60
- 2020-12-21 14:09Z → 18:00Z: 230
- 2020-12-25 01:59Z → 03:00Z: 60
- 2021-02-11 03:40Z → 05:00Z: 79
- 2021-03-06 01:59Z → 03:30Z: 90
- 2021-04-20 01:59Z → 04:30Z: 150
- 2021-04-25 04:00Z → 08:45Z: 284
- 2021-08-13 01:59Z → 06:30Z: 270
- 2021-09-29 06:59Z → 09:00Z: 120
- 2023-03-24 12:39Z → 14:00Z: 80

Total: **15 discontinuities; 2,325 missing one-minute bins**.

No discontinuities were observed in 2022 or 2024. File existence is not proof of uninterrupted observations; the raw sidecar is the authoritative all-month timestamp manifest.

## Hash anchors

- 2020-01 ZIP: `02df6da44ed8145fbb9ed819858185d9e2f15eb025c5bec8a4ea2d8738cd0d19`
- 2024-12 ZIP: `58fef0b7c7abce7a0201efd04ed3732f236f607f3fcecf228fb8384cad1ae2c1`
- Full 60-file hashes: raw sidecar named above.

## Missing-data and join rules

- Preserve missing bars as null.
- Never treat archive absence as zero volume or no trading.
- Invalidate every spot-derived feature whose lookback crosses a missing interval.
- Invalidate every label or comparison requiring spot continuity through a gap.
- Join to the BTC perpetual timeline using backward causal alignment after both bars are complete; never nearest or forward join.
- Constructed `mark/spot - 1` is distinct from Binance’s native premium index.

For Protocol v1, use a normalized spot/perpetual divergence only after its exact formula and validity-mask behavior are frozen on design data.

## Publication and operational availability

Binance monthly archives are published after the month and may be revised as files. They prove reproducible historical acquisition, not real-time latency. A production replay must source the same observations live, record ingestion time, and establish a conservative eligibility delay. Protocol v1 must not invent a fixed delay without measurement.

## Rights

Binance spot is outside the clearly named USD-M scope of the current provider-rights record. Internal research use is allowed only under the project’s owner-approved-pending-counsel posture. Before commercial or customer-facing use, amend/review the rights record for Binance spot. Raw redistribution remains prohibited unless separately cleared.

## Final A8 decision

- BTCUSDT spot price: **KEEP WITH EXPLICIT GAPS**.
- Constructed spot/perpetual divergence: **candidate KEEP**, subject to causal join and validity masks.
- Continuous-tape or execution studies crossing the gaps: **DROP unless independently reconstructed and verified from complete first-party trades**.
