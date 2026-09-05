# Quantara Protocol v1 — Zcode Execution Plan Index

**Status:** STAGE 1 ACCEPTED — Stage 2 is next but has not started
**Date:** 2026-08-31
**Project root:** `D:\PROJECT\Quantara`
**Implementation worker:** Zcode
**Acceptance auditor:** Hermes

## Why this is split

The former all-in-one plan was too large for reliable executor attention. Protocol v1 is divided at
four real acceptance seams. Zcode executes one packet only; Hermes audits before any next packet.
No stage may start until the previous stage is accepted.

## Stage order

1. `docs/superpowers/plans/2026-08-31-protocol-v1-stage-1-scientific-freeze.md`
   - Packets P00–P02.
   - Freezes scientific semantics and 2025 guardrails before implementation.
2. `docs/superpowers/plans/2026-08-31-protocol-v1-stage-2-data-platform-btc-funding.md`
   - Packets D00–D08 and S01-A/B/C.
   - Proves shared architecture against one complete real source before scaling.
3. `docs/superpowers/plans/2026-08-31-protocol-v1-stage-3-remaining-series.md`
   - Packets S02-A/B/C through S13-A/B/C.
   - Canonicalizes the remaining 12 series one source and one audit gate at a time.
4. `docs/superpowers/plans/2026-08-31-protocol-v1-stage-4-research-and-evaluation.md`
   - Packets H00–H07 and E00–E04.
   - Builds the point-in-time research table, rehearses on 2020–2021, runs locked 2022–2024, and
     conditionally evaluates 2025 once.

## Global routing rule

Never tell Zcode to execute a stage or all four plans. Give one packet id only. Zcode commits locally
and stops. Hermes independently checks the diff, tests, live data execution, hashes, quality,
publication graph, and protocol compliance. Only Hermes can return ACCEPTED.

## Next routing state

Stage 1 is accepted. No execution prompt is active in this index. Stage 2 is in progress. Authorized 2026-09-03: Protocol v1.1 is frozen (PR #10, merge `566f4c2`). D00–D08 are accepted and merged (PR #11 `8e1d288`, PR #12 `97f4e8b`, PR #13 `fdbb0e3`, PR #14 `69405b3`, PR #15 `0f5152c`, PR #16 `1dc1457`, PR #17 `830dcbc`, PR #18 `e095d39`, PR #19 `831a56f`); the shared data-platform layer is complete. **S01-A is accepted and merged (PR #20 `6708163`)** — the first packet to touch real exchange data; the frozen acquisition/parsing/canonical/quality/publication chain is verified against real `data.binance.vision` boundary archives for 2020-01 and 2024-12. **S01-B is accepted and merged (PR #21 `a3e6e46`)** — the full 60-period inventory is verified with 5481 settlements, zero duplicates, zero conflicts and provisional quality PASS on every period, so S01-C needs no designed-gap or duplicate approval. **D09 is accepted and merged (PR #22 `b526dd0`)** and **finding F-S01B-1 is CLOSED**: both acquisition layers now share one public classifier `transport_retry_kind` keyed on exception type instead of substring-matching the exception message, so a server-dropped connection (`httpx.RemoteProtocolError`) is retried and evidenced; suite 2097 → 2107. Residual risk: parallel acquisition is still unreliable against this provider — post-fix `workers=4` reaches 19 of 60 periods before a period fails all three genuine attempts, while `workers=1` completes 60/60 — so **full backfills run `workers=1`**. Next: **S01-C only**, from `2026-08-31-protocol-v1-stage-2-data-platform-btc-funding.md`. Per the successor master plan's post-C5 decision of record, Stage 2 packets no longer use a per-packet worktree: work in `D:\PROJECT\Quantara` on a dedicated feature branch with `git status --short` empty before starting; commit locally, do not push or merge, and stop for Hermes audit.
