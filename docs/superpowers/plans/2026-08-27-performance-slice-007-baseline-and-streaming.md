# Quantara Performance Slice 007 — Stage Baseline and Streaming Canonical Path Implementation Plan

**Status:** Proposed implementation plan; awaiting owner review before execution
**Date:** 2026-08-27
**Project root:** `D:\PROJECT\Quantara`
**Implementation baseline:** `9973b10cb069bcba96e1fdcf8adc78689dcaef3c`
**Governing policy:** This plan is self-contained. It authorizes exactly one bounded, contract-preserving performance slice. It does not authorize any Rust/PyO3 work, any new dependency, any schema/identity change, or any data republishing.

## 1. Goal

The data foundation (slices 001–006) is accepted and green. Before history/asset expansion multiplies every pipeline cost, this slice removes the two known avoidable Python materializations on the canonical path and records a measured baseline so the later native-kernel decision is evidence-driven:

1. **Stage baseline harness** — a committed, deterministic, offline benchmark (`benchmarks/stage_baseline.py`) that times the stable canonical-path stages (parse → assemble → quality → Parquet write → read-back/reconcile → content hash) with per-stage wall-clock and `tracemalloc` peak, over synthetic corpora of 44,640 and 200,000 rows. Baseline evidence is captured **before** any optimization and re-captured after.
2. **Streaming row-framed content hashes** — `canonical_content_hash` and `research_content_hash` currently serialize every row, append the bytes to a `parts` list, and SHA-256 one giant `b"".join(parts)` payload. Rewrite both to feed a single `hashlib.sha256()` incrementally, and convert the four production list-comprehension call sites to lazy generators. Digests stay byte-identical because the hashed byte sequence is unchanged.
3. **Streaming Parquet read-back reconciliation** — the 1m canonical pipeline currently materializes the entire Parquet table back to Python (`read_canonical_rows` + `reconcile_rows`). Add `reconcile_parquet` in `canonical.py`, which reconciles in record-batch slices, and adopt it in `pipeline.py`.

Every change must be byte-identical in output: same digests, same published identities, same exception classes and error ids, same pipeline exit semantics. Per the project's performance-migration policy, Python remains the control plane; native code is deliberately deferred to a later slice gated on this slice's recorded benchmark evidence.

Non-goals: no Rust/PyO3/DuckDB, no changes to `validation_content_hash`/`evaluation_content_hash` (single-artifact payloads, tiny), no Parquet writer-config change, no test-fixture/xdist/gate-config changes, no test-gate speedup work, no history/asset expansion, no README changes.

## 2. Required execution prompt

```text
Work in D:\PROJECT\Quantara.

Write this entire document verbatim to
docs/superpowers/plans/2026-08-27-performance-slice-007-baseline-and-streaming.md,
commit it exactly as Task T0 requires, then read that committed file completely and
execute it exactly.

Follow T0 through T4 in order. Use focused red-to-green TDD, preserve every forbidden
scope boundary, fix task-related failures before continuing, run the final gates once
on the final unchanged state, and report COMPLETE, BLOCKED, or INCOMPLETE with raw
commands and results. Do not push until every required gate passes. Then STOP.
```

The prompt is agent-independent. Codex CLI, OpenCode, or another filesystem-and-terminal coding agent may execute it without changing the plan contract.

## 3. Approved inputs and fixed contracts

- Implementation baseline: `9973b10cb069bcba96e1fdcf8adc78689dcaef3c` (Slice 006 correction, independently audited and accepted).
- No new runtime or dev dependency. `uv.lock`, `[project] dependencies`, and `[dependency-groups]` must not change. The only permitted `pyproject.toml` change is adding `"benchmarks"` to `[tool.ruff] src`.
- `HASH_CONTRACT_VERSION` (`hash_contract_v1`), `CONTENT_HASH_DOMAIN`, `RESEARCH_CONTENT_HASH_DOMAIN`, `CANONICAL_COLUMNS`, `RESEARCH_COLUMNS`, and all `*_SCHEMA_VERSION` constants are unchanged.
- Streaming rewrite produces byte-identical digests: SHA-256 over the identical byte sequence, just fed incrementally.
- Frozen anchors that must still hold at the end (already asserted by existing tests — do not weaken them):
  - `schema_fingerprint()` == `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8` (`tests/test_golden.py`)
  - golden `canonical_content_hash` == `8f78cd55e6ada9539a5e88c4debcdea05cab7d7c1c5adb3d43944ef3d290feab` (`tests/test_golden.py`)
  - the real-data January 2024 parent identity starting `9d7eee74…` (`tests/test_integration_derivation.py`)
