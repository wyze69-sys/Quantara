# Quantara Data Slice 004 — Validation Folds Implementation Plan

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-26-validation-folds-design.md`

## 1. Goal

Implement the validation-folds layer end to end with TDD: a validated descriptor gating on
`analyze_internal` (v2 record), deterministic anchored walk-forward fold engines with
label-horizon embargo and property-proven leakage invariants, exact-decimal per-fold test-segment
statistics with structural-null equality, a PASS-only quality evaluator, lineage-bound immutable
publication through the unchanged protocol with truthful milestones (including the `290c963`
referenced-commit contract) and idempotent reruns — proven offline against synthetic research
parents, against a frozen golden fixture (`N = 432` single fold), and against the real published
1h research table (744 rows, exactly 5 folds) in the marked integration module. No model fitting,
no search, no IC — structurally absent.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-26-data-slice-004-validation-folds.md
and execute it exactly. Do not modify scope. Follow task order; each task
ends green with raw command output pasted before its commit. Report
COMPLETE / BLOCKED / INCOMPLETE at exit with full gate outputs.
```

## 3. Approved inputs

- Governing design above; behavioral requirements derive from it plus predecessor publication
  contracts.
- Identity: commits use `258711354+wyze69-sys@users.noreply.github.com`.
- Legal posture: gates on `analyze_internal` via
  `configs/legal/binance-usdm-provider-rights.v2.yaml` only; no rights record is created or
  amended; `model_train_internal` stays `UNKNOWN` and unexercised.
- Stack: unchanged pins; no new runtime dependencies.
- Starting facts: the real 1h research table is published locally (commit lineage base
  `702dab9f…`, table commit `cb9079ea…`, 744 rows, quality PASS); the 31-bar 1d derived dataset
  exists for undersized-parent rejection tests; both verify.

## 4. Observed starting state

- Branch `main` == `origin/main`, tree clean, HEAD `290c96329aa06b439d7cf7bfab89d35ffc2c983c`
  (post-audit referenced-commit fix).
- Offline suite: 406 tests green; parallel `-n 4` green (~8m05s); integration serial green.
- Reuse unmodified (verified signatures): `read_research_rows(path) -> list[tuple]`
  (`research_pipeline.py:193`); `run_research_pipeline(descriptor_path, ...)`
  (`research_pipeline.py:540`) as the orchestration template; `RESEARCH_COLUMNS` positional order
  `open_time_ms, f_ret_1, f_roc_60, f_rvol_20, f_volratio_20, l_fwdret_24, l_fwddir_24`
  (`hashing.py:189`); `render_decimal_18(value) -> str`, canonical JCS helpers (`hashing.py`);
  `load_rights_record` and the `analyze_internal` permit path (`descriptor.py:99-104`,
  `:312-313`); `store_object`, `stage_commit`, `publish_commit`, `verify_commit_graph`,
  `read_and_verify_current`, `write_current` (`publication.py`); manifest builders and attempt
  writers (`manifests.py`, `pipeline.py::_write_attempt` pattern); truthful milestone dict and
  the referenced-commit-on-`pointer_replaced` rule from `research_pipeline.py` as corrected in
  `290c963`.
