# Quantara Data Slice 010B — Reviewed Derived Zero-Volume Bucket Approval and Full-Year 1h Recovery Plan

**Status:** Proposed implementation plan; code not yet changed
**Date:** 2026-08-28
**Project root:** `D:\PROJECT\Quantara`
**Prerequisite:** Slice 010A committed through `b627a1e` (base lane publishes authenticated `WARN_APPROVED` under policy v2); Slice 010 T5 remains honestly `BLOCKED` at the derived 1h layer.
**Purpose:** Complete the full-year 2024 chain by approving the single genuine `derived_zero_volume_bucket` warning on the 1h lane — the bar at `2024-10-28 20:00:00Z` whose 60 constituent minutes are the Binance USD-M maintenance window — without hiding the warning, weakening any hard check, or changing January/Q1 evidence.

## 1. Decision

Extend the policy-v2 approval mechanism from the base lane to the derived 1h lane. The derived pipeline currently hard-requires `report.state == "PASS"` (derive_pipeline.py line 973) and the derived current-graph verifier requires exactly `PASS` (line 817). A full-year 1h table carries exactly one genuine exchange-maintenance zero-volume hour; the 1d lane aggregates the same minutes into a non-zero daily bar and already passes. Under 010B, the 1h descriptor moves to policy v2 with its own immutable, content-bound approval record; publication becomes `WARN_APPROVED` with raw `WARN_BLOCKED` preserved; the research lane's parent verifier learns to accept an authenticated `WARN_APPROVED` derived parent exactly as T3 taught the derive lane to accept one from the base lane.

This is a **formal policy amendment for the derived lane**, symmetric to 010A's base-lane amendment. The 010A plan §5.5 assumption "derived outputs should evaluate to PASS" was falsified by real 2024 data; this plan supersedes it narrowly.

Rejected approaches:

- **Suppress or downgrade the derived warning:** rejected; the zero-volume hour is real evidence and must remain visible.
- **Change the integration test to expect exit 2 at the 1h lane:** rejected; abandons the requested full-year chain.
- **Drop, fill, or interpolate the maintenance hour:** rejected; changes official content, breaks reconciliation and completeness invariants.
- **Approve the 1d lane too:** rejected; unnecessary — its state is `PASS` with zero zero-volume bars.
- **Loosen research/validation/eval quality thresholds:** rejected; those lanes remain PASS-only in their own outputs.

## 2. Paste-ready Codex launcher

```text
Work in D:\PROJECT\Quantara. Do not reset, clean, stash, or discard anything.

Read this file completely:
docs/superpowers/plans/2026-08-28-data-slice-010b-reviewed-derived-zero-volume-approval.md

Then execute T0 through T5 exactly, using focused red-to-green TDD. Preserve the nine
existing commits after ca68589 and the untracked tests/test_integration_year.py. Make only
allowlisted changes. Do not weaken quality checks, remove warning evidence, fabricate
PASS, or alter official rows.

OWNER AUTHORIZATION: By giving you this launcher, the repository owner authorizes one
immutable quality-warning approval record for the exact frozen evidence in §4 only:
dataset binance_usdm_btcusdt_klines_1h_2024, canonical content hash
9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e,
quality-identity SHA-256 14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20,
finding digest 11db14d6d01bbe81bfefc89d20f0fc113e97f8991768c0007831d6a1b07ae05c for
exactly 1 derived_zero_volume_bucket warning at 2024-10-28T20:00:00Z. This authorizes no
other warning, dataset, content, source, or policy. Record the execution-time UTC decision
timestamp and owner identity 258711354+wyze69-sys@users.noreply.github.com. If any frozen
value does not reproduce exactly, STOP BLOCKED and create no approval record.

Run focused checks during repair and the complete final gates once on the final unchanged
state. Commit each task as specified. Push only after every gate passes. Report raw
commands/results and COMPLETE, BLOCKED, or INCOMPLETE. Then STOP.
```

