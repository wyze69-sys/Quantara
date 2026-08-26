# Quantara Data Slice 006 — Dual-IC Feature Evaluation Design

**Status:** Owner-approved design; authorizes implementation planning, not implementation
**Date:** 2026-08-27
**Project root:** `D:\PROJECT\Quantara`
**Frozen planning baseline:** `5ea2207f75ef6d44f4aef8c8cb2a7d5b88d424b8`
**Predecessors:** slice 003b research tables, slice 004 validation folds, slice 005 Q1 temporal expansion

## 1. Goal

Add a bounded, immutable statistical-evaluation lane over the verified BTCUSDT 1h Q1 2024 research table and anchored walk-forward validation folds.

The slice publishes deterministic per-fold Pearson and Spearman information coefficients (ICs) for the four approved `btcusdt_core_v1` features against `l_fwdret_24`. It is descriptive internal analysis only. It does not fit a model, select a feature, search a parameter, create a signal, run a backtest, or make a performance claim.

The result must be reproducible from authenticated parent bytes, lineage-bound to both the exact validation-fold commit and the exact research-table commit, quality-gated at exactly `PASS`, and published through Quantara's existing immutable content-addressed protocol.

## 2. Why this is the next slice

Slice 005 expanded the verified evidence window from January to all of Q1 2024:

- `2,184` one-hour research rows;
- `25` anchored walk-forward folds;
- `1,824` test rows after the excluded head;
- `72` test rows in each of the first 24 folds;
- `96` rows in the final remainder-merged fold, whose final 24 target labels are structurally null.

The repository can now evaluate feature/label relationships across multiple ordered out-of-sample segments without introducing model training. A dual-IC artifact is the smallest useful evaluation step that detects both linear association and general monotonic association while preserving the existing legal and temporal boundaries.

## 3. Governance posture

The governing rights record remains `configs/legal/binance-usdm-provider-rights.v2.yaml`.

The operation for this slice is `analyze_internal`, which is already `OWNER_APPROVED_PENDING_COUNSEL`. The slice does not exercise `model_train_internal`, which remains `UNKNOWN`.

All outputs remain:

- private and internal-use only;
- ineligible for commercial production;
- ineligible for customer display;
- ineligible for redistribution;
- unsuitable for investment or performance claims.

No rights record or approved-operation classification is changed by this slice.

## 4. Explicit non-goals

Slice 006 does not include:

- model fitting, coefficients, weights, or inference;
- feature selection or feature ranking decisions;
- hyperparameter, threshold, horizon, or metric search;
- train-derived calibration bins;
- p-values, confidence intervals, or statistical-significance claims;
- pooled global correlation across all test rows;
- transaction costs, slippage, turnover, or execution assumptions;
- backtesting, portfolio construction, or risk allocation;
- trading signals or recommendations;
- APIs, dashboards, reports, or customer-facing presentation;
- changes to existing feature formulas, labels, folds, parent artifacts, shared publication semantics, or legal posture.

A weak, negative, zero, or unstable IC is valid evidence. Metric direction or magnitude must never determine publication quality.

## 5. Architecture and parent lineage

### 5.1 Domain flow

```text
Q1 research commit
        |
        +--------- authenticated lineage ---------+
        |                                         |
Q1 validation-fold commit                         |
        |                                         |
        +-- evaluation descriptor -- evaluation pipeline
                                                  |
                                                  v
                                    immutable dual-IC artifact
```

The evaluation pipeline consumes two authenticated inputs:

1. The current Q1 validation-fold artifact selected by the evaluation descriptor's parent validation descriptor.
2. The current Q1 research-table artifact selected by that validation descriptor's parent research descriptor.

Both discovery pointers are authoritative. At invocation time, the validation `current.json` must authenticate to the Q1 validation dataset ID, Q1 period, approved fold set, and 2,184-row contract; the research `current.json` must authenticate to the exact Q1 research dataset and commit named by the validation lineage. A January pointer or any other valid-but-different dataset is `BLOCKED`; the pipeline must not search retained history for convenient commits. The resulting evaluation commit is bound to the exact stable analytical identities of both authenticated parents selected at that invocation.

The real Q1 acceptance setup may republish the already-retained Q1 research and validation commits as current, but it must preserve and restore both pre-test pointers. Normal evaluation never rewrites either parent pointer implicitly.

### 5.2 Required parent authentication

Before computation, the pipeline must:

1. Load and strictly validate the evaluation descriptor.
2. Apply the `analyze_internal` rights gate.
3. Load the referenced validation descriptor.
4. Resolve the validation dataset directory deterministically.
5. Authenticate its `current.json`, immutable commit directory, manifest, quality document, and artifact object bytes.
6. Require validation quality state exactly `PASS`.
7. Extract the validation commit's bound research parent identity.
8. Resolve and authenticate the Q1 research `current.json`, immutable commit, manifest digest, quality document, and Parquet object bytes through the research parent descriptor.
9. Require research quality state exactly `PASS`.
10. Verify that the authenticated research current commit, dataset ID, canonical content hash, Parquet SHA-256, and byte size exactly equal the research lineage bound by the validation commit.
11. Verify each identity at its proper layer and reject any mismatch:
    - CAS object SHA-256 over exact stored bytes;
    - validation canonical-content hash over its schema fingerprint and canonical JSON bytes;
    - research canonical-content hash over decoded canonical research rows;
    - each parent's lineage-bound commit-address equation.
12. Reconcile validation row counts, fold ranges, research row counts, and open-time ordering before metric computation.

Missing, stale, malformed, mismatched, or tampered parent graphs fail closed before publication.

## 6. Evaluation descriptor contract

### 6.1 Schema

Introduce `quantara.evaluation-descriptor/v1` with dataset type `feature_evaluation`.

The descriptor contains exactly:

```yaml
schema: quantara.evaluation-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1h_2024_q1_evaluation_dual_ic_v1
dataset_type: feature_evaluation
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1h_2024_q1
parent_descriptor: configs/datasets/binance-usdm-btcusdt-1h-2024-q1-validation-wf-v1.yaml
period:
  start: "2024-01-01T00:00:00Z"
  end: "2024-04-01T00:00:00Z"
evaluation_set:
  name: btcusdt_core_v1_dual_ic_v1
  version: "1"
features:
  - f_ret_1
  - f_roc_60
  - f_rvol_20
  - f_volratio_20
target: l_fwdret_24
metrics:
  - pearson_ic
  - spearman_ic
schema_version: quantara_feature_evaluation_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
```

### 6.2 Strict validation

The loader must:

- reject unknown and missing keys;
- reject non-object roots;
- require exact schema, dataset type, evaluation-set, schema-version, quality-policy, and legal-record values;
- require the exact approved feature order;
- require the exact target and metric order;
- reject duplicate, omitted, substituted, or reordered features and metrics;
- load the referenced validation descriptor and require exact equality with its provider, instrument, base dataset ID, period, feature-set name/version, validation scheme, fold-set name/version, and approved fold parameters;
- derive the stable dataset ID exactly as `f"{validation.parent_descriptor.base_dataset_id}_evaluation_dual_ic_v1"`; runtime commit addresses never participate in the dataset ID;
- use canonical validated semantics for descriptor identity so YAML key order does not change identity.

No free parameters are introduced in v1.

## 7. Row-selection semantics

For each validation fold, evaluate only:

```text
research_rows[fold.test_range.start : fold.test_range.end]
```

Training and embargo rows are excluded from every metric.

For each approved feature and the fixed target:

- a pair is valid only when both values are non-null;
- structural nulls are counted and excluded explicitly;
- no value is imputed, filled, clipped, winsorized, standardized, or transformed;
- row order is preserved;
- research open times must remain strictly increasing and aligned with the validation parent;
- booleans and binary floats are invalid numeric inputs;
- non-finite or malformed values fail quality rather than being skipped silently.

The Q1 acceptance matrix is:

- `25` folds;
- `4` features;
- `100` fold-feature records;
- `2` IC values per record;
- `200` published IC values;
- `72` valid feature-target pairs per record;
- `7,200` evaluated feature-target pair observations in total.

For the first 24 folds, all 72 test rows have valid target labels. The final fold has 96 test rows, but its final 24 `l_fwdret_24` values are designed structural nulls, leaving 72 valid pairs for every feature.

## 8. Decimal computation contract

All metric computation uses a dedicated `decimal.Context` with the complete contract:

- precision `50`;
- rounding `ROUND_HALF_EVEN`;
- `Emin = -999999`;
- `Emax = 999999`;
- `capitals = 1`;
- `clamp = 0`;
- traps enabled for `InvalidOperation`, `DivisionByZero`, and `Overflow`;
- all other signal traps disabled at context construction.

Every arithmetic operation, including sums, means, products, division, and square root, must use this context explicitly or execute inside a `localcontext` copied from it. Ambient process context must not affect results. Input rows remain in authenticated canonical open-time order; the metric contract does not promise arbitrary finite-precision permutation invariance.

