# Protocol v1.1 — Packet C3: Estimator Binding and Optional Family (audit B5, B6, item 7)

**Status:** `NEXT` — not started
**Date:** 2026-09-01
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c3-estimator`
**Branch:** `protocol-v11-c3-estimator`
**Packet parent commit:** `7abce82` (`main`, the C2 merge commit)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists

C1 froze version identity and time semantics. C2 froze inference (`B4`). Both left
the estimator and the optional-family decision rule deferred: the v1.1 draft still
carries `optional_family_retention.successor_repair_status: DEFERRED` with
`successor_repair_owner_packet: C3`, `holm_test_count: 2`, and no protocol-level
binding to the committed exact-Decimal IRLS implementation.

This packet repairs three audit findings:

- **B5 — deterministic estimator details are underbound.** The repository already
  contains a tested exact-Decimal IRLS contract in
  `src/quantara/training_metrics_logistic.py`. The protocol must *bind* to it and
  add the missing both-class and calibration-failure rules. It must not invent a
  second solver.
- **B6 — the optional-family graph is not fixed.** `M2K` is unnamed, the family is
  described as two tests when the retention graph needs three, and Holm thresholds
  are not tied to sorted observed p-values.
- **Change-set item 7 — optional-block 2022–2024 results must be labelled
  selection evidence, not independent replication.**

This is a **specification repair, not a scientific reset.** No new feature, no new
target, no new model family, no unsealing.

## 2. Hermes pre-verified findings

These were measured in this exact venv against the committed estimator before the
plan was written. They are the reason several rules below exist. Codex must
reproduce each one as a test, not trust this document.

**F1 — `fit_logistic_irls` does not enforce both training classes.** With 60 rows
and all-ones labels it converges in 25 iterations to
`intercept = 25.000000000037751345442790977516449695475234067772`,
`coefficient ≈ -2.75E-58`, with `eta_clamp_count = 120`. All-zero labels behave
symmetrically. The audit requires fail-closed here, so C3 adds the guard.

**F2 — the constant-feature guard is exact-zero only.** A column holding one
repeated 50-significant-digit value yields `std = 2.5E-49`, which is not
`is_zero()`, so `_standardization` passes and the failure surfaces later as
`zero pivot in logistic ridge solver`. A short exactly-representable constant
column (`Decimal("0.5")`) does raise
`zero train-window standard deviation for feature[0]`. Both paths must therefore
be named protocol outcomes. The audit explicitly rejected adding a pivot
threshold such as `1e-40`, so C3 must **not** introduce a tolerance — it binds
both existing exact guards as fail-closed.

**F3 — the calibration back-transform is exact.** Fitting the committed solver on
standardized `x = logit(p)` with `ridge_lambda = 0`, then applying

```text
calibration_slope     = beta_z / sd_x
calibration_intercept = beta_0 - beta_z * mu_x / sd_x
```

reproduces an independent direct raw-scale two-parameter IRLS fit to within
`2.1E-49` (slope) and `2.774E-50` (intercept), and the two agree exactly after
`ROUND_HALF_EVEN` quantization at `1e-18`. No second solver is needed.

**F4 — the logit endpoints are hostile.** Under `DECIMAL_CONTEXT`, `logit(0)`
returns `-Infinity` and `logit(1)` raises `DivisionByZero`. Clamping to
`[0.000000000001, 0.999999999999]` before the logarithm is mandatory, and
`clamp_mu` already implements exactly that: `clamp_mu(0) -> (1E-12, True)` and
`clamp_mu(1) -> (0.999999999999, True)`.

**F5 — non-convergence is not a separation detector.** With `ridge_lambda = 0` on
perfectly separated data the solver still converges: 24 iterations,
`coefficient ≈ 386.36`, `eta_clamp_count = 908`, `mu_clamp_count = 0`. Widening the
class margin does not cause failure either (gap 1 → 25 iterations, gap 100 → 28).
The only frozen signal that fires is the eta clamp, which is already fixed at 24.
The audit rejected a coefficient-magnitude threshold of 50, so C3 binds the
existing clamp instead of inventing a magnitude cutoff. See §5.4.

**F6 — every ladder width fits.** Widths 1, 3, 6, 7, 11, 12, 13, 16 all converge in
4–5 iterations on synthetic well-posed data. `M2K` is width 11.

**F7 — Holm literals at `B = 20000`.** With `alpha = 1/20` and `m = 3` the exact
step thresholds are `1/60`, `1/40`, `1/20`. The minimum attainable bootstrap
p-value is `1/20001`, which clears the strictest step. The largest exceedance
count that still clears `1/60` is `332`: `p(332) = 333/20001 = 111/6667 <= 1/60`
while `p(333) = 334/20001 > 1/60`.

## 3. Absolute prohibitions

Violating any of these is an automatic `BLOCKED`. Stop and report instead.

1. **Do not modify, move, reformat, or re-hash any Protocol v1 artifact.** These
   stay byte-identical to the packet parent `7abce82`:
   - `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`
   - `configs/protocols/quantara-protocol-v1.yaml`
   - `tests/fixtures/protocol_v1_expected.json`
   - `tests/test_protocol_document_contract.py`
   - `tests/test_protocol.py`
   - `tests/test_protocol_guardrails.py`
   - `src/quantara/protocol.py`
2. **Do not compute, invent, declare, or freeze a Protocol v1.1 semantic
   SHA-256.** That is packet C5. Any literal 64-hex string presented as the v1.1
   frozen hash is a defect. The draft-contract test enforcing
   `NOT_YET_ASSIGNED_PENDING_PACKET_C5` must keep passing.
3. **Do not make Protocol v1.1 loadable by `quantara.protocol.load_protocol`.**
   The loader stays pinned to the frozen v1 hash.
4. **Do not modify `src/quantara/training_metrics_logistic.py`.** This is the
   single most important prohibition in this packet. That module is the frozen
   slice-012 estimator; other frozen suites depend on its exact byte behaviour.
   C3 **binds** it and adds guards in a **new** module. If a guard cannot be added
   without editing it, stop `BLOCKED` and report — do not edit it.
5. **Do not touch** `src/quantara/bootstrap_b4.py`, `src/quantara/training_metrics.py`,
   `src/quantara/training_pipeline.py`, `src/quantara/evaluation_metrics.py`,
   `src/quantara/ic_stability_diagnostic.py`,
   `src/quantara/phase_auc_diagnostic.py`, `src/quantara/features.py`,
   `src/quantara/aggregation.py`, any canonical data, any manifest, any current
   pointer, or anything under `data/`.
6. **Do not implement C4/C5 content.** Specifically forbidden here:
   - no OI timestamp resolution;
   - no final pre-2025 refit sample or failure state;
   - no 2026 endpoint buffer, no `REPLICATED` gate;
   - no coverage/exclusion reporting, no claim-scope table;
   - no semantic hash, no fixture synchronization, no freeze.
7. **Do not change any success-gate criterion.** The seven criteria of
   `success_gate` and their thresholds are frozen. C3 changes only the
   optional-family retention machinery and the estimator binding. Do not
   renumber, re-threshold, add, or remove a gate criterion.
8. **Do not change the frozen estimator constants.** `lambda = 1`, unpenalized
   intercept, train-window z-score, `max_iterations = 50`, tolerance
   `0.000000000001`, eta clamp `24`, probability clamp `0.000000000001`, Gaussian
   elimination with partial pivoting. The calibration fit uses `lambda = 0`; that
   is a different fit, not a change to the model constant.
9. **Do not introduce any rejected reviewer invention.** Explicitly forbidden:
   80-digit precision, IEEE-754 floats, condition-number threshold `1e14`, pivot
   threshold `1e-40`, coefficient-magnitude separation threshold 50, silently
   fixing constant columns to zero, dropping a failed fold from the pooled result.
10. **Do not run anything on real Quantara data.** Synthetic fixtures only. No
    scoring is authorized while `protocol_status` is `DRAFT_UNFROZEN_SUCCESSOR`.
11. **Do not read, enumerate, or open any 2025 or 2026 data.** Sealed.
12. **Do not add a third-party dependency.** `numpy` is not installed and must not
    be added. Standard library plus `pytest` and `pyyaml==6.0.2` only.
13. **Do not push, merge, rebase, reset, stash, clean, or create a PR.** Commit
    locally and stop.
14. **If any scientific detail below is ambiguous, stop `BLOCKED`.** Never invent a
    scientific constant.

## 4. Environment

The shared editable install points at `D:\PROJECT\Quantara`, so this worktree must
override the import path explicitly:

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c3-estimator
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q <targets>
```

