# Quantara Data Slice 005 — Temporal Expansion 2024-Q1 Implementation Plan

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-26-temporal-expansion-q1-design.md`

## 1. Goal

Add multi-month range datasets at the kline layer (descriptor v2 with an ordered `months` list,
all-archive checksum verification before any parse, seam-proven concatenation) and extend the
verified window to 2024-Q1 through every layer — canonical 131,040 × 1m rows → derived 2,184 × 1h
and 91 × 1d bars → research table (feature set `btcusdt_core_v1`, budgets unchanged) →
validation folds (25 folds, `test_rows` 1824) — entirely through the unchanged integrity
protocol. Downstream modules are config-only; January's v1 chain stays byte-intact.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-26-data-slice-005-temporal-expansion-q1.md
and execute it exactly. Do not modify scope. Follow task order; each task
ends green with raw command output pasted before its commit. Report
COMPLETE / BLOCKED / INCOMPLETE at exit with full gate outputs.
```

## 3. Approved inputs

- Governing design above; behavioral requirements derive from it plus predecessor contracts.
- Identity: commits use `258711354+wyze69-sys@users.noreply.github.com`.
- Legal posture: v2 rights record only; all exercised operations already approved;
  network confined to the integration-marked module and `data.binance.vision`.
- Stack: unchanged pins; no new runtime dependencies.
- Starting facts: HEAD three-way synced; offline suite 464 green; integration 8 green; January
  chain retained under `data/datasets/binance/usdm/...` with research commit lineage base
  `702dab9f…`; validation store currently holds two retained commits (`d7581e4d…` superseded,
  `16665116…` current).

## 4. Observed starting state

- Branch `main` == `origin/main`, tree clean, HEAD `0d661988c826a21ce2081cd6888da8882c07f727`.
- Reuse unmodified: `expected_row_count` calendar arithmetic (`descriptor.py`); archive URL /
  checksum / member-pattern templates (`descriptor.py:73-77`); `_validate_urls` comparison
  pattern; `read_canonical_rows`, `PARQUET_SCHEMA`, `WRITER_CONFIG` (`canonical.py`);
  aggregation/derive/research/validation pipelines and their descriptors; truthful milestone and
  referenced-commit contracts; `store_object`, `stage_commit`, `publish_commit`,
  `verify_commit_graph`, `write_current` (`publication.py`).
- Frozen anchors: kline `schema_fingerprint()` = `feab7d2b…14c8`; v1 rights SHA `547fc79c…3697`;
  January research/validation artifacts byte-stable.
