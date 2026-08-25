# Quantara Data Slice 002 — Multi-Timeframe Derivation Implementation Plan

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-25
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-25-multi-timeframe-derivation-design.md`
(predecessor spec §18 requires exactly this subproject; its §19 orders it first after slice 001)

## 1. Goal

Implement Quantara's second vertical slice end to end with test-driven development: derive 1-hour (744 bars) and 1-day (31 bars) klines **only** from complete groups of the verified canonical BTCUSDT perpetual 1-minute dataset for January 2024, evaluate them under the same strict PASS-only quality policy, publish them through the unchanged content-addressed immutable protocol with full lineage back to the parent commit `9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f`, prove idempotency, and cross-check against official Binance 1h/1d archives as independent evidence — without any silent alteration, binary-float contamination, interpolation, parent mutation, or scope creep.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-25-data-slice-002-multi-timeframe-derivation.md
and execute it exactly. Do not modify scope. Follow TDD order. Report
COMPLETE / BLOCKED / INCOMPLETE with actual command output evidence.
```

## 3. Approved inputs

- Governing design: this slice's design specification (proposed above); behavioral requirements derive from it and predecessor §§7, 12–13, 18. The owner approves both documents by launching execution.
- Public identity: `wyze69-sys`; all commits use `258711354+wyze69-sys@users.noreply.github.com` (verified configured locally).
- Legal posture: derivation maps to the existing `normalize_internal` operation (`OWNER_APPROVED_PENDING_COUNSEL`, recorded risk acceptance). The rights record is **not modified**. Commercial/customer/redistribution states remain `UNKNOWN` and blocking. All artifacts stay private and internal-use only.
- Stack pins: unchanged from slice 001 (Python 3.11 via uv; pyarrow 25.0.1, PyYAML 6.0.2, httpx 0.28.1; pytest, hypothesis, ruff line length 100). No new runtime dependencies.
- Verified starting facts: parent dataset published at `data/datasets/binance/usdm/klines/BTCUSDT/1m/year=2024/month=01/` with commit `9d7eee74…`; Parquet object hash `84a8833…`; 44,640 source rows; quality exactly `PASS`.

## 4. Observed starting state

