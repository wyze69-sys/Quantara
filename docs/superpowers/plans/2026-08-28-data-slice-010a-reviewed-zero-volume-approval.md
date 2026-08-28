# Quantara Data Slice 010A — Reviewed Zero-Volume Warning Approval and Slice 010 Recovery Plan

**Status:** Proposed implementation plan; code not yet changed
**Date:** 2026-08-28
**Project root:** `D:\PROJECT\Quantara`
**Purpose:** Unblock the full-year 2024 chain without hiding the observed warning, weakening hard quality checks, or changing January/Q1 evidence.

## 1. Decision

Implement the quality-state model already described by the governing Slice 001 design: preserve the original `WARN_BLOCKED` findings, add one immutable and content-bound owner approval record, derive the effective state `WARN_APPROVED` only when every warning matches that record exactly, and allow that authenticated full-year base commit to feed derivation under quality policy v2.

This is a **formal policy amendment**, not a test workaround. Slice 010's policy-v1 run remains honestly `BLOCKED`; Slice 010A introduces the narrowly scoped mechanism that permits this exact reviewed warning under policy v2.

Rejected approaches:

- **Treat zero volume as PASS globally:** rejected because it erases real evidence and weakens January/Q1 semantics.
- **Change the integration test to expect exit 2:** rejected because it abandons the requested full-year chain.
- **Skip/drop/fill the 89 candles:** rejected because it changes official source content, breaks continuity/reconciliation, and creates data leakage/integrity risk.
- **Allow all `WARN_BLOCKED` parents downstream:** rejected because it destroys fail-closed behavior.
- **Hard-code “89 is okay” in Python:** rejected because it is not bound to the exact dataset, sources, content, findings, policy, or owner decision.

## 2. Paste-ready Codex launcher

```text
Work in D:\PROJECT\Quantara. Do not reset, clean, stash, or discard anything.

Read this file completely:
docs/superpowers/plans/2026-08-28-data-slice-010a-reviewed-zero-volume-approval.md

Then execute T0 through T6 exactly, using focused red-to-green TDD. Preserve the four
existing Slice 010 commits and the untracked tests/test_integration_year.py. Make only
allowlisted changes. Do not weaken quality checks, remove warning evidence, fabricate
PASS, or alter official rows.

OWNER AUTHORIZATION: By giving you this launcher, the repository owner authorizes one
immutable quality-warning approval record for the exact frozen evidence in §4 only:
dataset binance_usdm_btcusdt_klines_1m_2024, canonical content hash
28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5,
quality-identity SHA-256 10e100b458244a3d496666afaf37ef1518da15e8d8503d463abc632eccf343b8,
and exactly 89 zero_volume_candle warnings. This authorizes no other warning, dataset,
content, source set, or policy. Record the execution-time UTC decision timestamp and
owner identity 258711354+wyze69-sys@users.noreply.github.com. If any frozen value does
not reproduce exactly, STOP BLOCKED and create no approval record.

Run focused checks during repair and the complete final gates once on the final unchanged
state. Commit each task as specified. Push only after every gate passes. Report raw
commands/results and COMPLETE, BLOCKED, or INCOMPLETE. Then STOP.
```

## 3. Starting state and preservation gate

Expected state before Codex edits:

```text
branch: main
HEAD: 4f23b0a9b261d880080634ae3ac9cca6d77ed6c1
main...origin/main: ahead 4
commits after ca68589:
  4f23b0a feat(configs): 2024 full-year dataset descriptors
  2aa3f99 feat(evaluation): approved period contracts for 2024 ranges
  32278d5 feat(descriptor): full-year 2024 range identity
  4b9cfc2 docs(expansion): slice 010 temporal expansion 2024 plan
untracked:
  tests/test_integration_year.py
```

T0 must run and paste:

```bash
git status --short --branch
git log --oneline ca68589..HEAD
git config user.email
git ls-files data
git status --ignored --short data
uv run ruff check tests/test_integration_year.py
```

Hard gates:

- Preserve the four commits and the untracked integration file; never `git reset`, `git clean`, `git stash`, or rewrite history.
- `data/` remains ignored and untracked. Runtime files may be read and pipelines may write there, but no `data/` path may be staged.
- If HEAD, branch, tracked changes, or existing commit list differs materially, report `BLOCKED`; do not repair unrelated drift.
- Do not rerun the full offline suite in T0. Slice 010 T4 already established 654 offline passes; the full suite is rerun once in T6 on the final state.

