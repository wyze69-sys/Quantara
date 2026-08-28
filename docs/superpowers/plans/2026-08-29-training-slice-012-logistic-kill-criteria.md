# Training Slice 012 — Exact-Decimal Logistic Probability Head (IRLS) with Pre-Registered Kill Criteria

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-29
**Starting HEAD:** `7dc9811023f2c34c557ae302d262b51f0b06117a` (main, clean, synced with origin)
**Executor:** Codex (Act mode). Hermes wrote this plan from a verified live-store audit on 2026-08-29.

**Provenance:** implements the review outcomes deferred from slice 011's
amendment: log-loss/Brier metrics on a logistic probability model and
pre-registered lane kill criteria. The Binance Vision derivatives backfill
(funding monthly → 2020-01, metrics daily → 2020-09) is deliberately **not**
in this slice: it is a data-acquisition slice (013), not a modeling slice.
Verified archive facts for 013 are recorded in §3 so that plan can be
authored directly.

## 0. Owner authorization (read first)

The owner (wyze69-sys) approved internal model training in slice 011 via the
rights v3 record (`model_train_internal: OWNER_APPROVED_PENDING_COUNSEL`).
This slice trains under the **same** authorization: private internal research
evidence only — no customer display, no redistribution, no commercial
production use, no live trading. **No rights-record change is required or
permitted in this slice**; `binance-usdm-provider-rights.v3.yaml` stays
byte-identical.

## 1. Goal

Train the second Quantara model: a **logistic regression probability head**
on the four existing research features, predicting **direction**
(`l_fwddir_24`), fit per walk-forward fold by **IRLS (iteratively reweighted
least squares)** in exact `decimal.Decimal` arithmetic — zero binary floats —
scored with **calibrated probability metrics** (log-loss, Brier) against
honest causal baselines (majority class, momentum sign, climatology
probability), and judged by **pre-registered kill criteria** frozen in this
document and in the descriptor before any model runs. Published through the
existing immutable, content-addressed training lane with the same rights
gate, parent authentication, attempt manifests, no-op semantics, and
quality-evidence discipline as every prior slice.

Slice 011's lesson is the design driver: the ridge model lost to the
per-fold causal majority baseline (mean directional accuracy 0.514779 vs
0.534900; strictly better on only 18/117 folds). A model that cannot clear
the causal baseline is not evidence of skill. Slice 012 makes that judgment
explicit and non-negotiable in advance.

## 2. Frozen anchors (verified against the live store on 2026-08-29)

Year-chain parents are identical to 011 (all `quality_state: PASS`):

- **Research (year):** commit `5d4a2321f08d4fc61bfc979334e0198ab1e130e5fc812b59c73845502e31dbfc`, dataset_id `binance_usdm_btcusdt_klines_1h_2024_research_core_v1`, canonical_content_hash `d3efb5f7257534708b26b9f068d9264d0ff6fcc6da550cd4ad248f7c0f055e89`, parquet object `385b68d4326e3a150014a0f20b856e9d315c105cf1b9d6f7f2465ec48dac819a` (8,784 rows).
- **Validation (year):** commit `a919dda90b043d0e8a0617f07bb74375ec21439ab2d6c0dbd2f246dc97163be5`, dataset_id `binance_usdm_btcusdt_klines_1h_2024_validation_wf_v1`, folds artifact object `b321606b679e0995fea73fc7caf3ecb94d26403bacb04072a26a87011581d9d9` (117 folds; parameters `test_size: 72, min_train_size: 336, embargo: 24`; fold 0 `train [0,336)`, `embargo [336,360)`, `test [360,432)`; fold 116 `train [0,8688)`, `test [8712,8784)`).
- **Evaluation (year, sibling evidence only):** commit `24df03702ee835c215a8c1ae66e72c6e1aa14e8e925b1de6848100a97028c28a`, artifact `94cd085b75b1cd9a57940571812fa90238d98a4f97e0bf5139fd70a77698d922`.

Training-lane state from slice 011 (verified 2026-08-29):

