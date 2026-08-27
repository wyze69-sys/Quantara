# Quantara Native-Kernel Slice 009 — Rust Q18 Decimal Rendering Implementation Plan

**Status:** Proposed implementation plan; awaiting owner review before execution
**Date:** 2026-08-28
**Project root:** `D:\PROJECT\Quantara`
**Sequencing:** Authorized on Slice 008's honest `INCOMPLETE`-per-policy verdict (all correctness gates green; push correctly withheld because the frozen `content_hash` stage ratio was 0.6204 / 0.6249 against the required ≤ 0.35). Slice 008's own non-goals pre-authorized exactly this follow-up: *"no Rust port of `render_decimal_18` or `CanonicalRow.to_content_array` (Q18 rendering happens upstream of the hash boundary — rows arrive as str/int/bool only; a decimal-math port is a later slice gated on fresh profiling)"* — and Slice 008's boundary decomposition IS that fresh profiling: at 44,640 rows the `content_hash` stage is ~12.36 s ≈ 8.01 s of `to_content_array()` rendering (8 `render_decimal_18` calls per row) + ~4.11 s hashing, while the 008 kernel hashes prebuilt arrays in 0.270–0.285 s. Slice 008's four unpushed commits are the frozen base of this slice; the single push at the end lands both slices together once the frozen gate passes.
**Governing policy:** This plan is self-contained. It authorizes exactly one bounded extension of the existing Rust kernel: a native `render_decimal_18` behind the existing dispatch, with the Python body retained verbatim as the differential oracle. It does not authorize touching the frozen benchmark harness, `canonical.py`, any pipeline module, any validator/fingerprint/domain constant, or any threshold. The ≤ 35% retention threshold frozen in Slice 008 is **not amended** — this slice exists to meet it.

## 1. Goal

Slice 008 proved the Rust hash kernel 14–15× faster than Python on prebuilt row arrays, but the frozen `content_hash` benchmark stage times `(row.to_content_array() for row in assembled)` end to end, and the Python Q18 renderer inside that generator dominates the stage. This slice ports that one function — `render_decimal_18` in `src/quantara/hashing.py` — into the existing `quantara_kernel` crate behind the existing `QUANTARA_HASH_KERNEL` dispatch:

1. **`quantara_kernel.render_decimal_18`** — a new `#[pyfunction]` in `kernel/src/lib.rs` accepting a `decimal.Decimal` or `str`, reproducing the exact-or-raise Q18 rendering contract byte-for-byte (same outputs, same exception types, same messages), using only digit-string arithmetic (no new crates, no `f32`/`f64`, no bignum dependencies).
2. **Dispatch with retained oracle** — the public `render_decimal_18` in `src/quantara/hashing.py` becomes the dispatch point exactly mirroring the 008 pattern; the current body moves verbatim to `_render_decimal_18_python` and remains the forced-Python mode and differential oracle. Every production caller (`canonical.py` `to_content_array` 8×/row, `reconcile_rows`, `reconcile_parquet`, `fold_stats.py:166-168`, `research_pipeline.py:234`, `validation_pipeline.py:153`) picks up the kernel automatically with zero call-site changes.
3. **Differential proof at every level** — kernel vs Python equality over the existing golden corpus, a 2,000-value seeded randomized battery (both input forms), end-to-end `CanonicalRow` digest equality, and byte-identical error parity for rejects, special values, and malformed strings. Because `auto` is the default, the entire existing offline suite (635 tests post-008) — including `tests/test_hashing.py`'s `test_render_decimal_18_exact` (parametrized over both `str` and `Decimal` inputs), `test_render_decimal_18_never_rounds`, and `test_render_decimal_18_ignores_hostile_ambient_context` — executes through the kernel and becomes the differential oracle.
4. **The frozen gate finally passes** — with rendering native, the `content_hash` stage is expected at roughly 0.6–1.5 s vs Python's ~12.36 s at 44,640 rows (ratio ≈ 0.05–0.12; estimates are non-acceptance evidence), comfortably under the frozen ≤ 0.35 threshold at both scales, which unblocks the single combined push of slices 008 + 009.