## 4. Frozen real-archive evidence

The failed policy-v1 run was fail-closed and all 12 HTTP responses were 200. Independent local parsing of the retained, checksum-authenticated archives reproduced:

- Rows: **527,040**; source order valid.
- Schema fingerprint: `f0d6a8dd92a1a4f1dcf29c4f9222c4ec7daa75a2e648ead6b4bfa453d347724a`.
- Canonical content hash (Rust kernel): `28137ac3d5bf2f46156caf0dc188bd33cb392f4d110d8353af759c21b8648db5`.
- Raw quality state: `WARN_BLOCKED`.
- The only non-pass finding: `zero_volume_candle`, warning severity, count **89**, evidence `{"occurrences": 89}`.
- Canonical finding JCS SHA-256: `6db969a652860d9fe74f6725e33f7aaad43c9cfe1b35fbeed7bfccecb24bcc68`.
- Full quality-identity JCS SHA-256: `10e100b458244a3d496666afaf37ef1518da15e8d8503d463abc632eccf343b8`.
- All 89 source rows are in the official October archive on 2024-10-28 UTC, have both base and quote volume equal to zero, and have `trade_count == 0`. All hard checks, continuity, uniqueness, boundaries, positive-price checks, and source reconciliation pass.
- Earliest warning row: `2024-10-28T16:21:00Z` (`1730132460000`). Latest: `2024-10-28T21:13:00Z` (`1730149980000`).
- Ordered source-archive digest set SHA-256: `f7202c861a7f4fc66ea0969551ca763958360a37d3f98a22932012a40cce2cca`.

Ordered monthly archive SHA-256 values:

```text
2024-01 21eeac04a76a7a35b10467e5e752fb2f8cff77cdeb57df6b50a23ce8d69bb190
2024-02 1407acbf8ad99911bdf582805699b7e85fdbc346dbe12618ce8b6369f0d8058d
2024-03 040b8e448e4243072b88b0d9908dfebed91bba943b75f4e831fa5337a2e1dab9
2024-04 6a41f002da0c8e3f60bd46c841ea4ed766fb195764ad3b6b10e4f508d29c2eb7
2024-05 42de617ed643def54b5a2c3fceb7cd2edec91aafaa01104a097b2ded5c5122d4
2024-06 93499da4990fec5471bb0d73c91116e7d20a8b2697d7a4491665d6d1b8e85c85
2024-07 97f9cd5104a33828c5c2d8d03a2796d600102ab88737d1c6da515b9609540c3c
2024-08 f69dbcebfd7108dc97825bd6c35d8d9a51745082f66617cb69de888e867e8e89
2024-09 16fe2e13728236bfbd3efee99671612daadeea3b62dfd55d8874feae9faa4946
2024-10 aa8c79ad120a8d870e23276d1ad5966f99f59bc0a1886ef5927a3808a5efee36
2024-11 9c3dad038f4b043ec51d4200f57d15a0a07b3fc32b3ea3dca6a96543b9624941
2024-12 bfce141d2a152c2b94d85b797fe18ebfa195fa0e6091a7ccc06663ae1309466f
```

Before creating the approval record, Codex must reproduce all bold/frozen values from retained official objects using project parsers and hash functions. A mismatch is `BLOCKED`, not something to update in this plan.

## 5. Policy-v2 contract

### 5.1 Immutable approval record

Add `configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml` with strict schema `quantara.quality-warning-approval/v1` and exactly these semantic fields:

- `record_id` (fixed unique ID).
- `dataset_id`.
- `canonical_content_hash`.
- `schema_fingerprint`.
- ordered `source_sha256` list of 12 monthly digests.
- `quality_policy_version: "2"`.
- `quality_identity_sha256`.
- `approved_findings`: exactly one item containing `check_id`, `count`, and `canonical_finding_sha256`. The digest covers the complete JCS finding object — `check_id`, `outcome`, `severity`, `count`, and `evidence` — not merely the nested evidence mapping. For this approval the exact payload is `{"check_id":"zero_volume_candle","count":89,"evidence":{"occurrences":89},"outcome":"warn","severity":"warning"}` and its SHA-256 is `6db969a652860d9fe74f6725e33f7aaad43c9cfe1b35fbeed7bfccecb24bcc68`.
- `approver`: `258711354+wyze69-sys@users.noreply.github.com`.
- `decision_time_utc`: actual UTC execution time in strict `YYYY-MM-DDTHH:MM:SSZ` form.
- `rationale`: official source contains 89 no-trade candles; rows are preserved, all hard invariants pass, and approval is internal-analysis-only.
- `scope`: exact full-year BTCUSDT USD-M 1m canonical content only; no wildcard or future-data scope.
- `record_sha256`: SHA-256 of JCS-canonicalized validated semantics excluding `record_sha256` itself.

