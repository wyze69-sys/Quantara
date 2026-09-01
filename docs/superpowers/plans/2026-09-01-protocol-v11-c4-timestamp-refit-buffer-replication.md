# Protocol v1.1 — Packet C4: Timestamp, Refit, Buffer, and Replication Contract (audit B7, B8, B9, HIGH OI finding)

**Status:** `NEXT` — not started
**Date:** 2026-09-01
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c4-timestamp-buffer`
**Branch:** `protocol-v11-c4-timestamp-buffer`
**Packet parent commit:** `b02cbc5` (`main`, the C3 merge commit)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists

C1 froze version identity and the `T+2ms` ordering. C2 froze inference (`B4`). C3
bound the estimator and fixed the three-hypothesis optional family. Four items
remain deferred to this packet, and the draft protocol says so in three places:

- `deferred_change_set["C4"].status == "DEFERRED"`
- `sealed_2025.successor_buffer_and_replication_rule == "DEFERRED_PACKET_C4"`
- spec §8 last paragraph: *"The additional endpoint buffer and replication-gate
  details are `DEFERRED` to packet C4 and are not implemented here."*

This packet repairs four audit findings:

- **HIGH — OI timestamp semantics are asserted but unproven.** Frozen Protocol v1
  and the v1.1 draft both call the five-minute open-interest timestamp an
  *interval start*. The authoritative A10 consolidation says `create_time`
  semantics are **not** frozen as bar open and that conservative eligibility must
  be used. A2's earlier "bar open" claim was superseded by A10. The current REST
  schema does not prove the historical `data.binance.vision` metrics archive's
  `create_time` meaning. The protocol must stop making the unproven claim while
  keeping the same arithmetic.
- **B7 — the final pre-2025 refit is absent.** Nothing in the protocol says which
  rows the retained candidate and paired B2 are refit on before the single 2025
  score, or what happens when that fit fails.
- **B8 — a full calendar-2025 origin set requires a 2026 label buffer.** All three
  original reviewers missed this. The final 2025 origin `2025-12-31 23:00 UTC`
  needs a BTC perpetual close at `2026-01-01 22:59:59.999 UTC`, which does not
  exist inside the sealed 2025 boundary.
- **B9 — `REPLICATED` is undefined.** The seven multi-year `success_gate` criteria
  cannot be applied to one calendar year, and the audit rejected all three
  reviewers' proposed one-year gates.

This is a **specification repair, not a scientific reset.** No new feature, no new
target, no new model family, no unsealing, no threshold search.

## 2. Hermes pre-verified findings

These were measured in this exact venv against the committed code at `b02cbc5`
before the plan was written. They are the reason several rules below exist. Codex
must **reproduce each one as a test**, not trust this document.

**G1 — the calendar-2025 hourly origin set is exactly 8,760.**

```text
first origin              2025-01-01 00:00:00.000 UTC   epoch_ms 1735689600000
last  origin              2025-12-31 23:00:00.000 UTC   epoch_ms 1767222000000
count                     8760
last origin label close   2026-01-01 22:59:59.999 UTC   epoch_ms 1767308399999
```

This matches `nominal_hours(2025) == 8760` in the frozen C2 module, so the 2025
bootstrap grid length is already correct and needs no change.

**G2 — exactly 23 origins depend on 2026 data, and they need exactly 23 hourly
bars.**

```text
first buffer-dependent origin   2025-12-31 01:00 UTC  ->  label close 2026-01-01 00:59:59.999
last  buffer-dependent origin   2025-12-31 23:00 UTC  ->  label close 2026-01-01 22:59:59.999
buffer-dependent origin count   23
distinct 1h bar closes required 23
bar opens span                  2026-01-01 00:00 .. 2026-01-01 22:00 UTC
```

The `2026-01-01 23:00` bar (close `2026-01-01 23:59:59.999`) is **outside** the
buffer and must be refused, not merely unused. A naive "acquire calendar day
2026-01-01" would produce 24 bars where only 23 are authorized.

**G3 — the buffer is target-only by construction, not by promise.** Under the
frozen C1 ordering, `prediction_ts = T + 2 ms` and the join is
`eligibility_ts < prediction_ts`, so every eligible feature row satisfies
`eligibility_ts <= T + 1 ms`. For the last 2025 origin that upper bound is
`2025-12-31 23:00:00.001 UTC`. No 2026 feature row of any series can ever be
eligible for a 2025 origin. Target-only is therefore a **provable consequence of
the frozen ordering**, and the protocol must state it as such rather than as an
acquisition promise.

**G4 — 1h bars are derived from 1m, so the buffer must be specified at 1m
granularity.** `configs/datasets/binance-usdm-btcusdt-1h-2024-derived.yaml` carries
`base_dataset_id: binance_usdm_btcusdt_klines_1m_2024` and
`transformation.name: multi_timeframe_aggregation`. In
`src/quantara/aggregation.py::aggregate_timeframe` a bar is emitted only from **60
contiguous complete minutes**, and:

```text
close_time_ms        = bucket + timeframe_ms - 1
nominal_available_ms = bucket + timeframe_ms
```

Anything short raises `IncompleteGroup`. The 23 authorized bars therefore require
exactly:

```text
1m rows required     1380
first 1m open        2026-01-01 00:00 UTC
last  1m open        2026-01-01 22:59 UTC   epoch_ms 1767308340000
last  1m close_ts    2026-01-01 22:59:59.999 UTC
```

**G5 — every available archive granularity over-reaches, so a truncation rule is
mandatory.** Binance descriptors in this repo use monthly archives
(`BTCUSDT-1m-2024-01.zip`).

```text
required 1m rows                     1380
monthly BTCUSDT-1m-2026-01.zip       44640 rows   over-reach 43260
daily   BTCUSDT-1m-2026-01-01.zip     1440 rows   over-reach    60
```

Neither granularity lands on the boundary. The protocol must freeze an explicit
post-parse truncation rule instead of assuming an archive that stops where the
buffer stops.

**G6 — the exact final refit sample is 37,969 nominal hourly origins.** Applying
the frozen purge inequality `O + 24h <= S` with `S = 2025-01-01 00:00 UTC` and the
frozen training start `2020-09-01 00:00 UTC`:

```text
refit train start           2020-09-01 00:00 UTC   epoch_ms 1598918400000
last eligible origin        2024-12-31 00:00 UTC   epoch_ms 1735603200000
last required label close    2024-12-31 23:59:59.999 UTC
nominal origin count        37969
naive full-range count      37992
excluded tail               23 origins, 2024-12-31 01:00 .. 2024-12-31 23:00 UTC
```

The excluded tail is 23 origins, the same count as G2 and for the mirror-image
reason. The `2024-12-30 23:00` cutoff already rejected in spec §7 would be wrong
by one hour; `37992` would be wrong by 23 origins.

**G7 — `O + 5 minutes` is the tightest rule valid under *both* unresolved OI
readings.** With `T` an hourly boundary and `prediction_ts = T + 2 ms`:

```text
O = T - 10 min  ->  eligibility 11:55  eligible
O = T -  5 min  ->  eligibility 12:00  eligible      <- latest eligible row
O = T           ->  eligibility 12:05  not eligible
```

Under the *interval-start* reading, a row stamped `O` covers `[O, O+5m)` and is
truly complete at `O + 5m`, so the rule is exactly tight. Under the *interval-end*
reading the row is already complete at `O`, so the rule is 5 minutes
conservative. The arithmetic is causally safe either way. Therefore C4 keeps the
frozen arithmetic unchanged and removes only the **unproven semantic label**. The
audit explicitly rejected GPT's categorical "period end" claim and the superseded
A2 "bar open" claim; C4 must adopt neither.

**G8 — the frozen C2 bootstrap already handles a single 2025 year unmodified.**
Calling the committed `bootstrap_b4` with one year:

```text
grids            {2025: 8760 positions}
paired-valid     5840
comparison_id    REPLICATION_2025|M2_vs_B2
derived seed     13432793617478683004
result at B=200  observed_mean 1/1000, ci_lower 1/1000, ci_upper 1/1000, p 1/201
```

Fail-closed behaviour also survives the one-year case: 168 paired-valid
observations succeed, 167 raise
`BootstrapB4InferenceError(reason='insufficient_observed_paired_valid', year=2025)`.
C4 therefore introduces **no new inference code** and must not reimplement the
bootstrap. The 2025 geometry under the frozen `L = 168`:

```text
H_2025                  8760
n_blocks = ceil(H/L)    53
concatenated hours      8904
eligible block starts   0 .. 8592   (8593 distinct)
CI ranks at B = 20000   lower 500, upper 19500
```

**G9 — the one-year gate must be five criteria, and the reduction is forced.**
Against the frozen seven-criterion `success_gate`:

```text
criterion 3  "positive improvement in at least two validation years"
             unattainable with one year (2 <= 1 is False)      -> must be dropped
