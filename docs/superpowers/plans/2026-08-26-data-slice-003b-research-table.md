# Quantara Data Slice 003b — Research Table Implementation Plan

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-26-research-table-features-labels-design.md`

## 1. Goal

Implement the analytical layer end to end with TDD: a validated research-table descriptor gating on `analyze_internal` (v2 record), causal feature engines and forward label engines over exact decimals with explicit storage quantization `Q18`, a PASS-only research quality evaluator with calendar-derived null budgets, lineage-bound immutable publication through the unchanged protocol with truthful milestones and idempotent reruns — proven offline against synthetic parents, against a frozen golden fixture, and against the real published 1h dataset (744 bars) in the marked integration module.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-26-data-slice-003b-research-table.md
and execute it exactly. Do not modify scope. Follow task order; each task
ends green with raw command output pasted before its commit. Report
COMPLETE / BLOCKED / INCOMPLETE at exit with full gate outputs.
```

## 3. Approved inputs

- Governing design above; behavioral requirements derive from it plus predecessor publication contracts.
- Identity: commits use `258711354+wyze69-sys@users.noreply.github.com`.
- Legal posture: gates on `analyze_internal` via `configs/legal/binance-usdm-provider-rights.v2.yaml` only; no other state is exercised or changed.
- Stack: unchanged pins; no new runtime dependencies.
- Starting facts: parent datasets published locally — 1h commit with 744 bars (`702dab9f…`), 1d with 31 bars (`2d09178f…`); both verify.

## 4. Observed starting state