Unknown/missing keys, duplicate approved finding IDs, malformed hashes/timestamps, empty rationale/scope, wildcard values, non-warning finding IDs, or self-hash mismatch must fail closed.

### 5.2 Descriptor binding

The full-year base descriptor changes to quality policy `"2"` and explicitly names the approval record path. January and Q1 descriptors remain byte-identical with policy `"1"` and no approval field.

`descriptor.py` must enforce the approved combinations, not accept arbitrary policy strings:

- v1 January: policy 1, no approval record.
- v2 Q1: policy 1, no approval record.
- v2 full year: policy 2, exact repository-relative approval path.
- Any other policy/path combination: invalid descriptor.

Include the approval-record path in canonical descriptor semantics. Never load paths outside the repository or accept absolute/traversal paths.

### 5.3 Raw versus effective quality state

`evaluate_quality` remains unchanged: the 89 candles still produce raw `WARN_BLOCKED`, and all existing policy-v1 tests remain unchanged.

A new strict policy/approval module computes a separate effective decision:

- Raw `PASS` -> effective `PASS`; an unnecessary approval is rejected.
- Raw `FAIL` -> effective `FAIL`; no approval can override a hard failure.
- Raw `WARN_BLOCKED` + policy 1 -> effective `WARN_BLOCKED`.
- Raw `WARN_BLOCKED` + policy 2 -> effective `WARN_APPROVED` only if every warning, and no extra warning, is covered by the exact authenticated record and every dataset/source/content/policy binding matches.
- Missing, unreadable, malformed, stale, partial, extra, or mismatched approval -> `WARN_BLOCKED` and exit 2.

Never mutate finding outcomes or the raw quality identity.

The governing Slice 001 specification currently says the quality identity includes the policy version, while the shipped `quality_identity()` implementation is the JCS identity of ordered raw findings only. The formal amendment must resolve this explicitly: define the existing identity as the policy-independent **raw finding identity**, preserve its bytes and the frozen SHA-256 `10e100b458244a3d496666afaf37ef1518da15e8d8503d463abc632eccf343b8`, and add a separate effective-decision identity/binding containing policy version, raw-identity SHA-256, effective state, approval record ID, and approval record SHA-256. Do not silently change `quality_identity()` or invalidate existing January/Q1 evidence.

### 5.4 Committed evidence

For policy v2, commit the exact validated approval **semantics** alongside `manifest.json`, `content.json`, and `quality.json` as canonical `quality-approval.json`. The authoritative identity is `record_sha256` over canonical semantics excluding the self-hash; YAML comments, whitespace, and key order are intentionally non-semantic and do not invalidate a no-op. Semantic changes must change the record hash and invalidate no-op eligibility.

Policy-v2 `quality.json` must contain exact, authenticated fields for:

- effective `state: WARN_APPROVED`;
- `raw_state: WARN_BLOCKED`;
- `policy_version: "2"`;
- unchanged full `identity` and `findings`;
- `identity_sha256`;
- approval `record_id` and `record_sha256`.

Manifest and content evidence must both bind the raw/effective states, quality identity hash, approval record ID, and approval record SHA-256. Extend base no-op identity comparison to include these fields. Policy-v1 commit shapes and identities remain byte-compatible and readable.

### 5.5 Downstream eligibility

Only the base-to-derived parent verifier needs to accept `WARN_APPROVED`, because derived outputs should evaluate to `PASS`; research, validation, and evaluation continue consuming PASS-only parents.

The derived verifier may accept a base parent when:

- state is `PASS`; or
- state is `WARN_APPROVED`, policy is exactly 2, the descriptor explicitly binds the approval record, committed approval bytes hash correctly, repository approval semantics match committed semantics, raw findings re-authenticate, a fresh evaluation of retained Parquet rows reproduces the same raw `WARN_BLOCKED` identity, canonical content/source/schema bindings match, and applying the approval fresh yields the same `WARN_APPROVED` result.

A literal manifest string is never sufficient. Any mismatch blocks derivation. Existing January/Q1 PASS verification remains byte-compatible.

## 6. Exact allowlist