criterion 4  "no year BSS_B2 < -0.02"
             implied by criterion 1 (0.02 >= -0.02)            -> non-binding
criterion 7  "yearly |bias| <= 0.04"
             implied by criterion 5 (0.02 <= 0.04)             -> non-binding
```

With a single year the pooled and yearly quantities are the same numbers, so
criteria 4 and 7 add nothing and criterion 3 is impossible. Claude's literal reuse
of all seven is therefore not merely awkward, it is arithmetically impossible. The
audit's five-condition B9 gate is the correct reduction and is what C4 freezes.

## 3. Standing prohibitions

Codex must obey all of these. Violating any one is a `BLOCKED` report, not a
judgement call.

1. **Do not read, open, enumerate, glob, or list the contents of any 2025 or 2026
   data.** The seal permits filename inventory only, and this packet does not need
   even that. All fits and fixtures in this packet are synthetic.
2. **Do not acquire any data.** C4 writes the *contract* for the buffer. It does
   not download, fetch, or stage a single byte. No network call.
3. **Do not modify frozen Protocol v1.** These six files must stay byte-identical:
   `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`,
   `configs/protocols/quantara-protocol-v1.yaml`, `tests/test_protocol.py`,
   `tests/test_protocol_guardrails.py`,
   `tests/test_protocol_document_contract.py`,
   `tests/fixtures/protocol_v1_expected.json`.
4. **Do not modify the C2 or C3 deliverables.** `src/quantara/bootstrap_b4.py`,
   `src/quantara/estimator_c3.py`, `src/quantara/training_metrics_logistic.py`,
   `src/quantara/evaluation_metrics.py`, `tests/fixtures/bootstrap_b4_golden.json`,
   and `tests/fixtures/estimator_c3_golden.json` are frozen. Import them; never
   edit them.
5. **Do not compute, declare, or write any v1.1 semantic hash.** That is C5's job.
   `frozen_semantic_sha256` stays `NOT_YET_ASSIGNED_PENDING_PACKET_C5`.
   `protocol_status` stays `DRAFT_UNFROZEN_SUCCESSOR`.
6. **Do not touch `deferred_change_set["C5"]`.** It stays `DEFERRED`.
7. **Never invent a scientific constant.** Every number in this packet is either
   quoted from §2 above, quoted from the audit, or derived by exact arithmetic from
   an already-frozen rule. If you believe a required number is missing, stop and
   report `BLOCKED` naming it. Do not choose a plausible value.
8. **Do not add a dependency and do not use `numpy`.** Exact `Decimal` /
   `Fraction` / `int` only.
9. **Do not reintroduce any rejected reviewer invention.** Specifically none of:
   a signed-return replacement; a sigma denominator floor or epsilon; an arbitrary
   98% coverage pass threshold; Gemini's weaker `1.5% / 0.03 / 0.75–1.25` one-year
   gate; GPT's `0.04` one-year bias threshold; GPT's categorical OI "period end"
   claim; the superseded A2 OI "bar open" claim; a new feature family; a new
   stablecoin series; a pivot tolerance such as `1e-40`; a coefficient-magnitude
   separation cutoff.
10. **No git side effects.** No push, no PR, no merge, no rebase, no reset, no
    stash, no clean, no tag, no branch creation, no `git config`. Exactly one local
    commit at the end.
11. **Do not write anywhere under `D:\PROJECT\Quantara`.** All work happens in the
    worktree at `D:\PROJECT\Quantara-worktrees\protocol-v11-c4-timestamp-buffer`.
12. **Do not begin C5.**

## 4. Preconditions

Run these first, in the worktree. If any fails, stop and report `BLOCKED`.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c4-timestamp-buffer

# Right worktree, right branch.
git rev-parse --abbrev-ref HEAD          # must print protocol-v11-c4-timestamp-buffer
git status --short                       # must print nothing

# The packet parent is an ancestor of HEAD.
git merge-base --is-ancestor b02cbc5 HEAD && echo PARENT_OK

# The regression baseline is green before you change anything.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_protocol.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol_guardrails.py \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_bootstrap_b4.py \
  tests/test_estimator_c3.py
```