- Branch `main` == `origin/main`, tree clean, HEAD `f090b51f73dd71674cd8a2c72d242cf19ce3a12f` (xdist commit).
- Offline suite: 335 tests green serially; parallel `-n 4` green in ~7m20s.
- Reuse unmodified (verified signatures): `read_canonical_rows(path) -> list[tuple]`, `PARQUET_SCHEMA`, `WRITER_CONFIG` (`canonical.py`); `sha256_hex`, `render_decimal_18(value) -> str`, canonical JCS helpers (`hashing.py`); `load_rights_record` (`descriptor.py`); `store_object`, `stage_commit`, `publish_commit`, `verify_commit_graph`, `read_and_verify_current`, `write_current`, `existing_commit_matches(keys=...)` (`publication.py`); manifest builders and attempt writers (`manifests.py`, `pipeline.py::_write_attempt` pattern); truthful milestone dict from `derive_pipeline.py`.
- Frozen anchors captured at starting HEAD: kline `schema_fingerprint()` equals `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8`; v1 rights SHA-256 `547fc79c…3697`.

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
configs/datasets/binance-usdm-btcusdt-1h-2024-01-research-core-v1.yaml   # design §6 verbatim
src/quantara/research_descriptor.py   # strict loader for quantara.research-descriptor/v1
src/quantara/features.py              # causal + forward engines, Q18 quantization, pure functions
src/quantara/research_quality.py      # research_* evaluator, PASS-only policy v1
src/quantara/research_pipeline.py     # orchestration mirroring derive_pipeline.py incl. truthful milestones
src/quantara/hashing.py               # modified: additive research_schema_fingerprint + research_content_hash only
src/quantara/cli.py                   # modified: dispatch third schema to run_research_pipeline
tests/conftest.py                     # modified: additive helpers only (synthetic parent builder reuse)
tests/test_research_descriptor.py
tests/test_features.py
tests/test_research_quality.py
tests/test_research_pipeline.py
tests/test_research_recovery.py
tests/test_integration_research.py    # marked integration
README.md                             # modified: one appended short section "## Research tables status"
```

### 5.2 Forbidden changes

- No edits to: `pipeline.py`, `derive_pipeline.py`, `descriptor.py`, `derive_descriptor.py`, `aggregation.py`, `canonical.py`, `quality.py`, `derive_quality.py`, `publication.py`, `manifests.py`, `errors.py` beyond the allowlist; any existing dataset config; existing specs/plans; `.github/**`; `.gitignore`.
- No modification of existing tests except additive conftest helpers that leave current fixtures' behavior identical; the kline fingerprint regression test must keep passing byte-for-byte.
- No new feature sets, horizons beyond `{24}`, windows beyond `{60, 20}`, datasets, months, instruments, models, training code, splits, databases, APIs, CI workflows; no force-push; `/data/` never tracked; network confined to the integration-marked module.

## 6. Completion states

- **COMPLETE:** all tasks green with pasted evidence; real-parent integration publishes the 1h research table with exactly 744 rows and designed null budgets (ret 1 / roc 60 / rvol 20 / volratio 19 / labels 24 each side as derived from parent length), rerun shows `VERIFIED_NO_OP` byte-identical, parent provably untouched, undersized 1d base structurally `BLOCKED`, docs lint-clean, pushed once.
- **BLOCKED:** repository drift; rights gate closed; environment failure; owner declines before execution.
- **INCOMPLETE:** any causality property, quantization rule, identity binding, milestone-truthfulness, recovery, or documentation requirement unsatisfied.

**Known risks:** none anticipated functionally; the exact-zero return edge case (`close_{t+H} == close_t`) is covered by fixtures so sign labeling never becomes an implicit tolerance.

## 7. Tasks (each: red→green → paste raw output → one conventional commit)

- **T0 Preflight** — clean `main` at `f090b51`, synchronized after normal fetch; noreply identity; transaction dir `%TEMP%\quantara-slice-003b\`; capture anchors of §4 fresh.
- **T1 Descriptor loader + config** — `research_descriptor.py`: unknown-key/identity/period/whitelist/min-parent-size rules with stable diagnostics (`unsupported_parameter`, `undersized_base_dataset`); `canonical_semantics()` JCS stability under key reordering; rejection fixtures per rule incl. 31-row-base rejection arithmetic. Commit `feat(research-descriptor): validated research table descriptors`.
- **T2 Hashing additions** — `research_schema_fingerprint(schema_version)` over the seven-column payload; `research_content_hash(fingerprint, rows)` domain `quantara-research-content-v1`, Q18 string framing; regressions: distinctness across logical changes; kline fingerprint anchor equality untouched. Commit `feat(hashing): research table content identity`.
- **T3 Feature engines** — pure functions over positional tuples; explicit `Context(prec=50)`; `Q18` only at storage boundary; hand-computed fixtures including a non-terminating quotient (e.g. closes yielding 1/3-style ratios) proving single-rounding semantics; window-boundary fixtures for every column's first-valid index; **causality property test**: for randomized valid series, perturbing bars after *t* leaves features at `≤ t` bit-identical. Commit `feat(features): causal decimal feature engines`.
- **T4 Label engines** — strictly-forward computations; zero-return sign fixture; **forward-isolation property test**: perturbing bars before *t* leaves labels at `≥ t` bit-identical; trailing-null correctness. Commit `feat(features): forward label engines`.
- **T5 Research quality evaluator** — checks per design §7 with evaluator-derived budgets from actual parent count; failing fixtures per invariant; deterministic `quality_identity`. Commit `feat(research-quality): pass-only research evaluation`.
- **T6 Pipeline** — mirror `derive_pipeline.py` order: descriptor → `analyze_internal` gate (v2) → full base-graph authentication incl. Parquet hash → load rows → engines → quality PASS-only → object store (`normalized` kind) → lineage-bound address via new domain helper in `research_pipeline.py` mirroring `derived_commit_identity` → stage/verify/write_current/read-back → idempotency via extended evidence keys `{lineage}` → attempt manifests with truthful milestones → `--dry-run` verification-only mode. Offline end-to-end test publishing a synthetic ≥90-bar parent through real `run_pipeline` fixtures then deriving; rerun no-op; lost-pointer recovery asserting `commit_renamed=False, pointer_replaced=True, object_written=False`. Commit `feat(research-pipeline): lineage-bound research orchestration`.
- **T7 CLI dispatch** — third schema branch; `invalid_descriptor` otherwise; dry-run parity. Commit `feat(cli): research descriptor dispatch`.
- **T8 Golden fixture** — committed tiny parent (~40 bars) + expected full research table + hashes computed by independent script, reviewed then frozen; offline equality proof. Commit `test(golden): frozen research table fixture`.
- **T9 Recovery suite** — parent missing/unverifiable/corrupt; injected failures at object write, rename, pointer write (safe orphans only); stale `.staging-*` cleanup; legitimate parent republication ⇒ new lineage-bound commit while old stays immutable; undersized base BLOCKED pre-compute. Commit `test(recovery): research corruption scenarios`.
- **T10 Integration (marked)** — explicit invocation only; full gates first; publish research table from the real 1h dataset via CLI: exit 0, exactly 744 rows, null budgets 1/60/20/19/24, manifests bind base commit `702dab9f…`; rerun `VERIFIED_NO_OP` byte-identical; parent immutability hashes; 1d-based descriptor rejected `BLOCKED` with `undersized_base_dataset`. Commit if green `test(integration): real-parent research acceptance`.
- **T11 Docs, gates, push** — README section (~5 lines, internal-use framing); markdownlint clean; lock/ruff/offline(-n 4)/diff-check fresh; cleanliness proofs (allowlist match, v1+anchors unchanged, `data/` untracked); single normal push; three-way sync verified.

## 8. Failure handling

Fix forward; never weaken assertions, budgets, or policy. Gate closure ⇒ `BLOCKED` before compute, never bypassed. Post-push defects get fix commits only.

## 9. Final evidence report

Raw commands and outputs for: preflight; red→green per task; causality/forward-isolation property runs; golden equality; offline + integration results with row/null-budget numbers; no-op and recovery milestones; parent immutability hashes; lint results; push synchronization; terminal status COMPLETE / BLOCKED / INCOMPLETE with residual limitations. Passing unit tests alone is insufficient.