## 3. Starting state and preservation gate

Expected state before Codex edits:

```text
branch: main
HEAD: b627a1e (or later only if it is exactly 010A's test fixture fix)
main...origin/main: ahead 9
commits after ca68589:
  4b9cfc2 docs(expansion): slice 010 temporal expansion 2024 plan
  32278d5 feat(descriptor): full-year 2024 range identity
  2aa3f99 feat(evaluation): approved period contracts for 2024 ranges
  4f23b0a feat(configs): 2024 full-year dataset descriptors
  58d37c6 docs(quality): plan reviewed warning approval recovery
  fc9f867 feat(quality): authenticated reviewed-warning approvals
  d8e7609 feat(pipeline): publish exact warn-approved quality evidence
  d7161b1 feat(derive): authenticate reviewed-warning base parents
  b627a1e test(evaluation): bind policy-2 base descriptor fixture in quality suite
untracked: tests/test_integration_year.py (intentional, preserved)
```

Preflight (BLOCKED if any step fails):

1. `git status --short --branch` shows only `?? tests/test_integration_year.py`.
2. `uv run pytest -m "not integration" -n 4 --dist=load -q` passes with exactly 697 tests (654 + 35 approval + 3 descriptor + 5 derive). If the count differs, report the exact arithmetic and STOP.
3. `uv run ruff check .` passes.
4. The base full-year commit `28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5` is retained under `data/datasets/binance/usdm/klines/BTCUSDT/1m/year=2024/month=01/commits/` with `quality_state: WARN_APPROVED`, `quality_raw_state: WARN_BLOCKED`, and `quality-approval.json` present.
5. All six `current.json` pointers still reference January/Q1 commits (base 1m `9d7eee74…`, 1h `702dab9f…`, 1d `2d09178f…`, research `cb9079ea…`, validation `16665116…`, evaluation `d2354cd1…`).

## 4. Frozen real-archive evidence (verified offline from retained objects)

All values below were recomputed from the retained full-year base Parquet object `data/objects/normalized/sha256/4456d6a7b5693bac7bc4870affead2f5be79d52eba0593d9d235234e0b340726` by aggregating with `aggregate_timeframe` and evaluating with `evaluate_derived_quality`, and the method was validated by exactly reproducing the retained January 1h commit (`e65d8dbb…` content hash and its quality identity). Codex must reproduce every value in T0 before proceeding:

- **Parent base commit:** `28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5` (policy-2 `WARN_APPROVED`)
- **Parent base Parquet digest (source binding):** `4456d6a7b5693bac7bc4870affead2f5be79d52eba0593d9d235234e0b340726`
- **1h schema fingerprint:** `2e2fb0f01e206d892fd5f2116d5ee206c5af27cf6fc9bdfb288b4ead0c6b13ff`
- **1h full-year canonical content hash:** `9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e`
- **1h full-year row count:** 8,784 (366 days × 24 hours)
- **Raw derived quality state:** `WARN_BLOCKED`
- **Warning:** exactly one finding — `derived_zero_volume_bucket`, outcome `warn`, severity `warning`, count 1, evidence `{"occurrences": 1}`
- **Zero-volume bar:** `2024-10-28T20:00:00Z` open; all four prices equal 69566.1; base/quote volume, trade count all zero — the 60 minutes from 20:00:00 to 20:59:00 are the Binance USD-M maintenance window (all 60 constituent 1m candles carry zero volume)
- **All 12 other derived checks pass** (row count, boundaries, uniqueness, ordering, adjacency, OHLC bounds, price positivity, volume nonnegativity, taker bounds, close-time relation, reconciliation)
- **1h raw quality-identity SHA-256:** `14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20`
- **Derived finding digest (canonical_finding_sha256):** `11db14d6d01bbe81bfefc89d20f0fc113e97f8991768c0007831d6a1b07ae05c`
- **1d lane:** `PASS` — 366 bars, zero zero-volume bars, no approval required or permitted
- **January/Q1 retained 1h/1d commits:** policy v1, state PASS, byte-identical before and after