- Exception contract unchanged: `HashPayloadError` (error id `manifest_inconsistency`) for malformed hash rows; `ParquetFailure` (error id `FAILED_PARQUET_WRITE_OR_READ_BACK`) for Parquet read/schema/decode failures; `ReconciliationMismatch` for content or row-count mismatches.
- `run_pipeline` exit codes (0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED) and idempotent rerun semantics are unchanged.
- Decimal discipline unchanged: binary floats stay forbidden; `render_decimal_18` private-context behavior is untouched; the ambient Decimal context is never read or mutated (`test_hashing_module_never_touches_the_ambient_context` must stay green).
- Benchmark wall-clock numbers are non-acceptance evidence. The only benchmark-based acceptance criteria are the pinned peak-memory reductions in T4.

## 4. Observed repository seams to reuse

These were verified against the baseline commit; cite them rather than inventing APIs:

### 4.1 Hashing (`src/quantara/hashing.py`)

- `canonical_content_hash(fingerprint, rows)` (currently lines ~200–211): builds `parts = [domain, NUL, fingerprint, NL]`, appends `canonicalize(canonical_row_array(row)) + NL` per row, returns `sha256_hex(b"".join(parts))`.
- `research_content_hash(fingerprint, rows)` (~298–317): identical framing under `RESEARCH_CONTENT_HASH_DOMAIN` with `research_row_array`.
- `canonical_row_array` / `research_row_array` validators, `render_decimal_18`, `sha256_hex` — reuse unchanged.
- `validation_content_hash` and `evaluation_content_hash` are single-artifact framings — do not touch.

### 4.2 Production call sites to convert from list to generator (exactly four hunks)

1. `src/quantara/pipeline.py` ~429–431: `canonical_content_hash(fingerprint, [row.to_content_array() for row in assembled])`
2. `src/quantara/research_pipeline.py` ~373–377 (parent-closure recomputation): `canonical_content_hash(fingerprint, [row.to_content_array() for row in decoded_rows])`
3. `src/quantara/derive_pipeline.py` ~408–412 (parent-closure recomputation): `canonical_content_hash(expected_fingerprint, [row.to_content_array() for row in decoded_rows])`
4. `src/quantara/derive_pipeline.py` ~855–857 (derived-content hash): `canonical_content_hash(fingerprint, [row.to_content_array() for row in bars])`

Each iterable is consumed exactly once (verified); generator conversion is behavior-neutral. The `render_content_rows` helpers (`research_pipeline.py` ~227, `validation_pipeline.py` ~147) stay untouched — they feed small 1h tables.

### 4.3 Canonical read-back (`src/quantara/canonical.py`)

- `read_canonical_rows(path)` and `reconcile_rows(source_rows, parquet_rows)` stay unchanged (public API used by derive/research pipelines and tests).
- `write_canonical_parquet`, `PARQUET_SCHEMA`, `WRITER_CONFIG` stay unchanged.
- The pipeline switch point is `src/quantara/pipeline.py` ~393–394: `persisted_rows = read_canonical_rows(parquet_path)` then `reconcile_rows(assembled, persisted_rows)`.

### 4.4 Stage APIs for the harness

- `parse_rows(text, descriptor)` and `decode_member(bytes)` (`src/quantara/parsing.py`)
- `assemble_canonical_rows(rows, descriptor)` (`src/quantara/canonical.py`)
- `evaluate_quality(assembled, descriptor, source_order_valid=…, expected_count=…)` (`src/quantara/quality.py`)
- `schema_fingerprint()` (`src/quantara/hashing.py`)
- `load_descriptor(path)` (`src/quantara/descriptor.py`); a synthetic descriptor mirrors `VALID_DESCRIPTOR_YAML` from `tests/conftest.py` with the `period.start`/`period.end` pair covering exactly the corpus minutes (`expected_row_count` is derived automatically as `(end - start) // 1 minute`).

## 5. Exact file allowlist

Implementation changes must remain a subset of this list.

### 5.1 New files

```text
docs/superpowers/plans/2026-08-27-performance-slice-007-baseline-and-streaming.md   (T0 only)
benchmarks/__init__.py
benchmarks/stage_baseline.py
tests/test_stage_baseline.py
tests/test_streaming_hash.py
tests/test_reconcile_stream.py
```

