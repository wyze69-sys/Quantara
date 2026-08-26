# Quantara Data Slice 004 — Walk-Forward Validation Folds Design

**Status:** Proposed design; awaiting owner approval before implementation
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Predecessors:** slice 003b research tables (`268f038`), milestone-truthfulness fix (`290c963`)

## 1. Goal and non-goals

Slice 004 adds a lineage-bound, immutable **validation-folds artifact** derived from a published
research table: deterministic anchored walk-forward fold partitions with label-horizon embargo,
per-fold test-segment descriptive statistics computed with exact decimals, PASS-only quality
gates, and publication through the unchanged integrity protocol (CAS objects, authenticated
commits, current pointers, truthful milestones, idempotent reruns).

This is the evaluation harness that makes any future modeling trustworthy. It contains **no
model fitting, no parameter search, no information coefficient, no training code of any kind**.
Those are structurally out of scope while `model_train_internal` remains `UNKNOWN`.

## 2. Governance posture

- The descriptor gates on `analyze_internal` via
  `configs/legal/binance-usdm-provider-rights.v2.yaml` only. Fold construction and descriptive
  fold statistics over already-published internal analytical artifacts are analytical
  computation; `OWNER_APPROVED_PENDING_COUNSEL` permits them per `descriptor.py`
  (`APPROVED_INTERNAL_OPERATIONS`, permit check accepting that state for approved internal
  operations).
- No rights record is created, amended, or exercised beyond reading v2. `model_train_internal`,
  `commercial_production_eligible`, `customer_display`, and `raw_redistribution` stay `UNKNOWN`
  and untouched.
- Outputs remain private research evidence. `/data/` stays ignored and untracked.

## 3. Parent binding

The parent of a validation artifact is a **published research-table commit** (dataset type
`research_table`, e.g. the real 1h table whose commit address descends from base `702dab9f…`).
The validation descriptor must equal the parent research descriptor's approved identity fields
exactly: `provider`, `instrument_id`, `base_dataset_id`, `period`, feature-set name and version,
and all four parameters (`roc_window`, `vol_window`, `volume_window`, `label_horizon`). Any
mismatch is a stable descriptor error before any compute.

## 4. Fold scheme v1 (`anchored_walkforward_v1`)

Deterministic partition of the parent row range `[0, N)` into roles:

- `TRAIN` — anchored expanding history available for hypothetical future fitting.
- `EMBARGO` — gap immediately before each test segment.
- `TEST` — evaluation segment.
- `EXCLUDED` — rows in no fold (head warm-up region below the first viable test start).

Parameters (approved exact values only; any other value is a stable
`unsupported_parameter` error):

- `test_size = 72` (bars per test block)
- `min_train_size = 336` (two weeks of 1h bars)
- `embargo` — **derived, never user-set**: equals the parent's `label_horizon` (24)

Boundary arithmetic (all integer index math on `[0, N)`):

```text
first_test_start = min_train_size + embargo          # 336 + 24 = 360
test segments    = consecutive blocks of test_size rows starting at
                   first_test_start; the final partial block (< test_size)
                   merges into the last fold's test segment.
fold train       = [0, test_start - embargo) when its length >= min_train_size,
                   else the fold has no train region (train_range is null).
fold embargo     = [test_start - embargo, test_start) when train exists.
```

Rows `[0, first_test_start)` are `EXCLUDED`. Every row index belongs to exactly one role —
the four role sets form a disjoint, complete partition of `[0, N)`. A parent with
`N < min_train_size + embargo + test_size` yields zero viable folds and is rejected as
`undersized_parent_dataset` before any compute.

### Real-parent acceptance arithmetic (N = 744)

- `first_test_start = 360`; excluded head = 360 rows.
- Test segments start at 360, 432, 504, 576, 648; lengths 72, 72, 72, 72, and 96 (the final
  24-row remainder merges into fold 5).
- Exactly **5 folds**; total test coverage 384 rows; every train length ≥ 336; embargo 24 before
  every test.