## 5. Policy-v2 contract for the derived lane

### 5.1 Approval record

A second immutable YAML record `configs/quality/approvals/binance-usdm-btcusdt-1h-2024-derived-zero-volume.v1.yaml` under schema `quantara.quality-warning-approval/v1`, exactly like the base record but binding the derived lane:

- `dataset_id: binance_usdm_btcusdt_klines_1h_2024`
- `canonical_content_hash: 9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e`
- `schema_fingerprint: 2e2fb0f01e206d892fd5f2116d5ee206c5af27cf6fc9bdfb288b4ead0c6b13ff`
- `source_sha256: [4456d6a7b5693bac7bc4870affead2f5be79d52eba0593d9d235234e0b340726]` (the parent Parquet digest — derivation input bytes stand where the ZIP stood in 001)
- `quality_policy_version: "2"`
- `quality_identity_sha256: 14c8b656ab519f23b307149c243311e7d2337d6b79d77d39b2883ef48dd11f20`
- `approved_findings: [{check_id: derived_zero_volume_bucket, count: 1, canonical_finding_sha256: 11db14d6d01bbe81bfefc89d20f0fc113e97f8991768c0007831d6a1b07ae05c}]`
- `decision_time_utc`: execution-time UTC timestamp
- `approver: 258711354+wyze69-sys@users.noreply.github.com`
- `rationale`: the single zero-volume 1h bucket at 2024-10-28T20:00:00Z aggregates the 60-minute Binance USD-M maintenance window; rows are preserved, all hard invariants pass, approval is internal-analysis-only.
- `scope`: exact full-year BTCUSDT USD-M 1h canonical content only; no wildcard or future-data scope.
- `record_sha256`: canonical JCS self-hash computed over the semantics

`APPROVABLE_WARNING_CHECK_IDS` in `quality_approval.py` must add `derived_zero_volume_bucket` (it is the only derived warning check_id in the codebase; adding it grants nothing else).

### 5.2 Descriptor binding

`configs/datasets/binance-usdm-btcusdt-1h-2024-derived.yaml` changes exactly two fields:

```yaml
quality_policy_version: "2"
quality_approval: configs/quality/approvals/binance-usdm-btcusdt-1h-2024-derived-zero-volume.v1.yaml
```

`derive_descriptor.py` currently hard-rejects `quality_policy_version != "1"` (line 228). It must accept `"2"` only when the descriptor also carries `quality_approval`, and `"1"` only without it — the same combination rule T2 enforced on base descriptors in `descriptor.py`. January/Q1 derived descriptors stay v1 and byte-identical.

### 5.3 Raw versus effective quality state

`run_derivation_pipeline` computes `content_hash` only **after** the PASS gate today (line ~992). For the 1h lane under policy v2 it must:

1. Aggregate, stage Parquet, and evaluate the raw report exactly as now.
2. Compute fingerprint, descriptor hash, and canonical content hash.
3. Load the approval record bound by the descriptor; call `evaluate_effective_quality` with `dataset_id`, `canonical_content_hash`, `schema_fingerprint`, and `source_sha256=(parent parquet digest,)`.
4. Publish when the effective state is `PASS` or `WARN_APPROVED`; BLOCK otherwise with the existing attempt/terminal machinery.
5. Manifest gains `quality_raw_state`, `quality_identity_sha256`, `quality_approval_record_id`, `quality_approval_record_sha256` (mirroring T2's base manifest fields); `quality.json` uses the policy-v2 payload shape (`_quality_payload_v2` in `pipeline.py` is the reference — derive_pipeline needs its own copy or a shared helper); `quality-approval.json` (canonical semantics) is written into the commit directory.
6. No-Op evidence keys extend so changed approval semantics cannot produce `VERIFIED_NO_OP`: mirror the base lane's approach in `pipeline.py` lines 535–585 (add the five v2 keys to `identity_evidence` and verify the committed `quality-approval.json` bytes hash to the record's `record_sha256` before honoring a no-op).
7. Policy-v1 derived behavior and commit shape remain byte-compatible (January/Q1).