### 5.2 Modified files (exact hunks only)

```text
pyproject.toml                   — add "benchmarks" to [tool.ruff] src (T1)
src/quantara/hashing.py          — internal bodies of canonical_content_hash and research_content_hash only (T2)
src/quantara/pipeline.py         — two hunks: generator call site ~429; reconcile switch ~393 (T2/T3)
src/quantara/research_pipeline.py — one hunk: generator at ~375 (T2)
src/quantara/derive_pipeline.py  — two hunks: generators at ~409 and ~855 (T2)
src/quantara/canonical.py        — additive: new reconcile_parquet + __all__ export (T3)
benchmarks/stage_baseline.py     — one-line mirror of the T2 production call-site change (the T3 reconciliation switch is picked up automatically by the import dispatch built in T1)
```

No other file may change, including `uv.lock`, `README.md`, any `configs/` file, and anything under `data/`.

## 6. Forbidden changes

- No modification of `validation_pipeline.py`, `evaluation_*.py`, `features.py`, `folds.py`, `fold_stats.py`, `quality.py`, `aggregation.py`, `publication.py`, `manifests.py`, `cli.py`, `descriptor.py`, `jcs.py`, `archive.py`, `acquisition.py`, `errors.py`, or any existing test file.
- No change to `validation_content_hash` / `evaluation_content_hash`, `WRITER_CONFIG`, `PARQUET_SCHEMA`, domain constants, schema versions, or column registries.
- No dependency, lockfile, Python-version, pytest, ruff-rule, or xdist configuration changes beyond the single `[tool.ruff] src` addition.
- No weakening, deletion, or reclassification of any existing test, fixture, or frozen anchor.
- No writes inside `data/` and no tracked files under `data/` (`git ls-files data` must stay empty; `git status --ignored --short data` must show `!! data/`).
- No force-push, history rewrite, or `git add .`; stage only allowlisted files.
- No network access in the new benchmark harness or new tests; the only networked work is the final integration suite, which already exists.

## 7. Tasks

Execute in order. Each task ends with one conventional commit. Focused tests inside the task loop; the complete suites run once in T4.

### T0 — Preflight and plan commit

Before anything else, verify and paste the outputs of:

```bash
git rev-parse HEAD origin/main     # both must equal 9973b10cb069bcba96e1fdcf8adc78689dcaef3c
git status --short --branch        # clean, main synced with origin/main
git config user.email              # the GitHub noreply identity
git ls-files data                  # empty
git status --ignored --short data  # !! data/
```

A descendant of the baseline whose only extra commit is this plan document is also a valid start (idempotent rerun). Any other drift: report `BLOCKED`.

Then write this entire document verbatim to `docs/superpowers/plans/2026-08-27-performance-slice-007-baseline-and-streaming.md`, lint it with a temporary outside-repository config, and commit:

```bash
# create {"config":{"MD013": false}} as a temp file OUTSIDE the repo, then:
npx --yes markdownlint-cli2@0.23.2 --config <temp-config> docs/superpowers/plans/2026-08-27-performance-slice-007-baseline-and-streaming.md
# expect: zero issues; delete the temp config afterward
git add docs/superpowers/plans/2026-08-27-performance-slice-007-baseline-and-streaming.md
git commit -m "docs: add performance slice 007 implementation plan"
git show --stat --oneline HEAD     # exactly one file changed
```

**Acceptance:** markdownlint reports zero issues; the commit contains exactly the one plan file; working tree clean.

### T1 — Stage baseline harness

**RED:** create `tests/test_stage_baseline.py` with exactly these four tests (they fail while `benchmarks/` does not exist):

1. `test_synthetic_corpus_is_deterministic` — building the corpus twice with the same seed yields identical CSV text and identical descriptor canonical semantics.
2. `test_baseline_evidence_shape` — `run_baseline(row_count=240, repeats=1, …)` returns a JSON-serializable dict with keys `harness_version`, `row_count`, `repeats`, `stages`, `environment`; `stages` contains exactly the six names `parse`, `assemble`, `quality`, `parquet_write`, `verify_parquet`, `content_hash`, each with `seconds_all` (list), `seconds_median` (float ≥ 0), `tracemalloc_peak_bytes` (int ≥ 0).
3. `test_baseline_cli_emits_json` — `main(["--rows", "240", "--repeats", "1", "--json"])` returns 0 and stdout is valid JSON with the pinned shape (use `capsys`).
4. `test_parse_stage_corpus_passes_production_validation` — `parse_rows(decode_member(corpus_bytes), descriptor)` returns exactly `row_count` rows without error, proving the synthetic corpus and descriptor pass production validation unchanged.