Published decimal metrics are quantized once to `Q18` at the storage boundary. There is no intermediate Q18 rounding.

### 8.1 Pearson IC

For valid pairs `(x_i, y_i)`, calculate:

```text
numerator   = sum((x_i - mean_x) * (y_i - mean_y))
denominator = sqrt(sum((x_i - mean_x)^2) * sum((y_i - mean_y)^2))
pearson_ic  = numerator / denominator
```

Requirements:

- at least two valid pairs;
- non-zero feature variance;
- non-zero target variance;
- deterministic Decimal summation in row order;
- result within the closed interval `[-1, 1]` before and after Q18 quantization.

The algebraically equivalent covariance form is not a separate metric identity. The implementation must follow the versioned formula above so arithmetic order is deterministic.

### 8.2 Spearman IC

Spearman IC is Pearson IC over deterministic average ranks.

Ranking rules:

1. Sort values by exact Decimal comparison.
2. Rank positions begin at `1`.
3. Equal values form one tie group.
4. Every member of a tie group receives the exact arithmetic mean of the occupied rank positions.
5. Restore ranks to original row order.
6. Apply the Pearson formula from §8.1 to the paired rank vectors.

Average ranks are exact Decimals. Input row order breaks no ties and must not alter a tie group's rank.

A strictly increasing transformation that preserves equality groups must leave Spearman IC unchanged.

### 8.3 Undefined metrics

The pipeline must not fabricate `0` for an undefined metric. Fewer than two valid pairs, zero feature variance, or zero target variance makes the evaluation quality-ineligible and prevents publication.

## 9. Canonical evaluation artifact

The artifact is deterministic canonical JSON stored in the content-addressed object store. Its root object contains exactly these keys:

```text
schema
dataset_id
provider
instrument_id
period
evaluation_set
validation_parent
research_parent
features
target
metrics
decimal_contract
records
summaries
disclaimer
```

Exact fixed values and shapes:

- `schema` is `quantara.feature_evaluation/v1`.
- `period` is `{start, end}` using the descriptor's approved UTC strings.
- `evaluation_set` is `{name, version}`.
- `validation_parent` is `{dataset_id, commit_address, canonical_content_hash, artifact_sha256, artifact_size}`.
- `research_parent` is `{dataset_id, commit_address, canonical_content_hash, parquet_sha256, parquet_size}`.
- `features` and `metrics` preserve descriptor order.
- `decimal_contract` freezes precision, rounding, exponent bounds, clamp/capitals, traps, and Q18 storage.
- `records` and `summaries` use the exact fields and ordering below.
- `disclaimer` is the fixed string `internal descriptive analysis only; no model, signal, backtest, significance, or performance claim`.

### 9.1 Record order and fields

Records are ordered by:

1. `fold_id` ascending;
2. approved feature order.

Each fold-feature record contains:

- `fold_id`;
- `feature`;
- `target`;
- `test_range`;
- `test_row_count`;
- `valid_pair_count`;
- `excluded_pair_count`;
- `feature_null_count`;
- `target_null_count`;
- `pearson_ic` as a Q18 decimal string;
- `spearman_ic` as a Q18 decimal string.

Null counts may overlap when both values are null. Therefore:

```text
excluded_pair_count = test_row_count - valid_pair_count
```

must reconcile independently; it must not be inferred by adding feature and target null counts.

### 9.2 Cross-fold summaries

For each approved feature and each metric, publish one summary object with exactly:

- `feature`;
- `metric`;
- `fold_count`;
- `total_valid_pair_count`;
- `positive_fold_count`;
- `negative_fold_count`;
- `zero_fold_count`;
- `minimum`;
- `maximum`;
- `median`;
- `equal_weight_mean`.

Summary objects are ordered by approved feature order, then metric order.

Summaries are calculated from the stored Q18 per-fold metrics, not hidden higher-precision values. Derived Decimal summary values are quantized once to Q18.

For an even number of observations, median is the arithmetic mean of the two central sorted Q18 values. For an odd number, it is the central Q18 value.

No pooled global correlation is published. Pooling would overweight longer folds and could conceal regime instability.

### 9.3 Schema fingerprint and content identity

The evaluation schema fingerprint is:

```text
sha256(JCS({
  "domain": "quantara-evaluation-schema-v1",
  "schema_id": "quantara_feature_evaluation_v1",
  "evaluation_set": {"name": "btcusdt_core_v1_dual_ic_v1", "version": "1"},
  "features": ["f_ret_1", "f_roc_60", "f_rvol_20", "f_volratio_20"],
  "target": "l_fwdret_24",
  "metrics": ["pearson_ic", "spearman_ic"],
  "decimal_contract": {
    "precision": 50,
    "rounding": "ROUND_HALF_EVEN",
    "emin": -999999,
    "emax": 999999,
    "capitals": 1,
    "clamp": 0,
    "enabled_traps": ["InvalidOperation", "DivisionByZero", "Overflow"],
    "storage_quantum": "0.000000000000000001"
  },
  "parent_validation_fingerprint": validation_schema_fingerprint.lower()
}))
```

Render the artifact object with JCS and append one LF byte. These exact bytes are the CAS object bytes. Define:

```text
artifact_bytes = JCS(artifact).encode("utf-8") + b"\n"
artifact_sha256 = sha256(artifact_bytes)
canonical_content_hash = sha256(
    b"quantara-evaluation-content-v1\x00"
    + schema_fingerprint.lower().encode("ascii")
    + b"\n"
    + artifact_bytes
    + b"\n"
)
```

The extra final LF in the content-hash framing is intentional and matches the inherited analytical hashing pattern.

### 9.4 Lineage and commit identity

`evaluation_from` contains exactly:

```text
validation_dataset_id
validation_commit_address
validation_canonical_content_hash
validation_artifact_sha256
validation_artifact_size
research_dataset_id
research_commit_address
research_canonical_content_hash
research_parquet_sha256
research_parquet_size
evaluation_set_name
evaluation_set_version
features
target
metrics
decimal_contract
```

The commit address is:

```text
sha256(JCS({
  "domain": "quantara-evaluation-commit-identity-v1",
  "canonical_content_hash": canonical_content_hash.lower(),
  "evaluation_from": evaluation_from
}))
```

Runtime environment, timestamps, attempts, pointer state, and storage paths never participate in content or commit identity.

### 9.5 Commit evidence, manifest, and quality document

`content.json` contains exactly these idempotency keys:

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

`object_refs` is exactly one `{kind: "normalized", sha256: artifact_sha256}` object. The no-op matcher compares all eight keys.

The manifest extends the existing dataset-manifest envelope and must bind:

- dataset, instrument, period, schema version, schema fingerprint, and parser version;
- quality policy version, quality identity, and quality state;
- validation parent row count, fold count, feature count, metric count, and record count;
- canonical content hash and evaluation commit identity;
- artifact SHA-256, byte size, and object reference;
- legal record and operation states;
- the complete stable `evaluation_from` block;
- an operational `parent_discovery` block containing the validation and research pointer `manifest_sha256` values used to authenticate this invocation;
- evaluation set, features, target, metrics, and decimal contract.

Parent manifest byte digests authenticate discovery for the current invocation but contain operational timestamps/environment. They are therefore excluded from the evaluation artifact, schema fingerprint, canonical content hash, `evaluation_from`, and commit identity. They may vary across logically equivalent parent republications without changing analytical evaluation identity.

`quality.json` uses the inherited `{state, policy_version, identity, findings}` envelope. Its identity is the JCS string returned by `quality_identity()` over the ordered findings after excluding operational timestamps. Manifest, quality, and content files use sorted-key indented JSON plus one LF, matching existing immutable commit files.

## 10. Quality policy

Evaluation quality is exactly `PASS` only when all required checks pass.

Quality findings appear in this exact order and use these fixed `check_id` values:

1. `parents_authenticated`
2. `lineage_binding`
3. `descriptor_identity`
4. `fold_ranges`
5. `row_alignment`
6. `record_matrix`
7. `pair_counts`
8. `numeric_domain`
9. `metric_recomputation`
10. `metric_bounds`
11. `summary_recomputation`
12. `canonical_structure`
13. `identity_contract`

Together they require:

- both parent graphs authenticated at the CAS-byte, canonical-content, and lineage-bound commit layers;
- exact validation-to-research lineage binding;
- both parent quality states exactly `PASS`;
- descriptor, parent, and artifact identities to reconcile;
- fold ranges ordered as non-overlapping test segments within research bounds;
- research row count and open-time alignment to reconcile;
- the complete expected fold-feature matrix exactly once;
- every record's row and null counts to reconcile;
- every metric to freshly recompute from authenticated rows and match exactly;
- every metric within `[-1, 1]`;
- all summaries to freshly recompute from stored per-fold Q18 values;
- exact canonical ordering and serialization;
- no binary floats or non-finite values;
- descriptor semantics, schema fingerprint inputs, canonical artifact structure, parent lineage inputs, and prospective commit identity to reconcile before staging.