- **Training current pointer:** commit `0284c655c7c195820f7cb739ea5574bc69334986ca5a108537be585f2cfbc20f`, manifest_sha256 `77ef4d54aecb5651bf1594c3dd6827cd66df8c6de19fc8d93dca84443d8eebe5`, artifact `c2e45fc6e88e7e9ce67f87c4f28c20d817b2009611d86d497ebf70e452ca4487`, canonical_content_hash `aafc96e5dcf3c3a656335a2b005ce7e5774c1d31910ba15118b7f8cd8a78e122`, dataset_id `binance_usdm_btcusdt_klines_1h_2024_training_ridge_v1`.
- **011 frozen results** (kill-criteria inputs): ridge λ=1 mean Pearson IC **−0.140943023553775952** (vs return), mean directional accuracy **0.514779202279202279** over 8,400 predictions; baselines `majority_class_train_window` mean **0.534900284900284900**, `sign_f_ret_1` mean **0.493233618233618234**; model strictly beat the causal baseline on 18/117 folds, tied 63, lost 36.

Research-row tuple layout, null counts, and direction base rates are
unchanged from 011 §2 (8,784 rows; labeled 8,760: up=4706, down=4051,
zero=3; full-year up-rate 0.537215 — frozen data anchor only).

**Resting store pointers** (the integration test must snapshot these itself
and restore byte-exactly in `finally`; do not trust this list alone — verify
at T0 and record actual bytes in the final report):

```text
klines/BTCUSDT/1m       9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f
klines/BTCUSDT/1h       702dab9f66b9d7181458916324ce906020d6415709b4189b395b1378b6b9e271
klines/BTCUSDT/1d       2d09178f767dc563306359db8a31d96d7d00c90890ffd78635ffd94db35a02bf
research/BTCUSDT/1h     cb9079eab9e1f7237d736f5f5021270fd0c8dc176a5ee37d5fdd38ac9977c548
validation/BTCUSDT/1h   166651165729ec3cda1cc48967e45eace09dc6a9b078a3e619efc9af15b3a410
evaluation/BTCUSDT/1h   d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675
training/BTCUSDT/1h     0284c655c7c195820f7cb739ea5574bc69334986ca5a108537be585f2cfbc20f
```

The year commits above are retained in their lane directories but are NOT
what the resting klines/research/validation/evaluation pointers reference;
driving the year chain (as `tests/test_integration_year.py` does) re-points
them via the existing recovery path, then restores.

## 3. Scope and non-goals

In scope: logistic metrics module (IRLS, log-loss/Brier, climatology
baseline, kill-criteria evaluation); additive training-descriptor extension
(model family + kill-criteria block); additive training-quality extension
(`lane_kill_criteria` check); dual-path training-pipeline extension (publish
on pass; attempt-manifest evidence + exit 4 on kill); config YAML; unit
tests; a real-data dual-outcome integration test; plan-doc commit; one final
push.

Forbidden (STOP and report BLOCKED if tempted): any change to frozen slices
001–011 behavior or retained artifacts; any edit to any rights YAML; pandas
/ NumPy / SciPy / sklearn / any new dependency; binary floats in the
training path; training on anything except fold train ranges; touching
`data/` outside the documented pointer snapshot/restore and new training
publications; `git add .`; force-push; any model other than the specified
logistic IRLS model; hyperparameter search (λ, iterations, tolerance, and
clamps are frozen in the descriptor); any claim of predictive performance
beyond the computed metrics; renegotiating kill criteria after results are
observed.

Non-goals (deferred, with verified facts for slice 013): the Binance Vision
derivatives backfill. Verified 2026-08-29: funding monthly archives exist at
`data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-YYYY-MM.zip`
from **2020-01** (≈808 bytes/month, CSV columns `calc_time,
funding_interval_hours, last_funding_rate`, 3 rows/day at 8h interval);
metrics daily archives exist at
`data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip` from
**2020-09-01** (≈11 KB/day, CSV columns `create_time, symbol,
sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio,
sum_toptrader_long_short_ratio, count_long_short_ratio,
sum_taker_long_short_vol_ratio`); 2,188 daily metrics files cover
2020-09-01 → 2026-08-28 (≈30 MB total — light, no GB-scale concern). Slice
013 will acquire these as new retained lanes under the existing v3 rights.