**Critical ordering constraint:** the parent-side lineage block (`derived_from`) gains the same optional keys T3 added for base parents — `parent_quality_state`, `parent_quality_raw_state`, `parent_quality_approval_record_id`, `parent_quality_approval_record_sha256` when the base runs under policy 2. These lineage keys change `derived_commit_identity`, so they must be added in this slice and remain stable forever after; the January/Q1 lineage shape must stay exactly as today (v1 base parents carry none of these keys — the current code already skips them for v1, verify with tests).

### 5.4 Derived-graph verification

`_authenticate_quality_document` (derive_pipeline.py line 650) accepts only the 4-key v1 shape. It must accept the v2 shape (`state`, `raw_state`, `policy_version`, `identity`, `identity_sha256`, `approval_record_id`, `approval_record_sha256`, `findings`) when the manifest claims policy 2, authenticate findings/identity as now, and verify the committed `quality-approval.json` self-hash + record id match the manifest. `verify_derived_current_graph` (line 719) must accept `WARN_APPROVED` only when the manifest claims policy 2, the committed approval bytes authenticate, and — mirroring `_verify_parent`'s closure discipline — a fresh re-derivation of the retained Parquet rows reproduces the raw `WARN_BLOCKED` identity and re-applying the approval yields `WARN_APPROVED`. `PASS` remains accepted for every policy; policy-v1 `WARN_BLOCKED` still rejects.

### 5.5 Research-lane parent acceptance

`research_pipeline.py` `_verify_parent` (line 297) calls `verify_derived_current_graph` then re-evaluates parent quality and requires `fresh_report.state == "PASS"` (line 393). It must learn the policy-2 parent path exactly as T3 taught `derive_pipeline._verify_parent`: when the parent manifest claims policy 2 and state `WARN_APPROVED`, verify the committed approval record (self-hash, record id, dataset binding, canonical content hash binding, schema fingerprint binding, parent Parquet source digest binding, raw identity digest binding) and re-derive the effective decision fresh; accept only `PASS`/`WARN_APPROVED`; reject manifest-only state claims. Validation and evaluation lanes consume research/validation outputs (not the 1h lane directly — validation's parent is the research table; evaluation's parents are validation + research), and both remain PASS-only with zero changes.

## 6. Exact allowlist

```text
docs/superpowers/plans/2026-08-28-data-slice-010b-reviewed-derived-zero-volume-approval.md
configs/quality/approvals/binance-usdm-btcusdt-1h-2024-derived-zero-volume.v1.yaml
configs/datasets/binance-usdm-btcusdt-1h-2024-derived.yaml
docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md
docs/superpowers/plans/2026-08-28-data-slice-010a-reviewed-zero-volume-approval.md
docs/superpowers/plans/2026-08-28-data-slice-010-temporal-expansion-2024.md
src/quantara/derive_descriptor.py
src/quantara/quality_approval.py
src/quantara/derive_pipeline.py
src/quantara/manifests.py
src/quantara/research_pipeline.py
tests/test_derivation_descriptor.py
tests/test_derive_pipeline.py
tests/test_derive_recovery.py
tests/test_quality_approval.py
tests/test_research_pipeline.py
tests/test_integration_year.py
README.md
```

Do not change `quality.py`, `derive_quality.py`, `canonical.py`, `parsing.py`, `aggregation.py`, `features.py`, `folds.py`, evaluation/validation quality thresholds, any January/Q1 config, `kernel/**`, `pyproject.toml`, `uv.lock`, dependencies, official rows, or anything under `data/` in Git.