- Branch `main` == `origin/main`, working tree clean, HEAD `7e17ca83b272aff795497d919c26c2f4abfd726e`.
- Slice 001 accepted after independent audit; 194 offline tests green; ruff clean; lockfile verified.
- Relevant existing machinery to **reuse unmodified**: `CanonicalRow`, `write_canonical_parquet`, `read_canonical_rows`, `reconcile_rows`, `PARQUET_SCHEMA`, `WRITER_CONFIG` (`src/quantara/canonical.py`); `sha256_hex`, `canonical_row_array`, `canonical_content_hash`, `render_decimal_18`, `quality_identity` (`src/quantara/hashing.py`); `load_rights_record` (`src/quantara/descriptor.py`); `build_dataset_manifest`, `new_attempt_manifest`, `attempt_id_now`, `write_json` (`src/quantara/manifests.py`); `put_object`, `stage_commit`, `publish_commit`, `verify_commit_graph`, `read_and_verify_current`, `write_current` (`src/quantara/publication.py`).

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
configs/datasets/binance-usdm-btcusdt-1h-2024-01-derived.yaml
configs/datasets/binance-usdm-btcusdt-1d-2024-01-derived.yaml
src/quantara/derive_descriptor.py   # derived-dataset descriptor loading/validation (schema quantara.derived-dataset-descriptor/v1)
src/quantara/aggregation.py         # bucketing, completeness gating, exact OHLCV aggregation, persisted-row adapter
src/quantara/derive_quality.py      # derived-dataset quality evaluator (PASS-only policy v1)
src/quantara/derive_pipeline.py     # lineage-bound derivation orchestration + attempt manifests + exit codes
src/quantara/hashing.py             # modified: schema_fingerprint gains an optional schema-version parameter
src/quantara/publication.py         # modified: existing_commit_matches gains an optional evidence-key parameter
src/quantara/cli.py                 # modified: dispatch on descriptor schema field
tests/conftest.py                   # modified: additive shared helpers only
tests/test_derivation_descriptor.py
tests/test_aggregation.py
tests/test_derive_quality.py
tests/test_derive_pipeline.py
tests/test_derive_recovery.py
tests/test_integration_derivation.py  # marked integration
README.md                           # modified: one appended short section only
```

### 5.2 Forbidden changes

- No edits to: `src/quantara/pipeline.py`, `descriptor.py`, `canonical.py`, `quality.py`, `acquisition.py`, `archive.py`, `parsing.py`, `jcs.py`, `errors.py`, `manifests.py`; the legal rights record; the base dataset descriptor; the governing specs/plans of slice 001; `.github/**`; `.gitignore`.
- No semantic changes to existing tests; `conftest.py` additions must not alter existing fixtures' behavior.
- No new providers, markets, instruments, months, timeframes beyond `1h`/`1d`, features, labels, models, APIs, UI, databases, CI workflows, or remote repository-setting mutations.
- No network access in the default test run; networked work is confined to the integration-marked module invoked explicitly.
- No force-push; no rewriting existing history; `/data/` never enters Git.

## 6. Completion states

- **COMPLETE:** all tasks done; offline suite fully green; real-parent derivation publishes both datasets with quality exactly `PASS` (744 and 31 rows, exact calendar-derived counts and UTC boundaries); reruns demonstrate `VERIFIED_NO_OP` with byte-unchanged commits and pointers; the parent commit and pointer are provably untouched; official-archive cross-checks meet design §12 tolerances; documentation updated and lint-clean.
- **BLOCKED:** parent dataset missing or fails graph verification; rights record does not permit `normalize_internal`; environment prerequisites fail; owner declines this plan's proposed decisions before execution.
- **INCOMPLETE:** implementation exists but any correctness, completeness-gating, reconciliation, lineage, idempotency, or documentation requirement remains unsatisfied.

**Known acceptance risks (surfaced now):** (1) the exact-equality OHLC/count cross-check assumes Binance's higher-timeframe candles are consistent extremes of their own 1m series — if provider-side data revision breaks this, the slice lands INCOMPLETE-by-evidence requiring owner review, never silent tolerance widening; (2) volume-family deltas within `1e-8` are recorded, not hidden.

## 7. Task 0 — Preflight

1. `git status --short --branch` → clean `main`, HEAD `7e17ca8`, synchronized with `origin/main` after a normal fetch; stop on drift.
2. Verify `uv --version`, Python 3.11.x, `git config user.email` → noreply address.
3. Confirm parent artifacts exist locally and `data/` is ignored (`git status --ignored --short data` shows `!! data/`).
4. Create transaction dir `%TEMP%\quantara-slice-002\`; all scratch evidence lives there, outside Git.

## 8. Task 1 — Derived descriptor loader + configs (TDD)

Tests first, red → green:

- New module `derive_descriptor.py`: strict loader for `quantara.derived-dataset-descriptor/v1` — unknown keys rejected; identity fields must equal the loaded base descriptor's approved values exactly; `interval` restricted to `{"1h", "1d"}` (anything else → stable error `unsupported_timeframe`); `period` must equal the base descriptor's period exactly; timeframe must divide the period length with zero remainder (misalignment rejected before any compute); `schema_version` must equal `binance_usdm_kline_{interval}_v1`; `base_dataset_id`/`base_descriptor`/`transformation {name: multi_timeframe_aggregation, version: "1"}` required and shape-checked.
- Frozen dataclass exposing: identities, interval, `timeframe_ms` (3,600,000 / 86,400,000), period datetimes, `expected_row_count` derived purely by calendar math `(end − start) // timeframe_ms`, and `canonical_semantics()` JCS serialization (formatting-independent, including the transformation block and resolved base binding).
- Rejection fixtures: tampered instrument, `interval: 5m`, mid-hour period start, period differing from base, wrong schema_version, unknown key, non-divisible period.
- Semantic-hash stability: two YAML files differing only in formatting/key order hash identically.
- Write the two config YAMLs exactly as design §5.
- Commit `feat(derive-descriptor): validated derived dataset descriptors`.

## 9. Task 2 — Aggregation engine (TDD)

New module `aggregation.py`:

- Persisted-row adapter: reconstruct `CanonicalRow` from `read_canonical_rows` tuples positionally (timestamps arrive as epoch-ms ints; decimals as `Decimal`); reject wrong tuple width or float instances.
- Input contract: strictly ascending unique open times; duplicates raise `DuplicateOpenTime` (reused from `canonical.py`); unordered input is rejected, never silently sorted (design §8).
- Bucketing: epoch-aligned half-open `[B, B + tf)`; membership by minute `open_time_ms`.
- Completeness gate per bucket: exactly `tf_minutes` constituents, contiguous at 60,000 ms, fully covering the window; violations raise `incomplete_group` (new stable error string defined locally) — no interpolation, ever.
- Defensive constituent rule: any `source_ignore != "0"` rejects the group (`nonzero_source_ignore_in_group`).
- Exact aggregation per design §7 table: endpoint open/close, max/min high/low, exact `Decimal` sums for four volume fields, integer sum for `trade_count`, `close = B + tf − 1`, `nominal_available = B + tf`; identity tuple from the derived descriptor.
- Hand-computed fixtures spanning: ordinary hours, an hour boundary crossing, midnight/day boundary, high-precision decimals whose sums exercise trailing-zero rendering (`render_decimal_18`), extreme selection across minutes, incomplete group, duplicate minute, nonzero ignore. Hypothesis property: aggregating any generated valid hour equals a naive independent reference implementation written in the test (fixed seeds).
- Commit `feat(aggregation): exact multi-timeframe bucket aggregation`.

## 10. Task 3 — Derived quality evaluator (TDD)

New module `derive_quality.py`, mirroring `quality.py` structure (Finding/QualityReport shapes reused conceptually; check ids prefixed `derived_`):

- Checks: expected count vs calendar-derived value; exact first/last boundaries; uniqueness; strict ascent; adjacency exactly `timeframe_ms`; OHLC bounds; strictly positive prices; non-negative volumes/count; taker bounds; close-time relation; zero-volume-bucket warning (defensive); reconciliation outcome finding supplied by the pipeline.
- States exactly as policy v1: any warning ⇒ `WARN_BLOCKED`; any failure ⇒ `FAIL`; else `PASS`. Deterministic identity via `quality_identity`.
- Explicit failing fixtures per invariant.
- Commit `feat(derive-quality): derived dataset quality evaluation`.

## 11. Task 4 — Schema fingerprint parameterization (TDD)

- `hashing.schema_fingerprint(schema_version: str = SCHEMA_VERSION)`: payload's `schema_version` field becomes the parameter; column list unchanged.
- Regression proof: the no-argument call equals the frozen slice 001 fingerprint value captured in the transaction dir **before** any edit (reference anchor observed on 2026-08-25 at HEAD `7e17ca8`: `feab7d2bb40de94e3621d6ff9847363eddd52b7fd8cd3c07f66def664da614c8`); assert equality in a test.
- Distinct fingerprints proven for `binance_usdm_kline_1h_v1` and `binance_usdm_kline_1d_v1`; logical-change ⇒ identity-change property re-proven.
- Commit `feat(hashing): version-parameterized schema fingerprints`.

## 12. Task 5 — Publication extension (TDD)

- `publication.existing_commit_matches(data_root, commit_dir, evidence, keys=None)`: optional explicit key tuple; default argument preserves current behavior byte-for-byte (existing tests must pass untouched).
- Derivation will pass keys extended with `"derived_from"` (the lineage block).
- Tests: default-behavior equivalence, extended-key matching, mismatch on tampered lineage.
- Commit `feat(publication): extensible idempotency evidence keys`.

## 13. Task 6 — Derivation pipeline (TDD, offline)

New module `derive_pipeline.py` orchestrating, in order (mirroring `pipeline.py` structure, exit codes 0/2/3/4, attempt manifests via `new_attempt_manifest`):

1. Load + validate derived descriptor; resolve legal record ancestor-walk exactly as slice 001 does; gate on `normalize_internal` alone (design §13) → BLOCKED with diagnostic otherwise.
2. Load base descriptor; locate the parent dataset directory (same path convention, interval segment `1m`); require `current.json`; `read_and_verify_current` + full graph verification including the manifest's Parquet SHA-256 against the referenced `normalized` object → BLOCKED with `parent_dataset_unavailable` on any failure. Record the parent canonical-content hash from the pointer.
3. Read the parent Parquet object through `read_canonical_rows`; adapt rows (Task 2 adapter); aggregate per timeframe; evaluate derived quality → BLOCKED unless exactly `PASS`.
4. Write staged Parquet with the fixed writer config; read back; reconcile every derived row against recomputation field-by-field (exact decimal strings/ints; floats never constructed).
5. Identities: parameterized fingerprint, derived descriptor hash, `canonical_content_hash` over derived rows, Parquet SHA-256; `put_object(kind="normalized")`.
6. Identity evidence = slice 001 key set + `derived_from` lineage block (parent dataset_id, parent content hash, parent Parquet SHA/size, parent descriptor hash, parent fingerprint, transformation `{name, version, timeframe_ms}`). Existing-pointer match ⇒ `VERIFIED_NO_OP`, staging discarded, pointer untouched.
7. Publish: `stage_commit` → `publish_commit` into the derived dataset's `commits/<content_hash>` → `verify_commit_graph` → `write_current` → reopen discovery verification; stale `.staging-*` cleanup mirrors slice 001 recovery.
8. Dataset manifest carries all slice 001 fields plus the lineage block; attempt manifests unchanged in shape; `--dry-run` performs steps 1–2 verification only.

- Offline tests: (a) one end-to-end test publishing the synthetic 44,640-row parent through the real slice 001 `run_pipeline` with the established local-transport fixtures, then deriving both timeframes against that tmp data root; (b) targeted fast tests assembling minimal valid parent graphs directly through publication primitives.
- Commit `feat(derive-pipeline): lineage-bound derivation orchestration`.

## 14. Task 7 — CLI dispatch (TDD)

- `cli.main` peeks the descriptor YAML's `schema` field: `quantara.dataset-descriptor/v1` → `run_pipeline`; `quantara.derived-dataset-descriptor/v1` → derivation pipeline; anything else → exit 3 with `invalid_descriptor`. `--dry-run` works for both. No new flags.
- Commit `feat(cli): descriptor-schema dispatch`.

## 15. Task 8 — Golden offline fixture

Tiny committed fixture (≤ ~120 synthetic minutes spanning two hours and a midnight boundary): parent rows, expected 1h and 1d aggregates, canonical-content hashes, and quality identities computed by an independent script, reviewed, then frozen. Test proves engine output equals them offline. Commit `test(golden): frozen multi-timeframe transformation fixture`.

## 16. Task 9 — Corruption and recovery suite

Scenarios, each asserting hard stops with diagnostics and no discoverable partial graph: parent `current.json` missing/invalid; parent object bytes drifted (hash mismatch pre-compute); parent commit graph incomplete; derived pointer pointing at missing commit; injected failure between object write, commit rename, and pointer replacement (safe orphans reported, never canonical); stale staging discarded; parent legitimately republished with different content ⇒ derived rerun publishes a new lineage-bound commit while the old one stays immutable. Commit `test(recovery): derivation corruption and recovery scenarios`.

## 17. Task 10 — Real-parent integration (marked `integration`)

Explicit invocation `uv run pytest -m integration`. Fails loudly (never skips) if parent artifacts are absent:

1. Full gates re-run first: `uv lock --check`, `uv run ruff check .`, `uv run pytest -m "not integration"`.
2. Derive both timeframes from the retained parent via the CLI: exit 0; quality exactly `PASS`; row counts exactly 744 / 31 with calendar-derived first/last boundaries; manifests carry the lineage block referencing `9d7eee74…`.
3. Rerun both: `VERIFIED_NO_OP`; commits and pointers byte-identical (hashes compared); exactly two new attempt manifests total.
4. Parent immutability proof: parent `current.json` target and commit directory contents hash-identical before/after; `git status` proves `/data/` ignored and nothing staged from it.
Commit (if green) `test(integration): real-parent multi-timeframe derivation acceptance`.

## 18. Task 11 — Official-archive cross-check (marked `integration`)

Inside the marked module, a self-contained verified-download helper (httpx; strict CHECKSUM grammar `^[0-9a-f]{64}  <filename>$`; allow-listed host `data.binance.vision`; bounded retries for eligible transient failures) fetches `BTCUSDT-1h-2024-01.zip` and `BTCUSDT-1d-2024-01.zip` plus checksums. Compare per design §12: `open/high/low/close/count` exact; volume-family `|Δ| ≤ 1e-8` with every delta printed as evidence; any excess delta fails the slice. Results recorded in the transaction dir; official archives never enter the object store or publication identity. Commit (if green) `test(integration): official htf archives cross-check evidence`.

## 19. Task 12 — Documentation, final gates, push

1. Append one README section `## Derived datasets status` (~6 lines): 1h/1d derived internally from the verified January 2024 base; internal-use only; commercial/customer display ineligible while rights are pending counsel review.
2. `markdownlint-cli2@0.23.2` over `README.md` with temporary out-of-repo config `{"MD013": false}` → 0 issues; remove the temp config.
3. Full local gates fresh: lock check, ruff, offline suite, then the integration module once more end-to-end.
4. Push `main` normally once; verify remote head; confirm `/data/` absent remotely (`git ls-files data` empty locally and no `data/` path on origin).

## 20. Failure handling

- Any red gate: fix forward; never weaken an assertion, tolerance, or policy to pass.
- Cross-check exact-field mismatch: treat as an engine-or-provider inconsistency requiring investigation and owner-visible reporting; do not ship with widened tolerances.
- Parent verification failure: BLOCKED before any derived computation; never bypass.
- Post-push defect: new fix commit; revert via `git revert` only.

## 21. Final evidence report

Record actual commands and outputs for: tool versions; red→green evidence per task; frozen pre-edit slice 001 fingerprint equality proof; offline/integration suite results; derived counts, boundaries, quality states, canonical-content and Parquet hashes for both timeframes; `VERIFIED_NO_OP` evidence; parent-immutability hashes; cross-check delta tables; rights state exercised; `git status` cleanliness re `/data/`; commit SHAs pushed; terminal status COMPLETE / BLOCKED / INCOMPLETE with residual limitations. Passing unit tests alone is insufficient.
