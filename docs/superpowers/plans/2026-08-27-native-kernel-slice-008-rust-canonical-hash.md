# Quantara Native-Kernel Slice 008 — Rust Canonical-Hash Kernel Implementation Plan

**Status:** Proposed implementation plan; awaiting owner review before execution
**Date:** 2026-08-27
**Project root:** `D:\PROJECT\Quantara`
**Sequencing:** Authorized only after Slice 007 (`2026-08-27-performance-slice-007-baseline-and-streaming.md`) is COMPLETE and pushed. This plan is stage 2 of the project's native-performance-migration policy; Slice 007 (streaming Python) was stage 1.
**Governing policy:** This plan is self-contained. It authorizes exactly one bounded native-kernel slice: a Rust/PyO3 implementation of the canonical and research content-hash hot path, behind an explicit dispatch with the Python implementation retained as the differential oracle. It does not authorize porting the CSV parser, Parquet I/O, aggregation, features, folds, or evaluation metrics, any schema/identity change, or any data republishing.

## 1. Goal

The measured evidence (pre-007 profiling, 2026-08-25) showed `canonical_content_hash` at **21.2 s for 131,040 rows** — over four times the three-month CSV parse. Slice 007 removed the list/join materialization and streamed the Python implementation; it deliberately deferred native code. This slice introduces the narrow Rust/PyO3 data kernel the policy prescribes, for the one measured hotspot with a clean deterministic boundary:

1. **`quantara_kernel` native module** — a new `kernel/` cargo workspace member (PyO3 + RustCrypto `sha2`) exposing `hash_canonical_rows` and `hash_research_rows`. Each accepts a fingerprint string and an iterable of row arrays, replicates the exact row validation, JCS serialization, domain/NUL/fingerprint/LF framing, and incremental SHA-256, and returns the identical lowercase hex digest.
2. **Dispatch with retained oracle** — `canonical_content_hash` and `research_content_hash` in `src/quantara/hashing.py` route through the kernel when available (environment variable `QUANTARA_HASH_KERNEL` ∈ `rust`/`python`/`auto`, default `auto`). The 007 streaming Python bodies are retained verbatim as `_canonical_content_hash_python` / `_research_content_hash_python` and remain the forced-Python mode and differential oracle.
3. **Differential proof at every level** — kernel vs Python digest equality over golden fixtures, seeded and randomized adversarial corpora, streaming generators, and malformed-row error parity (same exception type, message, and error id). Because `auto` is the default, the entire existing offline suite (617 tests post-007) and the real-data integration identity (`9d7eee74…`) execute through the kernel, making the whole suite the differential oracle.
4. **Measured justification** — the committed 007 benchmark harness (`benchmarks/stage_baseline.py`, unmodified) measures the hash stage with the kernel on and off; retaining the additional language requires the kernel to meet a hard speed threshold.

Non-goals: no Rust port of `render_decimal_18` or `CanonicalRow.to_content_array` (Q18 rendering happens upstream of the hash boundary — rows arrive as str/int/bool only; a decimal-math port is a later slice gated on fresh profiling), no parser/aggregation/metrics work, no changes to `validation_content_hash`/`evaluation_content_hash` (single small artifacts), no test-gate/xdist/fixture changes, no CI or wheel publishing, no README changes, no history/asset expansion.

## 2. Required execution prompt

```text
Work in D:\PROJECT\Quantara.

Write this entire document verbatim to
docs/superpowers/plans/2026-08-27-native-kernel-slice-008-rust-canonical-hash.md,
commit it exactly as Task T0 requires, then read that committed file completely and
execute it exactly.

Follow T0 through T4 in order. Use focused red-to-green TDD, preserve every forbidden
scope boundary, fix task-related failures before continuing, run the final gates once
on the final unchanged state, and report COMPLETE, BLOCKED, or INCOMPLETE with raw
commands and results. Do not push until every required gate passes. Then STOP.
```

The prompt is agent-independent. Codex CLI, OpenCode, or another filesystem-and-terminal coding agent may execute it without changing the plan contract.

## 3. Approved inputs and fixed contracts