After the PASS report is fixed, the pipeline builds `content.json`, `quality.json`, and the manifest, stages the commit, and applies the separate immutable-graph verification. Pointer and immutable-commit graph authentication occurs after publication and is terminal discovery verification, not a pre-publication quality finding.

`PASS` says only that the artifact is complete, authentic, deterministic, and arithmetically correct. It says nothing about predictive usefulness.

## 11. Publication and recovery

Use Quantara's existing immutable object/commit/pointer primitives, with a stricter evaluation-lane single-writer rule:

1. Descriptor validation and CLI dispatch.
2. Parent authentication and rights gating.
3. Full in-memory deterministic computation and quality evaluation.
4. For non-dry-run only, atomically acquire `evaluation.lock` in the evaluation dataset directory using create-if-absent semantics and record the attempt ID as owner.
5. Create only this invocation's unique global and commit-staging directories.
6. Canonical JSON rendering.
7. PASS-only content-addressed object publication.
8. Immutable staged commit.
9. Atomic commit promotion.
10. Atomic `current.json` replacement.
11. Discovery read-back and full graph verification.
12. Attempt evidence, owner-only staging cleanup, and owner-only lock release.

The evaluation pipeline must never glob-delete sibling `.staging-*` directories. If `evaluation.lock` already exists, the invocation is `BLOCKED` as concurrent-or-stale ownership; it must not delete or steal the lock. Only the invocation whose attempt ID matches the lock contents may remove it, including in `finally`. A crashed stale lock requires explicit operator verification and removal outside the pipeline.

Required semantics:

- first successful publication returns `PUBLISHED`;
- unchanged rerun returns `VERIFIED_NO_OP`;
- no-op leaves pointer and commit tree byte-identical;
- lost-pointer recovery may return `PUBLISHED` while reusing authenticated retained object and commit bytes;
- `object_written`, `commit_renamed`, and `pointer_replaced` describe actions that genuinely occurred in the current invocation;
- prior immutable commits and content-addressed objects are never rewritten;
- cleanup failure preserves the primary terminal result while recording cleanup state truthfully;
- dry-run performs descriptor validation, rights gating, full parent authentication, complete in-memory metric computation, and fresh quality evaluation, then returns without acquiring the lock or writing any object, commit, pointer, staging directory, or attempt manifest.

The dedicated evaluation lane is rooted under:

```text
data/datasets/binance/usdm/evaluation/BTCUSDT/1h/year=2024/month=01/
```

The period-start directory is a storage label; the manifest's full half-open period is authoritative.

## 12. Exit-code and evidence taxonomy

Preserve existing analytical-pipeline behavior:

- `0`: `PUBLISHED`, `VERIFIED_NO_OP`, or successful dry-run;
- `2`: `BLOCKED` for a recognized evaluation descriptor whose fields are invalid, ineligible legal posture, missing/unusable/mismatched parents, an existing evaluation lock, undefined metrics, or computed quality other than exact `PASS`;
- `3`: `FAILED` for operational failures after evaluation dispatch;
- `4`: reserved for acquisition-data quarantine and unused by this analytical slice.

The shared CLI retains its established pre-dispatch contract: malformed YAML, a non-object root, a missing schema, or an unrecognized schema returns `3` with `invalid_descriptor` and cannot create pipeline attempt evidence because no pipeline was selected. Once the CLI recognizes `quantara.evaluation-descriptor/v1`, descriptor-field failures occur inside the evaluation pipeline and return `BLOCKED/2`.

Every non-dry-run terminal path reached after recognized evaluation dispatch produces a truthful attempt manifest. Dry-run and pre-dispatch CLI rejection are explicit no-write exceptions. Passing tests without truthful evidence on evidence-eligible paths is insufficient.

## 13. Testing requirements

### 13.1 Descriptor tests

Cover:

- the real repository descriptor;
- pre-dispatch malformed YAML, non-object, missing-schema, and unknown-schema documents returning `3` without attempt evidence;
- recognized evaluation-schema documents with invalid fields returning `BLOCKED/2` with attempt evidence;
- exact approved feature, target, and metric identities and ordering;
- duplicate, omitted, substituted, and reordered entries;
- parent provider, instrument, dataset, period, feature-set, and fold-set mismatch;
- unsupported schema, evaluation set, policy version, or legal record;
- canonical identity stability under YAML key reordering.

