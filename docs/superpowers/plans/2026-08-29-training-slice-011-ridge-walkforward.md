# Training Slice 011 — Exact-Decimal Ridge Walk-Forward Training

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-29
**Starting HEAD:** `be10a86b7fca43270aff64eb240f79390b497604` (main, clean, synced with origin)
**Executor:** Codex (Act mode). Hermes wrote this plan from a verified live-store audit on 2026-08-29.

**Amendment (2026-08-29, after external review):** the `majority_class` baseline
is renamed `majority_class_train_window` and is computed **per fold from that
fold's train-range labeled rows** (causal; ties → +1) — never from the full
year. The full-year up-rate 0.537215 remains a frozen data anchor only (§2).
No other aspect of this slice changed; the remaining review outcomes
(log-loss/Brier metrics on a logistic model, pre-registered lane kill
criteria, Binance Vision derivatives backfill: funding monthly archives →
2020-01, daily metrics archives → 2020-09) apply to slice 012+.

## 0. Owner authorization (read first)

The owner (wyze69-sys) has approved amending the provider-rights record so that
`model_train_internal` becomes `OWNER_APPROVED_PENDING_COUNSEL` — the same
private-research posture as acquire/retain/normalize/analyze. Scope of that
approval: **private internal research evidence only — no customer display, no
redistribution, no commercial production use, no live trading.** This plan
implements that amendment as a **new v3 record** (v2 stays immutable in place,
mirroring the v1→v2 precedent from slice 003a).

## 1. Goal

Train the first Quantara model: a **ridge-regularized linear model on the four
existing research features**, fit per walk-forward fold over the **year-scale
2024 research table** (8,784 hourly rows), predicted on each fold's frozen test
range, scored against honest baselines. Everything in exact `decimal.Decimal`
arithmetic — **zero binary floats anywhere in the training path** — published as
a new immutable, content-addressed `training` dataset lane, with the same
rights gate, parent authentication, attempt manifests, no-op semantics, and
quality-evidence discipline as every prior slice.

This slice deliberately trains a *small, fully-auditable* model. It is not a
performance play; it is the proof that the training lane exists, is
leakage-safe, is exactly reproducible, and reports honestly (including
baselines that may beat it).

## 2. Frozen anchors (verified against the live store on 2026-08-29)

The training parent chain (all `quality_state: PASS`):

- **Research (year):** commit `5d4a2321f08d4fc61bfc979334e0198ab1e130e5fc812b59c73845502e31dbfc`, dataset_id `binance_usdm_btcusdt_klines_1h_2024_research_core_v1`, canonical_content_hash `d3efb5f7257534708b26b9f068d9264d0ff6fcc6da550cd4ad248f7c0f055e89`, schema_fingerprint `89e5bad5b2c825b60adf5585aec4edc01426062d69d5c6bfeead14487171908e`, parquet object `385b68d4326e3a150014a0f20b856e9d315c105cf1b9d6f7f2465ec48dac819a` (465,088 bytes, 8,784 rows).
- **Validation (year):** commit `a919dda90b043d0e8a0617f07bb74375ec21439ab2d6c0dbd2f246dc97163be5`, dataset_id `binance_usdm_btcusdt_klines_1h_2024_validation_wf_v1`, canonical_content_hash `6be166b3ec6b4ab8d60c2698f1298fac51bffdbb6afc7a7e2b027d672530f10e`, folds artifact object `b321606b679e0995fea73fc7caf3ecb94d26403bacb04072a26a87011581d9d9` (65,475 bytes). `validation_from.parent_commit_address` binds the research commit above.
- **Evaluation (year, sibling evidence only):** commit `24df03702ee835c215a8c1ae66e72c6e1aa14e8e925b1de6848100a97028c28a`, artifact `94cd085b75b1cd9a57940571812fa90238d98a4f97e0bf5139fd70a77698d922` (468 records = 117 folds × 4 features).

