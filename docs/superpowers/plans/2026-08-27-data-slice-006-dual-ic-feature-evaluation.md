# Quantara Data Slice 006 — Dual-IC Feature Evaluation Implementation Plan

**Status:** Proposed implementation plan; awaiting owner review before execution
**Date:** 2026-08-27
**Project root:** `D:\PROJECT\Quantara`
**Implementation baseline:** `b54700791336d5b4132898de8ea83a371c564c9f`
**Governing design:** `docs/superpowers/specs/2026-08-27-dual-ic-feature-evaluation-design.md`

## 1. Goal

Implement one bounded, immutable feature-evaluation lane over the authenticated BTCUSDT 1h Q1 2024 research and validation parents.

The lane computes deterministic Decimal Pearson and average-rank Spearman information coefficients for the four approved `btcusdt_core_v1` features against `l_fwdret_24` over the 25 out-of-sample validation test folds. It publishes exactly 100 fold-feature records and 200 Q18 IC values, plus eight cross-fold summaries, through Quantara's existing content-addressed publication protocol.

This remains descriptive internal analysis. It does not train a model, select or rank features for action, search parameters, generate signals, run a backtest, calculate significance, or make a performance claim.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-27-data-slice-006-dual-ic-feature-evaluation.md completely and execute it exactly in D:\PROJECT\Quantara.