Verify at the start that `git status --short` is empty and that the packet parent is
an ancestor of `HEAD`. `HEAD` is **not** equal to `7abce82` — this plan document was
itself committed on the branch — so use ancestry, not equality:

```bash
git rev-parse --abbrev-ref HEAD                     # expect protocol-v11-c3-estimator
git merge-base --is-ancestor 7abce82 HEAD && echo parent-ok
git merge-base --is-ancestor c0bdaae HEAD && echo c2-ok
git status --short                                  # expect empty
```

All byte-identity gates in §11 compare against `7abce82`, the packet parent, not
against `HEAD`.

## 5. The frozen contract

### 5.1 Estimator binding (B5)

Protocol v1.1 binds to the **committed** exact-Decimal logistic-IRLS
implementation. The protocol records the contract; it does not restate an
independent algorithm.

```text
implementation:            src/quantara/training_metrics_logistic.py
entry point:               fit_logistic_irls
Decimal precision:         50
rounding:                  ROUND_HALF_EVEN
storage quantum:           0.000000000000000001
standardization:           train-window z-score, population denominator n
initial coefficients:      all zero
model L2 lambda:           1
intercept:                 unpenalized
convergence:               every abs(beta_new - beta_old) < 0.000000000001
maximum updates:           50
linear solver:             Gaussian elimination with partial pivoting
pivot failure:             exact-zero pivot, fail closed
constant train feature:    exact-zero train std, fail closed
non-convergence:           fail closed
binary float inputs:       forbidden
eta clamp:                 24
probability clamp:         0.000000000001
```