## 4. Pre-registered kill criteria (frozen before any 012 model runs)

Evaluated on the published-evidence summaries over the 2024 year, 117 folds,
all eligible test rows (non-null features, non-null label, non-zero
direction; `total_predicted_count` reported in the artifact):

- **K1 — Accuracy bar:** mean `directional_accuracy` ≥ `0.534900284900284900`
  (the 011 causal `majority_class_train_window` mean). The model must match
  or beat the naive causal baseline.
- **K2 — Direction IC bar:** mean `direction_ic` (per-fold Pearson IC of the
  predicted up-probability vs the binary direction label) ≥ `0.02`.
- **K3 — Log-loss bar:** mean `log_loss` ≤ `0.7625` (≈ 1.1 × ln 2 ≈ 0.76246;
  the model must not be materially worse than the constant-0.5 no-information
  predictor, log-loss ln 2 ≈ 0.69315).
- **K4 — Brier bar:** mean `brier` ≤ `0.25` (the constant-0.5 Brier; ties
  allowed).

Decision rule: **all four pass → the artifact publishes (quality PASS, exit
0). Any one fails → no lane publication: the training pointer stays at
011's commit, an attempt manifest with terminal_result
`KILL_CRITERIA_FAILED` and the observed values in diagnostics is written,
and the pipeline exits with new code 4.** The four constants are pinned in
the descriptor's `kill_criteria` block; post-hoc renegotiation is
prohibited. Kill-criteria failure is a legitimate, expected outcome — the
integration test accepts both branches. Failing the criteria is NOT a stop
condition for this slice; it is the slice working as designed.

Apples-to-apples note: 011's baseline mean was computed over its 8,400
predicted rows; 012 additionally excludes the 3 zero-direction rows, so the
artifact recomputes `majority_class_train_window` per fold on 012's
eligible rows for the evidence block. K1's constant stays the 011 number —
pre-registered means pre-registered; the 3-row difference is documented
noise.

## 5. Design

### 5.1 Logistic metrics (`src/quantara/training_metrics_logistic.py`)

New module; 011's `training_metrics.py` stays byte-identical. Copy the
DECIMAL_CONTEXT discipline (prec=50, ROUND_HALF_EVEN, Emin/Emax ±999999,
traps InvalidOperation/DivisionByZero/Overflow; Q18 storage quantum).

- **Labels:** `y = 1` if `l_fwddir_24 = +1`, `y = 0` if `−1`; rows with
  direction 0 (3/year) are excluded from training and scoring, counted as
  `zero_label_count` per fold.
- **Per fold, on research_rows:** usable train rows = train-range rows with
  all four features and the label non-null and non-zero; require ≥ 200
  usable rows else hard quality failure (fold 0 has 276 minus zeros).
- **Standardize** features with train-window Decimal mean/std exactly as
  011 (zero std → `MetricDomainError`).
- **IRLS:** parameters β = (intercept, 4 coefficients), β₀ = 0. For
  iteration ≤ `max_iterations` (50): η = Xβ; **clamp η to [−24, +24]**;
  μ = 1/(1+exp(−η)) via `DECIMAL_CONTEXT.exp` (verified working on this
  Python/decimal build); **clamp μ to [1e−12, 1−1e−12]** (separation
  guard); weights w = μ(1−μ); solve the 5×5 ridge system
  (XᵀWX + λI)β_new = XᵀWz with z = η + (y−μ)/w, **λ = Decimal("1") on the
  four coefficients only (intercept unpenalized)**, by Gauss elimination
  with partial pivoting (reuse the 011 solver pattern; do not mutate the
  frozen module — implement locally); converge when every
  |β_new,ᵢ − βᵢ| < `tolerance` (Decimal "0.000000000001"); no convergence
  in 50 iterations → `MetricDomainError("irls_did_not_conververge")`
  (exact id `irls_did_not_converge`). **Solve the whole IRLS loop twice per
  fold; require exact final-β equality** (determinism, surfaced to
  quality). Record `converged_iterations` per fold.