Non-goals: no port of `CanonicalRow.to_content_array` itself or of CSV parsing, aggregation, features, folds, or evaluation (Python list assembly per row stays); no changes to `canonical.py`, the benchmark harness, any pipeline module, `jcs.py`, or any schema/fingerprint/domain constant; no new dependencies of any kind; no threshold amendments; no CI, wheel publishing, or README changes.

## 2. Required execution prompt

```text
Work in D:\PROJECT\Quantara.

Write this entire document verbatim to
docs/superpowers/plans/2026-08-28-native-kernel-slice-009-rust-q18-rendering.md,
commit it exactly as Task T0 requires, then read that committed file completely and
execute it exactly.

Follow T0 through T3 in order. Use focused red-to-green TDD, preserve every forbidden
scope boundary, fix task-related failures before continuing, run the final gates once
on the final unchanged state, and report COMPLETE, BLOCKED, or INCOMPLETE with raw
commands and results. Do not push until every required gate passes. Then STOP.
```

The prompt is agent-independent. Codex CLI, OpenCode, or another filesystem-and-terminal coding agent may execute it without changing the plan contract.

## 3. Approved inputs and fixed contracts

- **Toolchain prerequisite (hard gate):** `cargo --version` and `rustc --version` must succeed and the MSVC linker must be present (target `x86_64-pc-windows-msvc`). On this machine cargo is off PATH: `export PATH="$HOME/.cargo/bin:$PATH"` first. The toolchain is installed and verified (cargo 1.98.0 / rustc 1.98.0, VS Build Tools 17.14 with VCTools 14.44 + Win SDK 10.0.19041, and a PyO3 0.23 + maturin release build proven working on 2026-08-27) — do not install or update anything. If broken, report `BLOCKED` with exact outputs.
- **Slice 008 base state (hard gate):** starting HEAD must be `2364d8040d9527a0eea1a0f32e06f9e8bef43af7` with `origin/main` at `d2296bf133976a2fbbe98f655046e79caceda98e` (intentionally 4 ahead — 008 correctly withheld its push), tree clean, and the four 008 commits present: `docs: add native-kernel slice 008 implementation plan`, `feat(kernel): scaffold rust canonical-hash crate`, `feat(kernel): rust canonical and research content-hash with python dispatch`, `test(kernel): adversarial parity battery for rust hash kernel`. All 18 existing kernel tests must pass. Any other state: report `BLOCKED` (probable drift — do not repair).
- **No dependency additions.** `kernel/Cargo.toml`, `Cargo.lock`, root `pyproject.toml`, and `uv.lock` must not change. The renderer is pure digit-string arithmetic over `std` only — no `rust_decimal`, no `num-bigint`, no `serde_json`.
- **The `render_decimal_18` contract (frozen; the kernel must reproduce it byte-for-byte).** Current body: `src/quantara/hashing.py:187-216`. Semantics:
  1. Input is `Decimal | str`. A `str` is parsed exactly as `Decimal(str(value))` would parse it — the CPython decimal-string grammar. Probe the oracle for lexical corners (surrounding whitespace, underscores between digits, case-insensitive `Inf`/`Infinity`/`NaN`/`sNaN`, optional `+` sign, leading `.` and trailing `.` forms, e-notation) and match whatever it does; malformed strings raise `decimal.InvalidOperation` exactly as the oracle does.
  2. Trailing coefficient zeros are insignificant for representability (the private-context `normalize` strips them first): `"0.1000000000000000000"` has 19 fractional digits but renders as `"0.100000000000000000"`.
  3. Any value needing more than 18 fractional digits after trailing-zero removal raises `HashPayloadError` (error id `manifest_inconsistency`) with the byte-identical message `decimal {number} exceeds 18 fractional digits; rounding is forbidden`, where `{number}` is `str()` of the parsed `Decimal` — CPython `str(Decimal)` rules: fixed notation when exponent ≤ 0 and adjusted exponent ≥ −6, otherwise scientific (`decimal 1E-19 exceeds …`). For `Decimal` inputs obtain this form via one `str()` call on the object; for `str` inputs re-render the parsed value through the same rules.
  4. Output: the exact integer magnitude `coefficient × 10^(exponent+18)` as sign + digits left-padded to ≥ 19 + split at the last 18 digits. `"-"` only when the magnitude is negative; negative zero renders unsigned `"0.000000000000000000"`. Never convert the magnitude to a machine integer — coefficient digit string plus `(exponent+18)` appended zeros avoids overflow for 40-digit coefficients with large exponents.
  5. Special values (`Infinity`, `-Infinity`, `NaN`, `sNaN`) and malformed strings: whatever exception type and message the Python oracle produces, the kernel must produce identically. Capture oracle behavior by running the Python path first and pin it in the tests — never guess. Non-`KernelHashPayloadError` exceptions (e.g. whatever `int(Decimal("Infinity"))` raises) must surface as the same Python exception class with the same message, unwrapped.
  6. Ambient `decimal` context is never read or mutated in either mode (existing test `test_render_decimal_18_ignores_hostile_ambient_context` must stay green — after this slice it runs through the kernel).