The last command must report `153 passed`. `PYTHONPATH="$PWD/src"` is mandatory in
every Python invocation in this worktree.

Commits in a worktree need the repo hooks path:

```bash
git -c core.hooksPath=.githooks commit -m "<message>"
```

## 5. The contract C4 must freeze

Every clause below is normative. Section numbers here map to the spec/YAML edits in
§7 and §8 and to the tests in §9.

### 5.1 OI timestamp role — `UNRESOLVED_CONSERVATIVE`

The frozen arithmetic is unchanged:

```text
for a five-minute OI row with provider timestamp O:
    eligibility_ts = O + 5 minutes
```

What changes is the **claim**, not the number. The protocol must record:

```text
oi_timestamp_role:            UNRESOLVED_CONSERVATIVE
oi_provider_field:            create_time
oi_eligibility_ts:            O + 5 minutes
oi_semantic_claim_permitted:  false
```

Required properties:

1. The provider timestamp is preserved natively. It is **not** relabelled
   `interval_open_ts` and **not** relabelled `interval_close_ts`.
2. The phrase "interval-start timestamp" must not appear in any v1.1 OI clause.
   Frozen v1 keeps its wording; v1.1 supersedes it in the successor document only.
3. The rule is justified as safe under **both** readings, per G7, and this
   justification is recorded rather than asserted.
4. At an hourly boundary `T`, the latest eligible OI row is the row with
   `O = T - 5 minutes`. This is a consequence of the frozen join
   `eligibility_ts < prediction_ts = T + 2 ms`, not a separate rule.
5. A resolution obligation is recorded: an archive-specific semantics check must be
   performed **before** OI canonicalization, with the measured or cited evidence
   written into the source contract. Until then the role stays
   `UNRESOLVED_CONSERVATIVE`.
6. The uncertainty is a disclosed limitation that must appear in every result
   report that uses an OI feature.
7. The same treatment does **not** extend to Kraken. Per audit §6, A9 establishes
   that Kraken documents candle timestamps as interval starts, so
   `kraken_timestamp_role: DOCUMENTED_INTERVAL_START` with `K + 1 hour` stays as
   frozen. C4 records that asymmetry explicitly so a future reader does not
   "harmonize" the two.

### 5.2 Final pre-2025 refit — `final_refit`

Before the single 2025 evaluation, and only after the 2022–2024 gate has passed:

```text
retained_candidate       = the model retained under the frozen C3 retention graph
paired_comparator        = B2
refit_train_start        = 2020-09-01 00:00:00.000 UTC
refit_origin_rule        = O + 24h <= 2025-01-01 00:00:00.000 UTC
refit_last_origin        = 2024-12-31 00:00:00.000 UTC
refit_last_label_close   = 2024-12-31 23:59:59.999 UTC
nominal_origin_count     = 37969
excluded_tail_count      = 23
excluded_tail_range      = 2024-12-31 01:00 .. 2024-12-31 23:00 UTC
```

Required properties:

1. **Identical sample.** The retained candidate and paired B2 are refit on the
   *same* origin set: the retained candidate's point-in-time complete-case origins.
   B2 is not given a larger sample merely because it needs fewer features.
2. **Standardization is refit.** The z-score means and population standard
   deviations are recomputed on exactly those refit rows. They are not carried over
   from any fold.
3. **Everything else is unchanged.** Target `k`, the feature set, `ridge_lambda`,
   `ETA_CLAMP`, `MU_CLAMP`, `max_iterations`, the estimator entry point, and the
   probability treatment all stay exactly as frozen. `k` in particular remains the
   value frozen from the pre-2022 design set and is **never** recomputed here.
4. **`37969` is nominal, not eligible.** It is the count of hourly origins in the
   window that satisfy the purge inequality. The eligible complete-case count is
   smaller and unknown until execution. The protocol must state that distinction so
   a smaller realized count is not read as a defect.
5. **Failure state.** A refit failure emits `FINAL_FIT_FAILURE`. That state:
   - is terminal for the run,
   - does **not** permit tuning, a feature change, a lambda change, a different
     estimator, or a retry with different rows,
   - does **not** permit running the 2025 evaluation, and
   - is **not** reportable as `DID_NOT_REPLICATE`, because no 2025 score exists.
6. The fail-closed causes are exactly the seven already frozen by C3 in
   `fail_closed_causes`. C4 adds no new cause and no new tolerance.
7. `FINAL_FIT_FAILURE` never drops a fold, a year, or a candidate from pooling —
   consistent with the frozen `fit_failure_propagation` rule.

### 5.3 Sealed 2026 target-only endpoint buffer — `target_endpoint_buffer_2026`

```text
purpose                  supply 24h label endpoints for the 23 calendar-2025
                         origins whose labels end in 2026
scope                    BTCUSDT perpetual traded-price klines ONLY
role                     target_only
origin_count_supported   8760   (all calendar-2025 hourly origins)
buffer_dependent_origins 23
first_dependent_origin   2025-12-31 01:00:00.000 UTC
last_dependent_origin    2025-12-31 23:00:00.000 UTC
required_1h_bar_count    23
first_1h_bar_open        2026-01-01 00:00:00.000 UTC
last_1h_bar_open         2026-01-01 22:00:00.000 UTC
first_1h_bar_close       2026-01-01 00:59:59.999 UTC
last_1h_bar_close        2026-01-01 22:59:59.999 UTC
required_1m_row_count    1380
first_1m_open            2026-01-01 00:00:00.000 UTC
last_1m_open             2026-01-01 22:59:00.000 UTC
buffer_end_inclusive_ms  1767308399999
```