### 13.2 Metric-engine tests

Cover:

- hand-computed Pearson fixtures;
- perfect positive and negative correlation;
- a valid zero-correlation fixture;
- deterministic Decimal summation order;
- exact average ranks for odd- and even-sized tie groups;
- all-equal and partially tied rank fixtures;
- Spearman invariance under strictly increasing transformations;
- null-pair accounting, including overlapping nulls;
- fewer-than-two-pairs and zero-variance rejection;
- binary-float, boolean, malformed, and non-finite rejection;
- pre- and post-quantization bounds;
- Q18 storage-boundary rounding;
- property-based determinism under authenticated canonical row order and rank-tie invariants.

### 13.3 Quality tests

Cover:

- complete matrix and summary reconciliation;
- missing, duplicate, reordered, and fabricated records;
- fold/test-range and count mismatches;
- out-of-range and malformed metrics;
- summary-sign and aggregate mismatches;
- fresh recomputation from actual research rows;
- proof that weak or negative valid metrics can still receive quality `PASS`.

### 13.4 Pipeline and recovery tests

Cover:

- missing and malformed parents;
- tampered validation artifact or research Parquet;
- validation-to-research lineage mismatch;
- non-PASS parent quality;
- first publication;
- verified no-op;
- retained-object and equivalent-commit reuse;
- lost-pointer recovery;
- an already-held lock blocking without lock theft or sibling-staging deletion;
- owner-only lock release on success and failure;
- object, staging, commit-promotion, pointer, read-back, and cleanup faults;
- truthful current-invocation milestones on every evidence-eligible disposition;
- dry-run full-computation success and quality failure with no lock, attempt, staging, object, commit, or pointer writes.

### 13.5 Real Q1 acceptance

The marked serial integration test must:

1. Establish or authenticate the complete retained Q1 research and validation chain.
2. Run Slice 006 through the real CLI.
3. Assert exactly 25 folds, 4 features, 100 records, 200 IC values, 72 valid pairs per record, and 7,200 evaluated pair observations.
4. Independently recompute every Pearson and Spearman IC from actual research rows.
5. Independently recompute every summary from stored Q18 records.
6. Verify exact parent lineage, legal record, PASS quality, object hash, commit identity, and pointer graph.
7. Rerun and require `VERIFIED_NO_OP` with byte-identical evaluation pointer and commit tree.
8. Preserve and restore every pre-test predecessor discovery pointer.
9. Prove all predecessor immutable commit trees remain byte-identical.

No expected IC value may be chosen because it looks favorable. Golden values and hashes, if frozen in the implementation plan, must come from an independent reference computation over authenticated parent bytes.

## 14. Verification workflow

During implementation, each task uses focused red-to-green tests and records raw output.

Because Slice 006 introduces a new immutable publication pipeline and recovery behavior, it uses the sensitive-state exit gate once on the final unchanged state:

```bash
set -o pipefail &&
uv lock --check &&
uv run ruff check . &&
uv run pytest -m "not integration" &&
uv run pytest -n 4 --dist=load -m "not integration" &&
uv run pytest -m integration &&
echo "QUANTARA_SLICE_006_GATE_PASSED"
```

Ordinary future slices return to the owner-approved routine gate with one complete parallel offline suite and serial integration.

## 15. Completion definition

### 15.1 Technical completion

The implementation is technically complete only when:

- implementation stays inside the approved plan allowlist;
- all focused TDD tasks and the final sensitive-state gate pass;
- real Q1 acceptance independently recomputes every published metric;
- first publication and byte-identical no-op are demonstrated;
- attempt evidence is truthful for current-invocation milestones;
- lock ownership and concurrent-invocation behavior are verified;
- predecessor artifacts remain immutable;
- `data/` remains ignored and untracked.

These conditions are reproducible on any clean branch with the required retained or freshly established Q1 parents.

### 15.2 Operational acceptance

After technical completion, the execution workflow separately requires:

- the approved design and implementation plan to be committed;
- independent review of the executor's diff and evidence;
- an authorized commit and normal push;
- clean repository state;
- local `HEAD`, `origin/main`, and remote `main` synchronization;
- code-graph refresh;
- final status `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with exact evidence.

Push, remote synchronization, and external review are release-process conditions, not properties the implementation or offline test suite must fabricate.

## 16. Design authorization

This owner-approved design authorizes implementation planning only. It does not authorize implementation, model training, feature selection, backtesting, trading use, commercial use, customer display, redistribution, or any weakening of Quantara's inherited integrity and legal gates.