The test file adds the repository root to `sys.path` (`sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`) before importing `benchmarks.stage_baseline`.

**GREEN:** implement `benchmarks/__init__.py` (empty) and `benchmarks/stage_baseline.py`:

- Module imports only: stdlib (`argparse`, `json`, `platform`, `random`, `sys`, `tempfile`, `time`, `tracemalloc`, `pathlib`) and `quantara.descriptor`, `quantara.parsing`, `quantara.canonical`, `quantara.quality`, `quantara.hashing`. No `httpx`, no network, no writes outside a `tempfile.mkdtemp` scratch dir that is removed at exit.
- `harness_version = "quantara-stage-baseline/1"`.
- `build_corpus(row_count, seed=20260827)` — contiguous one-minute rows starting at `2024-01-01T00:00:00Z` mirroring the 12-field `HEADER` contract from `quantara.parsing`; deterministic varied values from the seed, including some 18-fractional-digit prices; plus a synthetic descriptor mirroring `VALID_DESCRIPTOR_YAML` from `tests/conftest.py` with `period.start = 2024-01-01T00:00:00Z` and `period.end` = start + `row_count` minutes, loaded through `load_descriptor`. If the v1 loader rejects a period longer than one calendar month at large `row_count`, cap only the `parse` stage corpus at 44,640 rows and record that constraint in the final report; all other stages still time at the requested row count (they consume rows directly and only use descriptor identity fields).
- `run_baseline(row_count, repeats, workdir)` — for each stage, run it `repeats` times recording `time.perf_counter` deltas plus `tracemalloc` peak (start / `reset_peak()` / measure / stop around the median run). Stage implementations call the production APIs listed in §4.4; the `verify_parquet` stage uses the production dispatch: `reconcile_parquet(assembled, parquet_path)` when importable, else the legacy `read_canonical_rows` + `reconcile_rows` pair (so the stage name stays comparable before and after T3). The `content_hash` stage calls `canonical_content_hash(schema_fingerprint(), …)` over the assembled rows exactly as `pipeline.py` does at that HEAD (list comprehension now; T2 mirrors the production generator change here in the same commit).
- `main(argv=None) -> int` — argparse with `--rows` (default 44640), `--repeats` (default 3), `--json`; `--json` prints the evidence dict as JSON to stdout, otherwise a human-readable table; returns 0.
- Add `"benchmarks"` to `[tool.ruff] src` in `pyproject.toml` (one line).

**Capture the pre-change baseline (evidence, not committed):** run