Research-row tuple layout (by index): `[0] open_time_ms int`, `[1] f_ret_1`, `[2] f_roc_60`, `[3] f_rvol_20`, `[4] f_volratio_20`, `[5] l_fwdret_24` (Decimal), `[6] l_fwddir_24` int. Null counts over 8,784 rows: f_ret_1=1, f_roc_60=60, f_rvol_20=20, f_volratio_20=19, l_fwdret_24=24, l_fwddir_24=24. Direction base rates on 8,760 labeled rows: up=4706, down=4051, zero=3 → **full-year up-rate 0.537215** (frozen data anchor only; the baseline itself is per-fold causal — §4.3).

Fold structure (folds artifact, `parameters {test_size: 72, min_train_size: 336, embargo: 24}`, coverage `{fold_count: 117, test_rows: 8424, total_rows: 8784}`, `excluded_head_rows: 360`): fold 0 `train [0,336)`, `embargo [336,360)`, `test [360,432)`; fold 116 `train [0,8688)`, `embargo [8688,8712)`, `test [8712,8784)`. Embargo (24) equals the label horizon — train-label windows cannot overlap test rows.

**Resting store pointers** (the integration test must snapshot these itself and restore byte-exactly in `finally`; do not trust this list alone):

```text
klines/BTCUSDT/1m       9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f
klines/BTCUSDT/1h       702dab9f66b9d7181458916324ce906020d6415709b4189b395b1378b6b9e271
klines/BTCUSDT/1d       2d09178f767dc563306359db8a31d96d7d00c90890ffd78635ffd94db35a02bf
research/BTCUSDT/1h     cb9079eab9e1f7237d736f5f5021270fd0c8dc176a5ee37d5fdd38ac9977c548
validation/BTCUSDT/1h   166651165729ec3cda1cc48967e45eace09dc6a9b078a3e619efc9af15b3a410
evaluation/BTCUSDT/1h   d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675
```

The year commits above are retained in the same lane directories but are NOT
what the resting pointers reference; driving the year chain (as
`tests/test_integration_year.py` already does) re-points the pointers at the
retained year commits via the existing recovery path, then restores.

## 3. Scope and non-goals

In scope: rights-record v3 amendment; training descriptor; exact-decimal ridge
metrics module; training quality module; training pipeline + CLI dispatch;
config YAML; unit tests; a real-data integration test over the year chain;
plan-doc commit; one final push.

Forbidden (STOP and report BLOCKED if tempted): any change to frozen slices
001–010 behavior or their retained artifacts; any edit to
`binance-usdm-provider-rights.v2.yaml` (v2 stays byte-identical); pandas /
NumPy / SciPy / sklearn / any new dependency; binary floats in the training
path; training on anything except the fold train ranges; touching `data/`
outside the documented pointer snapshot/restore and new `training` lane;
`git add .`; force-push; any model other than the specified ridge linear
model; hyperparameter search (λ is frozen at 1 in the descriptor); any claim
of predictive performance in artifacts beyond the computed metrics.

## 4. Design

### 4.1 Rights-record v3

New file `configs/legal/binance-usdm-provider-rights.v3.yaml`: identical to v2
except `model_train_internal` →
`state: OWNER_APPROVED_PENDING_COUNSEL`, `source_terms: "Binance Terms of Use;
data.binance.vision public archives"`, `rationale: "Owner-approved internal
model training over already-retained, internally acquired artifacts pending
counsel review. Outputs remain private research evidence: no customer display,
no redistribution, no commercial production use."`, `review_date: 2026-08-29`,
`reviewer: wyze69-sys`; `record_id: binance-usdm-provider-rights.v3`.

Code change in `src/quantara/descriptor.py`: `APPROVED_INTERNAL_OPERATIONS`
gains `"model_train_internal"` (now the 5-tuple). This makes
`permits("model_train_internal")` true under v3 (and only v3) while leaving
commercial/customer/redistribution states requiring strict ALLOWED. Update the
pinning test `tests/test_rights_and_periods.py::test_approved_internal_operation_names`
to the new 5-tuple, and add a test that v3 loads and permits exactly the five
internal operations while still refusing `customer_display`.

### 4.2 Training descriptor