- **Dispatch contract:** same environment variable, helpers, and semantics as 008 — `QUANTARA_HASH_KERNEL` ∈ `rust`/`python`/`auto`, default `auto`, read at call time, unknown values fall back to `auto`, explicit `rust` with the kernel missing raises `RuntimeError` — via the existing `_use_rust_kernel()` / `active_hash_kernel()` helpers (`hashing.py:112-135`). `KernelHashPayloadError` is caught and re-raised as `HashPayloadError(str(exc)) from exc` exactly like the 008 dispatch block (`hashing.py:254-257`).
- **Kernel-reachable inputs:** only `Decimal` or `str` instances cross the boundary (the Python dispatch guards with `isinstance`); other types always route to the Python oracle, so their behavior is identical by construction (accepted boundary deviation, mirroring 008 §3).
- **Frozen anchors that must still hold at the end (asserted by existing tests — do not weaken):**
  - `schema_fingerprint()` == `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8` (`tests/test_golden.py`)
  - golden `canonical_content_hash` == `8f78cd55e6ada9539a5e88c4debcdea05cab7d7c1c5adb3d43944ef3d290feab` (`tests/test_golden.py`), now produced through kernel rendering + kernel hashing in default mode
  - the real-data January 2024 parent identity starting `9d7eee74…` (`tests/test_integration_derivation.py`), executed through the kernel by the integration gate
- **Benchmark gate (frozen from Slice 008 — this slice meets it, never amends it):** `content_hash` stage `seconds_median` in rust mode ≤ **35%** of python mode at **both** 44,640 and 200,000 rows; `content_hash` `tracemalloc_peak_bytes` in rust mode ≤ 110% of python mode; no stage's `seconds_median` regresses by more than 15% versus the T0 baseline at either scale. Wall-clock numbers other than these ratios are non-acceptance evidence.

## 4. Observed repository seams to reuse

Verified against the current source at HEAD `2364d80`; cite them rather than inventing APIs.

### 4.1 The port target (`src/quantara/hashing.py`)

