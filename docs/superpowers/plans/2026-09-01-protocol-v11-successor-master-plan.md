# Protocol v1.1 — Master Plan (Successor Freeze)

**Status:** IN PROGRESS — C1 `ACCEPTED` and merged (PR #5, merge commit `9a9196e`); C2 is `NEXT`; C3–C5 not started
**Date:** 2026-09-01
**Predecessor:** Protocol v1, frozen at semantic SHA-256
`91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`
**Authorizing audit:** `docs/superpowers/reviews/2026-09-01-protocol-v1-three-reviewer-deep-audit.md`
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## Why a successor version exists

Protocol v1 has a sound narrow confirmatory design but is not deterministic enough to
execute unchanged. The independent audit verified nine BLOCKER findings: the frozen
artifacts do not uniquely define several result-determining operations. The verdict was
`PROCEED_WITH_SUCCESSOR_VERSION` with no scientific reset, no feature redesign, and no
unsealing of 2025.

Stage 2 (data platform) stays **BLOCKED** until Protocol v1.1 is frozen and
independently audited.

## Packet sequence

Exactly one packet per Codex invocation. Hermes audits between packets. Never
auto-advance.

| Packet | Scope | Audit findings repaired | Status |
| --- | --- | --- | --- |
| C1 | Version identity, lineage/supersession record, `T+2ms` ordering, nearest-rank Q80, exact purge inequality | B1, B2, B3, item 14 | `ACCEPTED` (PR #5, `9a9196e`) |
| C2 | Year-stratified 168-clock-hour moving-block bootstrap, null-centred p-value, percentile CI, exact PRNG, 20,000 resamples, golden fixtures | B4 | not started |
| C3 | Exact-Decimal IRLS binding, both-class and calibration-failure rules, `M2K` naming, three fixed optional hypotheses under ordinary Holm, selection-evidence labelling | B5, B6, item 7 | not started |
| C4 | Archive-specific OI timestamp resolution or conservative unknown-role handling, exact final pre-2025 refit sample and failure state, sealed 2026 target-only endpoint buffer, one-year 2025 `REPLICATED` gate | B7, B8, B9, HIGH OI finding | not started |
| C5 | Coverage/exclusion reporting and claim scope, spec/YAML/fixture synchronization, new semantic SHA-256, full tamper/boundary/solver/bootstrap/seal suite | items 12, 13, freeze | not started |

Only C5 may compute and freeze the Protocol v1.1 semantic hash.

## Standing invariants across all five packets

1. Protocol v1 artifacts stay byte-identical. The v1 hash never changes.
2. 2025 and its 2026 target buffer stay sealed. No labels, feature distributions, model
   scores, conditional outcome inspection, or protocol adaptation.
3. No floats in protocol hash semantics; decimal constants are exact strings.
4. No signed-return replacement, no sigma denominator floor, no arbitrary coverage
   cutoff, no new feature search.
5. Reintroducing LightGBM, XGBoost, return regression, directional actions, or economic
   gates requires a separately preregistered successor experiment — never a v1/v1.1
   correction.
6. Each packet: dedicated branch/worktree, tests first with real red output, focused
   gate, local commit only, stop for Hermes audit.
7. Only Hermes may mark a packet `ACCEPTED`.

## Packet plans

- C1: `docs/superpowers/plans/2026-09-01-protocol-v11-c1-version-lineage-time-semantics.md`
- C2–C5: written after their predecessor is accepted, so each plan reflects real
  audited state rather than forecast state.

## Execution prompt

```text
Read D:\PROJECT\Quantara-worktrees\<worktree>\docs\superpowers\plans\<packet-plan>.md
and execute that packet only. Tests first with real red output. Run every packet gate.
Commit only the packet allowlist. Do not push, merge, or auto-advance.
Return COMPLETE / BLOCKED / INCOMPLETE with raw commands, outputs, changed files,
hashes, and risks. STOP after the report.
```