`src/quantara/training_descriptor.py`, schema `quantara.training-descriptor/v1`,
mirroring `evaluation_descriptor.py` exactly (frozen dataclass, strict loader,
unknown/missing key rejection, parent resolution relative to the descriptor
file, identity binding to parent, period must equal parent period, derived
`dataset_id` must equal `{base_dataset_id}_training_ridge_v1`,
`canonical_semantics()` JCS payload, `descriptor_hash` compatibility).
`parent_descriptor` = validation descriptor. Approved parameters enforced by
exact equality: `model {family: ridge_linear, lambda: "1", solver:
gauss_elimination_partial_pivot}`, `standardization: train_window_zscore`,
`baselines: [majority_class_train_window, sign_f_ret_1]`, `metrics: [pearson_ic,
directional_accuracy, mse]`, `features` = the four frozen features, `target:
l_fwdret_24`, `training_set {name: btcusdt_core_v1_ridge_v1, version: "1"}`,
`schema_version: quantara_model_training_v1`, `quality_policy_version: "1"`,
`legal_record: configs/legal/binance-usdm-provider-rights.v3.yaml`.

Config: `configs/datasets/binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml`
with period `2024-01-01T00:00:00Z` → `2025-01-01T00:00:00Z`, parent
`configs/datasets/binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml`.

### 4.3 Exact-decimal ridge training (`src/quantara/training_metrics.py`)

Per fold, on `research_rows`:

1. **Usable train rows** = rows in `train_range` where all four features and
   `l_fwdret_24` are non-null. Require ≥ 200 usable rows else the fold is a
   hard quality failure (fold 0 has 276).
2. **Standardize** features with train-window Decimal mean and Decimal std
   (`sqrt` under `Context(prec=50, ROUND_HALF_EVEN, Emin/Emax ±999999, traps
   InvalidOperation/DivisionByZero/Overflow)` — copy the evaluation module's
   `DECIMAL_CONTEXT` discipline). If a train-window std is exactly zero →
   explicit `MetricDomainError` (test this with a synthetic constant feature).
3. **Ridge normal equations** on centered data: solve
   `(ZᵀZ + λI) w = Zᵀ(y − ȳ)` for the 4 coefficients (λ = Decimal("1")),
   intercept `b = ȳ`, by Gauss elimination with partial pivoting in the same
   context. Zero pivot → `MetricDomainError`. **Solve twice and require exact
   coefficient equality** (determinism check, surfaced to quality).
4. **Predict** test rows (skip rows with any null feature or null label —
   record counts), quantize each prediction to Q18
   (`quantize_q18`-equivalent, ROUND_HALF_EVEN, single pass), compute
   `pearson_ic(pred, l_fwdret_24)` reusing the exact pair/rank/IC logic
   pattern from `evaluation_metrics.py` (implement locally; do not mutate the
   frozen module), `directional_accuracy` (sign agreement of prediction vs
   `l_fwddir_24`, zero-sign counts reported), `mse` (mean of squared Q18
   prediction-minus-label, Q18-quantized).
