# Quantara Data Slice 010 — Temporal Expansion 2024 Full-Year Implementation Plan

**Status:** Proposed implementation plan; awaiting owner review before execution
**Date:** 2026-08-28
**Project root:** `D:\PROJECT\Quantara`
**Sequencing:** Follows Slice 009 (Rust Q18 rendering, pushed `ca68589`). Repeats the proven Slice 005 range-expansion pattern: extend the verified window from 2024-Q1 to the full 2024 calendar year through every layer, reusing the existing v2 multi-month mechanism, fold engine, and evaluation machinery. The only structural work is generalizing the Q1-hardcoded acceptance contracts in the evaluation layer into an approved period-contract table (Q1 stays byte-identical).

## 1. Goal

Publish the full-year 2024 chain: canonical 527,040 × 1m rows (12 monthly archives) → derived 8,784 × 1h and 366 × 1d bars → research table (`btcusdt_core_v1`, budgets unchanged) → validation folds (117 folds, `test_rows` 8,424) → dual-IC feature evaluation — entirely through the unchanged integrity protocol. January's v1 chain and the Q1 chain stay byte-intact and retained; their frozen tests stay green unmodified.

Structural changes, exactly three:

1. **`descriptor.py`** — the v2 loader accepts a second approved identity table for the full-year range (`binance_usdm_btcusdt_klines_1m_2024`, months `2024-01`…`2024-12`). The months parser, period/union check, URL templates, and fingerprint month binding are already generic and untouched. Q1 loading stays byte-compatible.
2. **`evaluation_pipeline.py` + `evaluation_quality.py`** — replace the single hardcoded Q1 contract (`APPROVED_Q1_PERIOD`, `Q1_START/END_EPOCH_MS`, `2184`, `25` folds) with an approved contract table keyed by the validation parent's half-open period: Q1 `{2184 rows, 25 folds}` and 2024 `{8784 rows, 117 folds}`. A parent matching neither contract BLOCKs with a clear message. Existing Q1 message strings and behavior must remain byte-identical so every existing evaluation test passes unmodified.
3. **Six new config YAMLs** for the year range, plus additive tests and one new serial networked integration module mirroring `tests/test_integration_q1.py`.

Non-goals: no new instruments/intervals/timeframes; no changes to features, labels, fold parameters (`{72, 336, 24}`), evaluation metrics, or the fold/research/validation pipelines (verified generic — see §4); no training/model code; no Rust kernel changes; no new dependencies; no rights-record amendment (all exercised operations already approved under the v2 record).

## 2. Required execution prompt

```text
Work in D:\PROJECT\Quantara.

Write this entire document verbatim to
docs/superpowers/plans/2026-08-28-data-slice-010-temporal-expansion-2024.md,
commit it exactly as Task T0 requires, then read that committed file completely and
execute it exactly.

Follow T0 through T6 in order. Use focused red-to-green TDD, preserve every forbidden
scope boundary, fix task-related failures before continuing, run the final gates once
on the final unchanged state, and report COMPLETE, BLOCKED, or INCOMPLETE with raw
commands and results. Do not push until every required gate passes. Then STOP.
```

The prompt is agent-independent. Codex CLI, OpenCode, or another filesystem-and-terminal coding agent may execute it without changing the plan contract.

## 3. Approved inputs and fixed contracts

- **Identity:** all commits use `258711354+wyze69-sys@users.noreply.github.com` (verify with `git config user.email` in T0).
- **Legal posture:** v2 rights record only (`configs/legal/binance-usdm-provider-rights.v2.yaml`); every exercised operation (acquire, retain, normalize_internal, analyze_internal) is already approved. Network confined to the integration-marked module and `data.binance.vision`.
- **Stack:** unchanged pins; no new runtime dependencies; `uv.lock`, `pyproject.toml`, `kernel/` untouched.
- **Download budget (owner-approved, one-time):** 9 new monthly zips (2024-04 … 2024-12), each ≈ 1.5–2 MB compressed ⇒ ≈ 15–20 MB total from `data.binance.vision`. No other network use.
- **Starting state (hard gate):** HEAD == `origin/main` == `ca68589698dd7251b5995963984b0912c43c246c`, tree clean, `git ls-files data` empty, `git status --ignored --short data` shows `!! data/`. Offline suite baseline 646 passed; integration baseline 11 passed. Any other state: report `BLOCKED` (probable drift — do not repair).