- `render_decimal_18(value: Decimal | str) -> str` (lines 187-216): `number = value if isinstance(value, Decimal) else Decimal(str(value))`; private `Context(prec=max(len(digits), 60)+4, ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN, traps=[])`; `normalize` → `scaleb(Decimal(18))` → `to_integral_value`; if `scaled != integral` raise `HashPayloadError(f"decimal {number} exceeds 18 fractional digits; rounding is forbidden")`; else `int(integral)`, sign only when negative, `str(abs(magnitude)).rjust(19, "0")` split at the last 18 digits. This body moves verbatim to `_render_decimal_18_python`.
- Dispatch helpers already present from 008: `_kernel_mode()`, `active_hash_kernel()`, `_use_rust_kernel()` (lines 112-135); guarded module import `_quantara_kernel` / `_KERNEL_AVAILABLE` (lines 19-27); catch-rewrap pattern (lines 254-257).
- Production callers (all pass `Decimal`; none pass `str`): `canonical.py` imports it at line 19 and calls it 8× per row inside `CanonicalRow.to_content_array` (lines 63-71), plus `reconcile_rows` (line 282) and `reconcile_parquet` (line 331) rendering Parquet-read-back Decimals; `fold_stats.py:166-168`; `research_pipeline.py:234`; `validation_pipeline.py:153`. None of these files change.

### 4.2 The frozen benchmark harness (committed by 007, extended gate evidence by 008 — do not modify)

- `benchmarks/stage_baseline.py:222-228`: the `content_hash` stage calls `hashing.canonical_content_hash(fingerprint, (row.to_content_array() for row in assembled))` exactly as production does — the render dispatch is picked up automatically with no harness edit; `QUANTARA_HASH_KERNEL` toggles modes between runs. The corpus includes full-precision 18-fractional-digit prices every 97th row and 2–3-digit volumes otherwise (`_price_text`, lines 62-65), so both render paths are exercised at scale.

### 4.3 The kernel (`kernel/src/lib.rs`)

- Registers `hash_canonical_rows`, `hash_research_rows`, `module_version` in `#[pymodule]` (lines 206-208) and exposes `KernelHashPayloadError`, `CONTENT_HASH_DOMAIN`, `RESEARCH_CONTENT_HASH_DOMAIN`. Add `render_decimal_18` alongside them; splitting helpers into `kernel/src/*.rs` submodules is permitted (008 allowlist precedent).
- After every `kernel/src` edit, rebuild with `uv sync` before rerunning tests (release profile; each incremental rebuild is ~1–2 min). Verify the installed `.pyd` matches `kernel/target/release/` if a near-miss on the speed gate appears (008 lesson: a debug-profile wheel is the first suspect).

### 4.4 Existing oracle tests that become kernel tests automatically

- `tests/test_hashing.py`: `test_render_decimal_18_exact` (parametrized over `str` and `Decimal` forms), `test_render_decimal_18_never_rounds`, `test_render_decimal_18_ignores_hostile_ambient_context`.
- `tests/test_aggregation.py:227` and `tests/test_parquet.py:136` assert rendered values directly; `tests/test_golden.py` asserts the golden digest end to end.

## 5. Exact file allowlist

Implementation changes must remain a subset of this list.

### 5.1 New files

```text
docs/superpowers/plans/2026-08-28-native-kernel-slice-009-rust-q18-rendering.md   (T0 only)
tests/test_kernel_render.py
```

### 5.2 Modified files (exact hunks only)

```text
kernel/src/lib.rs          — add render_decimal_18 (+ private helpers/submodules) and register it (T1)
src/quantara/hashing.py    — public render_decimal_18 becomes the dispatch block; the current body
                             moves verbatim to _render_decimal_18_python with its docstring (T1)
```

No other file may change, including `canonical.py`, `benchmarks/` (frozen measurement infrastructure), `fold_stats.py`, `research_pipeline.py`, `validation_pipeline.py`, `jcs.py`, any pipeline module, any existing test file, `kernel/Cargo.toml`, `Cargo.lock`, `pyproject.toml`, `uv.lock`, `README.md`, and anything under `data/`.

## 6. Forbidden changes