If implementation genuinely requires a file outside the allowlist, stop `BLOCKED` and report the exact seam; do not silently widen scope.

## 7. Tasks and commits

### T0 — Preflight, evidence reproduction, plan commit

1. Run the §3 preflight.
2. Reproduce §4 offline from the retained base Parquet object (no network): aggregate to 1h, confirm 8,784 bars, `WARN_BLOCKED` with exactly one `derived_zero_volume_bucket` warning of count 1, the frozen content hash `9129f9ac…`, raw identity SHA-256 `14c8b656…`, and the finding digest `11db14d6…`. Also verify the 1d lane evaluates `PASS` with 366 bars and no zero-volume bars.
3. Commit only this plan:

```text
docs(quality): plan derived zero-volume bucket approval
```

Stop `BLOCKED` if any frozen evidence differs.

### T1 — Descriptor and approval-record plumbing

Red first in `tests/test_derivation_descriptor.py` and `tests/test_quality_approval.py`.

1. Extend `APPROVABLE_WARNING_CHECK_IDS` with `derived_zero_volume_bucket`.
2. Relax `derive_descriptor.py` policy validation: `"2"` accepted only with `quality_approval`; `"1"` only without. All other validation unchanged.
3. Add the frozen approval YAML per §5.1 (timestamp and self-hash computed at execution; verify by loading back).
4. Update the 1h-2024 derived descriptor to policy 2 with the approval path.
5. Adversarial descriptor tests: v2-without-approval rejected; v1-with-approval rejected; v2-with-approval accepted; January/Q1 v1 descriptors unchanged and still accepted; approval path traversal still rejected.

Commit:

```text
feat(descriptor): policy-2 derived warning approvals
```

### T2 — Derived pipeline publication under policy v2

Red first in `tests/test_derive_pipeline.py` (and `tests/test_derive_recovery.py` for the no-op path).

1. Implement §5.3 in `run_derivation_pipeline`: pre-compute the content hash before the publication decision when the descriptor is policy 2; evaluate effective quality; publish `WARN_APPROVED` with the v2 manifest/quality/content shapes and `quality-approval.json` in the commit directory.
2. Extend no-op evidence keys (§5.3 item 6) so approval-semantics drift cannot verify as no-op.
3. Keep policy-v1 behavior byte-compatible; add a regression test proving a v1 PASS parent still publishes the exact legacy commit shape.
4. Add the parent-quality lineage keys for policy-2 base parents (§5.3 critical ordering constraint) and prove January/Q1 lineage shape is unchanged.
5. Update `_authenticate_quality_document` and `verify_derived_current_graph` per §5.4.
6. Required adversarial tests: manifest-only `WARN_APPROVED` forgery rejected; tampered committed approval rejected; repository approval drift rejected; stale content/schema/source/identity bindings rejected; fresh re-derivation mismatch rejected; partial/extra approval rejected; policy-v1 `WARN_BLOCKED` and policy-v2-without-record both block; `PASS` under both policies still publishes/verifies.

Commit:

```text
feat(derive): publish warn-approved derived quality evidence
```

### T3 — Research-lane authenticated WARN_APPROVED parent

Red first in `tests/test_research_pipeline.py`.

1. Implement §5.5 in `research_pipeline.py` `_verify_parent`.
2. Required adversarial tests mirror T3 of 010A: exact authenticated `WARN_APPROVED` 1h parent accepted; manifest-only forgery rejected; tampered committed approval rejected; repository approval drift rejected; stale bindings rejected; fresh re-derivation mismatch rejected; policy-v1 `WARN_BLOCKED` parent rejected; legacy PASS parent accepted byte-compatibly; research output quality remains PASS-only.

Commit:

```text
feat(research): authenticate reviewed-warning derived parents
```

### T4 — Complete Slice 010 year integration

Update `tests/test_integration_year.py` in place (do not replace it with a weaker test):