**Frozen anchors (regression evidence, captured at the starting HEAD):**

- kline v1 no-arg `schema_fingerprint()` == `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8`
- Q1 v2 range fingerprint `schema_fingerprint("binance_usdm_kline_1m_v1", months=["2024-01","2024-02","2024-03"])` == `125c9e3f016826c40dae097965bfcafa39475af2c2d86cc6bbebb2d3a91b6f9f` — must stay byte-identical
- **New year anchor** `schema_fingerprint("binance_usdm_kline_1m_v1", months=["2024-01",…,"2024-12"])` == `f0d6a8dd92a1a4f1dcf29c4f9222c4ec7daa75a2e648ead6b4bfa453d347724a` (computed with the real function at the starting HEAD; the year publication must bind exactly this)
- Q1 descriptor `canonical_semantics()` SHA-256 == `8079498831e6033e1e04e5006c625b3651c3d6c7d492c7a9511949f0d97dee9a` — byte-identical after the loader change
- Fold arithmetic (real `build_walkforward_folds` outputs):
  - Year, n=8784, {72, 336, 24}: **117 folds**, `test_rows` **8424**, `excluded_head_rows` **360**, first test `(360, 432)`, last test `(8712, 8784)`, first train `(0, 336)`
  - Q1 regression, n=2184: 25 folds, `test_rows` 1824, `excluded_head_rows` 360
- Resting store pointers at start (the year integration test must restore these byte-exactly — snapshot them itself, do not trust this list alone):

```text
klines/BTCUSDT/1m       9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f   (2 retained commits)
klines/BTCUSDT/1h       702dab9f66b9d7181458916324ce906020d6415709b4189b395b1378b6b9e271   (3 retained)
klines/BTCUSDT/1d       2d09178f767dc563306359db8a31d96d7d00c90890ffd78635ffd94db35a02bf   (3 retained)
research/BTCUSDT/1h     cb9079eab9e1f7237d736f5f5021270fd0c8dc176a5ee37d5fdd38ac9977c548   (2 retained)
validation/BTCUSDT/1h   166651165729ec3cda1cc48967e45eace09dc6a9b078a3e619efc9af15b3a410   (3 retained)
evaluation/BTCUSDT/1h   d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675   (1 retained)
```

## 4. Observed repository seams to reuse (verified at `ca68589`)

- **`descriptor.py`** — v2 branch: `_parse_months` (line 260) validates ordered unique consecutive `YYYY-MM` covering exactly `[start, end)`; URLs/member patterns derived from templates per month; `V2_APPROVED_IDENTITIES` (line 66) pins `dataset_id: binance_usdm_btcusdt_klines_1m_2024_q1`; identity check loops `for field, approved in approved_identities.items()` (line 313). The change adds a second v2 identity table (`…_2024`) and validates the document matches exactly one of the two tables. `canonical_semantics()` (line 161) serializes `months` from the document — generic.
- **`hashing.py`** — `schema_fingerprint(schema_version, months)` (line 147) binds the ordered month list under `RANGE_SCHEMA_FINGERPRINT_DOMAIN`. **No change needed.**
- **`folds.py`** — pure engine, parameterized. **No change.**
- **`pipeline.py` / `derive_pipeline.py` / `research_pipeline.py` / `validation_pipeline.py`** — verified generic: no `2184`/`Q1`/period hardcodes; lane paths derive `year=%Y/month=%m` from the descriptor start (January start ⇒ same `month=01` lane; the year dataset publishes a new commit into the existing lane exactly like Q1 did alongside January).
- **`evaluation_pipeline.py`** — Q1 hardcodes to generalize: `APPROVED_Q1_PERIOD` / `Q1_START_EPOCH_MS` / `Q1_END_EXCLUSIVE_EPOCH_MS` (lines 90–96), `verify_validation_parent_q1_period` (line 106), `val_parent_rows != 2184` (line 507), `len(folds) != 25` (line 139), fold-set literal (line 509), `len(research_rows) != 2184` (line 694), Q1 period messages (lines 123, 722, 741).
- **`evaluation_quality.py`** — `parent_rows == n_rows == 2184` and hourly cadence gated on `2184` (lines 279–286): parameterize via the same contract table.
- **`evaluation_descriptor.py`** — verified generic (period must equal parent period; dataset_id derived from `base_dataset_id`; `EVALUATION_SET` name `btcusdt_core_v1_dual_ic_v1` reused). **No change.**
- **`validation_descriptor.py`** — `FOLD_SET_NAME = "btcusdt_core_v1_wf72_v1"` reused for the year config (same scheme + parameters ⇒ same fold-set identity; the parent is authenticated separately). **No change.**
- **`cli.py`** — dispatches on schema; v2 base descriptors already route through `run_pipeline`. **No change.**
- **`tests/conftest.py`** — `write_range_month_csv` / range descriptor builders to extend additively for year-shaped synthetic fixtures.
- **`tests/test_integration_q1.py`** — the template for the year integration module: snapshot pointers, run the CLI chain, pin acceptance numbers, prove idempotent reruns (`VERIFIED_NO_OP`, byte-identical pointers and retained-commit sets), restore pre-test pointers in `finally`, keep published commits retained.
- **T0 investigation note (mandatory before T1):** run `grep -rn "2184\|Q1\|2024-04-01\|1711929600000\|2024_q1" src/quantara/` and confirm every hit is inside the §5.2 modified-file set (`descriptor.py`, `evaluation_pipeline.py`, `evaluation_quality.py`, docstrings included). Any hit outside it (excluding `__pycache__`) is a scope blocker: report `BLOCKED` with the exact hit — do not silently widen scope.