The executor may change only a subset of:

```text
docs/superpowers/plans/2026-08-28-data-slice-010a-reviewed-zero-volume-approval.md
configs/quality/approvals/binance-usdm-btcusdt-1m-2024-zero-volume.v1.yaml
configs/datasets/binance-usdm-btcusdt-1m-2024.yaml
docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md
docs/superpowers/plans/2026-08-28-data-slice-010-temporal-expansion-2024.md
src/quantara/descriptor.py
src/quantara/quality_approval.py
src/quantara/pipeline.py
src/quantara/derive_pipeline.py
src/quantara/manifests.py
src/quantara/publication.py
tests/test_descriptor.py
tests/test_quality_approval.py
tests/test_pipeline.py
tests/test_pipeline_multi_month.py
tests/test_derive_pipeline.py
tests/test_derive_recovery.py
tests/test_publication.py
tests/test_integration_year.py
README.md
```

Do not change `quality.py`, `canonical.py`, `parsing.py`, `aggregation.py`, `features.py`, `folds.py`, evaluation/research/validation quality thresholds, any existing January/Q1 config, `kernel/**`, `pyproject.toml`, `uv.lock`, dependencies, official rows, or anything under `data/` in Git.

If implementation genuinely requires a file outside the allowlist, stop `BLOCKED` and report the exact seam; do not silently widen scope.

## 7. Tasks and commits

### T0 — Preflight, evidence reproduction, plan commit

1. Run the §3 preflight.
2. Reproduce §4 from retained objects without network and without writing tracked files.
3. Confirm `evaluate_quality` returns raw `WARN_BLOCKED`, only `zero_volume_candle` is non-pass, and count is 89.
4. Commit only this plan:

```text
docs(quality): plan reviewed warning approval recovery
```

Stop `BLOCKED` if any frozen evidence differs.

### T1 — Formal specification amendment and strict approval loader

Red first in new `tests/test_quality_approval.py`. Implement `quality_approval.py` as a small state-free validation/policy module. It must validate strict shape/types, canonical self-hash, repository-contained path, exact warning coverage, and all bindings described in §5.

Required adversarial tests:

- exact record -> `WARN_APPROVED`;
- missing record -> blocked;
- stale dataset/content/schema/source/policy/quality identity -> blocked;
- changed count/evidence hash/check ID -> blocked;
- one uncovered warning or one extra approved warning -> blocked;
- hard failure cannot be approved;
- raw PASS cannot consume an approval;
- unknown/missing keys, traversal path, malformed time/hash, duplicate IDs, altered record semantics/self-hash -> rejected; formatting-only YAML changes remain equivalent;
- policy 1 remains PASS-only and warning-blocking.

Amend the Slice 001 design sections 12.1, 12.3, 13.1, 13.3, 14.2, 15.9, and 16 narrowly. Resolve the shipped-contract mismatch by defining the existing quality identity as the policy-independent raw finding identity, and define the separate effective-decision binding described in §5.3. The original January golden slice remains PASS-only; later policy v2 may publish `WARN_APPROVED` only through exact immutable approval authentication. Add no broader exception.

Commit:

```text
feat(quality): authenticated reviewed-warning approvals
```

### T2 — Descriptor and base-pipeline integration

Red first for descriptor and multi-month pipeline tests.

1. Enforce the exact descriptor policy/path combinations in §5.2.
2. Add the frozen approval YAML only after §4 reproduces exactly; calculate its timestamp and self-hash, then verify by loading it back.
3. In `pipeline.py`, compute schema fingerprint, descriptor hash, canonical content hash, and source digest set before the publication decision when raw warnings exist. Do not write Parquet before approval succeeds.
4. Apply policy v2 without mutating the raw report.
5. Publish the policy-v2 evidence shape from §5.4 and include canonical approval JSON in the commit directory.
6. Extend no-op evidence and verification so changed approval semantics cannot produce `VERIFIED_NO_OP`; formatting-only YAML changes remain semantically equivalent by design.
7. Policy-v1 behavior and commit shape remain byte-compatible.

Focused gates:

```bash
uv run pytest tests/test_descriptor.py tests/test_quality_approval.py tests/test_pipeline.py tests/test_pipeline_multi_month.py tests/test_publication.py -q
uv run ruff check src/quantara/descriptor.py src/quantara/quality_approval.py src/quantara/pipeline.py src/quantara/manifests.py src/quantara/publication.py tests/test_quality_approval.py
```