- **Predict** on eligible test rows (skip null-feature/null-label/zero-label
  rows, count them): p̂ = sigmoid(clamped η), Q18-quantized; direction = +1
  if p̂ ≥ 0.5 else −1.
- **Metrics per fold:** `directional_accuracy` (sign agreement vs
  `l_fwddir_24`); `log_loss` = −mean ln(p̂ᵢ) for y=1 / ln(1−p̂ᵢ) for y=0,
  p̂ clamped to [1e−12, 1−1e−12] inside the log; `brier` = mean (p̂ᵢ−yᵢ)²;
  `direction_ic` = Pearson IC of p̂ vs y over the fold's scored rows
  (reuse the 011 pair/IC pattern locally); `pearson_ic` of p̂ vs
  `l_fwdret_24` reported for 011 continuity (not a criterion). All Q18.
- **Baselines per fold (causal):** `majority_class_train_window`
  (train-window majority direction, ties → +1) and `sign_f_ret_1` for
  accuracy, exactly as 011; **`climatology_p`**: constant probability =
  train-window up-rate (Q18) — the honest probability baseline scored with
  the same log-loss/Brier arithmetic. All three appear per fold and in the
  artifact baseline summaries.
- **Kill evaluation:** pure function mapping the metric summaries and
  baseline summaries to the four observed values with pass/fail booleans
  (K1 vs baseline mean; K2, K3, K4 vs their constants).
- Reject `float` inputs structurally (mirror 011's `_validate_numeric`).

### 5.2 Descriptor extension (`src/quantara/training_descriptor.py`)

Additive only; 011 descriptors must load byte-identically (regression test
pins dataset_id, descriptor_hash, and `canonical_semantics()` of the
committed 011 config). New accepted model family:
`model.family: logistic_irls` with exact-equality frozen parameters
(`lambda: "1"`, `max_iterations: 50`, `tolerance: "0.000000000001"`,
`eta_clamp: "24"`, `mu_clamp: "0.000000000001"`); derived dataset_id suffix
generalizes to `{base}_training_logistic_v1`; new required
`kill_criteria` block for the logistic family pinning the four constants
from §4 (exact Decimal strings). Config:
`configs/datasets/binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml`,
period `2024-01-01T00:00:00Z` → `2025-01-01T00:00:00Z`, parent
`binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml`, legal record v3,
`training_set {name: btcusdt_core_v1_logistic_v1, version: "1"}`,
`target: l_fwddir_24`, schema `quantara_model_training_v1` unchanged.

### 5.3 Quality extension (`src/quantara/training_quality.py`)

Add `lane_kill_criteria` to the ordered CHECK_IDS (hard) on the publish
path: (a) artifact `kill_criteria.constants` exactly equal the descriptor's
pinned constants (Decimal equality); (b) artifact `kill_criteria.observed`
values equal the artifact's own summaries/baseline summaries (internal
consistency); (c) all four booleans true. Existing checks unchanged and
still all-pass on the ridge path (regression-pinned).

### 5.4 Pipeline dual-path (`src/quantara/training_pipeline.py`)

Additive family dispatch: `ridge_linear` path untouched (regression test);
`logistic_irls` path builds the artifact via the new module. The kill gate
sits between artifact construction and publication:
- **All four pass:** publication exactly as 011 — staging → `store_object`
  → `stage_commit`/`publish_commit` → `verify_commit_graph` →
  `write_current` → `verify_training_current_graph`; attempt manifest
  `PUBLISHED`; idempotent rerun `VERIFIED_NO_OP`; exit 0.