- **Toolchain prerequisite (hard gate):** the Rust toolchain must already be installed — `cargo --version` and `rustc --version` must succeed, and the MSVC linker (VS Build Tools, "Desktop development with C++" workload) must be present, because the target is `x86_64-pc-windows-msvc`. If absent, report `BLOCKED` immediately with the exact outputs; do not install system toolchains yourself. Suggested owner installs: `winget install Rustlang.Rustup` and `winget install Microsoft.VisualStudio.2022.BuildTools --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"`, then a fresh shell and `rustup default stable`.
- **Slice 007 prerequisite (hard gate):** `git log --oneline` must contain all four 007 commits — `docs: add performance slice 007 implementation plan`, `feat(bench): add stage baseline harness`, `perf(hashing): stream row-framed content hashes`, `perf(canonical): stream parquet read-back reconciliation` — with `benchmarks/stage_baseline.py`, `tests/test_stage_baseline.py`, `tests/test_streaming_hash.py`, and `tests/test_reconcile_stream.py` present, and the tree clean and synced with `origin/main`.
- **Authorized dependency additions (this slice only):** the `kernel/` cargo package (`pyo3` with `extension-module`, `sha2`), `maturin>=1,<2` as the kernel package's build backend, and in the root `pyproject.toml`: `[tool.uv.workspace] members = ["kernel"]`, a `quantara-kernel` entry in `[project] dependencies`, and `[tool.uv.sources] quantara-kernel = { workspace = true }`. `uv.lock` is regenerated accordingly. Consequence (accepted by design): building/syncing the environment now requires the Rust toolchain on this machine; the root project wheel is not publishable while the kernel is a workspace-only source (repo-run product; publishing is a non-goal). All crate licenses must be MIT/Apache-2.0 dual or otherwise Apache-2.0-compatible (`pyo3` and `sha2` are MIT OR Apache-2.0); record the resolved versions in the final report.
- Digests are byte-identical: SHA-256 over the identical framing — domain, NUL, lowercased fingerprint, NL, then per row the RFC 8785 JCS serialization (UTF-8) and NL. The kernel is a reimplementation of the same byte sequence, not a new contract.
- Frozen anchors that must still hold at the end (asserted by existing tests — do not weaken them):
  - `schema_fingerprint()` == `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8` (`tests/test_golden.py`)
  - golden `canonical_content_hash` == `8f78cd55e6ada9539a5e88c4debcdea05cab7d7c1c5adb3d43944ef3d290feab` (`tests/test_golden.py`), now produced through the kernel in default mode
  - the real-data January 2024 parent identity starting `9d7eee74…` (`tests/test_integration_derivation.py`), executed through the kernel by the integration gate
- Exception contract: validation failures raise `HashPayloadError` (error id `manifest_inconsistency`) with messages byte-identical to the Python path; structural iteration failures on a non-iterable rows object or non-sequence row surface as `TypeError` in both modes. `JcsFloatRejected` never triggers inside these functions in either mode (the row validators reject floats first).
- Binary floats remain forbidden everywhere: the kernel uses no `f32`/`f64` and performs no numeric parsing beyond decimal-digit passthrough of already-validated Q18 strings; a source-scan test enforces this mechanically.
- Python remains the control plane: rights, publication, recovery, orchestration, and all small-payload hashes (`descriptor_hash`, quality identities, fingerprints, validation/evaluation hashes) stay in Python untouched.
- Documented boundary deviations (out-of-contract inputs, accepted): fingerprints are SHA-256 hex by construction; the kernel lowercases ASCII only. Parity tests use lowercase, uppercase, and mixed-case hex fingerprints. Lone-surrogate strings (unencodable to UTF-8) are outside the contract in both modes.
- Benchmark wall-clock numbers are non-acceptance evidence except the T4 thresholds in §7 T4.

## 4. Observed repository seams to reuse

Verified against the 007 plan's frozen contract and the current source; cite them rather than inventing APIs.

### 4.1 Hashing boundary (post-007 `src/quantara/hashing.py`)