- No modification of `canonical.py`, `jcs.py`, `pipeline.py`, `research_pipeline.py`, `derive_pipeline.py`, `validation_pipeline.py`, `evaluation_*.py`, `features.py`, `folds.py`, `fold_stats.py`, `quality.py`, `aggregation.py`, `publication.py`, `manifests.py`, `cli.py`, `descriptor.py`, `archive.py`, `acquisition.py`, `errors.py`, `parsing.py`, or any existing test file.
- No change to the benchmark harness, thresholds, domains, schema versions, column registries, validators, `WRITER_CONFIG`, or `PARQUET_SCHEMA`. The ≤ 35% retention threshold is frozen; a miss is `INCOMPLETE`, never an amendment.
- No new dependencies (Rust or Python); no `rust_decimal`, `num-bigint`, `serde_json`, or arrow crates. No `f32`/`f64` anywhere in `kernel/src` (the existing source-scan test enforces this mechanically).
- No weakening, deletion, or reclassification of any existing test, fixture, or frozen anchor.
- No writes inside `data/` and no tracked files under `data/` (`git ls-files data` empty; `git status --ignored --short data` shows `!! data/`).
- No force-push, history rewrite, or `git add .`; stage only allowlisted files; `kernel/target/` never committed. No network access in new tests; the only networked work is the existing final integration suite.

## 7. Tasks

Execute in order. Each task ends with one conventional commit. Focused tests inside the task loop; the complete suites run once in T3.

### T0 — Preflight, plan commit, and baseline capture

Before anything else, verify and paste the outputs of:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
git fetch origin
git rev-parse HEAD origin/main     # HEAD=2364d80..., origin/main=d2296bf... (4 ahead by design)
git log --oneline -6               # contains the four Slice 008 commit messages (§3)
git status --short --branch        # clean
git config user.email              # GitHub noreply identity
cargo --version && rustc --version # succeed
git ls-files data                  # empty
git status --ignored --short data  # !! data/
uv run python -c "import quantara_kernel; print(quantara_kernel.module_version())"
uv run pytest tests/test_kernel_dispatch.py tests/test_kernel_parity.py tests/test_kernel_adversarial.py -q   # 18 passed
```

Missing toolchain, wrong HEAD, drifted `origin/main`, or failing kernel tests: report `BLOCKED` (do not repair 008; do not install toolchains).

Then write this entire document verbatim to `docs/superpowers/plans/2026-08-28-native-kernel-slice-009-rust-q18-rendering.md`, lint it with a temporary outside-repository config, and commit:

```bash
# create {"MD013": false} as a temp file OUTSIDE the repo, then:
npx --yes markdownlint-cli2@0.23.2 --config <temp-config> docs/superpowers/plans/2026-08-28-native-kernel-slice-009-rust-q18-rendering.md
# expect: zero issues; delete the temp config afterward
git add docs/superpowers/plans/2026-08-28-native-kernel-slice-009-rust-q18-rendering.md
git commit -m "docs: add native-kernel slice 009 implementation plan"
git show --stat --oneline HEAD     # exactly one file changed
```

**Capture the pre-change baseline (evidence, not committed; run as a background job — the 200,000-row capture takes ~10 minutes; keep the machine quiet):**

```bash
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

Save both JSON outputs outside the repository and paste them into the final report. These are the no-regression comparison base for T3. Exit code 0 required.

**Acceptance:** preflight outputs pasted; markdownlint zero issues; one-file commit; both baseline JSONs captured; tree clean.

### T1 — Rust Q18 renderer and Python dispatch

**RED:** create `tests/test_kernel_render.py` with exactly these eight tests (they fail while the kernel function does not exist):