```bash
uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

Save both JSON outputs to files outside the repository and paste them into the final report. Exit code 0 required.

**Acceptance:**

```bash
uv run pytest tests/test_stage_baseline.py -q    # 4 passed
uv run ruff check .                              # 0 issues
git add benchmarks/__init__.py benchmarks/stage_baseline.py tests/test_stage_baseline.py pyproject.toml
git commit -m "feat(bench): add stage baseline harness"
```

### T2 — Streaming row-framed content hashes

**RED:** create `tests/test_streaming_hash.py` with exactly these six tests (the two memory tests fail on the current collect-and-join implementation):

1. `test_canonical_streaming_matches_join_reference` — an in-test independent reference recomputes the digest as SHA-256 over `domain + NUL + fingerprint.lower() + NL + jcs_canonicalize(row) + NL …` joined as one bytes object (using `quantara.jcs.canonicalize` directly, bypassing the row validator), and must equal `canonical_content_hash` output for the five golden fixture rows loaded from `tests/fixtures/golden/expected.json` (`rows` key) and for a seeded synthetic corpus of 300 canonical rows.
2. `test_research_streaming_matches_join_reference` — same parity check for `research_content_hash` over a seeded synthetic corpus of valid research rows (7 fields, Q18-string or `None` per `RESEARCH_COLUMNS`).
3. `test_content_hash_accepts_lazy_iterators` — both hash functions return the same digest for the same rows supplied as a `list`, a generator, and a tuple-iterator.
4. `test_malformed_row_mid_stream_raises_hash_payload_error` — a `float` planted mid-corpus raises `HashPayloadError` (error id `manifest_inconsistency`) whether rows arrive as a list or a generator.
5. `test_canonical_content_hash_bounds_peak_memory` — with a pre-built corpus of 30,000 canonical content-array rows, start `tracemalloc`, `reset_peak()`, call `canonical_content_hash` over a lazy iterator of the rows, and assert the traced peak is `< 4_000_000` bytes (the current implementation peaks far above 20 MB here: parts list + joined payload), then stop tracing. Also assert the returned digest equals the join reference.
6. `test_research_content_hash_bounds_peak_memory` — same shape for `research_content_hash` over 50,000 synthetic research rows with peak `< 3_000_000` bytes (current implementation peaks above ~15 MB).

**GREEN:** in `src/quantara/hashing.py`, rewrite only the internal bodies of `canonical_content_hash` and `research_content_hash`:

```python
def canonical_content_hash(fingerprint: str, rows: Iterable[Sequence[object]]) -> str:
    digest = hashlib.sha256()
    digest.update(CONTENT_HASH_DOMAIN.encode("ascii"))
    digest.update(b"\x00")
    digest.update(fingerprint.lower().encode("ascii"))
    digest.update(b"\n")
    for row in rows:
        digest.update(canonicalize(canonical_row_array(row)).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
```

and the identical structure for `research_content_hash` under `RESEARCH_CONTENT_HASH_DOMAIN` with `research_row_array`. Signatures, docstrings' contract meaning, validation behavior, and error classes stay unchanged. Then convert the four production call-site hunks listed in §4.2 from list comprehensions to generator expressions, and mirror the `pipeline.py` call-site change (one line) in the harness `content_hash` stage.

**Acceptance:**

```bash
uv run pytest tests/test_streaming_hash.py -q                                  # 6 passed
uv run pytest tests/test_hashing.py tests/test_golden.py -q                    # 21 passed
uv run pytest tests/test_pipeline.py tests/test_pipeline_multi_month.py tests/test_canonical.py tests/test_parquet.py -q   # 40 passed
git add src/quantara/hashing.py src/quantara/pipeline.py src/quantara/research_pipeline.py src/quantara/derive_pipeline.py tests/test_streaming_hash.py benchmarks/stage_baseline.py
git commit -m "perf(hashing): stream row-framed content hashes"
```

### T3 — Streaming Parquet read-back reconciliation

**RED:** create `tests/test_reconcile_stream.py` with exactly these five tests (they fail while `reconcile_parquet` does not exist):

1. `test_reconcile_parquet_round_trip_matches_legacy_pair` — for corpora of 1, 6, 7, 8, 13, and 14 canonical rows written through `write_canonical_parquet`, `reconcile_parquet(source_rows, path, batch_size=7)` succeeds exactly when the legacy `read_canonical_rows` + `reconcile_rows` pair succeeds (boundary sizes straddle the batch size).
2. `test_reconcile_parquet_detects_field_mismatch` — mutating one source row's Decimal makes both `reconcile_parquet` and the legacy pair raise `ReconciliationMismatch`.
3. `test_reconcile_parquet_detects_count_mismatch` — a Parquet written with fewer rows, and separately with extra rows appended, makes `reconcile_parquet` raise `ReconciliationMismatch` (row-count message).
4. `test_reconcile_parquet_rejects_foreign_schema` — a Parquet written under a modified Arrow schema makes `reconcile_parquet` raise `ParquetFailure` with the same error id as `read_canonical_rows`.
5. `test_reconcile_parquet_bounds_peak_memory` — with 30,000 canonical rows written to Parquet, measure `tracemalloc` peak separately for the legacy pair and for `reconcile_parquet(source_rows, path)` (default batch size 8192), with `gc.collect()` and `reset_peak()` between measurements; assert the streaming peak is at most 50% of the legacy peak.

Build corpora with `make_source_row` + `build_canonical_row` and the `valid_path` fixture from `tests/conftest.py`, exactly as existing canonical tests do.

**GREEN:** add to `src/quantara/canonical.py` (additive; export in `__all__`):

```python
def reconcile_parquet(
    source_rows: list[CanonicalRow],
    parquet_path: Path,
    *,
    batch_size: int = 8192,
) -> None:
```

Contract:

- Open via `pyarrow.parquet.ParquetFile`; if its Arrow schema differs from `PARQUET_SCHEMA`, raise `ParquetFailure` (same error id as the read-back path).
- Iterate `iter_batches(batch_size=batch_size)`; per batch, convert columns exactly as `read_canonical_rows` does (cast timestamp columns to `int64` before `to_pylist`; decimals arrive as `Decimal`), zip to rows, render Decimals with `render_decimal_18`, and compare field-by-field against the corresponding slice of `source_rows` using the same semantics as `reconcile_rows`.
- Track the total row count; if it differs from `len(source_rows)`, raise `ReconciliationMismatch` with a row-count message.
- Decode/conversion failures raise `ParquetFailure`; never construct binary floats.
- Peak memory stays bounded at one batch plus the source rows.

Then switch `src/quantara/pipeline.py` ~393–394 to `reconcile_parquet(assembled, parquet_path)` (the `persisted_rows` variable disappears; nothing else uses it), leaving `read_canonical_rows`/`reconcile_rows` in place for their other callers. The harness `verify_parquet` stage automatically picks up `reconcile_parquet` through its import dispatch — no harness edit needed.

**Acceptance:**

```bash
uv run pytest tests/test_reconcile_stream.py -q                                  # 5 passed
uv run pytest tests/test_pipeline.py tests/test_pipeline_multi_month.py tests/test_canonical.py tests/test_parquet.py -q   # 40 passed
git add src/quantara/canonical.py src/quantara/pipeline.py tests/test_reconcile_stream.py
git commit -m "perf(canonical): stream parquet read-back reconciliation"
```

### T4 — Final gates, benchmark comparison, and push

Run the complete gates once on the final unchanged state (the offline suite takes ~12 minutes with `-n 4` on this machine; run it as one sequential block and read every summary, not only the last exit code):

```bash
uv lock --check
uv run ruff check .
uv run pytest -m "not integration" -n 4 --dist=load --durations=15
uv run pytest -m integration
```

Expected: `uv lock --check` OK; ruff reports no issues; the offline suite reports **617 passed** (602 existing + 4 + 6 + 5 new) with at most the pre-existing single warning; the serial networked integration suite reports **11 passed**.

Then capture the post-change benchmark evidence with the exact same commands as T1:

```bash
uv run python -m benchmarks.stage_baseline --rows 44640 --repeats 3 --json
uv run python -m benchmarks.stage_baseline --rows 200000 --repeats 3 --json
```

**Benchmark acceptance (hard):** comparing post-change vs pre-change evidence on the same machine:

- `content_hash` stage `tracemalloc_peak_bytes` at 200,000 rows is at most 40% of the baseline value.
- `verify_parquet` stage `tracemalloc_peak_bytes` at 200,000 rows is at most 60% of the baseline value.
- No stage's `seconds_median` regresses by more than 15% at either scale. A larger regression means `INCOMPLETE` until diagnosed and fixed.
- The golden and integration identity anchors listed in §3 still pass (proven by the suites above).

Then push once:

```bash
git push origin main
git rev-parse HEAD origin/main     # equal
git status --short --branch        # clean and synced
git ls-files data                  # empty
git status --ignored --short data  # !! data/
```

## 8. Failure handling

- Fix task-related failures inside the same bounded task and rerun the affected focused tests; never weaken a test, threshold, or lint rule to go green.
- If a required change is blocked by a file outside the allowlist, stop and report `BLOCKED` with the exact blocker — do not silently widen scope.
- If preflight or any gate discovers an executor already committed part of this plan, do not discard or redo it: read the full diff, verify it against this allowlist, complete only the remaining tasks, and attribute per-commit provenance in the final report.
- A memory threshold that cannot be met with a correct streaming implementation indicates a measurement or corpus defect — diagnose with the harness before touching thresholds; thresholds may only change with an explicit, justified amendment recorded in the final report.
- Windows note: a timed-out long pytest run can leave orphaned processes; after any timeout, inspect process command lines and terminate only confirmed test orphans before rerunning.

## 9. Final evidence report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

- Starting HEAD, plan-commit SHA, and ending HEAD; `git status --short --branch` at the end.
- Per-task red→green evidence: the acceptance commands and their raw terminal outputs (paste output, never prose claims).
- The full pre-change and post-change benchmark JSON for both scales (44,640 and 200,000 rows), plus a comparison table per stage: `seconds_median` before/after and `tracemalloc_peak_bytes` before/after, with the two hard memory ratios computed explicitly.
- Raw outputs of all T4 gates, including the pytest summary lines and the `--durations=15` table.
- Confirmation that every frozen anchor in §3 still holds, citing the passing test names.
- The commit list (`git log --oneline <baseline>..HEAD`) with the conventional messages, and the single push result.
- Any residual limitations (for example a v1 loader period constraint discovered in T1).