5. **Baselines** on the same test rows, both strictly causal:
   `majority_class_train_window` direction accuracy (predict the majority
   direction of the fold's train-range labeled rows; ties → +1; computed from
   train rows only — never test rows, never the full year), and
   `sign_f_ret_1` direction accuracy (sign of the row's own f_ret_1). Both
   Q18.
6. Report coefficients/intercept as Q18 strings (full-precision values are
   used for prediction; the Q18 report is evidence, and a
   `metric_recomputation` check re-derives one fold's predictions from the
   stored Q18 coefficients ± quantization — recompute IC from stored
   predictions must match exactly).

Reject `float` inputs structurally (mirror `_validate_numeric`). No `float()`,
no `numpy`, no `math` on Decimals other than the context-bounded `sqrt`.

### 4.4 Training artifact

CAS JSON object (`quantara.model_training/v1`), JCS + trailing LF: header
(`dataset_id`, provider, instrument_id, period, features, target, model,
training_set, decimal_contract copied from the evaluation artifact's shape,
`disclaimer: "private internal research evidence; single-asset single-year
walk-forward; no live trading, no performance claim, no commercial use"`),
`research_parent` + `validation_parent` blocks (commit address, dataset_id,
canonical_content_hash, artifact hashes — same shape as the evaluation
artifact), `records` (117 fold entries), `summaries` (per metric:
equal_weight_mean, median, minimum, maximum, positive/negative/zero fold
counts, fold_count, total_predicted_count), `baselines` summary (mean
directional accuracy of each baseline for side-by-side honesty).

### 4.5 Training pipeline (`src/quantara/training_pipeline.py`)

Mirror `evaluation_pipeline.py` structure: schema-gated entry
`run_training_pipeline(descriptor_path, data_root, dry_run)`; rights gate
requiring BOTH `analyze_internal` and `model_train_internal` (v3 record);
parent resolution via `current.json` of the validation lane
(`_validation_dataset_dir`-equivalent, year start → same month=01 path),
byte-retain pointer before/after; `verify_validation_current_graph` +
`verify_research_current_graph` re-verification chain (copy the evaluation
pipeline's dual-parent pattern); fold/research-row consistency checks (117
folds, 8,784 rows, fold ranges within bounds, fold count == coverage count);
build records; quality report; staging → `store_object` →
`stage_commit`/`publish_commit` (commit identity domain
`quantara-training-commit-identity-v1`, lineage key `training_from`) →
`verify_commit_graph` → `write_current` → re-verify via
`verify_training_current_graph`; attempt manifests under
`data/attempts/training/`; no-op detection with
`TRAINING_EVIDENCE_KEYS` (descriptor_sha256, schema_fingerprint,
canonical_content_hash, quality_identity, object_refs, training_from,
training_commit_identity); exit codes 0/2/3 with the established meanings.
New dataset lane dir: `data/datasets/binance/usdm/training/BTCUSDT/1h/year=2024/month=01`.

`src/quantara/cli.py`: add `TRAINING_SCHEMA` dispatch block (lazy import) and
add `"model_training"` to `APPROVED_DATASET_TYPES`.

### 4.6 Training quality (`src/quantara/training_quality.py`)

Ordered `CHECK_IDS` (all hard, all must pass): `parents_authenticated`,
`lineage_binding`, `descriptor_identity`, `fold_alignment`, `train_matrix`
(usable-row floors, null accounting), `numeric_domain` (no floats; Q18
bounds), `solver_determinism` (double-solve equality), `metric_recomputation`
(re-derive one fold's IC from stored predictions), `metric_bounds` (IC ∈
[−1,1], accuracies ∈ [0,1], mse ≥ 0), `baseline_presence` (both baselines on
every fold), `canonical_structure`, `identity_contract`. Mirror the
finding/report/identity mechanics used by `evaluation_quality.py`; the
retained-commit verifier must re-check count, order, and identity agreement
across quality.json/manifest/content.json.

### 4.7 Leakage guarantees (encode as tests, not comments)

- Predictions for fold *k* use only train rows `< test_start − embargo`.
- Standardization statistics derive only from the fold's train rows.
- Test-row features never touch training (verified by construction: train
  matrix is sliced strictly by `train_range`).
- Embargo == label horizon: no train label window overlaps any test row.
- A deliberately poisoned fixture (train range extended into the test range)
  must be rejected by `fold_alignment`.

## 5. Task sequence (strict TDD — red before green, focused tests in-loop,
full offline suite once at the end)

- **T0 — Plan and baseline.** Write this document verbatim to
  `docs/superpowers/plans/2026-08-29-training-slice-011-ridge-walkforward.md`;
  commit `docs: plan training slice 011 ridge walk-forward`. Verify starting
  state: HEAD `be10a86b…`, clean tree, six resting pointers match §2, offline
  suite green before any change (`uv run pytest -m "not integration" -q`).
- **T1 — Rights v3.** Red: v3 permits `model_train_internal`, v2 still
  refuses; 5-tuple pin; commercial states still strict. Green: v3 YAML +
  `APPROVED_INTERNAL_OPERATIONS` change. Commit
  `feat(rights): approve internal model training pending counsel`.
- **T2 — Training descriptor.** Red: load/validate/reject/resolve-parent/
  canonical-semantics tests. Green: `training_descriptor.py` + config YAML.
  Commit `feat(descriptor): define training descriptor v1`.