Every decimal constant is recorded in YAML as a **quoted exact string**.

### 5.2 Both-class rule (B5)

Training outcomes for any fit must contain **both** classes. A single-class
training window fails the affected candidate comparison closed.

Per **F1** the committed solver does not enforce this: it converges to a
degenerate intercept-only model. C3 therefore adds the guard in the new C3 module
(§6) and **must not** edit the frozen estimator. The guard is checked *before*
calling `fit_logistic_irls`.

### 5.3 Fit-failure propagation rule (B5)

Any fit failure fails the affected **candidate comparison**. It never silently
omits a fold, a year, or a candidate from pooling. This is the protocol-level
counterpart of the C2 bootstrap fail-closed rules and must be recorded as such.

Named fail-closed causes, exactly these seven:

```text
single_class_training_outcome
constant_train_feature
zero_pivot
non_convergence
binary_float_input
calibration_single_class_outcome
calibration_degenerate_logit
```

### 5.4 Separation and the eta clamp (B5)

Per **F5**, neither non-convergence nor the probability clamp detects perfect
separation: with `lambda = 0` on separated data the solver converges in 24
iterations with a coefficient near `386` and `eta_clamp_count = 908`. The only
frozen signal that fires is the eta clamp at 24.

The frozen rule, using existing machinery only:

```text
The eta clamp at 24 is a recorded diagnostic, not a failure. Any fit whose
eta_clamp_count is greater than zero must report that count alongside its result.
For the calibration fit specifically, a positive eta_clamp_count fails the
calibration gate as calibration_degenerate_logit, because a clamped calibration
linear predictor means the reported slope is not the fitted slope on the observed
logit range.
```

No coefficient-magnitude threshold is introduced. The audit rejected the value 50
and C3 does not substitute another number.

### 5.5 Calibration contract (B5)

Calibration is an **unpenalized two-parameter Decimal logistic fit of `y` on
`x = logit(p)`** with an intercept, computed through the same committed solver
called with `ridge_lambda = 0`, then back-transformed to the raw-logit scale:

```text
x_i                   = ln( p_i / (1 - p_i) ), with p_i first passed through
                        clamp_mu, i.e. clamped to [0.000000000001, 0.999999999999]
calibration_slope     = beta_z / sd_x
calibration_intercept = beta_0 - beta_z * mu_x / sd_x
```

Per **F3** this reproduces a direct raw-scale fit to within `2.1E-49` on the slope
and `2.774E-50` on the intercept, and agrees exactly at the `1e-18` reporting
quantum. **The success-gate calibration-slope band `[0.8, 1.2]` applies to this
raw-logit slope, never to `beta_z`.**

The clamp is mandatory per **F4**: unclamped, `logit(0)` is `-Infinity` and
`logit(1)` raises `DivisionByZero`.

The calibration gate fails closed on any of:

```text
single-class outcome in the calibration sample
zero-variance logit(p)            -> surfaces as exact-zero std or zero pivot (F2)
undefined logit                   -> only reachable if the clamp is bypassed
singular solve                    -> zero pivot
separation                        -> positive eta_clamp_count in the calibration fit
non-convergence within 50 updates
```

Calibration is a diagnostic of predictions. It never alters a prediction, never
refits a candidate, and never enters the pooled Brier estimand.

### 5.6 `M2K` naming and ladder widths (B6)

Add exactly one named model. Nothing else in the ladder is renamed or changed.

```text
M2K = M2 + frozen four-column Kraken block
M4  = M3 + frozen four-column Kraken block   (already present, unchanged)
```

The Kraken block is the existing frozen four columns:
`kraken_ret_1h`, `kraken_rv_24h`, `binance_kraken_ret_divergence_1h`,
`binance_kraken_cross_quote_log_ratio`. No new feature, no transformation search.

Verified widths (**F6**), which a test must assert:

```text
B1  1     M2   7     M3   12    M4  16
B2  3     M2K 11     M3b  13
M1  6
```

### 5.7 The three fixed optional hypotheses (B6)

Freeze and compute **all three** before any retention decision is made:

```text
H_ETH:   M3  vs M2
H_K_M2:  M2K vs M2
H_K_M3:  M4  vs M3
```

Each is evaluated with the C2 frozen bootstrap. Each has a distinct
`comparison_id`, which is the C2 stream-derivation input. Freeze the three
identifiers exactly:

```text
H_ETH   -> "H_ETH|M3_vs_M2"
H_K_M2  -> "H_K_M2|M2K_vs_M2"
H_K_M3  -> "H_K_M3|M4_vs_M3"
```

All three p-values are computed even when the retention path cannot use one of
them. The unused branch is still multiplicity-controlled but receives no retention
authority on that path.

### 5.8 Ordinary Holm across all three (B6)

`holm_test_count` becomes **3**, superseding the current `2`. This is a disclosed
successor-version correction: the draft's two-test family does not cover the
three-hypothesis retention graph.

Thresholds are assigned **after sorting observed p-values ascending**, never
permanently assigned to model names:

```text
sort the three one-sided bootstrap p-values ascending: p_(1) <= p_(2) <= p_(3)
step i threshold: alpha / (m - i + 1) with alpha = 1/20, m = 3
    i=1 -> 1/60
    i=2 -> 1/40
    i=3 -> 1/20
reject in order while p_(i) <= threshold_i; stop at the first failure and
accept all remaining null hypotheses (ordinary step-down Holm)
```

Thresholds are exact rationals compared with `fractions.Fraction`. Never compare
against a decimal approximation of `0.0166...`.

Per **F7**, at `B = 20000` the strictest step is attainable: the minimum p-value is
`1/20001`, and the largest exceedance count still clearing `1/60` is `332`
(`p(332) = 111/6667 <= 1/60`, `p(333) = 334/20001 > 1/60`). These four literals go
in the spec and are asserted by tests.

Ties are resolved by the frozen hypothesis order `[H_ETH, H_K_M2, H_K_M3]` — with
equal p-values the earlier hypothesis takes the earlier step. Holm's outcome is
invariant to this choice, but the ordering is frozen so the reported step
assignment is reproducible.

### 5.9 Retention graph (B6)

Retention requires **all** of: the Holm-adjusted decision, the effect floor, the CI
condition, and both year conditions. The per-hypothesis gate is unchanged from the
draft except that Holm is now across three tests:

```text
per-hypothesis retention gate (all five required):
  1. pooled relative Brier improvement versus the currently retained model >= 0.01
  2. unadjusted two-sided 95% paired-bootstrap CI lower bound > 0
  3. one-sided bootstrap p-value passes ordinary Holm at alpha = 1/20 across the
     three-test family
  4. at least two validation years improve
  5. no validation year is worse than -0.02
```

The frozen decision graph:

```text
if H_ETH passes its gate:
    retain M3
    retain M4 instead only if H_K_M3 also passes its gate
else:
    retain M2
    retain M2K instead only if H_K_M2 also passes its gate
```

`M3b` / ETH OI is a secondary diagnostic on the identical post-2021-12-01 common
sample and can never alter the retained candidate. A rejected block receives no
alternative transformation search. The retained candidate must still pass the
complete seven-criterion `success_gate` versus paired B2 before 2025 unlocks.