- `canonical_content_hash(fingerprint: str, rows: Iterable[Sequence[object]]) -> str` — after 007, streams: `hashlib.sha256()` updated with `CONTENT_HASH_DOMAIN` ascii bytes, `b"\x00"`, `fingerprint.lower().encode("ascii")`, `b"\n"`, then per row `canonicalize(canonical_row_array(row)).encode("utf-8")` + `b"\n"`. This body moves verbatim to `_canonical_content_hash_python`; the public name becomes the dispatch point.
- `research_content_hash(fingerprint: str, rows: Iterable[Sequence[object]]) -> str` — identical framing under `RESEARCH_CONTENT_HASH_DOMAIN` with `research_row_array`; moves to `_research_content_hash_python`.
- `canonical_row_array(values)` — validates arity == `len(CANONICAL_COLUMNS)` (23); each value must be `isinstance(value, (str, int))` (so `bool` passes as an int subclass and later serializes as `true`/`false`; `None`, `Decimal`, `float`, and everything else raise `HashPayloadError`). Float message: `binary floats are forbidden in canonical rows`. Other-type message: `canonical rows admit strings/ints/bools/nulls only, got {type(value)!r}`.
- `research_row_array(values)` — validates arity == 7 against `RESEARCH_COLUMNS`; `None` only where nullable (`open_time_ms` never null); `DECIMAL_TYPE` columns must be strings matching `^-?\d+\.\d{18}$`; `int8`/`int64` columns reject `bool` explicitly and non-ints; floats rejected with `binary floats are forbidden in research rows`.
- `HashPayloadError(QuantaraError)` (error id `manifest_inconsistency`), `sha256_hex`, `CONTENT_HASH_DOMAIN`, `RESEARCH_CONTENT_HASH_DOMAIN`, `CANONICAL_COLUMNS`, `RESEARCH_COLUMNS`, `HASH_CONTRACT_VERSION` — unchanged.
- `render_decimal_18` and `CanonicalRow.to_content_array` are upstream of this boundary (rows arrive pre-rendered) — not ported, not modified.

### 4.2 JCS subset (`src/quantara/jcs.py`) — the exact serialization contract

- Strings: RFC 8785 §3.2.2.2 — short escapes `\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`; other code points below U+0020 as `\u00xx` (lowercase hex); everything else emitted raw (non-ASCII passes through as UTF-8).
- `True`/`False`/`None` → `true`/`false`/`null`; ints → `str(value)` (arbitrary precision; bool checked before int); lists → comma-joined bracketed arrays (row payloads are flat arrays); floats → `JcsFloatRejected`; other types → `TypeError`. Dict sorting (§3.2.3) is irrelevant here — row payloads are arrays — and stays Python-side for fingerprints.

### 4.3 Benchmark harness (committed by 007 — do not modify)

- `uv run python -m benchmarks.stage_baseline --rows {44640,200000} --repeats 3 --json`; the `content_hash` stage calls `canonical_content_hash` exactly as production does, so the kernel dispatch is picked up automatically with no harness edit; `QUANTARA_HASH_KERNEL` toggles modes between runs.

## 5. Exact file allowlist

Implementation changes must remain a subset of this list.

### 5.1 New files

```text
docs/superpowers/plans/2026-08-27-native-kernel-slice-008-rust-canonical-hash.md   (T0 only)
kernel/Cargo.toml
kernel/Cargo.lock
kernel/pyproject.toml            (maturin build backend; package name quantara-kernel)
kernel/.gitignore                (must ignore /target)
kernel/src/lib.rs                (module registration; may be split into kernel/src/*.rs submodules)
tests/test_kernel_dispatch.py
tests/test_kernel_parity.py
tests/test_kernel_adversarial.py
```

### 5.2 Modified files (exact hunks only)

```text
pyproject.toml              — [tool.uv.workspace] members, quantara-kernel dependency, [tool.uv.sources] (T1)
uv.lock                     — regenerated by uv for the workspace addition (T1)
src/quantara/hashing.py     — dispatch block + active_hash_kernel helper; the two 007 streaming bodies renamed to _canonical_content_hash_python / _research_content_hash_python with logic unchanged (T2)
```

No other file may change, including `README.md`, `benchmarks/` (the harness is measurement infrastructure and stays frozen), `src/quantara/jcs.py`, `src/quantara/canonical.py`, any pipeline module, any existing test file, any `configs/` file, and anything under `data/`.

## 6. Forbidden changes