- Frozen anchors captured at starting HEAD: kline `schema_fingerprint()` equals
  `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8`; v1 rights SHA-256
  `547fc79c…3697`; research fingerprint/content-hash outputs unchanged by this slice.

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
configs/datasets/binance-usdm-btcusdt-1h-2024-01-validation-wf-v1.yaml  # design §10 values
src/quantara/validation_descriptor.py # strict loader for quantara.validation-descriptor/v1
src/quantara/folds.py                 # pure partition/boundary engines, design §4–§5
src/quantara/fold_stats.py            # exact-Decimal per-fold test-segment stats, design §6
src/quantara/validation_quality.py    # validation_* evaluator, PASS-only policy v1, design §11
src/quantara/validation_pipeline.py   # orchestration mirroring research_pipeline.py, design §9
src/quantara/hashing.py               # modified: additive validation_schema_fingerprint + validation_content_hash only
src/quantara/cli.py                   # modified: dispatch fourth schema to run_validation_pipeline
tests/conftest.py                     # modified: additive helpers only (synthetic research-parent builder reuse)
tests/test_validation_descriptor.py
tests/test_folds.py
tests/test_fold_stats.py
tests/test_validation_quality.py
tests/test_validation_pipeline.py
tests/test_validation_recovery.py
tests/test_integration_validation.py  # marked integration
tests/fixtures/golden_validation/     # T8-mandated committed fixture data
README.md                             # modified: one appended short section "## Validation folds status"
```

### 5.2 Forbidden changes

- No edits to: `research_descriptor.py`, `research_pipeline.py`, `features.py`,
  `research_quality.py`, `pipeline.py`, `derive_pipeline.py`, `descriptor.py`,
  `derive_descriptor.py`, `aggregation.py`, `canonical.py`, `quality.py`, `derive_quality.py`,
  `publication.py`, `manifests.py`, `errors.py` beyond the allowlist; any existing dataset
  config; existing specs/plans; `.github/**`; `.gitignore`.
- No modification of existing tests except additive conftest helpers that leave current fixtures'
  behavior identical; kline fingerprint, v1 rights SHA, and all slice-003b hash outputs must keep
  passing byte-for-byte.
- No training/model/search/IC/backtest-PnL code of any kind; no new feature sets, horizons,
  windows, datasets, months, instruments, databases, APIs, CI workflows; no force-push;
  `/data/` never tracked; network confined to the integration-marked module.

## 6. Tasks (each red→green with raw gate output pasted before its commit)

- **T1 Descriptor** — `validation_descriptor.py` per design §10: schema
  `quantara.validation-descriptor/v1`; unknown keys rejected; identity fields equal parent
  research descriptor's approved values; parameters restricted to `{test_size: 72,
  min_train_size: 336}` exact values; embargo never accepted as input; minimum parent rows =
  `min_train_size + embargo + test_size` = 432 enforced pre-compute as
  `undersized_parent_dataset`. Commit `feat(validation-descriptor): validated fold descriptors`.
- **T2 Hashing** — additive `validation_schema_fingerprint` (domain-separated over schema id,
  scheme, parameters, fold set name/version, parent research fingerprint) +
  `validation_content_hash`; predecessor hashes byte-unchanged. Commit
  `feat(hashing): validation content identity`.
- **T3 Fold engines** — `folds.py`: pure boundary/partition functions per design §4 with
  properties §5.1–§5.4 over generated `N` (partition completeness/disjointness, embargo width,
  symbolic+empirical label-horizon safety, value-perturbation determinism). Commit
  `feat(folds): deterministic walk-forward partitions`.
- **T4 Statistics engines** — `fold_stats.py`: per-fold TEST-segment stats per design §6 (counts,
  time bounds, per-column nulls vs structural expectation, sign distribution summing correctly,
  Q18-rendered mean/min/max) with causality property §5.5. Commit
  `feat(fold-stats): causal fold segment statistics`.
- **T5 Quality evaluator** — `validation_quality.py` per design §11 with deterministic
  `quality_identity`; failing fixture per invariant. Commit
  `feat(validation-quality): pass-only fold evaluation`.
- **T6 Pipeline** — mirror `research_pipeline.py` order per design §9: descriptor → gate → full
  base-graph authentication incl. parent Parquet hash → rows → folds → stats → quality PASS-only
  → CAS put (kind per §7 decision recorded in `object_refs`) → lineage-bound address via domain
  helper → stage/verify/write_current/read-back → idempotency via extended evidence keys
  `{lineage}` → attempt manifests with truthful milestones including the `290c963` rule →
  `--dry-run` verification-on writes-nothing parity. Commit
  `feat(validation-pipeline): lineage-bound fold orchestration`.
- **T7 CLI dispatch** — fourth schema branch; `invalid_descriptor` otherwise; dry-run parity.
  Commit `feat(cli): validation descriptor dispatch`.
- **T8 Golden fixture** — freeze expected artifact for `N = 432` (exactly one fold, test
  `[360, 432)`), generator script out-of-repo under `%TEMP%\quantara-slice-004\` reimplementing
  design §4–§6 with stdlib decimal; committed JSONs byte-exact under
  `tests/fixtures/golden_validation/`. Commit `test(golden): frozen validation fold fixture`.
- **T9 Recovery/corruption** — missing/corrupt parent BLOCKED then restore-verifies; injected
  failures at object write / rename / pointer write → FAILED(3) with pointer untouched, no
  promoted partial commits, staging fully cleaned, stale `.staging-*` removed; legitimate parent
  republication rebinds while old validation commit stays byte-identical; undersized parent
  BLOCKED pre-compute. Commit `test(recovery): validation corruption scenarios`.
- **T10 Integration** — `-m integration`, serial: real 1h research parent publishes exactly
  5 folds with §4 numbers (excluded 360, test coverage 384, last test length 96), rerun
  `VERIFIED_NO_OP` byte-identical, parent tree digest unchanged across invocations. Commit
  `test(integration): real-parent fold acceptance`.
- **T11 Docs** — README appended section "## Validation folds status" (internal-use posture,
  no-training statement). Final gates below. Commit
  `docs(readme): validation folds internal-use status`.

## 7. Acceptance numbers (design §4 arithmetic, N = 744)

- `first_test_start = 360`; excluded head = 360; test starts at 360, 432, 504, 576, 648; test
  lengths 72, 72, 72, 72, 96; exactly 5 folds; every train length ≥ 336; embargo 24 everywhere.

## 8. Completion states

- **COMPLETE:** all tasks green with pasted evidence; real-parent integration publishes exactly
  5 folds per §7; rerun `VERIFIED_NO_OP` byte-identical; parent provably untouched; golden
  fixture byte-exact; docs lint-clean; pushed once; three-way sync verified.
- **BLOCKED:** repository drift; rights gate closed; environment failure; owner declines before
  execution.
- **INCOMPLETE:** any leakage invariant, determinism rule, null-equality, identity binding,
  milestone-truthfulness (including the `290c963` referenced-commit rule), recovery, or
  documentation requirement unsatisfied.

**Final gates:** offline serial `uv run pytest -m "not integration"` exit 0; offline parallel
`uv run pytest -n 4 -m "not integration"` exit 0; integration serial `uv run pytest -m
integration` exit 0; `uv run ruff check .`; `uv lock --check` unchanged; markdownlint clean on
new/changed docs lines; changed-vs-origin files ⊆ §5.1 allowlist; `git ls-files data` empty;
kline fingerprint and v1 rights SHA byte-identical to starting values.

**Known risks:** none anticipated functionally; the remainder-merge rule (final partial block
joins the last fold) is covered by fixtures so coverage accounting never becomes an implicit
tolerance; CAS object-kind vocabulary is resolved in T6 by inspecting `publication.py` rather
than assumed.