The existing `optional_family_retention.fallback` sentence — "If ETH is rejected,
compare Kraken against M2, not against an ETH-containing model" — is now
*implemented* by the graph via `H_K_M2`, and must be kept consistent with it rather
than deleted.

### 5.10 Selection-evidence labelling (change-set item 7)

Every optional-block result computed on 2022–2024 is **selection evidence**, not
independent replication. Record this as a first-class protocol field, not prose
only:

```text
optional_block_2022_2024_result_class: selection_evidence
independent_replication_source:        sealed 2025 only
```

The reason must be stated: the optional family is evaluated on the same 2022–2024
validation data used to choose among candidates, so its improvement estimates are
conditioned on that selection. Only the single frozen 2025 evaluation provides
independent replication evidence.

Reported claim wording for any retained optional block must therefore say
"selected on 2022–2024 development evidence", never "replicated".

The mandatory primary candidate `M2` is unaffected: it is preregistered, not
selected, and its 2022–2024 gate result keeps its existing status.

## 6. File allowlist

**Create exactly these three files:**

1. `src/quantara/estimator_c3.py` — the both-class guard, the fail-closed cause
   enumeration, the calibration fit and back-transform, the Holm procedure, and the
   retention graph. This module **wraps** the frozen estimator; it does not
   reimplement IRLS.
2. `tests/test_estimator_c3.py`
3. `tests/fixtures/estimator_c3_golden.json`

**Modify exactly these three files:**

4. `configs/protocols/quantara-protocol-v1_1.yaml`
5. `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`
6. `tests/test_protocol_v11_draft_contract.py`

**Delete:** none. Anything else requires stopping `BLOCKED` with an explanation.

## 7. Required YAML changes

In `configs/protocols/quantara-protocol-v1_1.yaml`:

1. Add a top-level `estimator_binding` mapping recording §5.1 verbatim, every
   decimal as a quoted exact string, plus the implementation path and entry point.
2. Add `fail_closed_causes` listing exactly the seven names of §5.3, and a
   `fit_failure_propagation` rule stating that a failure fails the candidate
   comparison and never drops a fold, year, or candidate from pooling.
3. Add a `calibration` mapping: the `lambda: '0'` unpenalized two-parameter fit on
   `logit(p)`, the mandatory clamp bounds, both back-transform formulas as exact
   strings, the statement that the `[0.8, 1.2]` gate band applies to the raw-logit
   slope, and the six calibration failure conditions.
4. Add `M2K` to `model_ladder` with `base: M2`, the four Kraken columns, and a
   definition line. Add a `ladder_widths` mapping with the eight verified widths of
   §5.6. Do not alter any existing ladder entry.
5. Replace `optional_family_retention` with the §5.7–§5.9 contract: the three
   frozen hypotheses with their `comparison_id` strings, `holm_test_count: 3`,
   `holm_family_wise_alpha: '0.05'`, the three exact step thresholds as quoted
   strings `'1/60'`, `'1/40'`, `'1/20'`, the sorted-assignment rule, the frozen tie
   order, the five per-hypothesis criteria, the decision graph, and the
   `compute_all_three_before_deciding: true` marker.
6. Record the F7 attainability literals: `min_attainable_p: '1/20001'`,
   `max_exceedance_count_clearing_first_step: 332`, `p_at_332: '111/6667'`,
   `p_at_333: '334/20001'`.
7. Add `optional_block_2022_2024_result_class: selection_evidence` and
   `independent_replication_source` per §5.10.
8. Set `optional_family_retention.successor_repair_status: IMPLEMENTED_PACKET_C3`
   and add `supersedes_draft_holm_test_count: true` with a `disclosed_design_change`
   note for the 2 → 3 family-size correction.
9. Set `deferred_change_set["C3"]["status"] = "IMPLEMENTED_PACKET_C3"`. C4 and C5
   stay `DEFERRED`. C2 stays `IMPLEMENTED_PACKET_C2`.
10. Still loadable by `yaml.safe_load`, no duplicate mapping keys, and the existing
    recursive no-float assertion must keep passing.

## 8. Required spec changes

In `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`:

1. In §4, add the `M2K` line to the ladder block and the ladder-width table. Do not
   alter any existing ladder line, formula, or the feature-window paragraph.