## 5. Leakage invariants (property-tested, not asserted once)

1. **Partition completeness/disjointness:** union of roles is `[0, N)` with no overlaps, for any
   generated `N`.
2. **Embargo width:** whenever both train and test exist, `test_start - train_end == embargo`
   exactly.
3. **Label-horizon safety:** because `embargo == label_horizon`, the forward label window of any
   TRAIN row (`t .. t+H`) ends strictly before the earliest TEST index. The property test proves
   this symbolically and empirically: `max(train index) + H < min(test index)` for every fold.
4. **Boundary determinism:** fold boundaries depend only on `N` and the three parameters —
   perturbing parent *values* (not length) leaves the partition byte-identical.
5. **Statistic causality:** each fold's statistics are computed only from rows inside that
   fold's TEST segment — mutating any row outside a fold's test segment leaves that fold's stats
   bit-identical.

## 6. Per-fold statistics v1 (exact decimal, storage quantization Q18)

Computed per fold over its TEST segment rows only, using positional tuples from the parent
research table (columns `open_time_ms`, `f_ret_1`, `f_roc_60`, `f_rvol_20`, `f_volratio_20`,
`l_fwdret_24`, `l_fwddir_24`):

- `row_count`, `open_time_ms_first`, `open_time_ms_last`
- Per-column null counts for the six nullable columns
- `l_fwddir_24` sign distribution: counts of `-1`, `0`, `+1` (exact integers; sum equals
  `row_count` minus label nulls)
- `l_fwdret_24` mean/min/max in exact `Decimal`, rendered with `render_decimal_18`

No cross-column correlations, no returns attribution, no fitted quantities.

Structural-null expectation: features are null only in the table-head warm-up region and labels
only in the table-tail horizon region (both inherited from slice 003b construction). For each
segment and column, expected nulls equal the overlap between the segment range and that column's
structural null region; the quality gate requires **actual == expected exactly**.

## 7. Artifact format

One canonical JSON object (JCS-canonicalized bytes, UTF-8, LF):

```text
{
  "schema": "quantara.validation_folds/v1",
  "fold_set": "btcusdt_core_v1_wf72_v1",
  "scheme": "anchored_walkforward_v1",
  "parameters": {"test_size": 72, "min_train_size": 336, "embargo": 24},
  "parent_rows": 744,
  "excluded_head_rows": 360,
  "folds": [
    {
      "fold_id": 0,
      "train_range": [0, 336],        # null when no train region
      "embargo_range": [336, 360],
      "test_range": [360, 432],
      "stats": { ...section 6 fields... }
    }, ...
  ],
  "coverage": {"total_rows": 744, "role_counts": {"TRAIN": ..., "EMBARGO": ...,
               "TEST": 384, "EXCLUDED": 360}}
}
```

Ranges are half-open `[start, end)` integer index pairs. No floating point anywhere; every
decimal field is a `render_decimal_18` string. The artifact is stored through the existing CAS;
if `publication.py` restricts object kinds to an enumerated set, reuse the existing analytical
kind; otherwise use kind `validation_folds`. Either way the choice is recorded in the commit's
`object_refs` and verified by graph authentication like any other object.

## 8. Identity, hashing, lineage

- Additive-only extensions in `hashing.py`: `validation_schema_fingerprint` (domain-separated,
  includes schema id, scheme, parameters, fold set name/version, and the parent research
  fingerprint) and `validation_content_hash` over the canonical artifact bytes. No existing hash
  output changes byte-for-byte.
- The validation commit address binds lineage exactly like predecessors: content identity +
  parent research commit address + fold-set version, via a domain helper mirroring
  `derived_commit_identity`/its research counterpart.
- Rerun evidence keys extend with `{lineage}` so an unchanged world produces `VERIFIED_NO_OP`
  with a byte-identical pointer and exactly one retained commit.

## 9. Pipeline contract

`validation_pipeline.py` mirrors `research_pipeline.py` orchestration order:

descriptor load → `analyze_internal` gate (v2 record) → full base-graph authentication including
parent Parquet hash → `read_research_rows` → fold engines → statistics engines → quality
PASS-only → CAS put → lineage-bound stage/verify/write_current/read-back → attempt manifests
with truthful milestones.

Milestone truthfulness follows the slice-002 contract as corrected in `290c963`:
`object_written=True` only on genuine creation, `commit_renamed=True` only on genuine staging
rename (retained-commit reuse keeps it `False`), `pointer_replaced=True` on genuine pointer
writes, and post-pointer failure evidence keys `referenced_commit` off `pointer_replaced` —
never off `commit_renamed`.

Exit codes unchanged: `0` PUBLISHED / VERIFIED_NO_OP, `2` BLOCKED, `3` FAILED, `4` QUARANTINED.
`--dry-run` verifies everything and writes nothing.

## 10. Descriptor loader

`validation_descriptor.py` mirrors `research_descriptor.py` strictness: unknown keys rejected;
identity fields equal to the parent research descriptor's approved values; parameters restricted
to `{test_size: 72, min_train_size: 336}` exact values; `embargo` absent by definition (derived);
minimum parent size derived arithmetically as `min_train_size + embargo + test_size` (= 432) and
enforced against the parent's actual row count — undersized parents are
`undersized_parent_dataset`, rejected pre-compute.

## 11. Quality policy v1 (`PASS` only)

Evaluator `validation_*`: coverage partition holds (§5.1); every fold satisfies §5.2–5.5
arithmetic; per-segment actual nulls equal structural expectations (§6); sign-count sum
consistency; deterministic `quality_identity`. Any failure is `BLOCKED`/`FAILED` — never a
degraded publish.

## 12. Error taxonomy

Stable error ids mirroring predecessors: `invalid_descriptor`, `unsupported_parameter`,
`undersized_parent_dataset`, plus reuse of existing blocked/failed/quarantine paths. New errors
never change exit-code semantics.

## 13. Testing requirements

- Unit: descriptor matrix (valid, unknown key, identity mismatch, unsupported parameter value,
  undersized parent); fold engine properties §5.1–5.4 over generated `N`; statistic causality
  §5.5; quality evaluator fixtures including a failing fixture per invariant; pipeline e2e on a
  synthetic research parent through the real orchestration with rerun `VERIFIED_NO_OP`;
  recovery/corruption scenarios (missing/corrupt parent BLOCKED then restore-verifies; injected
  failures at object write / rename / pointer write → FAILED(3) with pointer untouched, staging
  cleaned, stale `.staging-*` removed; legitimate parent republication rebinds while the old
  validation commit stays byte-identical).
- Golden fixture: frozen expected fold artifact for a minimum-viable synthetic parent
  (`N = 432` → exactly one fold, test `[360, 432)`), generated by an independent stdlib-decimal
  reimplementation kept out-of-repo; committed fixture JSONs under `tests/fixtures/golden_validation/`.
- Integration (marked, serial): real-parent acceptance against the real store — publish folds
  from the real 1h research table, assert exactly 5 folds, coverage/exclusion numbers of §4,
  rerun `VERIFIED_NO_OP` byte-identical, parent tree digest unchanged.

## Amendment 2026-08-26 (post-implementation audit)

Section §4 contained an internal contradiction: anchored expanding trains overlap across folds,
so a per-row disjoint four-role partition (`TRAIN`/`EMBARGO`/`TEST`/`EXCLUDED`) is impossible as
originally worded, and any published per-row role counts would be false evidence. Resolved by
amending §7's coverage schema: the artifact publishes only truthful dataset-level aggregates —
`coverage = {"total_rows", "fold_count", "test_rows"}` plus top-level `excluded_head_rows`
(= `parent_rows − test_rows`) — and never a `role_counts` object. Per-fold train/embargo extents
remain authoritative inside each fold record. The `validation_coverage_partition` quality gate
enforces exactly these keys; the presence of `role_counts` is a hard failure.