1. `test_render_parity_golden_corpus` — mirror the corpus and expectations of `tests/test_hashing.py::test_render_decimal_18_exact` (values include `"42571.90"`, `"42600"`, `"12.345678901234567890"`, `"987654.321098765432109876"`, `"7"`, `"400000"`): for each value in both `str` and `Decimal` form, rust-mode output == python-mode output == the known expected string.
2. `test_render_parity_randomized_battery` — 2,000 seeded values built as `(sign, coefficient digit string of 1–40 random digits, exponent −28…+28)` formatted as decimal strings (some with explicit e-notation, some positional, some with 0–25 trailing zeros); for each, assert rust mode == python mode, every accepted output matches `^-?\d+\.\d{18}$`, and every rejected value raises `HashPayloadError` with byte-identical messages in both modes.
3. `test_render_parity_canonical_rows_end_to_end` — construct `CanonicalRow` instances directly (10-string identity tuple, int timestamps, `Decimal` fields including a full-precision 18-fractional-digit value and a trailing-zeros value, `source_ignore="0"`); assert `canonical_content_hash(schema_fingerprint(), (row.to_content_array() for row in rows))` is identical across rust mode, python mode, and both modes' digests over 50 seeded rows.
4. `test_render_dispatch_modes` — with `QUANTARA_HASH_KERNEL=python`, output equals default-mode output on a corpus; with `hashing._KERNEL_AVAILABLE = False` (monkeypatch) and the variable set to `rust`, calling `render_decimal_18` raises `RuntimeError`; with the variable set to `banana`, behavior matches default `auto`.
5. `test_render_accepts_trailing_zeros_beyond_18` — `"0.1000000000000000000"` (19 dp), `"1.230000000000000000000"` (21 dp), `Decimal("0.500000000000000000000000")`: equal outputs in both modes, equal to the short-form rendering.
6. `test_render_zero_and_negative_zero` — `Decimal("-0")`, `"-0.000"`, `Decimal("0E-25")`, `"0E-30"` render `"0.000000000000000000"` in both modes.
7. `test_render_wide_coefficients_and_large_exponents` — a 40-digit coefficient, `"1E+30"`, and a 38-digit coefficient with exponent +5: rust == python for all; outputs pinned from the python oracle at authoring time.
8. `test_render_kernel_is_ambient_context_immune` — under a hostile ambient context (precision 1, `ROUND_DOWN`, clamped `Emax`/`Emin` via `decimal.setcontext`, restored in `finally`), default-mode rendering of wide-coefficient values equals the previously captured expectations.

**GREEN:** implement:

- `kernel/src/lib.rs` — `render_decimal_18(value: &Bound<'_, PyAny>) -> PyResult<String>`: if the value is a `str`, take the string; else (a `Decimal`) obtain its string form with one `str()` call (cache the `decimal.Decimal` type object at first use). Parse the decimal string per the CPython grammar (§3.1) into sign / coefficient digits / exponent; strip trailing coefficient zeros (adjusting the exponent); special values (`Infinity`/`NaN` forms) and unparseable strings follow the oracle-captured behavior (§3.5). Reject when the exponent after stripping is < −18, raising `KernelHashPayloadError` with the byte-identical message including the CPython `str(Decimal)` form of the parsed value (§3.3). Otherwise render: magnitude digit string = coefficient + `(exponent+18)` zeros, left-padded to ≥ 19, split at the last 18 digits, `"-"` prefixed only for negative nonzero magnitude. Pure `std` string arithmetic; no numeric conversion of the magnitude; no `f32`/`f64`. Register the function in `#[pymodule]`.
- `src/quantara/hashing.py` — the public `render_decimal_18` becomes:

```python
def render_decimal_18(value: Decimal | str) -> str:
    """Dispatch Q18 rendering to Rust or the retained Python oracle."""
    if isinstance(value, (Decimal, str)) and _use_rust_kernel():
        try:
            return _quantara_kernel.render_decimal_18(value)
        except _quantara_kernel.KernelHashPayloadError as exc:
            raise HashPayloadError(str(exc)) from exc
    return _render_decimal_18_python(value)
```

  The current body (lines 187-216) moves verbatim to `_render_decimal_18_python` with its docstring. `__all__` unchanged. Then `uv sync` (rebuild the wheel) and run the focused tests.