- **Any fail:** **no commit is staged, `write_current` is never called**
  (pointer stays at 011's commit); attempt manifest with
  `terminal_result: KILL_CRITERIA_FAILED`, diagnostics listing the four
  observed values vs constants and which failed; exit 4.
- Exit codes: 0/2/3 with established meanings; **4 reserved exclusively
  for KILL_CRITERIA_FAILED**.
- No-op detection unchanged (PASS commits only).
- `training_from` lineage for the logistic artifact binds the 011 training
  commit as parent (`training_parent` block in the artifact), so the lane
  history reads ridge → logistic.

### 5.5 Logistic artifact (publish path)

CAS JSON object `quantara.model_training_logistic/v1`, JCS + trailing LF:
header as 011 (dataset_id, provider, instrument_id, period, features,
target `l_fwddir_24`, model block with the frozen IRLS parameters,
training_set, decimal_contract, disclaimer "private internal research
evidence; single-asset single-year walk-forward; no live trading, no
performance claim, no commercial use"); `research_parent`,
`validation_parent`, `training_parent` blocks (011 commit/artifact hashes);
`records` (117 folds: per-fold Q18 coefficients + intercept,
converged_iterations, clamp hit counts, usable/excluded counts, per-fold
metrics, three baselines, scored-row counts); `summaries` (per metric:
equal_weight_mean, median, min, max, pos/neg/zero fold counts, fold_count,
total_predicted_count); `baselines` summary (three baselines);
`kill_criteria` block (constants, observed, booleans).

### 5.6 Leakage guarantees (encode as tests)

All 011 §4.7 guarantees carry over (train-range slicing, per-fold
standardization stats from train rows only, embargo == label horizon,
poisoned train-range fixture rejected by `fold_alignment`), plus
logistic-specific tests: IRLS fit uses only the fold's train rows; p̂ for
fold k uses only fold k's β; climatology p uses only the fold's train-window
labels; kill evaluation cannot see test data (it consumes summaries only).

## 6. Task sequence (strict TDD — red before green, focused tests in-loop,
full offline suite once at the end)

- **T0 — Plan and baseline.** Write this document verbatim to
  `docs/superpowers/plans/2026-08-29-training-slice-012-logistic-kill-criteria.md`;
  commit `docs: plan training slice 012 logistic kill criteria`. Verify
  starting state: HEAD `7dc9811…`, clean tree, the seven resting pointers
  (§2) match the live store, offline suite green
  (`uv run pytest -m "not integration" -q`).
- **T1 — Logistic metrics.** Red: hand-computed 2-feature IRLS fixture
  (expected β produced by an independent Decimal IRLS script embedded in
  the test), η/μ clamp behavior, separation clamp, zero-std rejection,
  float rejection, non-convergence error, determinism (double-run exact
  equality), log-loss/Brier arithmetic vs hand values, climatology
  baseline arithmetic, kill evaluation pass/fail boundaries (values exactly
  at each threshold). Green: `src/quantara/training_metrics_logistic.py`.
  Commit `feat(training): exact-decimal logistic IRLS metrics with kill criteria`.
- **T2 — Descriptor extension.** Red: logistic family accepted with exact
  parameters; kill_criteria block required and validated (exact constants);
  wrong family/parameters/missing block rejected; derived dataset_id
  `_training_logistic_v1`; **regression pin: the committed 011 ridge config
  loads with unchanged dataset_id, descriptor_hash, canonical_semantics**.
  Green: additive `training_descriptor.py` edits + config YAML. Commit
  `feat(descriptor): logistic training descriptor with pre-registered kill criteria`.
- **T3 — Quality extension.** Red: `lane_kill_criteria` in CHECK_IDS order;
  constants mismatch → fail; observed-vs-summaries mismatch → fail; any
  false boolean → fail; ridge path CHECK_IDS unchanged. Green: additive
  `training_quality.py` edits. Commit `feat(training): lane kill-criteria quality check`.
- **T4 — Pipeline dual-path.** Red (synthetic chain fixture; conftest
  extended additively with `write_training_descriptor_logistic` and an
  impossible-criteria variant): PASS path publishes with pointer move and
  `VERIFIED_NO_OP` rerun; FAIL path (e.g. K1 threshold 0.99) exits 4,
  leaves the training pointer byte-unchanged, writes an attempt manifest
  with `KILL_CRITERIA_FAILED` and observed values in diagnostics, stages no
  commit; ridge regression test still passes untouched. Green:
  `training_pipeline.py` dual-path. Commit
  `feat(training): dual-path training pipeline with pre-registered kill criteria`.
- **T5 — Real-data integration.** New
  `tests/test_integration_training_logistic.py` mirroring
  `test_integration_training.py` with the dual-outcome design: snapshot
  **seven** pointers (six resting + training); drive the year chain; run
  the logistic CLI on the real descriptor. **Both outcomes are supported
  and asserted:** exit 0 → full publication assertions (117 records,
  quality PASS with `lane_kill_criteria`, kill booleans all true,
  `training_parent` = 011 commit, no-op rerun byte-identical pointer); exit
  4 → training pointer byte-identical to the pre-run snapshot (still 011's
  commit), attempt manifest `KILL_CRITERIA_FAILED` with four observed
  values in diagnostics, no new commit dir. Either way: per-fold causality
  assertions (majority baseline recomputed independently in-test from
  train-range labels; climatology p recomputed from train-window up-rate),
  and `finally` restores all seven pointers byte-exactly. Note on ordering:
  `test_integration_training.py` sorts before
  `test_integration_training_logistic.py`; each test drives and restores
  the chain independently, so order does not matter. Commit
  `test(integration): real year-chain logistic run against pre-registered criteria`.
- **T6 — Final gates and push.** `uv lock --check`; `uv run ruff check .`;
  `uv run pytest -m "not integration" -q`; `uv run pytest -m integration -q`
  (both year-chain training drives take minutes each; keep the machine
  quiet); `git diff --check`; changed-file set equals §7 allowlist; single
  push; verify `HEAD == origin/main`, clean tree, `data/` untracked.
  Report COMPLETE/BLOCKED/INCOMPLETE with raw outputs, and the kill-criteria
  observed values vs constants verbatim.

## 7. Strict file allowlist

Create: `src/quantara/training_metrics_logistic.py`,
`configs/datasets/binance-usdm-btcusdt-1h-2024-training-logistic-v1.yaml`,
`tests/test_training_metrics_logistic.py`,
`tests/test_training_descriptor_logistic.py`,
`tests/test_training_quality_logistic.py`,
`tests/test_training_pipeline_logistic.py`,
`tests/test_integration_training_logistic.py`,
`docs/superpowers/plans/2026-08-29-training-slice-012-logistic-kill-criteria.md`.

Modify: `src/quantara/training_descriptor.py`,
`src/quantara/training_pipeline.py`, `src/quantara/training_quality.py`,
`tests/conftest.py` (all additive, each regression-pinned). Nothing else —
no CLI change (the `quantara.training-descriptor/v1` schema gate already
dispatches; family lives inside the descriptor), no rights change, no
`uv.lock` change. Any other changed file = BLOCKED.

## 8. Stop conditions

Report BLOCKED with evidence if: any §2 frozen anchor does not match the
live store at T0; the year parent chain fails verification; the IRLS solver
produces non-deterministic results; a fold cannot converge within 50
iterations on the real data (report the fold and iteration trace); the
integration test cannot restore the seven pointers byte-exactly; any §3
scope boundary would need violating. **Kill-criteria failure on the real
run is NOT a stop condition** — it is the expected possible outcome with
exit 4, dual-outcome-tested, reported honestly.

## 9. Final report requirements

Status (`COMPLETE`/`BLOCKED`/`INCOMPLETE`); starting/ending HEAD;
changed-file list vs §7; per-task red→green evidence; the seven restored
pointer bytes; attempt-manifest terminal_result for the real run
(`PUBLISHED` with commit/artifact/canonical hashes, or
`KILL_CRITERIA_FAILED` with the four observed values vs constants); the
summary metrics and baseline blocks verbatim (model vs majority vs momentum
vs climatology); gate outputs raw; push confirmation.