Follow T0 through T12 in order. Use focused red-to-green TDD, preserve every forbidden scope boundary, fix task-related failures before continuing, run the final sensitive-state gate once on the final unchanged state, inspect real attempt manifests and immutable graphs, and report COMPLETE, BLOCKED, or INCOMPLETE with raw commands and results. Do not push until every required gate passes. Then STOP.
```

The prompt is agent-independent. OpenCode, Codex CLI, or another filesystem-and-terminal coding agent may execute it without changing the plan contract.

## 3. Approved inputs and fixed contracts

- Governing design: the committed Slice 006 specification named above.
- Current implementation baseline: `b54700791336d5b4132898de8ea83a371c564c9f`; the earlier `5ea2207...` value in the design records its planning start, not the implementation checkout.
- Legal operation: `analyze_internal` under `configs/legal/binance-usdm-provider-rights.v2.yaml`.
- Parent descriptors:
  - `configs/datasets/binance-usdm-btcusdt-1h-2024-q1-research-core-v1.yaml`
  - `configs/datasets/binance-usdm-btcusdt-1h-2024-q1-validation-wf-v1.yaml`
- Evaluation descriptor identity:
  - schema: `quantara.evaluation-descriptor/v1`
  - dataset type: `feature_evaluation`
  - dataset ID: `binance_usdm_btcusdt_klines_1h_2024_q1_evaluation_dual_ic_v1`
  - evaluation set: `btcusdt_core_v1_dual_ic_v1`, version `1`
  - schema version: `quantara_feature_evaluation_v1`
  - quality policy: `1`
- Feature order:
  1. `f_ret_1`
  2. `f_roc_60`
  3. `f_rvol_20`
  4. `f_volratio_20`
- Target: `l_fwdret_24`.
- Metric order: `pearson_ic`, then `spearman_ic`.
- Decimal arithmetic: precision 50, `ROUND_HALF_EVEN`, `Emin=-999999`, `Emax=999999`, `capitals=1`, `clamp=0`, with only `InvalidOperation`, `DivisionByZero`, and `Overflow` trapped.
- Storage quantum: `0.000000000000000001`.
- No new runtime dependency or lockfile change is authorized.

## 4. Observed repository seams to reuse

Use these existing public contracts without modifying their defining modules unless that file is in the allowlist:

### 4.1 Parent descriptors and authentication

- `load_validation_descriptor()` and nested `ValidationDescriptor.parent_descriptor` from `validation_descriptor.py`.
- `verify_validation_current_graph()` from `validation_pipeline.py`.
- `verify_research_current_graph()` and `read_research_rows()` from `research_pipeline.py`.
- `load_rights_record()` and `RightsRecord.permits()` from `descriptor.py`.
- `research_schema_fingerprint()`, `research_content_hash()`, `validation_schema_fingerprint()`, and `validation_content_hash()` from `hashing.py`.

The two graph verifiers authenticate pointer structure, manifest digest, immutable commit graph, object references, quality identity, exact `PASS`, and parent commit equations. They return content evidence, not the complete parent manifest or decoded object. The evaluation pipeline must layer descriptor-specific Q1 checks, exact retained-byte recomputation, and pointer-snapshot stability on top; it must not weaken or replace the existing verifiers.

### 4.2 Publication and evidence

Reuse unchanged:

- `store_object()` and its truthful `.created` result;
- `existing_commit_matches()`;
- `stage_commit()`;
- `publish_commit()`;
- `verify_commit_graph()`;
- `write_current()`;
- `PUBLICATION_PROTOCOL_VERSION`;
- `attempt_id_now()`;
- `build_dataset_manifest()`;
- `environment_evidence()`;
- `new_attempt_manifest()`;
- `write_json()`;
- `quality_identity()`;
- `descriptor_hash()`;
- `sha256_hex()`;
- `canonicalize()`.

Do not copy validation pipeline behavior that glob-deletes sibling `.staging-*` directories. Slice 006 may remove only paths owned by its current attempt.

### 4.3 Test and integration patterns

Reuse additively:

- `validation_cfg_tree()`, `write_research_descriptor()`, and `write_validation_descriptor()` from `tests/conftest.py`;
- Q1 parent publication and pointer restoration from `tests/test_integration_q1.py`;
- current-invocation milestone assertions from research, validation, and derive recovery tests;
- retained-commit tree-digest checks and attempt-manifest inspection patterns.

## 5. Exact file allowlist

Implementation changes must remain a subset of this list.

### 5.1 New production and configuration files

```text
configs/datasets/binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml
src/quantara/evaluation_descriptor.py
src/quantara/evaluation_metrics.py
src/quantara/evaluation_quality.py
src/quantara/evaluation_pipeline.py
```

### 5.2 Modified production files

```text
src/quantara/hashing.py
src/quantara/cli.py
```

Both modifications are additive. All predecessor hashes and CLI routes must remain byte-compatible in behavior.

### 5.3 Test files

```text
tests/conftest.py
tests/test_evaluation_descriptor.py
tests/test_evaluation_hashing.py
tests/test_evaluation_metrics.py
tests/test_evaluation_quality.py
tests/test_evaluation_pipeline.py
tests/test_evaluation_recovery.py
tests/test_integration_evaluation.py
```

`tests/conftest.py` changes are additive evaluation builders only. Existing fixture behavior must not change.

### 5.4 Documentation

```text
README.md
```

Append only a short factual internal-use Slice 006 status section after real acceptance passes. Do not present IC direction or magnitude as predictive performance.

### 5.5 Forbidden files and behavior

Do not edit:

- `publication.py`, `manifests.py`, `jcs.py`, `errors.py`, or `canonical.py`;
- any existing research, validation, derived, or base descriptor/pipeline/quality module;
- existing dataset descriptors or legal records;
- dependencies, `pyproject.toml`, `uv.lock`, CI, `.gitignore`, existing specs, or predecessor plans;
- existing tests outside the exact allowlist.

Do not add:

- NumPy/Pandas/SciPy correlation paths or binary-float fallback;
- model training, feature selection/ranking decisions, threshold or horizon search;
- pooled IC, p-values, significance, confidence intervals, signals, backtests, PnL, or execution assumptions;
- API, dashboard, or customer-facing output;
- parent-pointer rewrites during normal evaluation;
- sibling staging deletion, lock theft, automatic stale-lock removal, immutable commit overwrite, or CAS overwrite;
- network access outside marked serial integration tests;
- tracked files under `data/`.

## 6. Proposed module boundaries

### 6.1 `evaluation_descriptor.py`

Public surface:

```text
EVALUATION_SCHEMA
EVALUATION_DATASET_TYPE
EVALUATION_SET
APPROVED_FEATURES
APPROVED_TARGET
APPROVED_METRICS
SCHEMA_VERSION
QUALITY_POLICY_VERSION
APPROVED_LEGAL_RECORD
EvaluationDescriptor
EvaluationDescriptorError
load_evaluation_descriptor
```

`EvaluationDescriptor` stores the loaded `ValidationDescriptor` with `compare=False` and exposes `canonical_semantics()` over validated fields only.

### 6.2 `evaluation_metrics.py`

Public surface:

```text
DECIMAL_CONTEXT
DECIMAL_CONTRACT
STORAGE_QUANTUM
MetricDomainError
average_ranks
evaluate_fold_feature
build_evaluation_records
build_evaluation_summaries
```

Keep Pearson and Spearman helpers private unless tests need a narrow public pure API. The module owns arithmetic, pair filtering, Q18 boundary quantization, record construction, and summary construction. It performs no I/O or publication.

Do not use `render_decimal_18()` for computed IC values. That helper intentionally rejects values requiring rounding, while Slice 006 requires one `ROUND_HALF_EVEN` quantization at the storage boundary.

### 6.3 `evaluation_quality.py`

Public surface:

```text
QUALITY_POLICY_VERSION
CHECK_IDS
Finding
EvaluationQualityReport
evaluate_evaluation_quality
```

The evaluator emits the exact 13 ordered design findings and freshly verifies metrics, summaries, structure, stable parent identities, and prospective identities.

Operational parent pointer manifest digests must not participate in quality identity. They belong only in the committed manifest's `parent_discovery` block. This prevents a logically equivalent parent republication from producing a same analytical commit address with a conflicting `content.json` quality identity.

### 6.4 `evaluation_pipeline.py`

Public surface:

```text
EVALUATION_EVIDENCE_KEYS
evaluation_commit_identity
build_evaluation_artifact
verify_evaluation_current_graph
run_evaluation_pipeline
```

Keep data-root resolution, parent-snapshot authentication, lock, attempt, cleanup, quality-envelope, and failure helpers private.

## 7. Tasks

Every task begins with a failing focused test, ends green, and records the exact command and output before its commit. Do not run the full suite after each task; use focused checks until T12.

### T0 — Preflight and contract map

Before editing:

```bash
git rev-parse --show-toplevel
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git ls-files data
```

Require:

- exact root `D:/PROJECT/Quantara`;
- clean `main` at the plan baseline or a clearly reviewed fast-forward descendant;
- no unrelated working-tree changes;
- `data/` ignored and untracked.

Post a short implementation map naming the exact parent-authentication, hashing, publication, lock, and CLI seams. Stop `BLOCKED` if repository drift invalidates the allowlist or contracts.

### T1 — Strict descriptor and real Q1 config

**Files:**

```text
src/quantara/evaluation_descriptor.py
configs/datasets/binance-usdm-btcusdt-1h-2024-q1-evaluation-dual-ic-v1.yaml
tests/conftest.py
tests/test_evaluation_descriptor.py
```

Write tests first for:

- exact root key set and non-object rejection;
- every missing and unknown key;
- exact schema, dataset type, evaluation set, schema version, quality policy, and legal record;
- exact feature, target, and metric identities and order;
- duplicate, omitted, substituted, and reordered entries;
- parent provider, instrument, base dataset ID, period, research feature set, validation scheme, fold set, `test_size=72`, `min_train_size=336`, and derived embargo `24`;
- the exact dataset-ID derivation from the validation parent research base dataset ID;
- canonical semantic stability under YAML key reordering;
- the real committed config loading successfully.

Recognized evaluation-schema field failures are `BLOCKED/2` when routed through the evaluation pipeline. Pre-dispatch malformed or unknown schema behavior remains a later CLI contract.

Focused gate:

```bash
uv run pytest tests/test_evaluation_descriptor.py -q
uv run ruff check src/quantara/evaluation_descriptor.py tests/test_evaluation_descriptor.py tests/conftest.py
```

Suggested commit: `feat(evaluation): strict dual-IC descriptor`

### T2 — Domain-separated hashing and identity vectors

**Files:**

```text
src/quantara/hashing.py
src/quantara/evaluation_pipeline.py
tests/test_evaluation_hashing.py
```

Add only:

- `EVALUATION_CONTENT_HASH_DOMAIN = "quantara-evaluation-content-v1"`;
- `EVALUATION_SCHEMA_VERSION = "quantara_feature_evaluation_v1"`;
- `evaluation_schema_fingerprint(...)` using the exact design §9.3 JCS payload;
- `evaluation_content_hash(...)` with exact domain/NUL/fingerprint/LF/artifact-bytes/LF framing.

`evaluation_commit_identity(...)` belongs in `evaluation_pipeline.py` (section 6.4 surface), not in `hashing.py`; T2 only adds the two hashing helpers above to `hashing.py`. The plan holds the one Q18 quantization and pre/post `[-1,1]` bounds such that real vectors never fall on a spurious boundary.

Require lowercase digest inputs and reject unsupported artifact types rather than coercing them. Verify every predecessor no-argument fingerprint and frozen hash remains unchanged.

Frozen identity vector for the authenticated retained Q1 parents:

- Parent validation fingerprint: `06f0cff54df3b5f61943423f6925c6e4ab7b4ed323c59eeb2a91f2d309d17c1c`.
- Evaluation schema fingerprint: `d454a7e142ac19cfbb75ccabd53f1fb20f26bc471968c6e4b84203030aa10843`.

Focused gate:

```bash
uv run pytest tests/test_evaluation_hashing.py tests/test_hashing.py -q
uv run ruff check src/quantara/hashing.py src/quantara/evaluation_pipeline.py tests/test_evaluation_hashing.py
```

Suggested commit: `feat(hashing): evaluation identity domains`

### T3 — Exact Decimal Pearson and Spearman engine

**Files:**

```text
src/quantara/evaluation_metrics.py
tests/test_evaluation_metrics.py
```

Use the fully specified private context for every sum, subtraction, multiplication, division, rank average, square root, median, and summary mean. Never read or mutate the ambient Decimal context.

Implement:

- paired non-null selection with independent feature-null, target-null, valid, and excluded counts;
- Pearson using the exact design operation order;
- deterministic average ranks with 1-based positions and exact odd/even tie-group means;
- Spearman as the same Pearson implementation over restored-order ranks;
- one Q18 quantization at storage only;
- pre- and post-quantization `[-1,1]` checks;
- loud undefined-metric rejection.

Red-to-green matrix:

- hand-computed Pearson;
- perfect positive and negative correlation;
- a valid zero-correlation fixture;
- deterministic canonical row-order summation;
- odd and even tie groups;
- all-equal and partially tied ranks;
- Spearman invariance under exact strictly increasing transforms preserving equality groups;
- overlapping feature/target nulls;
- fewer than two pairs;
- zero feature and target variance;
- bool, float, malformed Decimal, NaN, and infinities;
- Q18 half-even boundary cases;
- ambient-context mutation;
- Hypothesis determinism and tie-group properties.

Focused gate:

```bash
uv run pytest tests/test_evaluation_metrics.py -q
uv run ruff check src/quantara/evaluation_metrics.py tests/test_evaluation_metrics.py
```

Suggested commit: `feat(evaluation): exact dual-IC metrics`

### T4 — Records, summaries, and canonical artifact

**Files:**

```text
src/quantara/evaluation_metrics.py
src/quantara/evaluation_pipeline.py
tests/test_evaluation_metrics.py
tests/test_evaluation_pipeline.py
```

Build each record from only `research_rows[test_start:test_end]`. Use explicit research tuple indices:

```text
0 open_time_ms
1 f_ret_1
2 f_roc_60
3 f_rvol_20
4 f_volratio_20
5 l_fwdret_24
6 l_fwddir_24
```

Require:

- fold-major, feature-major record order;
- exact record key set and count reconciliation;
- feature-major, metric-major summary order;
- summaries computed from stored Q18 values;
- correct odd and even median rules;
- exact sign counts, min, max, median, and equal-weight mean;
- no pooled metric;
- exact artifact root keys, parent blocks, decimal contract, and disclaimer;
- JCS artifact bytes plus exactly one LF.

Use small hand-built fixtures for unit tests. Do not use production metric helpers as the expected-value oracle in the same test.

Focused gate:

```bash
uv run pytest tests/test_evaluation_metrics.py tests/test_evaluation_pipeline.py -k "record or summary or artifact or canonical" -q
```

Suggested commit: `feat(evaluation): canonical IC artifact`

### T5 — Exact ordered PASS-only quality policy

**Files:**

```text
src/quantara/evaluation_quality.py
tests/test_evaluation_quality.py
```

Emit these checks exactly once in this order:

```text
parents_authenticated
lineage_binding
descriptor_identity
fold_ranges
row_alignment
record_matrix
pair_counts
numeric_domain
metric_recomputation
metric_bounds
summary_recomputation
canonical_structure
identity_contract
```

Quality inputs include authenticated stable parent evidence, validation artifact, research rows, records, summaries, canonical artifact bytes, schema fingerprint, content hash, `evaluation_from`, and prospective commit identity.

Mutate one invariant per test:

- parent and validation-to-research lineage mismatch;
- descriptor identity mismatch;
- malformed, overlapping, reordered, or out-of-range folds;
- row-count or open-time misalignment;
- missing, duplicate, reordered, or fabricated records;
- invalid null/pair counts;
- float, non-finite, malformed, or out-of-bound metrics;
- metric recomputation mismatch;
- summary sign/count/aggregate mismatch;
- noncanonical root/record/summary structure or serialization;
- schema/content/commit identity mismatch.

A valid weak, zero, negative, or unstable metric set must still receive `PASS`. Metric favorability is never a quality condition.

Focused gate:

```bash
uv run pytest tests/test_evaluation_quality.py -q
uv run ruff check src/quantara/evaluation_quality.py tests/test_evaluation_quality.py
```

Suggested commit: `feat(evaluation): PASS-only quality contract`

### T6 — Stable two-parent authentication and full dry-run

**Files:**

```text
src/quantara/evaluation_pipeline.py
tests/test_evaluation_pipeline.py
```

Authentication order:

1. Strictly load the recognized evaluation descriptor.
2. Load rights and require `analyze_internal`.
3. Resolve the validation directory from the nested descriptor identity.
4. Read and retain the exact validation pointer bytes.
5. Call `verify_validation_current_graph()`.
6. Re-read and require byte-identical validation pointer bytes.
7. Load the authenticated manifest and artifact object selected by that pointer.
8. Require Q1 dataset, period, 2,184 rows, 25 folds, approved fold set, and exact `PASS`.
9. Recompute validation object SHA, byte size, schema fingerprint, canonical content hash, and commit equation.
10. Extract the bound research lineage.
11. Resolve the research directory from the validation parent descriptor.
12. Read and retain the exact research pointer bytes.
13. Call `verify_research_current_graph()`.
14. Re-read and require byte-identical research pointer bytes.
15. Require current research stable identities to match validation lineage exactly.
16. Recompute research object SHA, byte size, canonical row content hash, and commit equation.
17. Reconcile 2,184 rows, strict open-time ascent, fold ranges, and validation statistics.
18. Build records, summaries, artifact, prospective identities, and fresh quality.
19. Immediately before any non-dry-run publication, re-read both pointers and require equality with the authenticated snapshots. A changed parent pointer is `BLOCKED`; never mix snapshots.

Dry-run executes steps 1 through 18, including all metrics and quality, then returns `0` without creating an attempt ID file, lock, staging directory, object, commit, pointer, or attempt manifest. Quality failure in dry-run returns `2` and remains write-free.

Parent `manifest_sha256` values are captured for operational `parent_discovery`, but are excluded from artifact bytes, schema/content/commit identity, `evaluation_from`, `content.json`, quality findings, and quality identity.

Focused gate:

```bash
uv run pytest tests/test_evaluation_pipeline.py -k "parent or lineage or pointer_snapshot or dry_run or quality" -q
```

Suggested commit: `feat(evaluation): authenticated parent computation`

### T7 — CLI dispatch and evidence taxonomy

**Files:**

```text
src/quantara/cli.py
src/quantara/evaluation_pipeline.py
tests/test_evaluation_descriptor.py
tests/test_evaluation_pipeline.py
```

Add one evaluation schema route to `cli.py`. Preserve every existing route and pre-dispatch failure contract.

Verify:

- malformed YAML, non-object root, missing schema, and unknown schema return `3` with no pipeline attempt evidence;
- a recognized evaluation schema with invalid fields reaches the evaluation pipeline and returns `BLOCKED/2` with truthful attempt evidence when not dry-run;
- rights loading operational failure returns `FAILED/3`;
- legal ineligibility returns `BLOCKED/2`;
- dry-run remains the explicit no-attempt exception.

Focused gate:

```bash
uv run pytest tests/test_evaluation_descriptor.py tests/test_evaluation_pipeline.py -k "cli or dispatch or schema or attempt or rights or legal" -q
```

Suggested commit: `feat(cli): route evaluation descriptors`

### T8 — Exclusive lock and immutable publication

**Files:**

```text
src/quantara/evaluation_pipeline.py
tests/test_evaluation_pipeline.py
tests/test_evaluation_recovery.py
```

After exact in-memory `PASS` and the final parent-pointer snapshot check:

1. Generate the attempt ID in memory.
2. Atomically create `evaluation.lock` with create-if-absent semantics.
3. Write and fsync owner evidence containing exactly the attempt ID.
4. Create only this invocation's unique global and commit-staging paths.
5. Publish canonical artifact bytes with `store_object()`.
6. Build the eight-key `content.json`.
7. Build quality and manifest files.
8. Detect an authenticated byte-identical no-op under the lock.
9. Stage and atomically promote a new immutable commit when needed.
10. Replace `current.json` atomically.
11. Read back through `verify_evaluation_current_graph()`.
12. Write truthful attempt evidence.
13. Clean only owner paths and release only the owner lock in `finally`.

`EVALUATION_EVIDENCE_KEYS` is exactly:

```text
descriptor_sha256
schema_fingerprint
parser_version
canonical_content_hash
quality_identity
object_refs
evaluation_from
evaluation_commit_identity
```

`verify_evaluation_current_graph()` must authenticate:

- exact pointer keys and protocol;
- pointer manifest digest;
- immutable commit marker and object references;
- exact eight content keys;
- manifest/content agreement;
- quality structure, identity, and exact `PASS`;
- artifact SHA and byte size;
- canonical artifact structure and bytes;
- evaluation schema/content/commit equations;
- complete stable dual-parent lineage evidence.

Lock rules:

- acquisition occurs before any evaluation object or staging write;
- an existing lock is `BLOCKED/2` and is never deleted or stolen;
- only a lock creator may attempt release;
- release re-reads the lock and requires exact owner attempt ID;
- a crashed stale lock requires external operator review;
- no `.staging-*` glob deletion;
- cleanup failure preserves the primary result and is recorded truthfully.

Focused gate:

```bash
uv run pytest tests/test_evaluation_pipeline.py tests/test_evaluation_recovery.py -k "publish or graph or no_op or lock or cleanup" -q
```

Suggested commit: `feat(evaluation): immutable locked publication`

### T9 — Recovery, corruption, and truthful milestones

**Files:**

```text
src/quantara/evaluation_pipeline.py
tests/test_evaluation_recovery.py
```

Cover:

- missing, malformed, wrong-period, or January parent pointers;
- parent pointer change during authentication or before publication;
- validation manifest/artifact tamper;
- research manifest/Parquet tamper;
- validation-to-research lineage mismatch;
- non-PASS parent quality;
- undefined metrics and quality failures;
- lock already held, malformed owner evidence, and owner mismatch;
- object, global staging, commit staging, promotion, pre-pointer verification, pointer replacement, read-back, attempt write, cleanup, and lock-release faults;
- first publication;
- authenticated retained-object reuse;
- equivalent retained-commit reuse;
- byte-identical verified no-op;
- lost-pointer recovery;
- malformed retained evaluation graph never accepted as no-op;
- post-pointer failure referencing the genuinely published commit.

For every evidence-eligible path inspect:

```text
terminal_result
referenced_commit
attempt_staged
object_written
commit_renamed
pointer_replaced
discovery_verified
attempt_staging
lock_acquired
lock_released
lock_cleanup
```

Each value describes only the current invocation. Deduplicated objects and reused commits remain `False` for creation/rename milestones. A lost pointer may yield `PUBLISHED` with `pointer_replaced=True`, `object_written=False`, and `commit_renamed=False`.

Focused gate:

```bash
uv run pytest tests/test_evaluation_recovery.py -q
```

Suggested commit: `test(evaluation): recovery and evidence integrity`

### T10 — Independently frozen real-Q1 oracle vectors

**Files:**

```text
tests/test_integration_evaluation.py
```

The plan author generated a scratch reference directly from authenticated retained parent bytes using only stdlib Decimal/JCS-equivalent serialization plus PyArrow reading. A second independent agent reimplemented and recomputed the oracle without importing or executing the first script. Both matched exactly.

Parent anchors:

- Validation commit: `3f8a776bbdb195bb80fe1d7e19e978b0492d7e95ed30307a32b131fe57f901ca`.
- Validation artifact SHA: `0019fa7b2f7949c4e5e357fd8143ae8110f7985cf5ed82353c8795894ce942d2`.
- Validation content hash: `3977380dab576d60fffa74ae582ab08959197b93364495515eb16b4ecad7a19a`.
- Research commit: `ca878557b82c63d5265a307c2b4b39bb1f4e11ca171bef65a573b51f4c970ce3`.
- Research Parquet SHA: `8a93f03388fc0ee71c951db2b6476bc3d24fb13a7d4ac9c90056520295a49022`.
- Research content hash: `a2231983e3830d0a6bc1d8f0b3342f1b82e1a2bfbaa8f3d32d8072a7348947b2`.

Expected evaluation anchors:

- Schema fingerprint: `d454a7e142ac19cfbb75ccabd53f1fb20f26bc471968c6e4b84203030aa10843`.
- Artifact SHA: `4b8393a961b909393d0e7616eda2d9e741ca2f7c2216231700f419505cd53e8f`.
- Artifact size: `30991` bytes.
- Canonical content hash: `76f02fca4d149baca6380caa4b389527787af2c2770f374b1cbd7ca3297d984c`.
- Evaluation commit identity: `d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675`.
- Records: 100; IC values: 200; total valid pairs: 7,200.

Boundary records:

- Fold 0 / `f_ret_1`: range `[360,432]`, 72 valid, Pearson `-0.098918351208551690`, Spearman `-0.138111775676892405`.
- Fold 24 / `f_volratio_20`: range `[2088,2184]`, 96 rows, 72 valid, 24 target-null/excluded, Pearson `-0.009692885223140206`, Spearman `-0.009518296996591421`.

Eight summary anchors, shown as mean / min / median / max / positive-negative-zero folds:

- `f_ret_1` Pearson: `-0.111294186144914768` / `-0.303946195261965526` / `-0.113263945415598819` / `0.092814689936449646` / `4-21-0`.
- `f_ret_1` Spearman: `-0.111973760370441829` / `-0.428612772525564345` / `-0.110875297446781143` / `0.019004437584410573` / `3-22-0`.
- `f_roc_60` Pearson: `-0.458770428587482703` / `-0.874903358433405444` / `-0.531055317815273077` / `0.667172407469239722` / `2-23-0`.
- `f_roc_60` Spearman: `-0.438563251656055052` / `-0.910251463116599138` / `-0.487619782622676699` / `0.714515402919801917` / `2-23-0`.
- `f_rvol_20` Pearson: `-0.022548713854510610` / `-0.838060700487644293` / `-0.219967656501197583` / `0.793522346695004545` / `10-15-0`.
- `f_rvol_20` Spearman: `-0.007172165412566725` / `-0.833783523056145090` / `-0.173901858640427037` / `0.755096790790404528` / `9-16-0`.
- `f_volratio_20` Pearson: `-0.007589071509905910` / `-0.511670492972096072` / `0.029922685730146314` / `0.320023859571453847` / `13-12-0`.
- `f_volratio_20` Spearman: `-0.010408386391407808` / `-0.382178918258408901` / `0.031063090874011190` / `0.351340922245803589` / `13-12-0`.

These values are neutral test evidence, not feature recommendations or performance claims.

### T11 — Real Q1 serial acceptance and README

**Files:**

```text
tests/test_integration_evaluation.py
README.md
```

The marked integration test must:

1. Snapshot research and validation `current.json` bytes.
2. Snapshot all predecessor immutable commit-tree digests.
3. Establish or authenticate Q1 research and validation through real CLI routes.
4. Run the evaluation descriptor through the real CLI.
5. Assert 25 folds, 4 features, 100 records, 200 IC values, 72 valid pairs per record, and 7,200 total valid pairs.
6. Independently recompute all 200 ICs from authenticated research rows without calling production evaluation metric helpers.
7. Independently recompute all eight summaries from stored Q18 records.
8. Assert the T10 frozen hashes and vectors.
9. Verify parent lineage, legal record, exact `PASS`, CAS bytes, content hash, commit equation, and pointer graph.
10. Rerun and require `VERIFIED_NO_OP` with byte-identical evaluation pointer and commit tree.
11. Inspect the no-op attempt manifest and truthful milestones.
12. Restore both predecessor pointers in `finally`.
13. Prove every predecessor immutable tree remains byte-identical.

The independent integration oracle may use its own small Decimal functions inside the integration test, but must not import `evaluation_metrics` or call `build_evaluation_artifact()` to construct expected values.

Focused gate:

```bash
uv run pytest -m integration tests/test_integration_evaluation.py -q -s
```

Only after this passes, append a short README section stating the scope, record counts, immutable lineage, and internal descriptive status. Do not highlight favorable/unfavorable feature conclusions.

Suggested commit: `test(integration): dual-IC Q1 acceptance`

### T12 — Final sensitive-state gate, audit, commit, and push

Run once on the final unchanged implementation state:

```bash
set -o pipefail &&
uv lock --check &&
uv run ruff check . &&
uv run pytest -m "not integration" &&
uv run pytest -n 4 --dist=load -m "not integration" &&
uv run pytest -m integration &&
echo "QUANTARA_SLICE_006_GATE_PASSED"
```

If any failure causes a code or test change, rerun focused checks first and then rerun the complete gate on the new final state.

Then perform:

```bash
git diff --check
git diff --name-only b54700791336d5b4132898de8ea83a371c564c9f..HEAD
git ls-files data
git status --ignored --short data
git status --porcelain
```

Inspect real artifacts and attempt manifests, not just test output:

- first publication: created/renamed/replaced milestones true only where real;
- no-op: pointer and tree byte-identical, creation milestones false;
- lost pointer: retained object/commit reuse truthful;
- lock: acquired and owner-released, no sibling deletion;
- both parents and predecessor immutable trees unchanged.

Commit only allowlisted files using the configured GitHub noreply identity. Push only after the final gate and cleanliness checks pass. Fetch and prove:

```text
local HEAD == origin/main == remote main
```

Refresh the Quantara codebase-memory index after the final code commit and verify indexing completes.

## 8. Acceptance matrix

Technical acceptance requires all of the following:

- strict descriptor and real config;
- exact evaluation schema/content/commit identities;
- no ambient Decimal dependence or float fallback;
- exact average-rank ties and one Q18 storage quantization;
- 25 folds × 4 features = 100 ordered records;
- exactly 200 IC values and 7,200 valid-pair observations;
- eight summaries rebuilt from stored Q18 values;
- 13 ordered fresh quality checks and exact `PASS`;
- both Q1 current pointers authenticated and stable during snapshot selection;
- exact validation-to-research lineage binding;
- write-free full-computation dry-run;
- exclusive owner lock for every non-dry-run publication/no-op/recovery path;
- immutable first publication;
- authenticated byte-identical no-op;
- truthful lost-pointer recovery;
- current-invocation milestone evidence on every eligible path;
- full serial and parallel offline gates plus serial integration;
- no predecessor mutation and no tracked `data/`.

## 9. Completion states

### COMPLETE

All T0–T12 requirements pass with fresh raw evidence; the Q1 artifact matches the independently verified oracle; publication, no-op, recovery, lock, and attempt semantics are verified; only allowlisted files changed; repository and remote are synchronized; code graph refresh succeeds.

### BLOCKED

A foundational condition prevents honest completion, including repository drift that invalidates scope, a closed legal gate, unavailable/corrupt Q1 parents that cannot be re-established, an existing lock requiring operator review, external archive/network failure during integration, or remote publication failure after a valid local commit.

### INCOMPLETE

Any descriptor, arithmetic, identity, lineage, quality, lock, recovery, truthful-evidence, independent-oracle, full-gate, scope, cleanliness, synchronization, or graph-refresh requirement remains unmet.

## 10. Known risks and required defenses

1. **Parent verifier scope:** existing verifiers are necessary but not sufficient for evaluation-specific Q1 reconciliation; layer checks without bypassing them.
2. **Pointer races:** authenticate byte snapshots and require stable before/after reads plus a final pre-publication match.
3. **Operational digest leakage:** parent manifest digests belong only in manifest `parent_discovery`, never analytical or quality identity.
4. **Q18 helper mismatch:** `render_decimal_18()` forbids rounding; use the evaluation context's one allowed quantization.
5. **Ambient Decimal leakage:** every arithmetic operation, including ranks and summaries, uses the private context.
6. **Identity circularity:** quality verifies prospective stable identities, but quality identity does not enter artifact or commit address.
7. **Lock race:** atomic create-if-absent, fsynced owner evidence, owner recheck before unlink, and no stale-lock theft.
8. **Inherited staging cleanup:** never glob-delete sibling staging directories.
9. **Dry-run under-testing:** unlike predecessor analytical pipelines, Slice 006 dry-run computes all metrics and fresh quality.
10. **Integration restoration:** both shared January-labeled parent pointers restore in `finally`, even on network or assertion failure.
11. **Correlated test oracle:** integration expected metrics and hashes use the independently verified T10 reference, not production helpers.
12. **Interpretation risk:** negative or positive IC values are descriptive evidence only and must not become quality or product claims.