- **T3 — Ridge metrics.** Red: hand-computed 2-feature ridge fixture (compute
  expected coefficients with an independent Decimal script embedded in the
  test), standardization, zero-std rejection, float rejection, determinism,
  baseline accuracy arithmetic including the per-fold train-window majority
  baseline (ties → +1). Green: `training_metrics.py`. Commit
  `feat(training): exact-decimal ridge walk-forward metrics`.
- **T4 — Training quality.** Red: CHECK_IDS order/pass/fail/identity tests.
  Green: `training_quality.py`. Commit
  `feat(training): training quality evidence module`.
- **T5 — Pipeline + CLI.** Red (using a synthetic chain fixture built with
  the existing conftest builders extended additively — `rights_v3_yaml_dict`,
  `write_training_descriptor`): rights BLOCKED under a v2-style record with
  `model_train_internal: UNKNOWN`; full publish on synthetic chain; no-op
  rerun `VERIFIED_NO_OP`; pointer byte-identity; CLI dispatch. Green:
  `training_pipeline.py` + `cli.py` changes. Commit
  `feat(training): publish walk-forward training lane`.
- **T6 — Real-data integration.** `tests/test_integration_training.py`
  mirroring `test_integration_year.py`: snapshot the six resting pointers;
  drive the year chain to make the year parents current; run the training CLI
  on the real descriptor; assert 117 records, all quality checks pass,
  metrics within bounds, baselines present, and per fold the
  `majority_class_train_window` baseline equals the majority of that fold's
  train-range labels recomputed independently inside the test (causality
  assertion; no full-year constant), idempotent rerun
  `VERIFIED_NO_OP` with byte-identical training pointer; restore the six
  pointers byte-exactly in `finally`; year + training commits remain
  retained. Commit `test(integration): real year-chain training run`.
- **T7 — Final gates and push.** `uv lock --check`; `uv run ruff check .`;
  `uv run pytest -m "not integration" -q`; `uv run pytest -m integration -q`
  (includes the new training integration test — expect the year-chain drive
  to take minutes, keep the machine quiet); `git diff --check`; confirm the
  changed-file set equals the §6 allowlist; single push of all commits;
  verify `HEAD == origin/main`, clean tree, `data/` untracked. Produce the
  final evidence report (COMPLETE/BLOCKED/INCOMPLETE + raw outputs).

## 6. Strict file allowlist

Create: `configs/legal/binance-usdm-provider-rights.v3.yaml`,
`configs/datasets/binance-usdm-btcusdt-1h-2024-training-ridge-v1.yaml`,
`src/quantara/training_descriptor.py`, `src/quantara/training_metrics.py`,
`src/quantara/training_quality.py`, `src/quantara/training_pipeline.py`,
`tests/test_training_descriptor.py`, `tests/test_training_metrics.py`,
`tests/test_training_quality.py`, `tests/test_training_pipeline.py`,
`tests/test_integration_training.py`,
`docs/superpowers/plans/2026-08-29-training-slice-011-ridge-walkforward.md`.
Modify: `src/quantara/descriptor.py`, `src/quantara/cli.py`,
`tests/test_rights_and_periods.py`, `tests/conftest.py` (and `uv.lock` only
if — and only if — a `uv lock` refresh is genuinely required; no new
dependencies are permitted). Nothing else. Any other changed file = BLOCKED.

## 7. Stop conditions

Report `BLOCKED` with evidence if: the year parent chain fails verification;
any frozen anchor in §2 does not match the live store at T0; a quality check
cannot be made to pass honestly; the ridge solver produces non-deterministic
results; the integration test cannot restore the resting pointers
byte-exactly; any scope boundary in §3 would need violating.

## 8. Final report requirements

Status (`COMPLETE`/`BLOCKED`/`INCOMPLETE`); starting/ending HEAD; changed-file
list vs §6; per-task red→green evidence; the six restored pointer bytes;
training commit address + artifact + canonical_content_hash; the summary
metrics block verbatim (model IC/accuracy/MSE vs both baselines); gate
outputs raw; push confirmation.
