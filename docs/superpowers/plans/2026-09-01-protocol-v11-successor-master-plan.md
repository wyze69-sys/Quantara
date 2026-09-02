# Protocol v1.1 — Master Plan (Successor Freeze)

**Status:** IN PROGRESS — C1 `ACCEPTED` and merged (PR #5, merge commit `9a9196e`); C2 `ACCEPTED` and merged (PR #6, merge commit `7abce82`); C3 `ACCEPTED` and merged (PR #7, merge commit `b02cbc5`); C4 `ACCEPTED` and merged (PR #8, merge commit `3c77610`); C5a `ACCEPTED` and merged (PR #9, merge commit `c2e1a8d`); C5 is `NEXT` and is the final packet
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
| C2 | Year-stratified 168-clock-hour moving-block bootstrap, null-centred p-value, percentile CI, exact PRNG, 20,000 resamples, golden fixtures | B4 | `ACCEPTED` (PR #6, `7abce82`) |
| C3 | Exact-Decimal IRLS binding, both-class and calibration-failure rules, `M2K` naming, three fixed optional hypotheses under ordinary Holm, selection-evidence labelling | B5, B6, item 7 | `ACCEPTED` (PR #7, `b02cbc5`) |
| C4 | Archive-specific OI timestamp resolution or conservative unknown-role handling, exact final pre-2025 refit sample and failure state, sealed 2026 target-only endpoint buffer, one-year 2025 `REPLICATED` gate | B7, B8, B9, HIGH OI finding | `ACCEPTED` (PR #8, `3c77610`) |
| C5a | v1.1 draft loader, explicit semantic-hash scope rule, coverage/exclusion reporting and claim scope per candidate, exclusion-reason vocabulary, `longest_missing_run` definition, guardrail test suite | items 12, 13 | `ACCEPTED` (PR #9, `c2e1a8d`) |
| C5 | Spec/YAML/fixture synchronization, independent v1.1 expected fixture, new semantic SHA-256, and freeze | freeze | `NEXT` |

Only C5 may compute and freeze the Protocol v1.1 semantic hash. C5a defines the hash
*scope*; C5 computes the *value* against that scope.

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
8. Every packet gate list must include the **repository-wide** lint that CI runs,
   `ruff check src tests benchmarks`, not a lint scoped to the packet's new files.
   A scoped lint passes while a file the packet *edited* regresses. C4 shipped 4
   over-length lines in `tests/test_protocol_v11_draft_contract.py` past a clean
   scoped run; the audit caught it before merge. Local gate lists mirror CI or they
   are not gates.

## Packet plans

- C1: `docs/superpowers/plans/2026-09-01-protocol-v11-c1-version-lineage-time-semantics.md`
- C2: `docs/superpowers/plans/2026-09-01-protocol-v11-c2-bootstrap-inference.md`
- C3: `docs/superpowers/plans/2026-09-01-protocol-v11-c3-estimator-optional-family.md`
- C4: `docs/superpowers/plans/2026-09-01-protocol-v11-c4-timestamp-refit-buffer-replication.md`
- C5a: `docs/superpowers/plans/2026-09-01-protocol-v11-c5a-coverage-loader.md`
- C5: `docs/superpowers/plans/2026-09-02-protocol-v11-c5-freeze.md`

## Workflow scope and its termination (decided 2026-09-01)

The heavyweight flow — dedicated worktree per packet, PR before merge, independent
Hermes audit — is **scoped to packets C1–C5 only**. It ends when Protocol v1.1 is
frozen. It is not the permanent process for this repository.

It exists for three specific reasons, in descending order of weight:

1. **CI cannot run before code lands without a PR.** `.github/workflows/ci.yml`
   triggers on `pull_request` and on `push` to `main`. A branch push with no PR
   runs nothing at all. So the real choice is not "PR or no PR" but "gate before
   `main` or discover the failure after `main` is already red." Both C3 and C4
   proved this concretely: C3 failed CI on a shallow-clone artifact invisible
   locally, and C4 passed its plan-scoped lint while regressing the repository-wide
   `ruff check src tests benchmarks` gate that CI actually runs. Under a
   push-to-main flow both would have produced a red `main` plus a fixup commit in
   the permanent record.
2. **The PR body is the provenance artifact.** The scientific claim of this project
   is that every result-determining choice was frozen and hashed *before* the run.
   If the only evidence that an independent audit occurred is a chat transcript,
   it is not evidence. A PR is a timestamped, diffable record of what was verified
   against a named parent commit. In a project whose deliverable is credibility,
   that record is part of the output, not overhead.
3. **The worktree isolates the packet diff from unreported parallel work.** The
   `D:/PROJECT/Quantara` checkout receives real work on `main` outside the packet
   sequence. If a packet were implemented in that same directory, uncommitted
   edits would be swept into the packet diff and the byte-identity gates would
   prove nothing. This is the weakest of the three reasons: a plain feature branch
   in a single checkout gives identical isolation *provided the tree is verified
   clean at packet start*.

### What happens after C5

Once v1.1 carries a frozen semantic SHA-256, Stage 2 (P03 onward) is **execution
against a frozen contract**, not amendment of one. There is no post-hoc tuning
lever left to guard against, because the protocol text can no longer move without
invalidating its own hash. Reason 1 above still applies; reasons 2 and 3 largely
do not.

Therefore, from the first Stage 2 packet:

- **Drop the per-packet worktree.** Work in `D:/PROJECT/Quantara` on a feature
  branch. Precondition: `git status --short` is empty before the packet starts. If
  it is not, the packet does not start.
- **Keep branch + PR + CI green before merge.** Not for provenance now, but because
  CI is the only mechanism that runs the Windows/Rust/`-n 4` matrix, and local runs
  have twice diverged from it.
- **Keep the independent Hermes audit.** It is the step that has actually caught
  defects — a self-report has never been sufficient. It may be lighter than a
  protocol-packet audit: verify the gates CI does not cover, and re-derive any
  numeric constant the packet introduces.
- **Drop the frozen-artifact byte-identity loop**, except for the v1 and v1.1
  protocol artifacts and their fixtures, which stay byte-identical permanently.

This section is the decision of record. Any later drift back toward
push-straight-to-`main`, or forward into per-packet worktrees for ordinary Stage 2
work, should amend this section rather than happen silently.

## Execution prompt

```text
Read D:\PROJECT\Quantara-worktrees\<worktree>\docs\superpowers\plans\<packet-plan>.md
and execute that packet only. Tests first with real red output. Run every packet gate.
Commit only the packet allowlist. Do not push, merge, or auto-advance.
Return COMPLETE / BLOCKED / INCOMPLETE with raw commands, outputs, changed files,
hashes, and risks. STOP after the report.
```
