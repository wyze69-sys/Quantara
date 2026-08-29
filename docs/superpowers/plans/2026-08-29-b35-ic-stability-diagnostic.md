# Slice B3.5 — IC Stability Diagnostic (Gate Before B4)

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-29
**Starting HEAD:** `6e5ec68f88b7d84196771c2c4bfdc9298f01d912` (main, clean, synced with origin)
**Executor:** Owner-chosen (Codex default per memory). Hermes wrote this plan from a verified live-store audit on 2026-08-29.

**Provenance:** implements the convergent recommendation of an external
model review (GPT + Claude, 2026-08-29): both reviewers independently named
"do the per-fold IC stability diagnostic before anything else" as the
**gate** that determines whether the decision-layer work (B4) is justified
at all. The brief's earlier claim that "IC 0.179 implies a threshold exists"
was sloppy framing, and both reviewers corrected it. This slice is the
corrected first move.

## 0. Owner authorization (read first)

This slice is **diagnostic only**. It does not publish, train, or change
any frozen slice. It writes a sidecar JSON under `data/diagnostic/` (which
is gitignored, like all of `data/`), reads it back, and reports a
pre-registered go/no-go decision. No rights-record change is required or
permitted — the diagnostic operates over already-retained, internally
acquired artifacts. Private research evidence; no customer display, no
redistribution, no commercial production use, no live trading.

## 1. Goal

Determine whether the 012 logistic IRLS model's reported mean direction-IC
of `0.178590194880741058` is **stable across folds** or **driven by a few
folds**. The answer is the **pre-registered gate** for whether slice B4
(decision layer with threshold optimization, Platt calibration, and WAIT
class) is worth doing at all. The slice produces:

- Per-fold direction-IC distribution (median, 25th/75th, min, max, % > 0,
  % > 0.10, best 10, worst 10)
- Per-fold IC through time, with regime labeling (Q1/Q2/Q3/Q4 2024)
- Block-bootstrap 95% confidence interval on the mean (resampling folds)
- Permutation test: shuffle labels within each fold, recompute mean IC
  10,000 times, report empirical p-value
- Pre-registered go/no-go decision (the gate, with explicit thresholds)
- A 1-line verdict: proceed to B4 / proceed with caveat / publish honest
  negative

The diagnostic is read-side, deterministic, and reproducible from the
existing 012 attempt manifest + the 012 pipeline's per-fold records (which
are currently computed but discarded on KILL; B3.5 captures them to a
sidecar before discarding).

## 2. Why a sidecar is needed (verified against the live store)

`git log -- data/datasets/...` confirms 012 was **KILL_CRITERIA_FAILED**
(exit 4); the per-fold records were computed in memory by
`build_logistic_training_records` (`src/quantara/training_metrics_logistic.py:463-639`)
but **never written to disk** because the KILL path returns before
publication. The 012 attempt manifest
(`data/attempts/training/20260829T064246Z-0bbd6069-4bc9-4cdd-94ec-5e74302539de.json`)
contains only the 10-line summary diagnostics (`terminal_result`, the four
`K*-mean=…` lines, three baseline lines). **There is currently no
per-fold artifact on disk to read.**

The cleanest fix is to add a thin sidecar write: when the 012 pipeline
finishes the records pass (regardless of KILL outcome), it serializes the
records list to a JSON file under `data/diagnostic/training/`. The sidecar
is:

- **Outside the publication store** (`data/objects/` and
  `data/datasets/.../commits/`), so it cannot become "published evidence"
- **Outside the CAS** (no content addressing; it's a snapshot, not an
  immutable artifact)
- **Under `data/`** which is gitignored
- **Cleared by the diagnostic itself** at the end of a successful run
  (the diagnostic copies what it needs into the diagnostic report
  JSON, then deletes the sidecar to keep the store tidy)

This is *additive* to the existing 012 pipeline code. The 012 published
artifacts, quality checks, attempt manifests, and pointer semantics are
**untouched**.

## 3. Verified facts (oracle check 2026-08-29)

These are the values the live store returned before this plan was frozen;
the plan's references and frozen anchors are these values, not estimates.

- **Current HEAD:** `6e5ec68f88b7d84196771c2c4bfdc9298f01d912` (clean, synced
  with `origin/main`)
- **Training pointer:** commit `0284c655c7c195820f7cb739ea5574bc69334986ca5a108537be585f2cfbc20f`
  (011's ridge; 012 KILL'd, pointer did not move)