## 5. Exact file allowlist

Implementation changes must remain a subset of this list.

### 5.1 New files

```text
docs/superpowers/plans/2026-08-28-data-slice-010-temporal-expansion-2024.md   (T0 only)
configs/datasets/binance-usdm-btcusdt-1m-2024.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-derived.yaml
configs/datasets/binance-usdm-btcusdt-1d-2024-derived.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-research-core-v1.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-evaluation-dual-ic-v1.yaml
tests/test_integration_year.py
```

### 5.2 Modified files (exact purposes)

```text
src/quantara/descriptor.py        — second v2 approved-identity table for the year range; Q1 byte-compat (T1)
src/quantara/evaluation_pipeline.py — approved period-contract table {Q1, 2024}; period/rows/folds gates read it; Q1 messages byte-identical (T2)
src/quantara/evaluation_quality.py — parent-rows/cadence contract parameterized from the same table (T2)
tests/conftest.py                 — additive year-shaped synthetic builders (T3)
tests/test_descriptor.py          — additive: year descriptor loads; non-approved range id rejected (T1)
tests/test_evaluation_pipeline.py — additive: year contract accepted; wrong-period/wrong-rows/wrong-folds BLOCKED; Q1 regression unchanged (T2)
tests/test_evaluation_quality.py  — additive: year rows/cadence quality contract (T2)
tests/test_folds.py               — additive: year acceptance numbers n=8784 (T3)
README.md                         — appended short section "## 2024 full-year expansion status" (T6)
```

No other file may change, including `hashing.py`, `folds.py`, `canonical.py`, `pipeline.py`, `derive_pipeline.py`, `research_pipeline.py`, `validation_pipeline.py`, `research_descriptor.py`, `validation_descriptor.py`, `evaluation_descriptor.py`, `cli.py`, `publication.py`, `manifests.py`, `fold_stats.py`, `jcs.py`, `kernel/**`, any existing config YAML, any existing test file beyond the additive cases listed, `pyproject.toml`, `uv.lock`, and anything under `data/`.

### 5.3 Forbidden changes

- No weakening, deletion, or reclassification of any existing test, fixture, or frozen anchor; existing tests must pass **unmodified** (the Q1 message-string constraint in §3 is exactly what guarantees this).
- No new dependencies; no changes to fold parameters, feature/label definitions, metrics, thresholds, or quality policy.
- No writes inside `data/` except through the pipelines themselves; `git ls-files data` stays empty; `kernel/target/` never committed.
- No force-push, history rewrite, or `git add .`; stage only allowlisted files.
- Network only inside the integration-marked module against `data.binance.vision`.

## 6. Tasks (execute in order; each ends with one conventional commit)

### T0 — Preflight and plan commit

Verify and paste outputs: `git rev-parse HEAD origin/main` (equal, `ca68589…`), `git status --short --branch` (clean), `git config user.email` (noreply identity), `git ls-files data` (empty), `git status --ignored --short data` (`!! data/`), `uv run pytest --collect-only -q | tail -3` (recount: expect 657 items = 646 offline + 11 integration), and the §4 T0 grep with a one-paragraph analysis of every hit. Then write this document verbatim to `docs/superpowers/plans/2026-08-28-data-slice-010-temporal-expansion-2024.md` and commit **only that file**:

```text
docs(expansion): slice 010 temporal expansion 2024 plan
```

### T1 — Descriptor v2 year identity (red → green)

Add the year approved-identity table (`dataset_id: binance_usdm_btcusdt_klines_1m_2024`) to the v2 loader branch; the document must match exactly one v2 identity table; months parsing, templates, and `canonical_semantics()` untouched. RED first: `uv run pytest tests/test_descriptor.py -k year` fails because the year config does not load. Add the two additive tests (loads with 12 months and period 2024-01-01→2025-01-01; unknown/missing range dataset_id rejected with the existing `_reject` style). GREEN: focused file passes. Regression: `uv run pytest tests/test_descriptor.py tests/test_pipeline_multi_month.py tests/test_golden.py -q` green.

```text
feat(descriptor): full-year 2024 range identity
```

### T2 — Evaluation period-contract generalization (red → green)

Replace the single-Q1 constants in `evaluation_pipeline.py` with an approved contract table (start/end epoch-ms, expected parent rows, expected fold count, period label) for Q1 and 2024; select by the validation parent descriptor's period; unknown period → existing BLOCKED path with a clear new message. Parameterize `evaluation_quality.py` row gates from the same table. **Q1 behavior byte-identical** — existing Q1 message strings are produced verbatim for Q1 parents. RED: new year-shaped synthetic tests fail (BLOCKED on year parent). Additive tests: year contract accepted end-to-end on synthetic fixtures; wrong-period parent BLOCKED; wrong rows/folds BLOCKED; Q1 regression test asserts the Q1 path is unchanged. GREEN: `uv run pytest tests/test_evaluation_pipeline.py tests/test_evaluation_quality.py tests/test_evaluation_descriptor.py -q` green (all pre-existing tests unmodified and passing).

```text
feat(evaluation): approved period contracts for 2024 ranges
```

### T3 — Year configs, folds acceptance, and builders (red → green)

Write the six §5.1 YAMLs: 1m base v2 with `months: ["2024-01"…"2024-12"]`, period `2024-01-01T00:00:00Z` → `2025-01-01T00:00:00Z`; 1h/1d derived (`base_dataset_id: binance_usdm_btcusdt_klines_1m_2024`); research core v1 (`btcusdt_core_v1`, parameters `{60, 20, 20, 24}` unchanged); validation wf v1 (`{test_size: 72, min_train_size: 336}`, fold set `btcusdt_core_v1_wf72_v1` reused); evaluation dual-ic v1 (features/target/metrics unchanged, `evaluation_set` name `btcusdt_core_v1_dual_ic_v1` reused). Add the `test_folds.py` year acceptance test (117 folds, 8424 test rows, 360 excluded head, boundary ranges from §3) and additive conftest year builders. Acceptance command (paste output):

```bash
uv run python -c "
from pathlib import Path
from quantara.descriptor import load_descriptor
from quantara.derive_descriptor import load_derived_descriptor
from quantara.research_descriptor import load_research_descriptor
from quantara.validation_descriptor import load_validation_descriptor
from quantara.evaluation_descriptor import load_evaluation_descriptor
base = load_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1m-2024.yaml'))
print('rows', base.expected_row_count, 'months', len(base.months))
print('derived 1h', load_derived_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1h-2024-derived.yaml')).dataset_id)
print('derived 1d', load_derived_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1d-2024-derived.yaml')).dataset_id)
print('research', load_research_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1h-2024-research-core-v1.yaml')).dataset_id)
print('validation', load_validation_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1h-2024-validation-wf-v1.yaml')).dataset_id)
print('evaluation', load_evaluation_descriptor(Path('configs/datasets/binance-usdm-btcusdt-1h-2024-evaluation-dual-ic-v1.yaml')).dataset_id)
"
# expected: rows 527040 months 12, then the five _2024... dataset ids
```

Also offline CLI dry-run of the base descriptor against a synthetic store (no network): exit code 0 or 2 with a clean BLOCKED reason, never a traceback.

```text
feat(configs): 2024 full-year dataset descriptors
```

### T4 — Investigation checkpoint (no commit)

Before the networked run: `grep -rn "2184\|25 folds\|Q1 2024" src/quantara/` must return only contract-table entries in the two modified evaluation files; re-run `uv run pytest -m "not integration" -n 4` in the background with completion notification and confirm the interim offline suite is green. Expected arithmetic: 646 baseline + 8 new additive offline tests (2 descriptor + 4 evaluation-pipeline + 1 evaluation-quality + 1 folds) = **654 passed**; if your new-test count differs, paste the exact arithmetic. This is a gate, not a commit.