1. The derived-1h assertions change from `state == "PASS"` to: policy 2; `quality_state == "WARN_APPROVED"`; `quality_raw_state == "WARN_BLOCKED"`; approval record id `binance-usdm-btcusdt-1h-2024-derived-zero-volume-v1` with its committed self-hash; `canonical_content_hash == "9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e"`; quality findings contain exactly one warn (`derived_zero_volume_bucket`, count 1) and 12 passes; committed `quality-approval.json` authenticates.
2. The derived-1d, research, validation, and evaluation assertions remain exactly `PASS`.
3. All original row/fold/null/fingerprint/evaluation contracts and the six `VERIFIED_NO_OP` reruns remain exact.
4. January/Q1 retained commit-tree digests remain unchanged (the test already asserts this).

Run serially:

```bash
uv run pytest tests/test_integration_year.py -m integration -q
uv run pytest -m integration -q
```

Expected integration count: 12 passing (previous 11 + this module). If collection differs, report exact arithmetic rather than editing the expectation to hide a test.

Commit:

```text
test(integration): approve exact 2024 derived zero-volume evidence
```

### T5 — Final gates, documentation, push

1. Update the 010A plan §5.5 assumption note and the Slice 010 plan status: full-year chain completed under policy v2 with both approvals (base 89 candles + derived 1 maintenance hour); future content or warning drift blocks and requires new human review.
2. README status append: derived-lane approval scope, raw/effective distinction, internal-analysis-only posture.
3. Run the complete gates once on the final state:

```bash
set -o pipefail && uv lock --check \
  && uv run ruff check . \
  && uv run pytest -m "not integration" -n 4 --dist=load -q \
  && uv run pytest -m integration -q
```

Also run:

```bash
git diff --check
git diff --stat ca68589..HEAD
git ls-files data
git status --short --branch
git log --oneline ca68589..HEAD
```

Acceptance requirements:

- Lock and lint green.
- Offline suite green; report actual count and arithmetic (697 + new tests).
- Integration suite exactly 12 passing.
- January/Q1 descriptor semantics, frozen hashes, current pointers, and retained commit digests byte-identical.
- Raw 1h warning remains visible and reproducible; effective state is authenticated `WARN_APPROVED`, never fabricated `PASS`.
- All six year stages complete and no-op reruns verify.
- Diff is a subset of §6; no tracked `data/`; no dependency/kernel/lock changes.

Only after all gates pass:

```bash
git push origin main
git rev-parse HEAD origin/main
git status --short --branch
```

Push once. If push fails, report local completion and publication `BLOCKED`; do not rewrite or retry destructively.

## 8. Failure handling

- Any frozen evidence mismatch: `BLOCKED`; do not regenerate the approval around new values.
- Any warning besides the exact approved `derived_zero_volume_bucket` finding: `BLOCKED`.
- Any hard failure: `FAIL`; approval is irrelevant.
- Any approval/descriptor/source/content/policy/identity mismatch: `BLOCKED` before Parquet publication.
- Any downstream inability to independently reproduce the raw findings and approval decision: reject the parent.
- Network remains confined to integration tests and `data.binance.vision`; retained objects should make reruns lightweight.
- Never "fix" acceptance by changing rows, thresholds, expected counts, timestamps, folds, metrics, or tests.
- Never stage runtime data or temporary approval-generation files.

## 9. Required final report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` and include:

- Starting/ending HEAD and final `git status`.
- Exact per-task commits and allowlist diff.
- Raw T0 evidence reproduction: parent digest set, 1h content hash, raw state, warning count, finding digest, raw identity hash, 1d PASS proof.
- Derived approval record ID, UTC decision time, self-hash, and load-back result.
- Focused test commands/results.
- Real serial year-chain output and six restored pointer values.
- Final lock/lint/offline/integration summaries with count arithmetic.
- January/Q1 byte-compatibility evidence.
- Push result and `HEAD == origin/main` proof.
- Any limitation or unverified claim stated explicitly.