- **T0 placement note (investigate first, then commit):** the multi-archive loop, per-archive
  checksum gate, and concatenated assembly belong in whichever of `pipeline.py` / `archive.py` /
  `aggregation.py` owns row assembly — inspect before T3 and keep edits inside the allowlist.
  Concatenated-row invariants (design §4.1–§4.3) are checked pre-publication.

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
configs/datasets/binance-usdm-btcusdt-1m-2024-q1.yaml                  # descriptor v2, months [2024-01,2024-02,2024-03]
configs/datasets/binance-usdm-btcusdt-1h-2024-q1-derived.yaml          # period spans Q1, parent = q1 1m dataset id
configs/datasets/binance-usdm-btcusdt-1d-2024-q1-derived.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-q1-research-core-v1.yaml # feature set btcusdt_core_v1 unchanged
configs/datasets/binance-usdm-btcusdt-1h-2024-q1-validation-wf-v1.yaml # parameters {72,336} unchanged, embargo derived
src/quantara/descriptor.py    # modified: additive v2 loader branch (months list); v1 path byte-compatible
src/quantara/hashing.py       # modified: additive fingerprint binding for v2 month lists only
src/quantara/archive.py       # modified: reusable single-month fetch+verify helper if needed
src/quantara/pipeline.py      # modified: v2 multi-archive acquire + chronological concat + §4 invariant checks
src/quantara/cli.py           # modified: route base descriptor v1 and v2 through run_pipeline
src/quantara/derive_pipeline.py # modified: authenticate v2 parents with month-bound range fingerprint; preserve v1 identity
tests/conftest.py             # modified: additive synthetic two-month builder helpers
tests/test_descriptor.py      # modified: additive v2 matrix cases
tests/test_pipeline_multi_month.py
tests/test_derive_pipeline.py # modified: v1/v2 parent-fingerprint regression
tests/test_recovery.py        # modified: additive second-archive corruption cases
tests/test_integration_q1.py  # marked integration, serial, networked
tests/test_validation_pipeline.py # modified: make recovery regression xdist-independent
tests/test_integration.py     # modified: assert retained-commit stability on rerun
tests/test_integration_research.py # modified: assert retained-commit stability on rerun
README.md                     # modified: one appended short section "## Q1 2024 expansion status"
```

### 5.2 Forbidden changes

- No edits to: `research_*`, `validation_*`, `features.py`, `folds.py`,
  `fold_stats.py`, `publication.py`, `manifests.py`, `errors.py`, `canonical.py`, `jcs.py`
  beyond the allowlist; existing v1 configs or their published artifacts; existing specs/plans
  except this recorded scope amendment; `.github/**`; `.gitignore`.
- No modification of existing tests except the additive cases explicitly listed in §5.1;
  kline v1 fingerprint, v1 rights SHA, and all predecessor hash outputs byte-for-byte stable.
- No training/model/search code; no new instruments/intervals beyond configured Q1 set; no
  force-push; `/data/` never tracked; network confined to the integration-marked module.

### 5.3 Scope amendment — T7 preflight blocker (2026-08-26)

Codex correctly stopped before T7 because the original allowlist omitted two required
integration surfaces. `cli.py` recognized only base descriptor v1, and
`derive_pipeline.py` authenticated a retained parent using the v1-only fingerprint call.
The plan author's “downstream modules are config-only” assumption was therefore false.
The narrowly approved repair adds `cli.py`, `derive_pipeline.py`, and the two regression-test
files named in §5.1: v2 dispatch routes through the existing base pipeline, while parent
authentication selects the frozen legacy fingerprint for v1 and the ordered-month-bound
fingerprint for v2. No derived artifact schema or transformation behavior changes.

### 5.4 Scope amendment — final parallel-gate blocker (2026-08-27)

The required default-xdist gate exposed a pre-existing order dependency in
`test_lost_pointer_recovery_reports_truthful_milestones`: it assumed another test had already
published `current.json` on the same worker. Default xdist scheduling provides no such guarantee.
The narrowly approved repair adds `tests/test_validation_pipeline.py` to §5.1 and makes only that
recovery regression self-contained by publishing its prerequisite before simulating pointer loss.
Production behavior, scheduling policy, and acceptance semantics remain unchanged.

### 5.5 Scope amendment — evolved-store integration assertions (2026-08-27)

The final serial integration gate exposed two pre-existing tests that equated idempotency with a
fresh-store history of exactly one commit. Slice 004 legitimately retained superseded immutable
January commits, so those assertions reject a healthy evolved store. The narrowly approved repair
adds `tests/test_integration.py` and `tests/test_integration_research.py` to §5.1 and changes only
their rerun checks to compare the retained commit-name set before and after the no-op invocation.
Pointer and current-commit byte stability checks remain intact; production code is unchanged.

## 6. Tasks (each red→green with raw gate output pasted before its commit)

- **T0 Investigation note** — one-paragraph statement of where the multi-archive loop and
  concatenation live and why; posted before T1's commit, no code.
- **T1 Descriptor v2** — additive loader branch: schema `quantara.dataset-descriptor/v2`;
  ordered non-empty unique `months` list of `YYYY-MM` strings; period must equal the union of
  month calendars exactly; URLs/member patterns derived from templates; v1 loading untouched.
  Commit `feat(descriptor): multi-month range datasets v2`.
- **T2 Hashing** — v2 identity binds the ordered month list via a dedicated domain; v1 outputs
  byte-unchanged. Commit `feat(hashing): range dataset identity`.
- **T3 Acquisition + concatenation** — fetch/verify ALL archives before parsing; chronological
  concat; design §4.1–§4.5 invariants enforced pre-publication; failure in any month blocks the
  whole dataset. Commit `feat(pipeline): verified multi-month acquisition`.
- **T4 Multi-month unit/property suite** — synthetic two-month fixtures: clean seam passes;
  gapped seam BLOCKED; duplicated bar BLOCKED; segment accounting mismatch BLOCKED; identity
  distinctness across month sets. Commit `test(pipeline): multi-month seam invariants`.
- **T5 Recovery additions** — second-archive checksum corruption and parse failure → blocked/
  failed pre-publication, staging cleaned, no partial commit; healthy rerun publishes. Commit
  `test(recovery): multi-archive corruption scenarios`.
- **T6 Config files** — the five q1 YAMLs verbatim-consistent with design §5 ids/periods.
  Offline dry-run parity for each against synthetic stores where possible. Commit
  `feat(configs): 2024-Q1 dataset descriptors`.
- **T7 Integration end-to-end** — `-m integration`, serial, networked: acquire real Q1 archives
  → normalize → derive 1h/1d → research → validation via CLI; assert design §5 acceptance
  numbers at every layer; January v1 tree digest unchanged; per-layer rerun `VERIFIED_NO_OP`
  byte-identical; 1d validation BLOCKED undersized. Commit
  `test(integration): q1 chain acceptance`.
- **T8 Docs** — README appended section "## Q1 2024 expansion status" (window, numbers,
  internal-use posture). Final gates below. Commit `docs(readme): q1 expansion status`.

## 7. Acceptance numbers (design §5)

Canonical 131,040 · derived 1h 2,184 · derived 1d 91 · research 2,184 rows with budgets
{1,60,20,19} head and {24,24} tail · validation first-test-start 360, folds 25, test lengths
72×24 then 96, `test_rows` 1824, `excluded_head_rows` 360.

## 8. Completion states

- **COMPLETE:** all tasks green with pasted evidence; integration publishes the full q1 chain
  with §7 numbers; January chain provably untouched; reruns idempotent; docs lint-clean; pushed
  once; three-way sync verified.
- **BLOCKED:** repository drift; rights gate closed; archive unavailability/checksum failure on
  data.binance.vision; environment failure; owner declines before execution.
- **INCOMPLETE:** any seam invariant, all-or-nothing guarantee, identity binding, v1-compat
  requirement, milestone-truthfulness rule, or documentation requirement unsatisfied.

**Final gates:** offline serial `uv run pytest -m "not integration"` exit 0; parallel
`uv run pytest -n 4 -m "not integration"` exit 0; integration serial `uv run pytest -m
integration` exit 0; `uv run ruff check .`; `uv lock --check` unchanged; markdownlint clean on
new/changed doc lines; changed-vs-origin ⊆ §5.1 allowlist; `git ls-files data` empty; frozen
anchors byte-identical.

**Known risks:** February leap-day arithmetic is covered by fixtures so calendar math never
becomes an implicit tolerance; Binance Vision archive layout changes would surface as checksum
failures (fail-closed by design).