### T5 — Year chain integration (serial, networked)

New `tests/test_integration_year.py` mirroring `test_integration_q1.py`: snapshot all six lane pointers; drive the full CLI chain (1m acquire/normalize → 1h/1d derive → research → validation → evaluation) under `data/`; assert every §7 acceptance number; assert the year range fingerprint is exactly `f0d6a8dd…347724a`; prove idempotent rerun per layer (`VERIFIED_NO_OP`, byte-identical pointers and retained-commit sets); assert 1d validation is BLOCKED undersized (366 < 432 minimum); assert January and Q1 retained commits byte-untouched; restore pre-test pointers in `finally`; year commits remain retained. Run:

```bash
uv run pytest tests/test_integration_year.py -m integration -q   # serial, networked
# then the full serial integration suite:
uv run pytest -m integration -q                                    # expect 12 passed
```

```text
test(integration): 2024 year chain acceptance
```

### T6 — README status, final gates, push

Append a short `## 2024 full-year expansion status` section (window, acceptance numbers, internal-use posture — mirror the Q1 section's length and tone). Final gates once, on the final unchanged state, as a fail-fast chain:

```bash
set -o pipefail && uv lock --check && uv run ruff check . \
  && uv run pytest -m "not integration" -n 4 --dist=load -q \
  && uv run pytest -m integration -q
# expected: lock ok; ruff clean; 654 passed (646 baseline + 8 new); 12 passed
```

Markdown-lint the changed README lines (out-of-repo `markdownlint-cli2@0.23.2` with `{"config":{"MD013":false}}` via explicit `--config`; expect 0 issues; delete the config afterward). Verify `git diff --stat origin/main..HEAD` ⊆ §5.1 allowlist, frozen anchors byte-identical, `git ls-files data` empty. Then push once:

```bash
git push origin main
git rev-parse HEAD origin/main     # equal
git status --short --branch        # clean and synced
```

```text
docs(readme): 2024 full-year expansion status
```

## 7. Acceptance numbers (frozen)

- Canonical 1m: **527,040 rows** (366 days × 1440; 2024 is a leap year)
- Derived 1h: **8,784 bars**; derived 1d: **366 bars**
- Research: **8,784 rows**, budgets `{1, 60, 20, 19}` head and `{24, 24}` tail unchanged
- Validation: first-test-start **360**, **117 folds**, `test_rows` **8,424**, `excluded_head_rows` **360**, last test `(8712, 8784)`
- Evaluation: dual-IC over the 8,784-row parent, 117 folds, metrics `pearson_ic` / `spearman_ic` unchanged
- 1d validation attempt: BLOCKED undersized (366 < 432)

## 8. Failure handling

- Wrong starting HEAD, drifted `origin/main`, failing T0 recount, or a §4 grep hit outside the modified-file set: report `BLOCKED` with exact outputs; do not repair prior slices or silently widen scope.
- Fix task-related failures inside the same bounded task and rerun the affected focused tests; never weaken a test, threshold, or lint rule to go green.
- Archive unavailability / checksum mismatch on `data.binance.vision` is fail-closed by design: report `BLOCKED` with the failing URL.
- Windows: launch the ~13-minute offline gate as a background job with completion notification (the 600 s foreground cap kills it); after any timeout, inspect process command lines and terminate only confirmed test orphans.
- An honest miss on any acceptance number is `INCOMPLETE`, never an amendment.

## 9. Final evidence report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

- Starting HEAD, plan-commit SHA, ending HEAD; `git status --short --branch` at the end; the single push result and three-way sync proof.
- Per-task red→green evidence: acceptance commands and raw terminal outputs (paste output, never prose claims).
- The §4 T0 grep analysis; the T3 config-load output; the T4 interim suite arithmetic.
- Integration evidence: per-layer terminal results, the six restored pointer bytes, retained-commit counts per lane before/after, the year fingerprint assertion, and the idempotent rerun outputs.
- Final gate raw outputs: lock, ruff, offline parallel summary line, serial integration summary line, markdownlint result, allowlist diff check.
- The commit list (`git log --oneline ca68589..HEAD`) with conventional messages.
- Any residual limitations or accepted deviations.