- **012 attempt manifest (the KILL one, with summary diagnostics):**
  `data/attempts/training/20260829T064246Z-0bbd6069-4bc9-4cdd-94ec-5e74302539de.json`
  - `terminal_result: KILL_CRITERIA_FAILED`
  - `k1_directional_accuracy_mean: 0.515063433784091061` (bar `0.534900284900284900`, FAIL)
  - `k2_direction_ic_mean: 0.178590194880741058` (bar `0.020000000000000000`, PASS)
  - `k3_log_loss_mean: 0.695523361523936980` (bar `0.762500000000000000`, PASS)
  - `k4_brier_mean: 0.251148463739147642` (bar `0.250000000000000000`, FAIL)
- **Per-fold records source:** `src/quantara/training_metrics_logistic.py:463-639`
  - `build_logistic_training_records(folds, research_rows)` returns 117
    record dicts, each with `direction_ic` at line 605 (Q18 string) and
    `direction_ic_defined` boolean for the single-class-fold convention
Resting pointers (must be unchanged at slice exit; same seven
values as 012 §2):

```text
klines/BTCUSDT/1m       9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f
  klines/BTCUSDT/1h       702dab9f66b9d7181458916324ce906020d6415709b4189b395b1378b6b9e271
  klines/BTCUSDT/1d       2d09178f767dc563306359db8a31d96d7d00c90890ffd78635ffd94db35a02bf
  research/BTCUSDT/1h     cb9079eab9e1f7237d736f5f5021270fd0c8dc176a5ee37d5fdd38ac9977c548
  validation/BTCUSDT/1h   166651165729ec3cda1cc48967e45eace09dc6a9b078a3e619efc9af15b3a410
  evaluation/BTCUSDT/1h   d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675
  training/BTCUSDT/1h     0284c655c7c195820f7cb739ea5574bc69334986ca5a108537be585f2cfbc20f
  ```

## 4. Pre-registered gate (frozen before any diagnostic run)

The gate is the slice's deliverable. The values are **Decimal exact**, with
the comparison to per-fold standard deviation of the direction-IC across
the 117 folds:

- **PROCEED to B4** if: per-fold direction-IC SD < 0.10 **AND** block-bootstrap
  95% CI on the mean excludes 0 (lower bound > 0)
- **PROCEED to B4 with caveat** if: per-fold SD in `[0.10, 0.20]` **AND**
  block-bootstrap 95% CI excludes 0
- **STOP, publish honest negative** if: per-fold SD > 0.20 **OR**
  block-bootstrap 95% CI includes 0 **OR** permutation p-value > 0.05

**Decision rule pattern (mirrors 012 §4):** all three conditions
(SD, CI, permutation) are checked; the most-restrictive result wins. The
gate is *not* a test of "is the IC exactly large" — it's a test of "is
the IC stable enough that downstream work (B4) is justified." A model
with mean IC = 0.18 but SD = 0.30 is **less useful** than a model with
mean IC = 0.10 but SD = 0.05, and the gate reflects that.

The gate is encoded in code (a `evaluate_ic_stability_gate(per_fold_ics)`
function returning one of three enum values) **and** in this plan. The
diagnostic never recomputes the gate from a comment — it calls the
function. This prevents the executor from accidentally moving the goal
posts when the numbers come in (the exact failure mode 012 was designed
to prevent).