- No modification of `jcs.py`, `canonical.py`, `pipeline.py`, `research_pipeline.py`, `derive_pipeline.py`, `validation_pipeline.py`, `evaluation_*.py`, `features.py`, `folds.py`, `fold_stats.py`, `quality.py`, `aggregation.py`, `publication.py`, `manifests.py`, `cli.py`, `descriptor.py`, `archive.py`, `acquisition.py`, `errors.py`, or any existing test file.
- No change to `validation_content_hash` / `evaluation_content_hash`, `render_decimal_18`, domain constants, schema versions, column registries, `WRITER_CONFIG`, or `PARQUET_SCHEMA`.
- No Rust port of anything except the two row-framed hash functions and their row validators. No decimal arithmetic in Rust; no `f32`/`f64` anywhere in `kernel/src`.
- No dependency additions beyond §3 (no `rust_decimal`, no `serde_json`, no arrow crates — hand-rolled JCS subset and framing only).
- No CI/workflow files, no wheel publishing, no changes to pytest/ruff/xdist configuration, no test-fixture scope changes.
- No weakening, deletion, or reclassification of any existing test, fixture, or frozen anchor.
- No writes inside `data/` and no tracked files under `data/` (`git ls-files data` must stay empty; `git status --ignored --short data` must show `!! data/`).
- No force-push, history rewrite, or `git add .`; stage only allowlisted files. `kernel/target/` must never be committed.
- No network access in new tests; the only networked work is the existing final integration suite.

## 7. Tasks

Execute in order. Each task ends with one conventional commit. Focused tests inside the task loop; the complete suites run once in T4.

### T0 — Preflight, plan commit, and no-kernel baseline

Before anything else, verify and paste the outputs of:

```bash
git rev-parse HEAD origin/main     # equal, clean, synced with origin/main
git log --oneline -6               # contains the four Slice 007 commit messages (§3)
cargo --version                    # succeeds
rustc --version                    # succeeds
git ls-files data                  # empty
git status --ignored --short data  # !! data/
uv run pytest tests/test_stage_baseline.py tests/test_streaming_hash.py tests/test_reconcile_stream.py -q   # 15 passed
```

Missing toolchain, missing 007 commits, or failing 007 focused tests: report `BLOCKED` (do not install toolchains; do not repair 007).

Then write this entire document verbatim to `docs/superpowers/plans/2026-08-27-native-kernel-slice-008-rust-canonical-hash.md`, lint it with a temporary outside-repository config, and commit:

```bash
# create {"config":{"MD013": false}} as a temp file OUTSIDE the repo, then:
npx --yes markdownlint-cli2@0.23.2 --config <temp-config> docs/superpowers/plans/2026-08-27-native-kernel-slice-008-rust-canonical-hash.md
# expect: zero issues; delete the temp config afterward
git add docs/superpowers/plans/2026-08-27-native-kernel-slice-008-rust-canonical-hash.md
git commit -m "docs: add native-kernel slice 008 implementation plan"
git show --stat --oneline HEAD     # exactly one file changed
```

**Capture the no-kernel hash baseline (evidence, not committed):**

```bash
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

(The variable is not yet read by the code; setting it keeps measurement conditions identical across T0 and T4.) Save both JSON outputs outside the repository and paste them into the final report. Exit code 0 required.

**Acceptance:** preflight outputs pasted; markdownlint zero issues; one-file commit; both baseline JSONs captured; tree clean.

### T1 — Kernel crate scaffold and workspace wiring

**RED:** create `tests/test_kernel_dispatch.py` with exactly these five tests (they fail while the kernel does not exist):

1. `test_kernel_module_importable` — `import quantara_kernel` succeeds and the module exposes `hash_canonical_rows`, `hash_research_rows`, `KernelHashPayloadError`, `CONTENT_HASH_DOMAIN`, and `RESEARCH_CONTENT_HASH_DOMAIN`.
2. `test_default_mode_uses_kernel` — with `QUANTARA_HASH_KERNEL` unset (monkeypatch `delenv`), `quantara.hashing.active_hash_kernel()` returns `"rust"`.
3. `test_forced_python_mode_matches_kernel_mode` — with the variable set to `python`, `active_hash_kernel()` returns `"python"`, and `canonical_content_hash` over a 50-row seeded corpus returns the same digest as under default mode.
4. `test_explicit_rust_without_kernel_raises_runtime_error` — monkeypatch `hashing._KERNEL_AVAILABLE = False`, set the variable to `rust`: calling `canonical_content_hash` raises `RuntimeError`.
5. `test_invalid_mode_value_falls_back_to_auto` — set the variable to `banana`: no error; behaves as `auto` (kernel used when available).

**GREEN:** scaffold the crate and wire the workspace:

- `kernel/Cargo.toml` — `[package] name = "quantara-kernel"` (or valid crate name mapping to the module), `[lib] name = "quantara_kernel" crate-type = ["cdylib"]`, `edition = "2021"`, `license = "Apache-2.0"`; dependencies `pyo3` (feature `extension-module`) and `sha2`; record the exact resolved versions in the final report and commit `kernel/Cargo.lock`.
- `kernel/pyproject.toml` — `[build-system] requires = ["maturin>=1,<2"] build-backend = "maturin"`; `[project] name = "quantara-kernel" version = "0.1.0" requires-python = ">=3.11" license = "Apache-2.0"`.
- `kernel/src/lib.rs` — minimal module: register `hash_canonical_rows` and `hash_research_rows` as `#[pyfunction]` stubs returning `"unimplemented"` (T2/T3 fill them), define `KernelHashPayloadError` as a `#[pyclass]` subclass of `Exception`, expose `CONTENT_HASH_DOMAIN` and `RESEARCH_CONTENT_HASH_DOMAIN` as module constants equal to the Python values, and a `module_version() -> String`.
- `kernel/.gitignore` — `/target`.
- Root `pyproject.toml` — add `[tool.uv.workspace] members = ["kernel"]`, `quantara-kernel` to `[project] dependencies`, `[tool.uv.sources] quantara-kernel = { workspace = true }`.
- Run `uv sync` (this builds the wheel via maturin; MSVC link errors here mean the toolchain prerequisite is unmet — `BLOCKED`, do not work around), then verify:

```bash
uv run python -c "import quantara_kernel; print(quantara_kernel.module_version())"   # prints, no ImportError
uv run pytest tests/test_kernel_dispatch.py -q    # tests 1 passes; 2-5 fail until T2 — acceptable only if committed together with T2? NO:
```

Correct sequencing: commit the scaffold only with test 1 green and tests 2–5 marked as the T2/T3 RED set (leave the file in place; they stay failing until T2 wires dispatch — that is the intended red state). Use `uv run pytest tests/test_kernel_dispatch.py::test_kernel_module_importable -q` as this task's green check.

**Acceptance:**

```bash
uv run pytest tests/test_kernel_dispatch.py::test_kernel_module_importable -q   # 1 passed
uv run ruff check .                                                            # 0 issues
git status --ignored --short kernel                                            # target/ ignored
git add kernel/ pyproject.toml uv.lock tests/test_kernel_dispatch.py
git commit -m "feat(kernel): scaffold rust canonical-hash crate"
```

### T2 — Rust canonical hash and Python dispatch

**RED:** create `tests/test_kernel_parity.py` with exactly these six tests:

1. `test_golden_canonical_digest_under_kernel` — load the five golden fixture rows from `tests/fixtures/golden/expected.json` (`rows` key) and the golden fingerprint; the digest equals `8f78cd55e6ada9539a5e88c4debcdea05cab7d7c1c5adb3d43944ef3d290feab` in default (kernel) mode and in forced `python` mode.
2. `test_canonical_parity_seeded_corpus` — 300-row seeded canonical content-array corpus (mirror the corpus builder style of `tests/test_streaming_hash.py`): kernel-mode digest == python-mode digest == the in-test join reference (domain + NUL + fingerprint.lower() + NL + `jcs_canonicalize(row)` + NL per row, joined and SHA-256'd).
3. `test_research_parity_seeded_corpus` — seeded research rows including `None` in nullable columns and valid Q18 strings: kernel == python == join reference under `RESEARCH_CONTENT_HASH_DOMAIN`.
4. `test_parity_randomized_property_battery` — 100 seeded random rows varying string lengths, embedded quotes/backslashes/control characters, non-ASCII and emoji strings, huge ints (beyond 64-bit), negative ints, and `True`/`False` placed in int positions: kernel digest == python digest for every row set.
5. `test_parity_large_streaming_corpus` — 30,000 seeded rows consumed as a generator under kernel mode: digest equals the python-mode digest (proves Rust-side streaming without materialization) and equals the join reference.
6. `test_kernel_domains_match_python_constants` — `quantara_kernel.CONTENT_HASH_DOMAIN == hashing.CONTENT_HASH_DOMAIN` and likewise for the research domain.

**GREEN:** implement in `kernel/src/lib.rs`:

- `hash_canonical_rows(fingerprint: &str, rows: &Bound<'_, PyAny>) -> PyResult<String>` — iterate `rows` via `PyIterator`; for each row, require a sequence (structural failures propagate as `TypeError`); validate arity and per-item types exactly mirroring `canonical_row_array` (`PyBool` before `PyLong` for the bool-is-int acceptance; `PyString`; `PyFloat` → `KernelHashPayloadError("binary floats are forbidden in canonical rows")`; any other type → `KernelHashPayloadError` whose message is byte-identical to `canonical rows admit strings/ints/bools/nulls only, got <class '...'>` — obtain the type representation by calling `repr()` on the row item's type object, guaranteeing message parity); serialize each accepted row directly into the hasher: `"`-wrapped RFC 8785-escaped strings (short escapes, `\u00xx` below U+0020, raw UTF-8 otherwise), `true`/`false` for bools, `str()` of the Python int object for ints (arbitrary precision parity), `,` separators inside `[` `]`; frame with `CONTENT_HASH_DOMAIN` + NUL + ASCII-lowercased fingerprint + NL before the first row and NL after every row; feed a `sha2::Sha256` incrementally; return the lowercase hex digest.
- `hash_research_rows` — same structure under `RESEARCH_CONTENT_HASH_DOMAIN`, mirroring `research_row_array` (arity 7; `None` only in nullable positions rendered as `null`; Q18 string pattern `^-?\d+\.\d{18}$` enforced with the identical failure message; bool explicitly rejected in int columns with the identical message).
- Wire the dispatch in `src/quantara/hashing.py`: module-level guarded import of `quantara_kernel` setting `_KERNEL_AVAILABLE`; `_kernel_mode()` reading `QUANTARA_HASH_KERNEL` (call time, values `rust`/`python`/`auto`, anything else → `auto`); `active_hash_kernel() -> str` reporting `"rust"` or `"python"`; the public `canonical_content_hash`/`research_content_hash` route to the kernel when enabled (explicit `rust` with no kernel raises `RuntimeError`), catching `KernelHashPayloadError` and re-raising `HashPayloadError(str(exc)) from exc`; the 007 streaming bodies move verbatim into `_canonical_content_hash_python` / `_research_content_hash_python` and serve forced-Python mode.

**Acceptance:**

```bash
uv run pytest tests/test_kernel_dispatch.py tests/test_kernel_parity.py -q        # 11 passed
uv run pytest tests/test_hashing.py tests/test_golden.py tests/test_streaming_hash.py -q   # 27 passed
uv run pytest tests/test_pipeline.py tests/test_canonical.py tests/test_parquet.py -q      # green, unchanged counts
git add kernel/src/lib.rs kernel/Cargo.lock src/quantara/hashing.py tests/test_kernel_parity.py
git commit -m "feat(kernel): rust canonical and research content-hash with python dispatch"
```

### T3 — Adversarial parity battery

**RED:** create `tests/test_kernel_adversarial.py` with exactly these seven tests (several fail against a naive kernel):

1. `test_float_row_raises_identically` — a `float` planted mid-corpus raises `HashPayloadError` with the byte-identical message under both modes, whether rows arrive as a list or a generator (generator must raise mid-consumption in both modes).
2. `test_wrong_arity_raises_identically` — 22- and 24-field canonical rows raise `HashPayloadError` with identical messages under both modes.
3. `test_unsupported_type_raises_identically` — `None`, `Decimal`, and a plain object in a canonical row raise `HashPayloadError` with identical messages (including the exact `<class '...'>` type rendering) under both modes.
4. `test_non_sequence_row_raises_typeerror_both_modes` — `rows=iter([5])` raises `TypeError` under both modes.
5. `test_bool_renders_as_json_bool_identically` — canonical rows containing `True`/`False` in int positions produce identical digests under both modes (pins the bool-is-int acceptance plus `true`/`false` rendering).
6. `test_research_validation_errors_identical` — a non-Q18 string in a decimal column, `None` in never-null `open_time_ms`, and a `bool` in the int8 label column each raise `HashPayloadError` with identical messages under both modes.
7. `test_kernel_source_contains_no_binary_floats` — scan every file under `kernel/src/` and assert the tokens `f64` and `f32` do not occur (mechanical enforcement of the no-binary-float policy).

**GREEN:** fix the kernel until all seven pass. Any divergence is a kernel defect — never adjust the Python path or the test to close the gap.

**Acceptance:**

```bash
uv run pytest tests/test_kernel_adversarial.py -q                                  # 7 passed
uv run pytest tests/test_kernel_dispatch.py tests/test_kernel_parity.py tests/test_kernel_adversarial.py -q   # 18 passed
git add kernel/src/lib.rs tests/test_kernel_adversarial.py
git commit -m "test(kernel): adversarial parity battery for rust hash kernel"
```

### T4 — Final gates, benchmark comparison, and push

Run the complete gates once on the final unchanged state (the offline suite takes ~12 minutes with `-n 4` on this machine; run as one sequential block and read every summary, not only the last exit code):

```bash
uv lock --check
uv run ruff check .
cd kernel && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cd ..
uv run pytest -m "not integration" -n 4 --dist=load --durations=15
uv run pytest -m integration
```

Expected: `uv lock --check` OK; ruff clean; cargo fmt/clippy clean; the offline suite reports **635 passed** (617 post-007 + 18 new) with at most the pre-existing single warning; the serial networked integration suite reports **11 passed** — through the kernel in default mode, re-proving the real-data `9d7eee74…` identity end to end.

Then capture the comparison evidence with the exact same harness commands, on the final state, alternating modes:

```bash
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=rust   uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
QUANTARA_HASH_KERNEL=python uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
QUANTARA_HASH_KERNEL=rust   uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

**Benchmark acceptance (hard):** comparing `rust` vs `python` runs on the same final state and machine:

- `content_hash` stage `seconds_median` with the kernel is at most **35%** of the python-mode value at **both** 44,640 and 200,000 rows (≥ ~2.9× speedup — the threshold that justifies retaining a second language; a near-miss usually means a debug-profile build — verify the maturin wheel was built release before diagnosing further).
- `content_hash` stage `tracemalloc_peak_bytes` with the kernel is at most 110% of the python-mode value.
- No stage's `seconds_median` in rust mode regresses by more than 15% versus the T0 no-kernel baseline at either scale.

Then push once:

```bash
git push origin main
git rev-parse HEAD origin/main     # equal
git status --short --branch        # clean and synced
git ls-files data                  # empty
git status --ignored --short data  # !! data/
```

## 8. Failure handling

- Missing Rust toolchain or MSVC linker at T0/T1: report `BLOCKED` with the exact command outputs and the §3 install suggestions; never install system toolchains or silently fall back to shipping a Python-only slice.
- Fix task-related failures inside the same bounded task and rerun the affected focused tests; never weaken a test, threshold, or lint rule to go green. A parity divergence is always a kernel defect, never a Python-path or test change.
- If a required change is blocked by a file outside the allowlist, stop and report `BLOCKED` with the exact blocker — do not silently widen scope.
- If preflight or any gate discovers an executor already committed part of this plan, do not discard or redo it: read the full diff, verify it against this allowlist, complete only the remaining tasks, and attribute per-commit provenance in the final report.
- A missed speed threshold with correct digests means `INCOMPLETE`: check the build profile first, then profile the kernel boundary (PyO3 conversion overhead vs hashing), and report findings; thresholds may only change with an explicit, justified amendment recorded in the final report.
- Windows note: a timed-out long pytest run can leave orphaned processes; after any timeout, inspect process command lines and terminate only confirmed test orphans before rerunning.

## 9. Final evidence report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

- Starting HEAD, plan-commit SHA, and ending HEAD; `git status --short --branch` at the end.
- Per-task red→green evidence: the acceptance commands and their raw terminal outputs (paste output, never prose claims).
- The resolved `pyo3`/`sha2`/`maturin` versions and their licenses; confirmation `kernel/target/` is untracked.
- Digest-parity evidence summary: golden anchor values, the 100-row randomized battery result, and the integration `9d7eee74…` identity passing through the kernel.
- The full benchmark JSON for all four T4 runs plus the T0 baseline, and a per-stage comparison table (`seconds_median` python vs rust, `tracemalloc_peak_bytes` python vs rust) with the hard ratios computed explicitly.
- Raw outputs of all T4 gates, including the pytest summary lines and the `--durations=15` table.
- The commit list (`git log --oneline <baseline>..HEAD`) with conventional messages, and the single push result.
- Any residual limitations (e.g., build-profile notes, deviations accepted under §3).