Required properties:

1. **Same controls as 2025.** The buffer is covered by the identical seal, hash,
   and no-inspection rules: `state: SEALED`, the same five permitted pre-gate
   checks (`file_inventory`, `cryptographic_hashes`, `parser_compatibility`,
   `expected_boundaries`, `mechanical_corruption`) and the same five forbidden
   operations (`labels`, `feature_distributions`, `model_scores`,
   `conditional_outcome_inspection`, `protocol_adaptation`).
2. **Target-only is provable, not promised.** Record G3: because
   `prediction_ts = T + 2 ms` and the join is strict, every eligible feature row
   for a 2025 origin has `eligibility_ts <= T + 1 ms`, so no 2026 row of any series
   can be a feature for any 2025 origin. State this as a derived consequence.
3. **Forbidden 2026 content is enumerated.** No 2026 feature origin is scored. No
   2026 funding, open interest, mark price, index price, native premium, Binance
   spot, Kraken, or any ETH series is acquired, parsed, or joined. The buffer's
   permitted series set has exactly one member.
4. **Hard end boundary.** Any 1h bar with open at or after
   `2026-01-01 23:00:00.000 UTC` is **out of scope and must be refused**, not
   silently ignored. A parser or derivation that emits the `23:00` bar is a
   contract violation.
5. **Explicit truncation rule.** Per G5, no available archive granularity stops at
   the boundary. The frozen rule is: parse the source archive, then **discard every
   1m row with open time outside `[2026-01-01 00:00:00.000, 2026-01-01 22:59:00.000]`
   UTC inclusive** before aggregation. Truncation is post-parse and pre-aggregation.
   Discarded rows are counted and reported; they are never used for any purpose.
6. **1h derivation is explicitly frozen and testable.** Per G4, the 1h bars are
   *derived* from 1m via `multi_timeframe_aggregation`, requiring 60 contiguous
   complete minutes per bar with `close_time_ms = open + 3600000 - 1` and
   `nominal_available_ms = open + 3600000`. An incomplete final group is a hard
   failure (`IncompleteGroup`); it is never padded, interpolated, or emitted short.
   The canonical 1h target-close semantics are unchanged from the frozen lane.
7. **The buffer cannot widen.** Its permitted extent is exactly the 23 bars above.
   Acquiring more 2026 data "for convenience" is a contract violation even if the
   extra rows are never read.
8. **Missing buffer data is fail-closed, not fail-open.** If a required buffer bar
   is unavailable, the affected origin's label is invalid and the origin is
   excluded as an incomplete case. It is never approximated from a shorter horizon,
   a nearest bar, or a 1d bar.

### 5.4 One-year 2025 replication gate — `replication_gate_2025`

Scope: the complete retained candidate versus paired B2, on all point-in-time
complete-case eligible calendar-2025 origins.

```text
REPLICATED iff all five hold:
  1. pooled BSS_B2(candidate) >= 0.02
  2. two-sided 95% bootstrap CI lower bound for (BS_B2 - BS_candidate) > 0
  3. abs(mean(p - y)) <= 0.02
  4. calibration slope in [0.8, 1.2]
  5. the calibration regression is defined and converges

otherwise: DID_NOT_REPLICATE
```

Required properties:

1. **Exactly five conjunctive criteria.** Per G9, multi-year criterion 3 ("at least
   two validation years improve") is arithmetically impossible with one year and is
   dropped; criteria 4 and 7 are implied by criteria 1 and 5 respectively and are
   likewise not restated. Record why each was dropped, so the reduction is auditable
   rather than looking like a weakening.
2. **Rejected alternatives are named.** Gemini's `1.5% / 0.03 / 0.75–1.25` gate,
   GPT's `0.04` one-year bias threshold, and Claude's literal reuse of all seven
   multi-year conditions are each explicitly rejected in the record.
3. **Inference is the frozen C2 bootstrap, unchanged.** Per G8, `bootstrap_b4`
   already accepts a single year. `B = 20000`, `block_hours = 168`, non-circular
   moving blocks, null-centred p-value, nearest-rank percentile CI, and the
   fail-closed `< 168` paired-valid rule all apply as frozen. C4 writes no new
   inference code.
4. **The 2025 geometry is recorded exactly:**
   ```text
   H_2025                       8760
   block_hours                  168
   n_blocks = ceil(H / L)       53
   concatenated_hours           8904
   eligible_block_starts        0 .. 8592
   distinct_eligible_starts     8593
   ci_rank_lower at B = 20000   500
   ci_rank_upper at B = 20000   19500
   ```
5. **`comparison_id` naming is frozen** so the PRNG stream is reproducible:
   ```text
   pattern     REPLICATION_2025|<MODEL>_vs_B2
   M2          REPLICATION_2025|M2_vs_B2     seed 13432793617478683004
   M2K         REPLICATION_2025|M2K_vs_B2    seed 17576365771105646995
   M3          REPLICATION_2025|M3_vs_B2     seed 15946086953525544617
   M4          REPLICATION_2025|M4_vs_B2     seed 3803725181447297110
   ```
   These seeds are `derive_stream_seed(comparison_id, 2025)` under the frozen C2
   derivation and were verified in this venv. Codex must assert them, not retype
   them from memory.
6. **Calibration reuses the frozen C3 machinery.** `lambda = 0`, the mandatory
   `clamp_mu` to `[0.000000000001, 0.999999999999]`, the back-transform
   `slope = beta_z / sd_x` and `intercept = beta_0 - beta_z * mu_x / sd_x`, the
   `[0.8, 1.2]` band applied to the raw-logit slope and never to `beta_z`, and the
   six frozen calibration failure conditions. Criterion 5 is satisfied by the
   absence of those six conditions; it is not a new test.
7. **Exactly one evaluation.** `run_count_permitted: 1`. A `DID_NOT_REPLICATE`
   outcome is the final result. No redesign, no re-score, no second look.
8. **Claim scope is bounded.** `REPLICATED` means the complete retained frozen model
   replicated aggregate probability-forecast improvement versus paired B2 in
   calendar 2025. It does **not** establish that any individual ETH or Kraken
   feature replicated. Per-block claims require that block's own frozen parent
   comparison to independently satisfy the same five-criterion gate; the frozen
   component chain is scored once in 2025 as claim-specific diagnostics.
9. **Coverage reporting is required but its threshold is not.** Report
   candidate-eligible rows and percentage, exclusion reasons, and the longest
   missing run. Per the standing rejections there is **no** minimum-coverage pass
   threshold — not 98%, not any other number. The result applies to
   candidate-complete timestamps and must say so.
10. `FINAL_FIT_FAILURE` from §5.2 is distinct from `DID_NOT_REPLICATE` and the two
    must never be conflated in the outcome enumeration.

## 6. File allowlist

**Create exactly these three files:**

1. `src/quantara/replication_c4.py` — the executable binding for this packet:
   origin enumeration, buffer geometry and the truncation predicate, refit-sample
   enumeration, and the five-criterion one-year gate. It **wraps** frozen
   machinery: it imports from `bootstrap_b4` and `estimator_c3` and reimplements
   nothing.
2. `tests/test_replication_c4.py`
3. `tests/fixtures/replication_c4_golden.json`

**Modify exactly these three files:**

4. `configs/protocols/quantara-protocol-v1_1.yaml`
5. `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`
6. `tests/test_protocol_v11_draft_contract.py`

**Delete:** none.

Anything else requires stopping `BLOCKED` with an explanation. In particular do not
touch `pyproject.toml`, `.github/workflows/ci.yml`, or any `configs/datasets/`
descriptor — the buffer descriptor is an acquisition artifact and is **not** part of
this packet. Also do not edit this plan document or
`docs/superpowers/plans/2026-09-01-protocol-v11-successor-master-plan.md`; both were
already committed by Hermes in the preceding plan commit on this branch, so they are
outside the packet diff.

## 7. Required module contract

`src/quantara/replication_c4.py` must expose exactly these names, using exact
integer / `Decimal` / `Fraction` arithmetic only.

```text
# frozen epoch-millisecond constants (assert; never recompute from a float)
HOUR_MS                      = 3600000
MINUTE_MS                    = 60000
LABEL_HORIZON_MS             = 86400000
SEAL_BOUNDARY_MS             = 1735689600000   # 2025-01-01 00:00:00.000 UTC
FIRST_2025_ORIGIN_MS         = 1735689600000
LAST_2025_ORIGIN_MS          = 1767222000000   # 2025-12-31 23:00
ORIGIN_COUNT_2025            = 8760
BUFFER_FIRST_BAR_OPEN_MS     = 1767225600000   # 2026-01-01 00:00
BUFFER_LAST_BAR_OPEN_MS      = 1767304800000   # 2026-01-01 22:00
BUFFER_END_INCLUSIVE_MS      = 1767308399999   # 2026-01-01 22:59:59.999
BUFFER_REFUSED_BAR_OPEN_MS   = 1767308400000   # 2026-01-01 23:00
BUFFER_BAR_COUNT             = 23
BUFFER_FIRST_MINUTE_OPEN_MS  = 1767225600000
BUFFER_LAST_MINUTE_OPEN_MS   = 1767308340000   # 2026-01-01 22:59
BUFFER_MINUTE_COUNT          = 1380
REFIT_TRAIN_START_MS         = 1598918400000   # 2020-09-01 00:00
REFIT_LAST_ORIGIN_MS         = 1735603200000   # 2024-12-31 00:00
REFIT_NOMINAL_ORIGIN_COUNT   = 37969
REFIT_EXCLUDED_TAIL_COUNT    = 23
OI_ELIGIBILITY_OFFSET_MS     = 300000          # 5 minutes
OI_TIMESTAMP_ROLE            = "UNRESOLVED_CONSERVATIVE"
KRAKEN_TIMESTAMP_ROLE        = "DOCUMENTED_INTERVAL_START"
FINAL_FIT_FAILURE            = "FINAL_FIT_FAILURE"
REPLICATION_CRITERIA         = ordered tuple of the five criterion ids
REPLICATION_COMPARISON_IDS   = {"M2","M2K","M3","M4"} -> comparison_id str

# functions
enumerate_2025_origins()                  -> tuple[int, ...]   length 8760
label_close_ms(origin_ms)                 -> int               origin + 24h - 1ms
requires_2026_buffer(origin_ms)           -> bool
buffer_dependent_origins()                -> tuple[int, ...]   length 23
buffer_bar_opens()                        -> tuple[int, ...]   length 23
buffer_minute_opens()                     -> tuple[int, ...]   length 1380
is_buffer_minute_in_scope(open_ms)        -> bool
truncate_buffer_minutes(open_ms_seq)      -> tuple[kept_tuple, discarded_count]
enumerate_refit_origins()                 -> tuple[int, ...]   length 37969
is_refit_eligible_origin(origin_ms)       -> bool
latest_eligible_oi_open_ms(boundary_ms)   -> int               boundary - 300000
replication_comparison_id(model)          -> str
replication_stream_seed(model)            -> int               delegates to C2
evaluate_replication_gate(evidence)       -> ReplicationDecision
```

Required behaviour:

1. `enumerate_2025_origins` is built by integer millisecond arithmetic from
   `FIRST_2025_ORIGIN_MS`, not by a calendar library, and its length must equal
   `bootstrap_b4.nominal_hours(2025)`.
2. `requires_2026_buffer(origin_ms)` is
   `label_close_ms(origin_ms) >= BUFFER_FIRST_BAR_OPEN_MS`.
3. `is_buffer_minute_in_scope` is inclusive on both ends of
   `[BUFFER_FIRST_MINUTE_OPEN_MS, BUFFER_LAST_MINUTE_OPEN_MS]`. A minute at
   `2026-01-01 23:00` is out of scope.
4. `truncate_buffer_minutes` never mutates its input and returns the discarded count
   so it can be reported.
5. `replication_stream_seed` calls the frozen
   `bootstrap_b4.derive_stream_seed(comparison_id, 2025)`. It must not hardcode seed
   values; the fixture holds them and the test asserts equality.
6. `evaluate_replication_gate` takes an evidence dataclass with `bss_b2`,
   `ci_lower`, `probability_bias`, `calibration_slope` (all `Decimal`) plus
   `calibration_defined_and_converged` (`bool`), and returns a frozen dataclass
   carrying the five named criterion booleans and
   `outcome in {"REPLICATED", "DID_NOT_REPLICATE"}`. It must raise on `float` input
   for any Decimal field, consistent with the C3 `binary_float_input` discipline.
7. Criterion 4 must not restate `0.8` / `1.2` as a second independent literal pair.
   The frozen C3 helper is
   `estimator_c3.calibration_slope_passes(fit, *, lower=Decimal("0.8"), upper=Decimal("1.2"))`,
   which takes a `CalibrationFit` rather than a bare slope. Bind the band by reading
   the helper's own default arguments — for example via
   `inspect.signature(calibration_slope_passes).parameters["lower"].default` — or by
   constructing a `CalibrationFit` and delegating to the helper directly. Whichever
   you choose, `tests/test_replication_c4.py` must assert that the band used by
   `evaluate_replication_gate` is *identical to* the helper's defaults, so the two
   can never drift. State in the report which binding you used and why.
8. `FINAL_FIT_FAILURE` is a distinct module-level constant and is never a possible
   return value of `evaluate_replication_gate`.

## 8. Required YAML changes

In `configs/protocols/quantara-protocol-v1_1.yaml`. Every decimal is a quoted exact
string; no YAML float may appear anywhere, so the existing recursive no-float
assertion must keep passing.

1. Add a top-level `oi_timestamp_resolution` mapping carrying the §5.1 role, the
   provider field, the eligibility formula, `semantic_claim_permitted: false`, the
   both-readings safety justification, the pre-canonicalization resolution
   obligation, the disclosed-limitation requirement, and the explicit Kraken
   asymmetry with `kraken_timestamp_role: DOCUMENTED_INTERVAL_START`.
2. In `point_in_time`, replace the `oi_eligibility` text so it no longer says
   "interval-start timestamp". The new text says provider timestamp `O` with
   `eligibility_ts = O + 5 minutes` and cross-references the unresolved role. Do not
   change `kraken_eligibility`, `funding_eligibility`, `kline_eligibility`,
   `join_rule`, or any other existing `point_in_time` key.
3. Add a top-level `final_refit` mapping with every §5.2 literal: train start, the
   origin-rule string, last origin, last label close,
   `nominal_origin_count: 37969`, `excluded_tail_count: 23`, the excluded tail
   range, the identical-sample rule, the standardization-refit rule, the
   unchanged-parameters list, the nominal-versus-eligible clarification, and a
   `failure` submapping whose `state: FINAL_FIT_FAILURE` carries the four
   prohibitions of §5.2 item 5.
4. Add a top-level `target_endpoint_buffer_2026` mapping with every §5.3 literal,
   including `role: target_only`, `permitted_series: [btcusdt_perp_ohlcv]`, the
   23-bar and 1380-minute geometry, `buffer_end_inclusive_ms: 1767308399999`, the
   `refused_bar_open_ms: 1767308400000` hard boundary, the truncation rule, the
   derivation contract of §5.3 item 6, the cannot-widen rule, the fail-closed
   missing-data rule, and the derived target-only proof of §5.3 item 2.
5. Add a top-level `replication_gate_2025` mapping with the five criteria as an
   ordered list of `{id, rule, threshold}` entries, `outcome_on_failure:
   DID_NOT_REPLICATE`, `run_count_permitted: 1`, the dropped-criterion record
   (which multi-year ids were dropped and why), the named rejected alternatives, the
   2025 bootstrap geometry block of §5.4 item 4, the `comparison_id` pattern with
   the four model ids, the claim-scope statement, and the coverage-reporting
   requirement with `minimum_coverage_threshold: NONE_BY_DESIGN`.
6. In `sealed_2025`, change `successor_buffer_and_replication_rule` from
   `DEFERRED_PACKET_C4` to `IMPLEMENTED_PACKET_C4` and add
   `buffer_contract: target_endpoint_buffer_2026` and
   `replication_contract: replication_gate_2025`. Do not alter `state`,
   `scoring_permission`, `allowed_pre_gate_checks`, `forbidden_operations`,
   `on_gate_pass`, `failure_outcome`, or `failure_rule`.
7. Set `deferred_change_set["C4"]["status"] = "IMPLEMENTED_PACKET_C4"`. `C5` stays
   `DEFERRED`; `C2` stays `IMPLEMENTED_PACKET_C2`; `C3` stays
   `IMPLEMENTED_PACKET_C3`.
8. Add `outcome_states` listing exactly the distinct terminal states this protocol
   can report, including both `FINAL_FIT_FAILURE` and `DID_NOT_REPLICATE` as
   separate entries.
9. The file has 41 top-level keys at `b02cbc5`. This packet adds exactly five —
   `oi_timestamp_resolution`, `final_refit`, `target_endpoint_buffer_2026`,
   `replication_gate_2025`, `outcome_states` — for a final count of 46. Do not add,
   remove, or reorder any other top-level key. Do not touch
   `frozen_semantic_sha256`, `protocol_status`, `target`, `model_ladder`,
   `success_gate`, `optional_family_retention`, `estimator_binding`, `calibration`,
   or the bootstrap block. `deferred_change_set` entries carry exactly two keys each
   (`owner_packet`, `status`); keep that shape.

## 9. Required spec changes

In `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`.

1. In §5, replace only the five-minute OI bullet. On disk at `b02cbc5` it is lines
   287–288 and reads exactly:
   ```text
   - For five-minute OI with source timestamp `O`,
     `eligibility_ts = O + 5 minutes`.
   ```
   The replacement keeps that arithmetic and adds the unresolved-role statement,
   with a short subsection recording the A10 supersession of A2, the rejection of
   the categorical "period end" claim, the both-readings safety argument, and the
   pre-canonicalization resolution obligation. Do not alter the adjacent Kraken
   bullet at line 289 (`For Kraken hourly OHLCVT with interval-start K`) — its
   `interval-start` wording is correct and must survive. Do not alter the `T+2ms`
   ordering block, the funding clauses, or the `P[t]` paragraph. Note that line 298
   also contains the phrase "five-minute OI" in a summary sentence; check whether it
   makes a semantic claim and repair it only if it does.
2. In §7, add a `Final pre-2025 refit` subsection with the §5.2 literals and the
   `FINAL_FIT_FAILURE` state, placed after the existing purge-contract boundary
   examples. Do not alter the fold definitions, the purge inequality, the existing
   verified boundary examples, the Brier definitions, or the calibration paragraph.
3. Replace the last paragraph of §8 — lines 650–651 on disk at `b02cbc5`, which read
   "2025. The additional endpoint buffer and replication-gate details are `DEFERRED` to
   packet C4 and are not implemented here." — with two new subsections:
   `2026 target-only endpoint buffer` (§5.3) and `One-year 2025 replication gate`
   (§5.4). Preserve the sentence fragment that precedes "The additional endpoint
   buffer"; only the deferral sentence is removed. The five criteria appear as a
   fenced `text` block in the same order as the module's `REPLICATION_CRITERIA`. Keep
   the existing §8 opening paragraph about permitted pre-gate checks unchanged.
4. In §11, the C4 row is line 697, headed
   `| Timestamp, refit, buffer, and replication contract | `DEFERRED` | C4 | …`.
   Change only its `Status` cell to `IMPLEMENTED`, leaving the scope text and owning
   packet unchanged. The C5 row (`Coverage and final freeze`) stays `DEFERRED`. The
   standing-rejections paragraph immediately after the table stays unchanged.
5. Do not touch §12, and do not introduce any 64-hex literal other than the
   predecessor hash
   `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`, which already
   appears and must stay in its existing position.

## 10. Required tests

Add `tests/test_replication_c4.py`. Every one of G1–G9 must be reproduced as an
assertion, not quoted. Minimum coverage:

**Buffer geometry (G1, G2)**

- `enumerate_2025_origins()` has length 8760, first `1735689600000`, last
  `1767222000000`, and strictly ascending 3600000-ms spacing.
- Its length equals `bootstrap_b4.nominal_hours(2025)`.
- `label_close_ms(1767222000000) == 1767308399999`.
- `buffer_dependent_origins()` has length 23, first `1767142800000`
  (`2025-12-31 01:00`), last `1767222000000`.
- `buffer_bar_opens()` has length 23, first `1767225600000`, last `1767304800000`,
  and `1767308400000` (`2026-01-01 23:00`) is **not** a member.
- Every non-buffer 2025 origin has `label_close_ms < 1767225600000`.

**Target-only proof (G3)**

- For the last 2025 origin, `prediction_ts = origin + 2` and the greatest possible
  eligible `eligibility_ts` is `origin + 1`, which is strictly less than
  `BUFFER_FIRST_BAR_OPEN_MS`. Assert the inequality, so target-only is tested rather
  than asserted in prose.

**1m granularity and truncation (G4, G5)**

- `buffer_minute_opens()` has length 1380, first `1767225600000`, last
  `1767308340000`.
- Grouping those minutes by `open - (open % 3600000)` yields exactly 23 buckets of
  exactly 60 members each.
- Feed the 23 buckets through the frozen aggregation entry point, whose real
  signature is
  `aggregate_timeframe(minutes: Sequence[CanonicalRow], identity: tuple[str, ...], timeframe_ms: int) -> list[CanonicalRow]`,
  with `timeframe_ms=3600000` and synthetic `CanonicalRow` values (fields:
  `identity`, `open_time_ms`, `close_time_ms`, `nominal_available_ms`, `open`,
  `high`, `low`, `close`, `base_asset_volume`, `quote_asset_volume`, `trade_count`,
  `taker_buy_base_volume`, `taker_buy_quote_volume`, `source_ignore`). Assert 23
  bars are produced, each with `close_time_ms == open + 3599999` and
  `nominal_available_ms == open + 3600000`.
- Dropping one minute from the final bucket must raise
  `quantara.aggregation.IncompleteGroup`.
- `truncate_buffer_minutes` over a synthetic full calendar day
  `2026-01-01 00:00..23:59` keeps 1380 and discards 60.
- `truncate_buffer_minutes` over a synthetic full month `2026-01-01..2026-01-31`
  keeps 1380 and discards 43260.
- `is_buffer_minute_in_scope(1767308400000)` is `False`.

**Refit sample (G6)**

- `enumerate_refit_origins()` has length 37969, first `1598918400000`, last
  `1735603200000`.
- Every member satisfies `origin + 86400000 <= 1735689600000`.
- `is_refit_eligible_origin(1735603200000)` is `True`;
  `is_refit_eligible_origin(1735606800000)` (`2024-12-31 01:00`) is `False`.
- The naive count `37992` minus the eligible count equals
  `REFIT_EXCLUDED_TAIL_COUNT == 23`.
- The already-rejected `2024-12-30 23:00` cutoff is wrong: assert the last eligible
  origin is **not** `1735599600000`.

**OI eligibility (G7)**

- `latest_eligible_oi_open_ms(T)` equals `T - 300000` for at least three distinct
  hourly boundaries.
- A row with `O = T` satisfies `O + 300000 >= T + 2`, so it is **not** eligible.
- A row with `O = T - 300000` satisfies `O + 300000 < T + 2`, so it **is** eligible.
- `OI_TIMESTAMP_ROLE == "UNRESOLVED_CONSERVATIVE"` and
  `KRAKEN_TIMESTAMP_ROLE == "DOCUMENTED_INTERVAL_START"`.
- The v1.1 spec §5 OI clause and the v1.1 YAML `point_in_time.oi_eligibility` do
  **not** contain the substring `interval-start` (case-insensitive), while
  `kraken_eligibility` still does. Read the files inside the test; this is the
  regression guard against a future "harmonization".

**Frozen inference reuse (G8)**

- `replication_comparison_id("M2") == "REPLICATION_2025|M2_vs_B2"`, and likewise for
  `M2K`, `M3`, `M4`.
- `replication_stream_seed(m)` equals `derive_stream_seed(comparison_id, 2025)` for
  all four models and equals the fixture values.
- A single-year `bootstrap_b4({2025: grid}, comparison_id=..., resamples=<small>)`
  call succeeds on a synthetic grid of length 8760 and returns exact `Fraction`
  values. Keep `resamples <= 200` so the suite stays fast; the frozen `B = 20000` is
  asserted from YAML, not executed here.
- 168 paired-valid observations succeed; 167 raise `BootstrapB4InferenceError` with
  `reason == "insufficient_observed_paired_valid"` and `year == 2025`.
- `ceil(8760 / 168) == 53`, concatenated hours `8904`, largest eligible block start
  `8592`, and the `B = 20000` nearest-rank CI ranks are `500` and `19500`.

**One-year gate (G9)**

- All five criteria satisfied → `REPLICATED`.
- Each criterion individually violated, as five separate cases →
  `DID_NOT_REPLICATE`, with that named criterion `False` and the other four `True`.
- Inclusive boundaries pass their own criterion: `bss_b2 == Decimal("0.02")`,
  `abs(bias) == Decimal("0.02")`, `slope == Decimal("0.8")`,
  `slope == Decimal("1.2")`.
- `ci_lower == 0` **fails** criterion 2, because the inequality is strict.
- A `float` in any Decimal field raises rather than silently coercing.
- Multi-year criterion 3 is absent: the criterion-name set has exactly five members
  and contains no year-count criterion.
- The rejected thresholds appear nowhere in the new module: assert the strings
  `0.015`, `0.03`, `0.75`, `1.25`, `0.04`, and `0.98` are absent from
  `replication_c4.py`. (`0.04` is the GPT one-year bias threshold; `0.98` is the
  rejected coverage cutoff.)
- `FINAL_FIT_FAILURE` is never returned by `evaluate_replication_gate` and is a
  distinct member of the YAML `outcome_states`.

Extend `tests/test_protocol_v11_draft_contract.py` with:

- `deferred_change_set["C4"]["status"] == "IMPLEMENTED_PACKET_C4"` and C5 still
  `DEFERRED` — update the existing loop so it no longer asserts C4 is deferred.
- `sealed_2025.successor_buffer_and_replication_rule == "IMPLEMENTED_PACKET_C4"`.
- The four new top-level keys exist and carry the exact literals of §8 items 1, 3,
  4, and 5.
- `protocol_status` is still `DRAFT_UNFROZEN_SUCCESSOR` and
  `frozen_semantic_sha256` is still `NOT_YET_ASSIGNED_PENDING_PACKET_C5`.
- The spec §11 C4 row reads `IMPLEMENTED` and the C5 row still reads `DEFERRED`.

`tests/fixtures/replication_c4_golden.json` holds the four `comparison_id` strings
with their 2025 seeds, the buffer geometry integers, the refit counts, the 2025
bootstrap geometry, and one worked `REPLICATED` plus one worked
`DID_NOT_REPLICATE` decision with all five criterion booleans. Decimals and
fractions are stored as strings, never as JSON numbers with a fractional part.

## 11. Verification gates

Run all of these and paste the real output.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c4-timestamp-buffer

# Focused gate.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_replication_c4.py \
  tests/test_protocol_v11_draft_contract.py

# Regression gate: the frozen predecessors must not move.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_protocol.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol_guardrails.py \
  tests/test_bootstrap_b4.py \
  tests/test_estimator_c3.py \
  tests/test_training_metrics_logistic.py \
  tests/test_evaluation_metrics.py \
  tests/test_aggregation.py

# Full suite.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q

# Repository-wide lint. This MUST match the CI gate exactly. A scoped lint over
# only the new files is NOT sufficient: it passes while an *edited* file
# regresses, which is exactly how C4 shipped 4 over-length lines in
# tests/test_protocol_v11_draft_contract.py past a clean scoped run.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check src tests benchmarks

# Whitespace hygiene.
git diff --check
```

Capture the **red** output of the focused gate before implementing and the green
output after. A report without genuine verbatim red output is `INCOMPLETE`.

## 12. Byte-identity gates

All six of these must print **nothing**. Any output is a failed packet.

```bash
git diff --stat b02cbc5 -- docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md
git diff --stat b02cbc5 -- configs/protocols/quantara-protocol-v1.yaml
git diff --stat b02cbc5 -- tests/fixtures/protocol_v1_expected.json
git diff --stat b02cbc5 -- src/quantara/bootstrap_b4.py src/quantara/estimator_c3.py
git diff --stat b02cbc5 -- src/quantara/training_metrics_logistic.py src/quantara/evaluation_metrics.py src/quantara/aggregation.py
git diff --stat b02cbc5 -- pyproject.toml .github/workflows/ci.yml configs/datasets
```

Also confirm `tests/test_estimator_c3.py` still contains
`PACKET_PARENT_ESTIMATOR_BLOB` and was not edited.

## 13. Commit

Stage only the six allowlisted files. Commit locally with exactly:

```text
feat(protocol): freeze v1.1 timestamp, refit, buffer, and replication contract
```

Then **stop**. Do not push, do not open a PR, do not begin C5.

## 14. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA.
2. The single commit SHA.
3. Exact list of changed files.
4. Raw red output captured before implementation.
5. Raw green focused-gate output, raw green regression-gate output, and the full
   suite's pass count.
6. Raw output of all six byte-identity `git diff --stat` commands and of
   `git diff --check`.
7. Ruff result.
8. Confirmation that no 2025 or 2026 data was read, opened, enumerated, globbed, or
   listed, and that every fit and fixture is synthetic.
9. Confirmation that no data was acquired and no network call was made.
10. Confirmation that no v1.1 semantic hash was computed or declared, and that
    `protocol_status` and `frozen_semantic_sha256` are unchanged.
11. Confirmation that `deferred_change_set["C5"]` is still `DEFERRED`.
12. Confirmation that no dependency was added and `numpy` was not used.
13. Confirmation that no rejected reviewer invention was introduced, naming each of
    the eleven items in prohibition 9 and how its absence was verified.
14. An explicit mapping of which of G1–G9 each new test reproduces.
15. The exact wording chosen for the replacement OI clause in both spec and YAML,
    quoted, so the auditor can check that no semantic claim survived.
16. Test count and any residual risk.

A green unit test alone is not `COMPLETE`. Hermes performs the independent audit and
is the only role that may mark this packet `ACCEPTED`.