2. In §4, expand the estimator paragraph into the §5.1 binding, naming
   `src/quantara/training_metrics_logistic.py` and `fit_logistic_irls` as the bound
   implementation, and adding the both-class rule, the seven fail-closed causes, and
   the fit-failure propagation rule.
3. Replace the existing §7 calibration paragraph ("Calibration intercept and slope
   are obtained diagnostically…") with the §5.5 contract, including both
   back-transform formulas, the mandatory clamp, the explicit statement that the
   `[0.8, 1.2]` band applies to the raw-logit slope, and the six failure conditions.
   Keep the sentence that these calculations do not alter predictions.
4. Replace the §7 optional-family paragraph with §5.7–§5.9: the three frozen
   hypotheses, ordinary Holm across all three with the exact thresholds `1/60`,
   `1/40`, `1/20`, sorted assignment, the frozen tie order, the F7 attainability
   literals, and the decision graph.
5. Update the §7 sentence that currently reads "across these two optional-family
   tests" to the three-test family, and state plainly that this is a disclosed
   successor-version correction of the draft's two-test family.
6. Add the §5.10 selection-evidence labelling, with the reason and the required
   claim wording.
7. Update the §11 deferred-table `C3` row to `IMPLEMENTED` naming this packet.
   Leave the C4 and C5 rows untouched.
8. Do not alter the header block, the `NOT_YET_ASSIGNED_PENDING_PACKET_C5` hash
   state, the scoring-permission text, the §5 point-in-time contract, the §7
   fold/purge contract, the seven success-gate criteria, the C2 bootstrap section,
   or any C1 section.
9. Remove the C3 forward-reference in the §7 bootstrap text that currently reads
   "the family definition remains `DEFERRED` to C3" — the family is now defined.
   Keep the `B = 20000` justification and all three Monte Carlo literals unchanged.

## 9. Required tests

`tests/test_estimator_c3.py`, standard library plus `pytest` and `PyYAML` only.
Independent literal expectations — do not import the module's own constants to
assert the module's own behaviour where a literal is the point.

### 9.1 Estimator binding

- The bound constants in YAML match the committed module's actual attributes:
  `RIDGE_LAMBDA == Decimal("1")`, `MAX_ITERATIONS == 50`,
  `TOLERANCE == Decimal("0.000000000001")`, `ETA_CLAMP == Decimal("24")`,
  `MU_CLAMP == Decimal("0.000000000001")`, precision 50, `ROUND_HALF_EVEN`, storage
  quantum `1e-18`. A drift in either direction must fail.
- `src/quantara/training_metrics_logistic.py` is byte-identical to the packet
  parent. Assert this in the test suite, not only in the gate.
- Every ladder width of §5.6 fits successfully on synthetic well-posed data
  (reproduces **F6**), and the YAML `ladder_widths` values match the column lists in
  `model_ladder` — computed from the YAML, not hardcoded twice.

### 9.2 Both-class rule (reproduces F1)

- All-ones labels raise the C3 `single_class_training_outcome` failure.
- All-zero labels raise the same failure.
- **The regression proof:** calling the frozen `fit_logistic_irls` directly with
  all-ones labels still converges and returns an intercept of
  `25.000000000037751345442790977516449695475234067772` with
  `eta_clamp_count == 120`. This asserts the frozen module was not edited and that
  the guard genuinely lives in the C3 layer.
- A mixed-label window with one minority example passes the guard.

### 9.3 Constant-feature and pivot paths (reproduces F2)

- A short exactly-representable constant column raises the exact-zero-std failure,
  mapped to `constant_train_feature`.
- A column of one repeated 50-digit value produces `std == Decimal("2.5E-49")`,
  passes `_standardization`, and fails later as `zero_pivot`. Both map to
  fail-closed causes; neither returns a partial result.
- No tolerance constant appears anywhere in the C3 module. Assert by scanning the
  module source for `1e-40`, `1E-40`, and a condition-number threshold, and assert
  absent.

### 9.4 Calibration (reproduces F3, F4)

- The back-transform reproduces an independently implemented direct raw-scale
  two-parameter IRLS fit: absolute slope difference `<= 1E-45` and equality after
  `ROUND_HALF_EVEN` quantization at `1e-18`. Embed the independent fit in the test
  file; do not call the C3 module for both sides.
- `clamp_mu(Decimal(0)) == (Decimal("1E-12"), True)` and
  `clamp_mu(Decimal(1)) == (Decimal("0.999999999999"), True)`.
- Unclamped `logit(1)` raises `DivisionByZero` and unclamped `logit(0)` returns
  `-Infinity` under `DECIMAL_CONTEXT`; the C3 path never reaches either because it
  clamps first.
- A single-class calibration sample fails `calibration_single_class_outcome`.
- A zero-variance `logit(p)` sample fails closed.
- A separated calibration sample produces a positive `eta_clamp_count` and fails
  `calibration_degenerate_logit` (reproduces **F5**: it does *not* fail by
  non-convergence).
- The gate band is applied to the raw-logit slope: a case whose `beta_z` is inside
  `[0.8, 1.2]` while the back-transformed slope is outside must **fail** the
  calibration gate, and the reverse case must pass. This is the test that catches
  the most likely implementation error in this packet.

### 9.5 Holm (reproduces F7)

- The three step thresholds are exactly `Fraction(1, 60)`, `Fraction(1, 40)`,
  `Fraction(1, 20)`.
- Thresholds are assigned by sorted rank, not by model name: swapping which
  hypothesis carries the smallest p-value swaps the step assignment.
- Step-down stopping: when `p_(1)` passes and `p_(2)` fails, `p_(3)` is **not**
  rejected even if `p_(3) <= 1/20`.
- Attainability: `Fraction(1, 20001) <= Fraction(1, 60)`;
  `Fraction(333, 20001) == Fraction(111, 6667)` and `<= Fraction(1, 60)`;
  `Fraction(334, 20001) > Fraction(1, 60)`; and the boundary count is exactly `332`
  found by search, not hardcoded.
- All three p-values are computed even when the retention path uses only two —
  assert the result object carries three.
- No float appears in the Holm path: comparisons are `Fraction`. Assert that
  passing a float p-value raises.
- The three frozen `comparison_id` strings are exactly as specified and produce
  three distinct C2 stream seeds via `derive_stream_seed`.

### 9.6 Retention graph

- ETH passes, Kraken-on-M3 passes → retained `M4`.
- ETH passes, Kraken-on-M3 fails → retained `M3`.
- ETH fails, Kraken-on-M2 passes → retained `M2K`.
- ETH fails, Kraken-on-M2 fails → retained `M2`.
- Each of the five per-hypothesis criteria, failed alone with the other four
  passing, blocks retention. Five separate cases; a single combined case is
  insufficient.
- `M3b` never appears as a retained candidate under any input, including inputs
  where its improvement is the largest of all.
- A rejected block triggers no re-evaluation with a different transformation:
  assert the retention function is pure and called once per hypothesis.
- The retained candidate is still subject to the seven-criterion `success_gate`:
  assert the retention result does not itself unlock 2025.

### 9.7 Selection-evidence labelling

- The YAML carries `optional_block_2022_2024_result_class: selection_evidence` and
  `independent_replication_source` naming sealed 2025 only.
- The retention result object labels every optional-block outcome as selection
  evidence.
- The spec contains the required claim wording and does not contain the word
  "replicated" applied to a 2022–2024 optional-block result. A targeted text
  assertion is acceptable here.
- The `M2` primary result is not relabelled as selection evidence.

### 9.8 Protocol-artifact synchronization

Extend `tests/test_protocol_v11_draft_contract.py` minimally:

- `deferred_change_set["C3"]["status"] == "IMPLEMENTED_PACKET_C3"`, C2 stays
  `IMPLEMENTED_PACKET_C2`, C4 and C5 stay `DEFERRED`. The current test asserts C3 is
  `DEFERRED` and **will fail** once the YAML changes — that failure is expected and
  must be repaired by this narrow edit, not by weakening the assertion to a
  wildcard.
- `optional_family_retention.holm_test_count == 3` and
  `successor_repair_status == "IMPLEMENTED_PACKET_C3"`.
- `estimator_binding`, `calibration`, and `fail_closed_causes` exist with the
  required keys.
- `model_ladder["M2K"]` exists with `base: M2` and the four Kraken columns.
- The recursive no-float assertion still passes over the modified YAML.
- Every C1 and C2 assertion still passes unchanged, including
  `test_v11_bootstrap_b4_contract_is_frozen_by_packet_c2` and the
  `NOT_YET_ASSIGNED_PENDING_PACKET_C5` hash-state test.
- The seven `success_gate` criteria are unchanged: assert ids `1..7`, their rule
  strings, and their thresholds against literals.

### 9.9 Golden fixture

`tests/fixtures/estimator_c3_golden.json` pins a synthetic end-to-end optional-family
decision with:

- the three `comparison_id` strings and their derived C2 seeds,
- three p-values as exact rational strings,
- the sorted Holm step assignment and per-step thresholds,
- each hypothesis's five criterion outcomes,
- the retained model name,
- one calibration fit: `beta_z`, `mu_x`, `sd_x`, `beta_0`, and both
  back-transformed values as exact 18-dp strings,
- the result class `selection_evidence`.

Use a reduced `B` (e.g. `B = 200`) with a documented deterministic generator
embedded in the test. The fixture must be regenerable by the test file alone and
must fail loudly if the contract changes. Synthetic data only; no repository data,
no 2025.

## 10. Execution order

1. Confirm clean worktree, correct branch, and `7abce82` an ancestor of `HEAD`
   (§4).
2. **Tests first.** Write `tests/test_estimator_c3.py` before
   `src/quantara/estimator_c3.py` exists and capture the **real red output**. Paste
   it verbatim in the report. A report without genuine red output is `INCOMPLETE`.
3. Implement `src/quantara/estimator_c3.py`.
4. Generate `tests/fixtures/estimator_c3_golden.json` from the frozen contract.
5. Apply the YAML change (§7), then the spec change (§8), then the narrow
   draft-contract test change (§9.8).
6. Iterate until the focused gate is green.

## 11. Gates — all required

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c3-estimator

# Focused gate: the new C3 suite plus every protocol suite, proving v1 intact,
# C2 intact, and the v1.1 draft still fail-closed.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_estimator_c3.py \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_bootstrap_b4.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py

# Regression gate: the frozen estimator and its dependent suites must be untouched
# and still green.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_training_metrics_logistic.py \
  tests/test_training_quality_logistic.py \
  tests/test_training_pipeline_logistic.py \
  tests/test_integration_training_logistic.py \
  tests/test_training_descriptor_logistic.py \
  tests/test_evaluation_metrics.py

# Byte-identity proof for every v1 artifact, the frozen estimator, and C2.
git diff --stat 7abce82 -- \
  docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md \
  configs/protocols/quantara-protocol-v1.yaml \
  tests/fixtures/protocol_v1_expected.json \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py \
  src/quantara/protocol.py \
  src/quantara/training_metrics_logistic.py \
  src/quantara/training_metrics.py \
  src/quantara/training_pipeline.py \
  src/quantara/evaluation_metrics.py \
  src/quantara/bootstrap_b4.py \
  tests/test_bootstrap_b4.py \
  tests/fixtures/bootstrap_b4_golden.json \
  src/quantara/ic_stability_diagnostic.py \
  src/quantara/phase_auc_diagnostic.py

# Whitespace hygiene.
git diff --check

# Scoped lint.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check \
  src/quantara/estimator_c3.py tests/test_estimator_c3.py

# No stray dependency was added.
git diff --stat 7abce82 -- pyproject.toml
```

Both `git diff --stat` commands must print **nothing**. Any output is a failed
packet.

## 12. Commit

Stage only the six allowlisted files. Commit locally with exactly:

```text
feat(protocol): freeze v1.1 estimator binding and optional family
```

Then **stop**. Do not push, do not open a PR, do not begin C4.

## 13. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA.
2. The single commit SHA.
3. Exact list of changed files.
4. Raw red output captured before implementation.
5. Raw green focused-gate output and raw green regression-gate output.
6. Raw output of both byte-identity `git diff --stat` commands and of
   `git diff --check`.
7. Ruff result.
8. Confirmation that `src/quantara/training_metrics_logistic.py` was not modified.
9. Confirmation that no v1.1 semantic hash was computed or declared.
10. Confirmation that no 2025 or 2026 data was read or enumerated, and that all
    fits ran on synthetic data only.
11. Confirmation that no dependency was added and `numpy` was not used.
12. Confirmation that no rejected reviewer invention was introduced, naming each of
    the seven from prohibition 9 and how its absence was verified.
13. Which of F1–F7 each new test reproduces.
14. Test count and any residual risk.

A green unit test alone is not `COMPLETE`. Hermes performs the independent audit and
is the only role that may mark this packet `ACCEPTED`.