**Acceptance:**

```bash
uv run pytest tests/test_kernel_render.py -q                    # 8 passed
uv run pytest tests/test_hashing.py tests/test_canonical.py tests/test_parquet.py tests/test_kernel_parity.py -q   # green, unchanged counts
uv run ruff check .                                             # 0 issues
git status --ignored --short kernel                             # target/ ignored
git add kernel/src/lib.rs src/quantara/hashing.py tests/test_kernel_render.py
git commit -m "feat(kernel): rust q18 decimal rendering with python dispatch"
```

### T2 — Adversarial parity battery

**RED:** add exactly these three tests to `tests/test_kernel_render.py`:

9. `test_render_rejects_over_18_fractional_digits_identically` — `"0.1234567890123456789"`, `"1e-19"`, `Decimal("1E-19")`, `"0.12345678901234567890"` (20 dp ending in zero — still rejected), `"-1.2345678901234567891"`: both modes raise `HashPayloadError` with byte-identical messages (pin the exact expected messages, captured from the python oracle — note `"1e-19"` must produce `decimal 1E-19 exceeds …`).
10. `test_render_special_values_raise_identically` — `Decimal("Infinity")`, `Decimal("-Infinity")`, `Decimal("NaN")`, `Decimal("-NaN")`, `Decimal("sNaN")`: **before writing assertions, run each through the python oracle** (`QUANTARA_HASH_KERNEL=python`) and record the actual exception type and `str(exc)`; pin rust mode to type-and-message equality with what the oracle does (do not guess; if the oracle raises `HashPayloadError` for NaN and something else for Infinity, pin both as-is).
11. `test_render_malformed_strings_raise_identically` — `"abc"`, `""`, `"1e"`, `"1.2.3"`, `"--1"`, `"1_000"`, `" 1.5 "`, `".5"`, `"5."`, `"+5"`: same oracle-capture-first discipline — whatever the oracle does (accept with a value, or raise `decimal.InvalidOperation` with specific args), rust mode must do identically, including exception type and message.

**GREEN:** fix the kernel until all eleven pass. Any divergence is a kernel defect — never adjust the Python path, the oracle, or a test to close the gap.

**Acceptance:**

```bash
uv run pytest tests/test_kernel_render.py -q                                       # 11 passed
uv run pytest tests/test_kernel_dispatch.py tests/test_kernel_parity.py tests/test_kernel_adversarial.py tests/test_hashing.py -q   # green, unchanged counts
git add kernel/src/lib.rs tests/test_kernel_render.py
git commit -m "test(kernel): adversarial q18 rendering parity battery"
```

### T3 — Final gates, benchmark comparison, and push

Before any timing capture: request that the owner keep the machine quiet (heavy apps closed, no installs/downloads), and note observed heavy processes in the report. Run the complete gates once on the final unchanged state (run the offline suite as a background job — ~5 minutes with `-n 4`):

```bash
uv lock --check
uv run ruff check .
cd kernel && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cd ..
uv run pytest -m "not integration" -n 4 --dist=load --durations=15
uv run pytest -m integration
```

Expected: `uv lock --check` OK (lockfiles untouched); ruff clean; cargo fmt/clippy clean; the offline suite reports **646 passed** (635 post-008 + 11 new) with at most the pre-existing single warning; the serial networked integration suite reports **11 passed** — through kernel rendering + hashing in default mode, re-proving the real-data `9d7eee74…` identity end to end.

Then capture the comparison evidence with the exact same harness commands, on the final state, alternating modes:

```bash
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=rust   uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
QUANTARA_HASH_KERNEL=rust   uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

**Benchmark acceptance (hard, frozen from Slice 008):** comparing `rust` vs `python` runs on the same final state and machine:

- `content_hash` stage `seconds_median` in rust mode ≤ **35%** of the python-mode value at **both** 44,640 and 200,000 rows.
- `content_hash` stage `tracemalloc_peak_bytes` in rust mode ≤ 110% of the python-mode value.
- No stage's `seconds_median` regresses by more than 15% versus the T0 baseline at either scale, in either mode.

**Noise protocol (007/008 lessons, mandatory before declaring failure):** a near-miss on the ratio → first verify the wheel is a release build (installed `.pyd` matches `kernel/target/release/`); an untouched-stage regression beyond 15% with wide repeat spread or observed heavy concurrent activity → rerun the affected comparison **interleaved** (same final state, alternating `QUANTARA_HASH_KERNEL=python`/`rust` round-by-round, ≥ 4 rounds per side, compare per-side medians) before concluding failure; single-sample outliers (008 saw one 1192.8 s verify sample) are noted and settled by medians plus a rerun. Untouched code cannot regress — treat such misses as environmental until proven otherwise.

Then push once (this lands Slice 008's four commits together with this slice's commits — intended and required; 008 withheld its push on this same gate):

```bash
git push origin main
git rev-parse HEAD origin/main     # equal
git status --short --branch        # clean and synced
git ls-files data                  # empty
git status --ignored --short data  # !! data/
```

## 8. Failure handling

- Missing toolchain, wrong starting HEAD, drifted `origin/main`, or failing 008 kernel tests at T0: report `BLOCKED` with exact outputs; never repair prior slices or install system toolchains.
- Fix task-related failures inside the same bounded task and rerun the affected focused tests; never weaken a test, threshold, or lint rule to go green. A parity divergence is always a kernel defect, never a Python-path or test change.
- If a required change is blocked by a file outside the allowlist, stop and report `BLOCKED` with the exact blocker — do not silently widen scope.
- If preflight or any gate discovers an executor already committed part of this plan, do not discard or redo it: read the full diff, verify it against this allowlist, complete only the remaining tasks, and attribute per-commit provenance in the final report.
- A missed speed threshold with correct outputs means `INCOMPLETE`: check the build profile first, apply the noise protocol, then profile the kernel boundary (PyO3/`str()` conversion vs rendering) with an out-of-repository probe; report findings. Thresholds may only change with an explicit, justified owner-approved amendment recorded outside this slice — never inside it.
- Windows note: a timed-out long pytest run can leave orphaned processes; after any timeout, inspect process command lines and terminate only confirmed test orphans before rerunning.

## 9. Final evidence report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

- Starting HEAD, plan-commit SHA, and ending HEAD; `git status --short --branch` at the end.
- Per-task red→green evidence: the acceptance commands and their raw terminal outputs (paste output, never prose claims).
- Resolved crate versions and licenses (expected unchanged: `pyo3` 0.23.5, `sha2` 0.10.9, `maturin` 1.15.0 — all MIT OR Apache-2.0); confirmation `kernel/target/` is untracked and lockfiles are untouched.
- Parity evidence summary: the golden-corpus result, the 2,000-value randomized battery result, the end-to-end `CanonicalRow` digest equality, the special-value and malformed-string pins (with the oracle-captured expectations), and the integration `9d7eee74…` identity passing through kernel rendering.
- The full benchmark JSON for all four T3 runs plus the two T0 baselines, and a per-stage comparison table (`seconds_median` python vs rust, `tracemalloc_peak_bytes` python vs rust) with the hard ratios computed explicitly — including the expected substantial `verify_parquet` improvement in rust mode (reported, not gated).
- Raw outputs of all T3 gates, including the pytest summary lines and the `--durations=15` table.
- The commit list (`git log --oneline d2296bf..HEAD`) with conventional messages and per-commit provenance (which slice's session produced each), and the single push result.
- Any residual limitations (e.g. lexical-grammar corners accepted as oracle-captured deviations under §3).