Commit:

```text
feat(pipeline): publish exact warn-approved quality evidence
```

### T3 — Authenticated WARN_APPROVED base-to-derived seam

Red first in derive tests. Update the base-parent verifier only as described in §5.5.

Required tests:

- exact authenticated WARN_APPROVED year base accepted;
- manifest-only state forgery rejected;
- missing/tampered committed approval rejected;
- repository approval drift rejected;
- stale source/content/schema/quality identity rejected;
- fresh retained-row evaluation mismatch rejected;
- partial/extra warning approval rejected;
- hard failure rejected;
- policy-v1 WARN_BLOCKED and WARN_APPROVED both rejected;
- legacy PASS parent still accepted with existing evidence shape;
- derived current/no-op verification remains PASS-only.

Focused gate:

```bash
uv run pytest tests/test_derive_pipeline.py tests/test_derive_recovery.py tests/test_quality_approval.py -q
```

Commit:

```text
feat(derive): authenticate reviewed-warning base parents
```

### T4 — Complete Slice 010 year integration

Use the already written `tests/test_integration_year.py`; do not replace it with a weaker test. Update only its base-quality assertions to require:

- raw state `WARN_BLOCKED`;
- effective state `WARN_APPROVED`;
- policy 2;
- approval record ID/hash and unchanged 89-count finding;
- all other findings pass;
- canonical content hash exactly `28137ac3...8db5`;
- committed approval bytes authenticate;
- derived 1h/1d, research, validation, and evaluation states remain `PASS`;
- all original row/fold/null/fingerprint/evaluation contracts remain exact;
- six-layer reruns are `VERIFIED_NO_OP`;
- all six pointers restore byte-exactly in `finally`;
- January/Q1 retained commit-tree digests remain unchanged.

Run serially:

```bash
uv run pytest tests/test_integration_year.py -m integration -q
uv run pytest -m integration -q
```

Expected integration count is the previous 11 plus this module = 12. If collection differs, report exact arithmetic rather than editing the expectation to hide a test.

Commit:

```text
test(integration): approve exact 2024 zero-volume evidence
```

### T5 — Status documentation

1. Change Slice 010 plan status from proposed to: policy-v1 T5 honestly blocked on 89 official zero-volume candles; resumed only through Slice 010A policy-v2 approval. Do not rewrite its historical forbidden-scope contract.
2. Append README status with raw/effective state distinction, exact scope, internal-analysis-only posture, and the original full-year acceptance numbers.
3. State explicitly that future content or warning drift blocks and requires a new human review; this approval does not roll forward.

Commit:

```text
docs(expansion): record reviewed full-year quality status
```

### T6 — Final gates, audit, push

Run focused tests during fixes. On the final cleaned state, run the complete gates once:

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
- Offline suite green; report actual count and arithmetic from 654 plus the exact number of new tests.
- Integration suite exactly 12 passing unless collection arithmetic proves a different legitimate count.
- January/Q1 descriptor semantics, frozen hashes, current pointers, and retained commit digests byte-identical.
- Raw 2024 warning remains visible and reproducible; effective state is authenticated `WARN_APPROVED`, never fabricated `PASS`.
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
- Any warning besides the exact approved `zero_volume_candle` finding: `BLOCKED`.
- Any hard failure: `FAIL`; approval is irrelevant.
- Any approval/descriptor/source/content/policy/identity mismatch: `BLOCKED` before Parquet publication.
- Any downstream inability to independently reproduce the raw findings and approval decision: reject the parent.
- Network remains confined to integration tests and `data.binance.vision`; retained objects should make the base rerun lightweight.
- Never “fix” acceptance by changing rows, thresholds, expected counts, timestamps, folds, metrics, or tests.
- Never stage runtime data or temporary approval-generation files.

## 9. Required final report

Report `COMPLETE`, `BLOCKED`, or `INCOMPLETE` and include:

- Starting/ending HEAD and final `git status`.
- Exact per-task commits and allowlist diff.
- Raw T0 evidence reproduction, including source digest set, canonical content hash, raw quality state, warning count, finding hash, and quality-identity hash.
- Approval record ID, UTC decision time, self-hash, and load-back result.
- Focused test commands/results.
- Real serial year-chain output and six restored pointer values.
- Final lock/lint/offline/integration summaries with count arithmetic.
- January/Q1 byte-compatibility evidence.
- Push result and `HEAD == origin/main` proof.
- Any limitation or unverified claim stated explicitly.