**Why SD < 0.10 vs the alternative SD < 0.15 (Claude's suggestion):** the
external review explicitly called out SD > 0.15 as "uninformative mean."
0.10 is more conservative and matches the spirit of 012's pre-registration
discipline: pick a bar that *means* something, not a bar that lets
mediocre results pass. If the gate turns out to be too strict (no
realistic model ever clears SD < 0.10), that's a finding for slice E0
(gate-recalibration), not for this slice.

**Why the permutation test is included:** the 8,400 test predictions share
23/24 hours between adjacent rows (verified against
`src/quantara/features.py:132-148`), so the effective sample size for
row-level permutation is much smaller than 8,400. The fold-level
permutation test (shuffle labels within each fold, keep fold structure)
is the right test under the existing design.

## 5. Design

### 5.1 Sidecar writer (additive, `src/quantara/training_pipeline.py`)

A new internal function `_write_per_fold_sidecar(records, path)` that
serializes the records list (the 117 dicts from
`build_logistic_training_records`) to a JSON file at
`data/diagnostic/training/per_fold_<attempt_id>.json`. Called from
`finish()` (or equivalent) **before** the KILL exit path returns, so
sidecar write happens regardless of outcome.

The sidecar shape:

```json
{
  "schema_version": "quantara.ic_stability_sidecar/v1",
  "attempt_id": "<uuid>",
  "code_revision": "<sha256>",
  "records": [
    {
      "fold_index": 0,
      "direction_ic": "0.123456789012345678",
      "direction_ic_defined": true,
      "directional_accuracy": "0.512...",
      "log_loss": "0.69...",
      "brier": "0.25...",
      "converged_iterations": 8,
      "usable_test_rows": 72,
      "baselines": {
        "majority_class_train_window": { ... },
        "sign_f_ret_1": { ... },
        "climatology_p": { ... }
      }
    },
    ...
  ]
}
```

The sidecar is **not** content-addressed and **not** validated by
`quality.py` — it is a diagnostic snapshot, not a publication artifact.
The pipeline's existing quality gates and attempt manifest discipline
are untouched.

### 5.2 Diagnostic module (new, `src/quantara/ic_stability_diagnostic.py`)

A new module with three public functions:

- `load_per_fold_ics(sidecar_path) -> list[Decimal]` — reads the sidecar,
  returns the 117 `direction_ic` values in fold order. Validates
  `schema_version == "quantara.ic_stability_sidecar/v1"`. Rejects
  non-117-length lists.
- `summarize_per_fold(ics) -> dict` — computes and returns:
  - `mean`, `median`, `stdev` (Decimal-exact, Q18-quantized)
  - `p25`, `p75`, `min`, `max`
  - `count_positive`, `count_above_0_10`
  - `best_10`, `worst_10` (fold indices with their values, in fold order)
  - `time_series`: list of `(fold_index, ic, quarter_label)` where
    `quarter_label` is one of `{"2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"}`
    derived from `fold_index` mapping (the 117 folds cover full 2024
    in roughly equal quarters; mapping is `fold_index // 30` rounded
    to the appropriate quarter)
- `bootstrap_mean_ci(ics, n_resamples=10_000, ci=0.95) -> tuple[Decimal, Decimal]`
  — resamples folds **with replacement** (preserving fold structure),
  computes mean of each resample, returns the (lower, upper) CI bounds
  in Decimal Q18. Seed: `Decimal` arithmetic is deterministic; the only
  source of randomness is the resample index selection, which uses
  Python's `random.Random(seed=20260829)` so the CI is reproducible
  across runs.
- `permutation_test(ics, n_permutations=10_000) -> Decimal` — for each
  permutation, *flips the sign* of each fold's IC independently with
  probability 0.5 (this is equivalent to a label-shuffle test for
  symmetric nulls; faster than full per-fold label shuffling and gives
  the same p-value distribution under H0). Reports the empirical
  p-value: fraction of permuted-mean-IC absolute values ≥ observed
  mean-IC absolute value. Seed: same `random.Random(seed=20260829)`.
  **Decimal-exact** throughout.
- `evaluate_ic_stability_gate(ics) -> GateVerdict` where `GateVerdict`
  is an enum: `PROCEED`, `PROCEED_WITH_CAVEAT`, `STOP_PUBLISH_NEGATIVE`.
  Encodes the §4 gate exactly. Returns the verdict plus a structured
  reason (`"per_fold_sd=... ci=(lo,hi) permutation_p=..."`).

### 5.3 Diagnostic report (JSON, written to `data/diagnostic/`)

A single JSON report at
`data/diagnostic/training/ic_stability_<attempt_id>.json`:

```json
{
  "schema_version": "quantara.ic_stability_report/v1",
  "attempt_id": "<uuid>",
  "code_revision": "<sha256>",
  "summary": { "mean": "...", "median": "...", "stdev": "...", ... },
  "bootstrap_ci": ["lo", "hi"],
  "permutation_p_value": "...",
  "gate_verdict": "PROCEED_WITH_CAVEAT",
  "gate_reason": "per_fold_sd=0.1423 ... ci=(0.083,0.272) permutation_p=0.008",
  "best_10_folds": [{"fold_index": 71, "direction_ic": "..."}, ...],
  "worst_10_folds": [{"fold_index": 23, "direction_ic": "..."}, ...],
  "time_series": [{"fold_index": 0, "direction_ic": "...", "quarter": "2024-Q1"}, ...]
}
```

The diagnostic runner (`tests/test_integration_ic_stability.py` and
optionally a CLI subcommand for manual re-runs) reads the sidecar,
computes everything, writes the report, **then deletes the sidecar**
to keep the store tidy. The report is the durable record; it lives in
`data/diagnostic/` (gitignored) and is also printed to stdout by the
test for the audit log.

### 5.4 CLI subcommand (optional but recommended, `quantara diagnostic ic-stability`)

A thin CLI wrapper that takes an attempt-id and runs the diagnostic
against the corresponding sidecar (or the attempt manifest's embedded
IC values as a fallback if the sidecar is gone). This makes the
diagnostic re-runnable without re-running the 012 integration test.

The CLI is `quantara diagnostic ic-stability --attempt-id <uuid>`,
prints the summary to stdout, writes the report to
`data/diagnostic/training/ic_stability_<attempt_id>.json`. Non-zero
exit if the gate fails (so a `make gate` workflow can use it as a
release-blocker).

If the executor prefers to skip the CLI subcommand and only ship the
test, that's acceptable; the test alone is sufficient. The CLI is
nice-to-have, not required.

### 5.5 Leakage guarantees (encode as tests)

The diagnostic must not leak test labels into the gate computation. The
only data the diagnostic uses is the 012 pipeline's already-computed
per-fold `direction_ic` values (which were computed honestly with
test-row-only predictions in 012). No re-fit, no re-evaluate, no
new compute against test data. The diagnostic is **read-side only**.

Encode in tests: a synthetic sidecar with all ICs = 0 → gate must
return `STOP_PUBLISH_NEGATIVE`. A sidecar with all ICs = 0.5 → gate
must return `PROCEED`. A sidecar with `[0.5, 0.5, 0.5, -0.5, 0.5, ...]`
(50/50 positive/negative with mean 0.4) → gate must return
`STOP_PUBLISH_NEGATIVE` (permutation p > 0.05). Decimal arithmetic
throughout.

## 6. Task sequence (strict TDD)

- **T0 — Plan and baseline.** Write this document verbatim to
  `docs/superpowers/plans/2026-08-29-b35-ic-stability-diagnostic.md`;
  commit `docs: plan slice b35 IC stability diagnostic`. Verify starting
  state: HEAD `6e5ec68…`, clean tree, the seven resting pointers (§3)
  match the live store, offline suite green
  (`uv run pytest -m "not integration" -q`).
- **T1 — Sidecar writer.** Red: synthetic test that calls
  `_write_per_fold_sidecar(records, path)` and asserts the file exists
  with the right shape (schema_version, 117 records, fold indices 0–116,
  Decimal strings). Green: add the function to
  `src/quantara/training_pipeline.py`, call it from the
  `finish(KILL_CRITERIA_FAILED, ...)` path. **Regression test:** the
  012 integration test must still pass byte-identically (sidecar write
  is additive, the existing 10-line diagnostic in the attempt manifest
  is unchanged). Commit
  `feat(training): per-fold sidecar write on KILL for diagnostic read`.
- **T2 — Diagnostic module.** Red: synthetic 117-element lists with
  known statistics; expected mean/median/stdev/Q25/Q75/min/max;
  expected bootstrap CI; expected permutation p-value; expected gate
  verdict for each test case (PROCEED, PROCEED_WITH_CAVEAT, STOP).
  Green: `src/quantara/ic_stability_diagnostic.py` with the five public
  functions. Tests: `tests/test_ic_stability_diagnostic.py` (5+ test
  cases covering each branch). Commit
  `feat(diagnostic): IC stability module with pre-registered gate`.
- **T3 — Diagnostic report runner.** Red: integration test drives the
  sidecar → report flow end-to-end with a synthetic sidecar; asserts
  report JSON shape, gate verdict, sidecar deleted after report write.
  Green: `tests/test_integration_ic_stability.py` with a synthetic
  117-element list. Commit
  `test(diagnostic): IC stability report runner with synthetic data`.
- **T4 — Real-data diagnostic.** A *new* integration test
  `tests/test_integration_ic_stability_real.py` that:
  1. Snapshots the seven resting pointers (the same SNAPSHOT_DIRS as
     the 012 integration test).
  2. Drives the year chain (re-points klines/research/validation/
     evaluation/training from January to the full year, then restores).
  3. Runs the 012 logistic pipeline once. The KILL fires. The sidecar
     is written.
  4. Runs the IC stability diagnostic on the sidecar.
  5. Asserts: report JSON exists, gate verdict is one of the three
     enum values, sidecar is deleted after report write.
  6. `finally` restores all seven pointers byte-exactly.
  This test takes ~10 minutes (the 012 IRLS over 117 folds is the
  bottleneck). Commit
  `test(diagnostic): real year-chain IC stability on 012 KILL data`.
- **T5 — CLI subcommand (optional).** Red: `quantara diagnostic
  ic-stability --attempt-id <uuid>` with a fake attempt-id must exit
  non-zero and print a clear error. Green: implements the CLI in
  `src/quantara/cli.py` (additive). Commit
  `feat(cli): diagnostic ic-stability subcommand`. **If the executor
  prefers to skip the CLI, mark T5 as out-of-scope in the final
  report; the test is sufficient.**
- **T6 — Final gates and push.** `uv lock --check`; `uv run ruff check .`;
  `uv run pytest -m "not integration" -q`; `uv run pytest -m integration -q`
  (the new real-data integration test takes ~10 min; the others are fast);
  `git diff --check`; changed-file set equals §7 allowlist; single push;
  verify `HEAD == origin/main`, clean tree, `data/` untracked. Report
  COMPLETE/BLOCKED/INCOMPLETE with raw outputs, the gate verdict, the
  per-fold IC distribution (mean, median, SD, Q25/Q75, min, max, % > 0,
  % > 0.10), the block-bootstrap 95% CI on the mean, the permutation
  p-value, and the diagnostic report path.

## 7. Strict file allowlist

Create:

- `src/quantara/ic_stability_diagnostic.py`
- `tests/test_ic_stability_diagnostic.py`
- `tests/test_integration_ic_stability.py`
- `tests/test_integration_ic_stability_real.py`
- `docs/superpowers/plans/2026-08-29-b35-ic-stability-diagnostic.md`

Modify:

- `src/quantara/training_pipeline.py` — add the `_write_per_fold_sidecar`
  function and call it from the KILL exit path. **No change to existing
  quality checks, attempt manifest, or publication semantics.**
  Regression-pinned by the existing 012 integration test
  (`tests/test_integration_training_logistic.py`).
- `src/quantara/cli.py` — *only if T5 is in scope*; otherwise no change.
- `tests/conftest.py` — additive only: a `write_synthetic_sidecar(path,
  ics)` helper for the new tests.

Nothing else — no rights change, no `uv.lock` change, no change to
011/012 published artifacts, no change to any other pipeline module.
Any other changed file = BLOCKED.

## 8. Stop conditions

Report BLOCKED with evidence if: any §3 frozen anchor does not match
the live store at T0; the year parent chain fails verification during
T4; the sidecar writer changes the existing 012 attempt manifest
(verifiable by byte-comparing the 10-line diagnostic before and after
T1); the diagnostic's gate evaluation returns a verdict that does not
match the §4 rule (a unit test for the rule is in T2 — a regression in
T4 means a real bug, not a result); the integration test cannot
restore the seven pointers byte-exactly; any §3 scope boundary would
need violating.

**The gate verdict itself is NOT a stop condition.** PROCEED, PROCEED_WITH_CAVEAT,
and STOP_PUBLISH_NEGATIVE are all valid outcomes. The slice works
correctly in all three cases; the report and the verdict are the deliverable.

## 9. Final report requirements

Status (`COMPLETE`/`BLOCKED`/`INCOMPLETE`); starting/ending HEAD;
changed-file list vs §7; per-task red→green evidence; the seven restored
pointer bytes; the diagnostic report path; the full per-fold IC
distribution (mean, median, SD, Q25/Q75, min, max, % > 0, % > 0.10,
best 10 / worst 10 by fold index); the block-bootstrap 95% CI on the
mean; the permutation p-value; the gate verdict and the structured
reason string; raw gate outputs; push confirmation.

If the gate verdict is `PROCEED` or `PROCEED_WITH_CAVEAT`, the report
also includes a 1-line recommendation for B4 (e.g., "B4 plan should
use rolling pooled τ starting at fold 30" or "B4 plan should treat
the IC as concentrated in Q1, not stable across the year"). If the
verdict is `STOP_PUBLISH_NEGATIVE`, the report includes a 1-line
statement that no further work is justified on the 012 model and the
honest negative is the publishable result.
