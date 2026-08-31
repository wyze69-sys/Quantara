# Quantara Protocol v1 — Zcode Execution Plan Index

**Status:** IN PROGRESS — P00 accepted; P01 is next
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
   - Packets D00–D07 and S01-A/B/C.
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

## First prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-31-protocol-v1-stage-1-scientific-freeze.md and execute P01 only.

Use a dedicated branch/worktree. Preserve all pre-existing untracked files. Follow the P01 file
allowlist and tests-first order. Run every P01 acceptance command. Commit locally only; do not push
or merge. Do not start P02. Do not acquire data, generate features, train models, or access 2025.
Return COMPLETE / BLOCKED / INCOMPLETE with raw commands, outputs, changed files, hashes, and
remaining risks. STOP after the report.
```
