# Quantara Data Slice 005 — Temporal Expansion 2024-Q1 Design

**Status:** Proposed design; awaiting owner approval before implementation
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Predecessors:** slice 003b research tables (`268f038`), slice 004 validation folds (`0d66198`)

## 1. Goal and rationale

Extend the verified data window from one month (January 2024, 744 × 1h bars) to the full first
quarter (January–March 2024) across every layer: klines → canonical → derived (1h, 1d) →
research table → validation folds. Slice 004 showed the binding constraint is no longer code —
744 bars yield only 5 folds / 384 test rows, which is statistically thin. Every downstream layer
already generalizes to larger N (property-tested), so expansion multiplies usable evidence
without touching the analytical core.

Q1 2024 is 91 days (Jan 31 + Feb 29 + Mar 31; 2024 is a leap year).

## 2. Governance posture

Unchanged: `acquire_internal`, `retain_raw_internal`, `normalize_internal`, `analyze_internal`
are `OWNER_APPROVED_PENDING_COUNSEL` under `binance-usdm-provider-rights.v2.yaml`; no rights
record is created or amended; `model_train_internal` stays `UNKNOWN` and unexercised. Network
access remains confined to the integration-marked module and `data.binance.vision` (the already-
approved host), with per-archive SHA-256 checksum verification before any parse.

## 3. Core idea: range datasets at the kline layer

Upstream archives are monthly zips, but nothing else in the stack is month-bound:
`expected_row_count` is calendar math over `[start, end)` at one-minute cadence, and all
downstream layers consume positional tuples plus lineage. Therefore:

- Introduce **dataset-descriptor/v2**: identical to v1 except the single-month source fields are
  replaced by an ordered `months` list (e.g. `["2024-01", "2024-02", "2024-03"]`) from which
  archive/checksum URLs and member patterns are derived by the existing templates. Strict
  loading: unknown keys rejected; v1 descriptors continue to load byte-compatibly; the schema id
  participates in identity so v1 artifacts are unaffected.
- The base pipeline acquires **every** archive first, verifies **every** checksum, then parses
  and concatenates in chronological month order. Any failed month blocks the whole dataset
  before publication — never a partial publish.
- Downstream layers need **configs only**: new derived/research/validation descriptors reference
  the q1 parent ids; no module changes.

## 4. Boundary-integrity invariants (the heart of the slice)

Concatenation must prove seam correctness, not assume it:

1. **Continuity:** consecutive 1-minute `open_time_ms` values differ by exactly `60_000` across
   the entire span — including month seams (no gaps, no overlaps).
2. **Monotonicity:** timestamps strictly increase over the full range.
3. **Segment accounting:** each month's parsed row count equals its own calendar expectation
   (e.g. February 2024 contributes 29 × 1440 = 41,760 rows); the total equals
   `expected_row_count`.
4. **Identity binding:** schema fingerprint/content hash bind the ordered month list; a dataset
   over different months can never collide with another.
5. **All-or-nothing:** checksum failure, parse failure, or invariant violation in ANY month
   aborts pre-publication with the standard exit-code taxonomy.
6. **Immutability:** January's existing v1 chain remains byte-for-byte intact; q1 datasets use
   new dataset ids and fresh lineage roots.

Store layout note: the dataset directory derives from the period start (`month=01`); this is a
labeling detail, documented here — not a semantics change.

## 5. Acceptance arithmetic (pinned before implementation)

| Layer | Artifact | Expected |
| --- | --- | --- |
| Canonical 1m | `…_1m_2024_q1` | 91 d × 1440 = **131,040 rows** |
| Derived 1h | `…_1h_2024_q1` | 91 d × 24 = **2,184 bars** |
| Derived 1d | `…_1d_2024_q1` | **91 bars** (still undersized for validation — rejection path preserved) |
| Research | `…_1h_2024_q1_research_core_v1` | 2,184 rows; null budgets `{ret 1, roc 60, rvol 20, volratio 19, labels 24}` (head/tail regions independent of N) |
| Validation | `…_1h_2024_q1_validation_wf_v1` | first test start 360; **25 folds**; test lengths 72×24 then 96 (remainder merge); `test_rows` 1824; `excluded_head_rows` 360 |

Validation coverage uses the truthful aggregates from the slice-004 amendment
(`{total_rows, fold_count, test_rows}`; no `role_counts`).

## 6. Pipeline contracts carried forward unchanged

Truthful milestones (`object_written` = genuine creation, `commit_renamed` = genuine rename,
`pointer_replaced` drives post-pointer `referenced_commit`), PASS-only quality, exit codes
`0/2/3/4`, `--dry-run` verification-on writes-nothing, idempotent rerun `VERIFIED_NO_OP`
byte-identical, lineage binding to the immediate parent commit address at every layer.

## 7. Testing requirements

- Unit: v2 descriptor matrix (valid months list; v1 byte-compat; unknown key rejected;
  unsorted/duplicate months rejected; empty months rejected); concatenation invariants over
  synthetic two-month fixtures including deliberately gapped/duplicated seams (must BLOCK);
  per-month segment accounting; identity distinctness across month sets.
- Recovery: injected failure in the second archive (checksum/parse) → BLOCKED/FAILED with no
  partial commit and staging cleaned; rerun after fix publishes normally.
- Integration (marked, serial, networked): acquire real Q1 archives → normalize → derive 1h/1d
  → research → validation through the CLI; assert §5 numbers end-to-end; January v1 chain tree
  digest unchanged throughout; rerun `VERIFIED_NO_OP` byte-identical at each layer.
