# Protocol v1.1 — Packet C5: Synchronization, Independent Fixture, and Semantic Freeze

**Status:** `NEXT` — not started
**Date:** 2026-09-02
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c5-freeze`
**Branch:** `protocol-v11-c5-freeze`
**Packet parent commit:** `c2e1a8d` (`main`, the C5a merge commit)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists and why it is not split

C1 froze version identity and `T+2ms` ordering. C2 froze inference (`B4`). C3 bound the
estimator and the three-hypothesis optional family. C4 froze OI timestamp role, the
final pre-2025 refit, the sealed 2026 target-only buffer, and the one-year 2025
`REPLICATED` gate. C5a bound the draft loader, the every-key-except-own-hash
projection rule, the coverage/claim-scope contract, and the closed exclusion
vocabulary. One item remains:

```text
deferred_change_set["C5"].status == "DEFERRED"
spec §11: | Coverage and final freeze | `DEFERRED` | C5 |
spec §12: frozen_semantic_sha256 == NOT_YET_ASSIGNED_PENDING_PACKET_C5
```

C5 discharges it: synchronize spec/YAML, hand-render an independent expected fixture,
compute the Protocol v1.1 semantic SHA-256 **once**, flip the document from draft to
frozen, convert the loader and guard from refuse-everything to a real frozen-protocol
authorization path, and add the audit's repeated tamper, future-mutation, boundary,
solver, bootstrap, and 2025-seal tests.

**This packet is deliberately not split, and the reason is a hard ordering
constraint.** `src/quantara/protocol_v11.py::load_protocol_v11` currently *requires*
the draft state:

```python
expected_state = {
    "frozen_semantic_sha256": V11_UNASSIGNED_HASH,
    "protocol_status": "DRAFT_UNFROZEN_SUCCESSOR",
    "scoring_permission": "NONE_UNTIL_FROZEN",
}
```

The instant the YAML flips to frozen, the loader raises and every test in
`tests/test_protocol_v11_loader_coverage.py` goes red. So the YAML freeze and the
loader freeze-path cannot land in different commits without an intermediate red state.

A "render the fixture first, freeze later" split fails for a second reason:
`protocol_status` and `scoring_permission` are **in hash scope** (only
`frozen_semantic_sha256` is excluded). A fixture rendered while the document is still
`DRAFT_UNFROZEN_SUCCESSOR` would encode draft strings and would have to be rewritten
at freeze, so the "independent" render would happen twice and the second pass would be
a copy of the first. One packet, one render, one hash.

This is a **specification freeze, not a scientific change.** No new feature, no new
target, no new model family, no new threshold, no unsealing.

## 2. Hermes pre-verified findings

Measured in this exact worktree against committed code at `c2e1a8d` before this plan
was written. Codex must **reproduce each one as a test or as a reported check**, not
trust this document.

**H0 — the baseline is green and the tree is clean.** Measured at `c2e1a8d`, before
Hermes's docs commit was added on top:

```text
git rev-parse c2e1a8d                  c2e1a8d912d00ff20ff3a293652e6191c7359eeb
git rev-parse --abbrev-ref HEAD        protocol-v11-c5-freeze
git status --short                     (empty)
git merge-base --is-ancestor bcd1f1c c2e1a8d   -> C5a IS ancestor
git merge-base --is-ancestor 3c77610 c2e1a8d   -> C4  IS ancestor
gh pr list --state all                 PR #9 MERGED 2026-09-02T01:46:15Z (C5a)
focused 8-file protocol gate           211 passed
full suite, serial                     1129 passed, 16 deselected, 1 warning
ruff check src tests benchmarks        All checks passed!
```

Your `HEAD` at start is **not** `c2e1a8d`: it is Hermes's docs commit, whose sole parent
is `c2e1a8d` and whose only content is this plan plus the master-plan update. See §4.

The full suite takes ~23 minutes single-process. Budget for it; do not skip it. The
pass floor for this packet is **1129 plus the new tests**.

**H1 — the document now has 49 top-level keys, 48 in scope.** C5a raised the count
from 46 by adding `semantic_hash_scope`, `coverage_and_claim_scope`, and
`exclusion_reason_vocabulary`. The committed scope clause is self-consistent:

```text
projection_rule:        every top-level key except the excluded set
excluded_keys:          [frozen_semantic_sha256]
in_scope_key_count:     48
total_key_count:        49
canonicalization:       json.dumps(projected, sort_keys=True, separators=(',',':'), ensure_ascii=True)
hash_algorithm:         sha256
basis:                  utf8_text_normalized_to_lf_before_sha256
owner_packet_for_value: C5
```

`src/quantara/protocol_v11.py` pins the same numbers as `V11_IN_SCOPE_KEY_COUNT = 48`
and `V11_TOTAL_KEY_COUNT = 49` and cross-checks them against the loaded document. Any
key C5 adds or removes must move the YAML clause, both module constants, and the
fixture together, or `hash_scope_projection` fails closed.

**H2 — the fixture C5 must hand-render is 48 keys, 41,862 canonical bytes, 1,181
pretty-printed lines. 23.7% of it is inheritable and 76.3% is not.**

```text
ALL 48 in-scope keys, indent=2 pretty JSON   50,108 bytes / 1,181 lines
canonical JSON (the hashed string)           41,862 bytes
16 keys byte-identical to the v1 fixture's expected_semantic    9,920 bytes (23.7%)
32 keys new or changed vs v1                                   31,893 bytes (76.3%)
```

The two per-key figures are sums of each key's canonical `"key":value` fragment, so
they total 41,813, not 41,862. The 49-byte remainder is the wrapper: two braces plus the
47 separating commas. That is arithmetic, not a missing key — do not go hunting for it.
The percentages are shares of 41,813.

The 16 inheritable keys, verified equal to `tests/fixtures/protocol_v1_expected.json`
→ `expected_semantic` by value comparison:

```text
audit_reference_hash_basis  canonical_lane_immutability  canonical_record_fields
cross_quote_dislocation_policy  dislocation_roles  feature_formulas
feature_window_completeness  inventory  logistic_constants
missing_and_duplicate_policy  model_mandates  planning_baseline
realized_volatility  research_question  search_and_calibration_restrictions
success_gate
```

The 32 that must be rendered from the specification, largest first by canonical bytes:

```text
validation 5,334   replication_gate_2025 3,505   target_endpoint_buffer_2026 2,664
point_in_time 2,480   optional_family_retention 2,429   exclusion_reason_vocabulary 2,119
final_refit 1,654   oi_timestamp_resolution 1,381   target 1,350   model_ladder 1,251
coverage_and_claim_scope   exclusions   semantic_hash_scope   estimator_binding
calibration   fail_closed_causes   fit_failure_propagation   ladder_widths
sealed_2025   standing_rejections   deferred_change_set   lineage   outcome_states
audit_references   protocol_id   protocol_status   frozen_date   draft_date
supersedes   predecessor_semantic_sha256   authorizing_audit   scoring_permission
```

**H3 — the v1.1 spec is not a mechanically sufficient render source for 12 of those
32 keys.** Their key names never appear anywhere in
`docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`:

```text
deferred_change_set  estimator_binding  exclusion_reason_vocabulary
fit_failure_propagation  frozen_date  ladder_widths  optional_family_retention
outcome_states  point_in_time  replication_gate_2025  semantic_hash_scope
target_endpoint_buffer_2026
```

The spec carries the *content* under prose section headings (§5 Point-in-time
contract, §7 Validation and gate, §8 Sealed 2025, §11 Deferred change-set items, §12
Draft semantic-hash state) but not the machine key names. Consequence: "independent"
cannot mean "regenerate each key by grepping the spec for its name." §6 defines the
render protocol that C5 must actually follow, and §9.1 requires C5 to close this gap
by naming every machine key in the spec so the *next* auditor has a mechanical path.

**H4 — five numeric literals in the changed keys are absent from the spec text, and
four of them are derivable.**

```text
'0.95'                 validation.bootstrap.interval.confidence   (spec writes "two-sided 95%")
13432793617478683004   replication_gate_2025.comparison_id.seeds_2025.M2
17576365771105646995   replication_gate_2025.comparison_id.seeds_2025.M2K
15946086953525544617   replication_gate_2025.comparison_id.seeds_2025.M3
3803725181447297110    replication_gate_2025.comparison_id.seeds_2025.M4
```

Hermes independently re-derived all four seeds from the frozen C2 rule and they
**match**:

```text
payload = "quantara-protocol-v1_1|bootstrap-b4|" + comparison_id + "|2025"
seed    = int.from_bytes(sha256(payload.encode("utf-8")).digest()[:8], "big")

REPLICATION_2025|M2_vs_B2   -> 13432793617478683004  MATCH
REPLICATION_2025|M2K_vs_B2  -> 17576365771105646995  MATCH
REPLICATION_2025|M3_vs_B2   -> 15946086953525544617  MATCH
REPLICATION_2025|M4_vs_B2   -> 3803725181447297110   MATCH
```

The `comparison_id` string is load-bearing: deriving from a bare `"M2"` instead of
`"REPLICATION_2025|M2_vs_B2"` yields `13605954171529852932`, a different number.
`src/quantara/replication_c4.py` builds the ids as
`f"REPLICATION_2025|{model}_vs_B2"` and the spec states them at §7. The fixture must
therefore **derive** these four integers rather than copy them, and `'0.95'` must be
rendered as the quoted decimal string it is, never as a float.

**H5 — v1.1 `audit_references` are placeholders, and the eight real predecessor
digests are verified correct on disk.** All eight v1.1 entries read
`INHERITED_FROM_PROTOCOL_V1`. Spec §9 says the digests "are not recopied into this
unfrozen draft… pending the C5 synchronized fixture and semantic freeze." Hermes
recomputed all eight under the declared basis
(`utf8_text_normalized_to_lf_before_sha256`) against the live files:

```text
a7_report    379a70250630f1e914618eda33131f6d396535126cbedbde7955a4216e7b2f72  MATCH
a7_sidecar   3b3b6ea81b3e1d91a9c10140333b2e01ab39929ff9022d0573878defd043ff58  MATCH
a8_report    548ad0c2c6d766f49d5bb41de0fa1fecd0e928ec8939d253db5a1d31e55a9919  MATCH
a8_sidecar   08f972fcbc9776d5a6cdc028a2d7523d24355887b204dddc2277a540c22a2c52  MATCH
a9_report    225793a4723c1f55345084fe0a5be5c68273181798ce96ba61ac3283adaf5fb5  MATCH
a9_sidecar   808c1a17c0b710187c36254c31992d2b645cc2533b7fec4b4c0d05b7d42f7c14  MATCH
a10_report   61881d940dca4810293b487cb172427fc5c18d1936724ba28939eabc4a88e9ee  MATCH
a10_sidecar  621c5781df4d94810dbfc2fa61f9a78767f6b735ed9d42c421d2cfc5e10cfe86  MATCH
```

C5 replaces the eight placeholders with these eight digests. This is a real semantic
change entering the hash, and it is safe precisely because every value was
independently recomputed from the files it names.

**H6 — no freeze path exists in code, and the guard refuses everything.**

```text
load_protocol_v11        requires frozen_semantic_sha256 == NOT_YET_ASSIGNED_PENDING_PACKET_C5
                         requires protocol_status       == DRAFT_UNFROZEN_SUCCESSOR
                         requires scoring_permission    == NONE_UNTIL_FROZEN
                         computes canonical projection but deliberately NO digest
guard_protocol_v11_operation(op) -> NoReturn, raises ProtocolV11GuardError for every op
```

v1's equivalents live in `src/quantara/protocol.py`: `load_protocol` compares the
computed digest against `FROZEN_SEMANTIC_SHA256`, and `guard_protocol_operation`
allows the five pre-gate checks while `score_2025` additionally requires an
HMAC-authenticated, hash-bound, all-pass artifact whose key comes from
`QUANTARA_PROTOCOL_V1_GATE_HMAC_KEY` and whose type is
`quantara-protocol-v1-gate-result`. C5 must give v1.1 the same shape with **v1.1's
own artifact type and own environment key**, because a v1 gate artifact must never
authorize v1.1 scoring and vice versa.

**H7 — the audit's six repeated test categories are unevenly covered. Two are real
gaps.**

```text
tamper            v1 covered (tests/test_protocol.py); v1.1 covered but asserts the DRAFT state
                  (test_draft_state_tampering_is_rejected) and must be re-pointed at the frozen state
future-mutation   NO TEST ANYWHERE. grep for as_of / asof / backward / future_row across tests/
                  returns one string assertion, tests/test_protocol_document_contract.py:291
boundary          PARTIAL. test_v11_time_semantics_are_explicit_and_boundary_ordering_is_causal
                  asserts four eligibility strings but performs arithmetic for funding only.
                  The audit requires "boundary-test every source": kline C+1ms, OI O+5min,
                  Kraken K+1h have no arithmetic test.
solver            covered, tests/test_estimator_c3.py (C3)
bootstrap         covered, tests/test_bootstrap_b4.py (C2)
2025-seal         v1 covered (tests/test_protocol_guardrails.py, 13 tests); v1.1 covered only as
                  "the draft guard refuses everything", which stops being true in this packet
```

The future-mutation gap matters most. `point_in_time.join_rule` states "All joins are
backward as-of joins on `eligibility_ts`; `eligibility_ts < prediction_ts` without
exception" and `point_in_time.forbidden` lists `future_revisions`, but nothing
executable enforces that appending a later-timestamped row leaves earlier features
unchanged.

**H8 — no v1.1 fixture and no v1.1 spec digest pin exist.**

```text
tests/fixtures/protocol_v1_1_expected.json          does not exist
EXPECTED_V11_SPEC_SHA256 pinned in any test         no
v1 precedent: EXPECTED_SPEC_SHA256 = 9aaa9d76557d76ced7a5c0cff20a02dbb7f735f555a8e696c3289dfe3963ec68
              pinned in tests/test_protocol_document_contract.py:43 via _normalized_md_sha256
current v1.1 spec, LF-normalized sha256:
              4c72d2e672d7f46ef9af8b7fb30d3263d6b0a5cb0e52216256aaefb7965ef150
```

That `4c72d2e6…` value is the **pre-edit** digest. C5 edits §9, §11, and §12, so the
pinned value must be the post-edit one. Do not paste `4c72d2e6…` into a test.

**H9 — the v1 fixture's own header states the render standard C5 must meet.**

```json
"fixture_id": "protocol_v1_expected_semantic",
"rendered_by": "Independently hand-rendered from docs/superpowers/plans/2026-08-31-protocol-v1-stage-1-scientific-freeze.md sections 3-4 without importing any production code.",
"canonicalization": {"method": "json.dumps(projected_semantic, sort_keys=True, separators=(',', ':'), ensure_ascii=True)", "hash_algorithm": "sha256"},
"expected_top_level_keys": [27 names],
"semantic_sha256": "91457d3f…c65a",
"expected_semantic": {27 keys}
```

Six keys, that order, 511 lines. "Without importing any production code" is the
binding clause and §6 operationalizes it.

**H10 — there is no `.githooks` directory and `core.hooksPath` is unset.** Commit with
a plain `git commit`. Do not copy the C4 plan's `-c core.hooksPath=.githooks` flag.

**H11 — CI is stricter than a local serial run.** `.github/workflows/ci.yml` runs on
Windows/Python 3.11 with `git config --global core.autocrlf true`, `uv sync --locked`,
`uv run ruff check src tests benchmarks`, `cargo test --locked --manifest-path
kernel/Cargo.toml`, and `uv run pytest -n 4`. `pyproject.toml` sets
`addopts = -m "not integration"`, so the 16 deselected tests are the networked
integration set and stay deselected. Two consequences: the repository-wide lint is the
gate, and the suite must pass under `-n 4`, not only serially.

## 3. Standing prohibitions

Violating any of these fails the packet regardless of test results.

1. **Compute the v1.1 semantic SHA-256 exactly once, from the fixture.** The number is
   derived from `tests/fixtures/protocol_v1_1_expected.json` → `expected_semantic`.
   The YAML is then *proven* to canonicalize to the same value. Do not compute a hash
   from the YAML and back-fill the fixture from it: that inverts the independence
   argument and makes the fixture a copy.
2. **Do not iterate toward a hash.** If the fixture and the YAML disagree, fix the
   *disagreeing key* on its merits from the specification. Never edit the fixture
   merely to make a digest match, and never adjust the YAML to match a fixture typo.
   Report every disagreement found, with the resolution and which side was wrong.
3. **Protocol v1 artifacts stay byte-identical.** The v1 spec, v1 YAML, v1 fixture,
   `src/quantara/protocol.py`, and the v1 hash `91457d3f…c65a` never change. This
   packet has **no** exception for `protocol.py` — see §7.3.
4. **Do not touch frozen packet machinery**: `bootstrap_b4.py`, `estimator_c3.py`,
   `replication_c4.py`, `training_metrics_logistic.py`, `evaluation_metrics.py`,
   `aggregation.py`. C5 imports and wraps; it reimplements nothing scientific.
5. **2025 and 2026 stay sealed.** Do not read, open, enumerate, glob, or list any 2025
   or 2026 data path. No network call. Every fixture and fit is synthetic. Freezing
   the protocol authorizes *nothing* about 2025 by itself:
   `sealed_2025.scoring_permission` is
   `FORBIDDEN_UNTIL_GATE_PASS_AND_PROTOCOL_FREEZE` and only the freeze half becomes
   satisfiable in this packet.
6. **Do not add a minimum-coverage threshold.**
   `replication_gate_2025.coverage_reporting.minimum_coverage_threshold` stays
   `NONE_BY_DESIGN`.
7. **Do not change any scientific constant.** The five replication criteria, `0.02`
   thresholds, `20000` resamples, the 168-clock-hour block length, the nearest-rank
   quantile convention, the `T+2ms` ordering, the `1e-18` quantum, the Holm procedure,
   the three optional hypotheses, and the model ladder all stay exactly as committed.
   The only in-scope value changes permitted are the fifteen enumerated in §5.1, plus
   the one nested addition in §5.2 and the one out-of-scope assignment in §5.3.
8. **No new dependency, and no `numpy`.** Decimal/Fraction/int arithmetic only. No
   float anywhere in hash semantics.
9. **Do not reintroduce any rejected reviewer invention**: signed-return replacement,
   sigma denominator floor, arbitrary coverage cutoff, new feature search, LightGBM,
   XGBoost, return regression, directional actions, economic gates, a new stablecoin
   family to relabel the Kraken confound, Gemini's weaker gate, or Claude's
   seven-condition one-year reuse.
10. **Do not rename any file.** `tests/test_protocol_v11_draft_contract.py` keeps its
    filename even though the document is no longer a draft; renaming it destroys the
    reviewable diff for no benefit. Update the tests inside it.
11. **Do not edit this plan document** or the master plan. Hermes commits both before
    Codex starts; they are outside the packet allowlist.
12. **Do not push, open a PR, merge, or advance to Stage 2.** Stop after the report.

## 4. Preconditions

Run these first, in the worktree. If any fails, stop and report `BLOCKED`.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c5-freeze

# Right worktree, right branch, clean tree.
git rev-parse --abbrev-ref HEAD      # must print protocol-v11-c5-freeze
git status --short                   # must print nothing

# The packet parent, and proof C5a and C4 really are merged. HEAD is Hermes's docs
# commit, whose sole parent is c2e1a8d and whose only content is this plan plus the
# master-plan update. It is your starting SHA (§14 item 1). c2e1a8d is the *byte-identity
# base* used by §12, not HEAD.
git rev-parse HEAD                                   # the docs commit, NOT c2e1a8d
git rev-parse HEAD~1                                 # c2e1a8d912d00ff20ff3a293652e6191c7359eeb
git diff --stat HEAD~1 HEAD                          # only docs/superpowers/plans/, 2 files
git merge-base --is-ancestor c2e1a8d HEAD && echo C5A_MERGE_COMMIT_IS_ANCESTOR_OK
git merge-base --is-ancestor bcd1f1c HEAD && echo C5A_WORK_MERGED_OK
git merge-base --is-ancestor 3c77610 HEAD && echo C4_MERGED_OK

# The regression baseline is green before you change anything.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  -p no:randomly \
  tests/test_protocol.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol_guardrails.py \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_protocol_v11_loader_coverage.py \
  tests/test_bootstrap_b4.py \
  tests/test_estimator_c3.py \
  tests/test_replication_c4.py
```

The last command must report `211 passed`. `PYTHONPATH="$PWD/src"` is mandatory in
every Python invocation in this worktree. Commit with a plain `git commit` (H10).

## 5. The exact contract C5 must freeze

### 5.1 The fifteen in-scope value changes

These are the **only** in-scope changes permitted. Every one was verified present in
its stated current form at `c2e1a8d`. Anything not on this list must keep its
committed bytes.

```text
#   key path                                            from -> to
1   protocol_status                                     DRAFT_UNFROZEN_SUCCESSOR
                                                     -> FROZEN_BEFORE_2022_2024_SCORING
2   frozen_date                                         NOT_APPLICABLE_DRAFT -> 2026-09-02
3   scoring_permission                                  NONE_UNTIL_FROZEN
                                     -> AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED
4   audit_references.a7_report.sha256                   INHERITED_FROM_PROTOCOL_V1 -> 379a7025…
5   audit_references.a7_sidecar.sha256                  INHERITED_FROM_PROTOCOL_V1 -> 3b3b6ea8…
6   audit_references.a8_report.sha256                   INHERITED_FROM_PROTOCOL_V1 -> 548ad0c2…
7   audit_references.a8_sidecar.sha256                  INHERITED_FROM_PROTOCOL_V1 -> 08f972fc…
8   audit_references.a9_report.sha256                   INHERITED_FROM_PROTOCOL_V1 -> 225793a4…
9   audit_references.a9_sidecar.sha256                  INHERITED_FROM_PROTOCOL_V1 -> 808c1a17…
10  audit_references.a10_report.sha256                  INHERITED_FROM_PROTOCOL_V1 -> 61881d94…
11  audit_references.a10_sidecar.sha256                 INHERITED_FROM_PROTOCOL_V1 -> 621c5781…
12  deferred_change_set.C5.status                       DEFERRED -> IMPLEMENTED_PACKET_C5
13  target.quantile.fixture_status                      DEFERRED
                                                     -> REQUIRED_BEFORE_2022_2024_SCORING
14  target.quantile.fixture_owner_packet                C5 -> STAGE_2
15  validation.bootstrap.monte_carlo_justification.holm_threshold_context
                                                        DEFERRED_TO_PACKET_C3
                                                     -> IMPLEMENTED_PACKET_C3
```

Use the **full 64-character** digests from H5 for rows 4–11, not the abbreviations
shown above. Recompute all eight yourself under
`utf8_text_normalized_to_lf_before_sha256` against the paths already recorded in the
document; if any recomputation disagrees with H5, stop `BLOCKED` and report both
values. Do not paste H5's digests without recomputing them.

`draft_date: '2026-09-01'` **stays unchanged.** The document keeps both dates: it was
drafted on the 1st and frozen on the 2nd. Do not delete `draft_date` and do not
change `predecessor_semantic_sha256`, which stays
`91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a` and stays in
hash scope.

Row 1's value is v1's own convention, verified: `configs/protocols/quantara-protocol-v1.yaml`
carries `protocol_status: FROZEN_BEFORE_2022_2024_SCORING`. Row 3's value must name
both surviving preconditions, because freezing satisfies neither on its own — see §5.4.

### 5.2 The one nested key addition

Add exactly one new nested key, under `target.quantile`, immediately after
`fixture_owner_packet`:

```yaml
    fixture_binding_rule: >-
      The synthetic quantile fixture and the frozen k fixture and its hash must exist
      and be committed before any 2022-2024 scoring. Protocol v1.1 freezes the
      threshold method, never the threshold value: k is derived from design data and
      is therefore outside this document's semantic identity.
```

This is a nested addition, so `in_scope_key_count` stays `48` and `total_key_count`
stays `49`. Do not touch either number and do not touch
`V11_IN_SCOPE_KEY_COUNT` / `V11_TOTAL_KEY_COUNT`.

### 5.3 The one out-of-scope assignment

```text
frozen_semantic_sha256   NOT_YET_ASSIGNED_PENDING_PACKET_C5 -> <the computed digest>
```

This key is the sole member of `excluded_keys`, so assigning it does not change the
hash it records. It is assigned **last**, after §6 has produced the fixture and the
fixture and YAML have been proven to agree.

### 5.4 What the freeze authorizes, and the two distinct criterion sets

This subsection exists because the obvious reading — "freezing the protocol unlocks
scoring" — is wrong in two separate ways, and a wrong `scoring_permission` string
would be frozen permanently.

**There are two criterion sets, and only one of them authorizes anything. Verified at
`c2e1a8d`:**

```text
success_gate.criteria                      7 criteria, ids 1..7, a LIST of mappings
                                           byte-equal to Protocol v1's success_gate (compared: True)
                                           unlock_rule: "The frozen candidate may unlock 2025 only
                                           if all criteria hold."
                                           role: AUTHORIZATION for score_2025
replication_gate_2025.criteria             5 criteria, ids 1..5, a LIST of mappings
                                           role: OUTCOME evaluation of the single 2025 run
                                           run_count_permitted 1; outcome REPLICATED or
                                           DID_NOT_REPLICATE
```

`src/quantara/protocol.py` hardcodes `_GATE_CRITERION_IDS = frozenset(str(i) for i in
range(1, 8))` — seven, matching `success_gate`, because the 7-criterion 2022–2024 gate
is what unlocks 2025. **The five replication criteria are not an authorization artifact
and must not be wired into the guard.** They decide what the 2025 result is *called*
after the one permitted run. §8.2 therefore gives v1.1 a 7-criterion authorization set
exactly parallel to v1's, and C5 adds no second artifact type. Note also that both
criteria collections are YAML *lists of mappings* keyed by an integer `id`, while the
gate artifact's `criteria` field is a *mapping* of string ids to booleans — do not
conflate the two shapes.

**Freezing satisfies neither precondition on its own.**

```text
sealed_2025.scoring_permission = FORBIDDEN_UNTIL_GATE_PASS_AND_PROTOCOL_FREEZE
```

That is a conjunction. This packet satisfies the freeze half only; the gate half
requires a passing 7-criterion `success_gate` result on 2022–2024, which cannot exist
yet because no scoring has run. Therefore **2025 stays sealed after this packet**, and
`sealed_2025` must not be edited at all — it is not on the §5.1 list.

2022–2024 scoring is likewise not immediately runnable: the threshold `k` does not
exist (§5.2). So the frozen `scoring_permission` states an authorization with its
remaining precondition named, rather than claiming unconditional permission:

```text
AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED
```

If you believe a shorter or more accurate string is warranted, stop `BLOCKED` and
propose it rather than substituting one silently: this value is frozen forever.

### 5.5 Why `target.quantile` moves to `STAGE_2`

The committed draft says C5 owns the threshold fixture:

```text
target.quantile.fixture_status        DEFERRED
target.quantile.fixture_owner_packet  C5
```

C5 cannot discharge it. Spec §3 lines 92–95 say "do not generate `k`, and do not read
design data," and this plan's prohibition 5 forbids reading any sealed path while
prohibition 4 forbids touching scientific machinery. C5's allowlist (§7) contains no
data path. So freezing the document with `fixture_owner_packet: C5` would permanently
record an obligation pinned to a packet that verifiably did not meet it — the same
class of defect the three-reviewer audit raised against v1.

The repair is a **label change only**. `target.quantile` holds exactly twelve keys,
verified at `c2e1a8d`. Ten are method and stay byte-identical and hashed; only the last
two change:

```text
ordering                            Z_(1) <= ... <= Z_(N)          unchanged
rank                                j = ceil(0.80 * N)             unchanged
selection                           k = Z_(j)                      unchanged
label                               Y_t = 1[Z_t > k]               unchanged
decimal_precision                   50                             unchanged
decimal_rounding                    ROUND_HALF_EVEN                unchanged
interpolation                       FORBIDDEN                      unchanged
threshold_rounding                  FORBIDDEN                      unchanged
canonical_threshold_representation  full Decimal string            unchanged
tie_break                           NOT_REQUIRED_FOR_...           unchanged
fixture_status                      DEFERRED                       -> row 13
fixture_owner_packet                C5                             -> row 14
```

`threshold_design_end`, `threshold_design_rule`, `threshold_fixed_rule`, and
`quantile_alternatives` are **siblings under `target`, not members of
`target.quantile`.** They are also unchanged and also stay hashed, but do not look for
them inside the quantile mapping — `target` has eleven keys of which `quantile` is one.
The §5.2 addition goes inside `quantile`, after `fixture_owner_packet`, making it
thirteen.

The owner is named as a **condition**, not a packet number
(`REQUIRED_BEFORE_2022_2024_SCORING` / `STAGE_2`), specifically because
`holm_threshold_context: DEFERRED_TO_PACKET_C3` demonstrates how a packet number goes
stale and drifts undetected. A condition cannot go stale.

### 5.6 The three labels that currently drift untested

`grep` across `tests/` returns **nothing** for `fixture_status`,
`fixture_owner_packet`, and `holm_threshold_context`. That is why rows 13–15 were
found by reading the document rather than by a failing test. §10.6 requires a test that
pins all three post-freeze values, so the next auditor is not relying on manual
reading either.

## 6. The render protocol: what "independent" means here

H3 established that 12 of the 32 changed keys have no machine key name anywhere in the
spec, so "regenerate each key by grepping the spec for its name" is not available. This
section defines what C5 must do instead. It is the scientific core of the packet: if the
fixture is a copy of the YAML, the freeze proves nothing except that a file equals
itself.

### 6.1 Create the fixture file, six keys, v1's shape

`tests/fixtures/protocol_v1_1_expected.json`, mirroring
`tests/fixtures/protocol_v1_expected.json` (H9) exactly in shape:

```text
fixture_id               "protocol_v1_1_expected_semantic"
rendered_by              a sentence naming the spec + this plan as sources and stating that
                         no production code was imported
canonicalization         {"method": "json.dumps(projected_semantic, sort_keys=True,
                          separators=(',', ':'), ensure_ascii=True)",
                          "hash_algorithm": "sha256"}
expected_top_level_keys  the 48 in-scope key names
semantic_sha256          the digest computed from expected_semantic
expected_semantic        the 48 keys
```

Same six keys, same order as the v1 fixture. Pretty-print with `indent=2` as v1 does.

### 6.2 The binding rule: no production import while rendering

While building `expected_semantic`, do not import `quantara.protocol`,
`quantara.protocol_v11`, or any other project module, and do not read
`configs/protocols/quantara-protocol-v1_1.yaml`. Render from the specification text and
from §5 of this plan. The YAML is consulted only in §6.5, after the fixture is written,
and only to compare.

Rendering with `yaml.safe_load` on the v1.1 YAML and dumping the result is the single
failure mode this whole packet exists to prevent. It would produce a green test and a
worthless one.

### 6.3 The 16 inheritable keys: copy, then prove

For the 16 keys listed in H2, copy the value from
`tests/fixtures/protocol_v1_expected.json` → `expected_semantic`. This is legitimate
because v1 is frozen at `91457d3f…c65a` and those keys are unchanged by design, so
copying inherits an already-audited value rather than short-circuiting a new one.

Then prove the inheritance is real, per key:

```text
for each of the 16: v11_fixture[key] == v1_fixture["expected_semantic"][key]
count == 16, and none of the 16 appears in the 32-key changed list
```

If any of the 16 turns out to differ from v1, stop `BLOCKED`. Either H2 is wrong or a
prior packet silently changed an inherited key; both need a decision, not a workaround.

### 6.4 The 32 changed keys: render, and derive what must be derived

Render each of the 32 from the spec sections named in H3 plus §5 of this plan. Two
subsets need explicit care.

**The four 2025 bootstrap seeds must be derived, never transcribed** (H4). In the
fixture-building script, compute them:

```python
payload = "quantara-protocol-v1_1|bootstrap-b4|" + comparison_id + "|2025"
seed = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
```

with `comparison_id` built as `f"REPLICATION_2025|{model}_vs_B2"` for `M2`, `M2K`, `M3`,
`M4`. `hashlib` is stdlib, not production code, so this does not violate §6.2. Deriving
from a bare `"M2"` yields `13605954171529852932` and is wrong — the full comparison_id
string is load-bearing. If a derived seed disagrees with the YAML in §6.5, the YAML is
what gets corrected, and the disagreement is reported.

**`'0.95'` is a quoted decimal string, not a float.** Spec §7 writes "two-sided 95%";
the machine value is the string `'0.95'` at
`validation.bootstrap.interval.confidence`. Every numeric protocol value is an exact
string or an int. `_validate_hash_value` rejects floats at every depth, and
`semantic_hash_scope.float_policy` is `FORBIDDEN_AT_EVERY_DEPTH`. The four seeds are
genuine ints and stay ints.

### 6.5 Compare fixture to YAML, key by key, before hashing anything

Only now read the YAML. Compare per key and report the full result:

```text
for each of the 48 in-scope keys: fixture[key] == yaml_projection[key]
```

For every mismatch, resolve it **on the merits from the specification** and report
which side was wrong and why. Prohibition 2 is absolute here: never edit the fixture to
make a digest match, and never edit the YAML to match a fixture typo. A packet that
reports "0 mismatches" on the first attempt is more suspicious than one reporting three
resolved mismatches — say so honestly either way.

### 6.6 Compute the digest once, from the fixture

```text
canonical = json.dumps(fixture["expected_semantic"], sort_keys=True,
                       separators=(',', ':'), ensure_ascii=True)
digest    = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Write `digest` into the fixture's `semantic_sha256`, into
`V11_FROZEN_SEMANTIC_SHA256` in `src/quantara/protocol_v11.py`, and into
`frozen_semantic_sha256` in the YAML — the same one number in three places, never
recomputed from the YAML side. Two further copies follow later: the spec declaration
(§9.2) and the test literal (§10.1). §10.1 lists all five and requires them to agree.

Sanity check before proceeding: **do not use 41,862.** That is H2's *pre-edit*
measurement of the committed draft. This packet adds eight 64-character digests in
place of eight `INHERITED_FROM_PROTOCOL_V1` placeholders and adds the §5.2 nested
clause, so the correct canonical length grows by roughly 700 bytes. Expect a canonical
string in the **42,300–42,900 byte** range and report the exact number you measure. A
length near 41,862 means the audit digests or the nested addition are missing; a length
far outside the range means a key was dropped or duplicated. Treat the range as a smoke
test only — it proves nothing about correctness, and the §10 tests are what actually
bind the value.

## 7. File allowlist

### 7.1 Create exactly these two files

```text
tests/fixtures/protocol_v1_1_expected.json     the §6 hand-rendered 48-key fixture
tests/test_protocol_v11_frozen_contract.py     the §10 freeze/tamper/mutation/boundary suite
```

### 7.2 Modify exactly these five files

```text
configs/protocols/quantara-protocol-v1_1.yaml            §5.1 + §5.2 + §5.3
docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md   §9
src/quantara/protocol_v11.py                             §8
tests/test_protocol_v11_draft_contract.py                §10.7
tests/test_protocol_v11_loader_coverage.py               §10.7
```

Seven files total. **Delete:** none. **Rename:** none.

There is no separate "YAML changes" section in this plan because §5 already enumerates
every permitted YAML edit exactly: fifteen in-scope values (§5.1), one nested addition
(§5.2), one out-of-scope assignment (§5.3). Treat §5 as the YAML specification and do
not infer additional edits from prose elsewhere.

### 7.3 Forbidden to touch, with no exception for `protocol.py`

```text
src/quantara/protocol.py                    d61577861d2ab2caabf39d217ee7d3d7a110d13e
src/quantara/bootstrap_b4.py                491611b247449438753f5c49a13aaa271ef5077c
src/quantara/estimator_c3.py                b2dace357cc04117c85c33e91a04ed39419e3142
src/quantara/replication_c4.py              1092883e153f2e39a0df5009544d9115d6fe3485
src/quantara/training_metrics_logistic.py   f2a0a8111d4231105b45b7eb22486965495c0d1c
src/quantara/evaluation_metrics.py          c71b38944092611a30b4a8e6cc0019ad980a5042
src/quantara/aggregation.py                 9e72c1c852de58a1682d161a983b46b0bd26a8b7
tests/fixtures/protocol_v1_expected.json    6a885d73d7bfed1c4eec182c8d19fe1deed86d71
configs/protocols/quantara-protocol-v1.yaml f26b4a747f098befb4014ba72f78aeb3a447dba5
docs/.../2026-08-31-quantara-protocol-v1.md 72322b09be800b4002aab507b4d142545ccd4c10
tests/test_protocol.py                      89f81f701c62d4c098425f3f44fad84b86a3399f
tests/test_protocol_guardrails.py           958d7f1cf3191c438a5a21219997169d249ba214
tests/test_protocol_document_contract.py    7fdc8d9d4dec3acc1ae7156dcfd5470ff19d5d9b
tests/test_replication_c4.py                07c2dc1c28f3ce7df8d305fa152ca14b76fcb40f
tests/test_estimator_c3.py                  df7d03d4766542aec3d411433cb3dd4216ffc96f
tests/test_bootstrap_b4.py                  954d0a3e9d3b30283e9ede020b33fcd06cecb3fa
pyproject.toml                              57d8921b833e5f13e3c82c9d923d9373d8f1d679
.github/workflows/ci.yml                    31a6e9cda89b73ae2400985222f181bd2a492871
```

Those blob ids are as they stand at the packet parent `c2e1a8d`, verified with
`git rev-parse c2e1a8d:<path>`. §12 re-checks every one of them after the work.

`src/quantara/protocol.py` deserves a specific note: C5a was allowed a narrow
rename-only exception there, and in the end **did not use it** — the blob is
byte-identical from `3c77610` through `c2e1a8d`. C5 has **no** exception at all. v1.1
already imports the five helpers it needs (`_UniqueKeySafeLoader`,
`_validate_hash_value`, `_reject_duplicate_series`, `_reject_duplicate_features`,
`canonical_semantic_json`). If the frozen v1.1 path appears to need one more, stop
`BLOCKED` and say which one; do not edit the frozen v1 module.

Also forbidden: `configs/datasets/`, `kernel/`, `benchmarks/`, `temp/`, anything under
`docs/superpowers/reviews/`, this plan document, and
`docs/superpowers/plans/2026-09-01-protocol-v11-successor-master-plan.md`. The last two
were committed by Hermes before this packet started, so they must not appear in the
packet diff.

Anything outside §7.1 and §7.2 requires stopping `BLOCKED` with an explanation.

## 8. Required module contract — `src/quantara/protocol_v11.py`

C5a's module is a refuse-everything draft loader. C5 converts it into a frozen-protocol
loader with a real authorization path, mirroring `src/quantara/protocol.py` in shape
while keeping v1.1's identity strictly separate from v1's.

### 8.1 Constants

```python
V11_FROZEN_SEMANTIC_SHA256: str      # the one §6.6 digest, 64 lowercase hex chars
V11_FROZEN_STATUS = "FROZEN_BEFORE_2022_2024_SCORING"
V11_SCORING_PERMISSION = (
    "AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED"
)
V11_UNASSIGNED_HASH = "NOT_YET_ASSIGNED_PENDING_PACKET_C5"   # KEEP: now a rejected sentinel
V11_HASH_EXCLUDED_KEYS = ("frozen_semantic_sha256",)         # unchanged
V11_IN_SCOPE_KEY_COUNT = 48                                  # unchanged
V11_TOTAL_KEY_COUNT = 49                                     # unchanged
EXCLUSION_REASONS                                            # unchanged, the nine C5a members
_V11_PRE_GATE_OPERATIONS: frozenset    # exactly sealed_2025.allowed_pre_gate_checks
_V11_GATE_CRITERION_IDS: frozenset     # str(i) for i in range(1, 8)  -- seven, per §5.4
_V11_GATE_ARTIFACT_TYPE = "quantara-protocol-v1_1-gate-result"
_V11_GATE_HMAC_KEY_ENV = "QUANTARA_PROTOCOL_V1_1_GATE_HMAC_KEY"
```

`V11_UNASSIGNED_HASH` stays deliberately. It flips role from "the required value" to
"a value the frozen loader must reject", which is what §10.2 tests. Deleting it would
silently drop that tamper case.

The artifact type and the environment variable are **new strings, not v1's**. A v1 gate
artifact must never authorize v1.1 and a v1.1 artifact must never authorize v1. §10.5
proves both directions.

`_V11_PRE_GATE_OPERATIONS` must be derived from, or asserted equal to, the document's
`sealed_2025.allowed_pre_gate_checks`, which is verified at `c2e1a8d` as exactly:

```text
file_inventory  cryptographic_hashes  parser_compatibility
expected_boundaries  mechanical_corruption
```

### 8.2 The authorization path, and why it is seven criteria

`guard_protocol_v11_operation` changes signature. This is a deliberate breaking change
to a C5a function; §10.7 updates its callers in the test suite.

```python
def guard_protocol_v11_operation(
    protocol_hash: str,
    operation: str,
    *,
    gate_result_artifact: bytes | None = None,
) -> None:
    ...
```

Required behaviour, parallel to `guard_protocol_operation` in `protocol.py`:

```text
protocol_hash != V11_FROZEN_SEMANTIC_SHA256        -> ProtocolV11GuardError
operation not a str                                -> ProtocolV11GuardError
operation in _V11_PRE_GATE_OPERATIONS              -> return, and reject any artifact
                                                      passed alongside it
operation == "score_2025" and artifact is None     -> ProtocolV11GuardError
operation == "score_2025" and artifact present     -> verify, then return
any other operation                                -> ProtocolV11GuardError
```

Artifact verification requirements, all of which must be enforced **before** any data
access, over an immutable `bytes` snapshot rather than a path:

```text
envelope keys exactly {payload, mac}
payload keys exactly {artifact_type, schema_version, protocol_sha256, operation, criteria}
duplicate JSON keys rejected at parse time
mac is 64 lowercase hex chars, compared with hmac.compare_digest over the canonical
  payload bytes, key from _V11_GATE_HMAC_KEY_ENV only: never an argument, never in source
artifact_type    == _V11_GATE_ARTIFACT_TYPE
schema_version   is int and == 1              (bool rejected: type(x) is not int)
protocol_sha256  == V11_FROZEN_SEMANTIC_SHA256
operation        == "score_2025"
criteria         is a mapping whose key set == _V11_GATE_CRITERION_IDS and whose every
                 value is exactly boolean True
```

**Seven, not five.** `success_gate.criteria` carries ids 1–7 and is byte-equal to
Protocol v1's `success_gate`; it is the authorization artifact. `replication_gate_2025`
carries five criteria and is the *outcome* vocabulary for the single permitted 2025 run.
Wiring the five into the guard would let a replication verdict authorize the run that
produces it. See §5.4. C5 adds exactly one artifact type.

The key loader mirrors v1's: read the env var, require exactly 64 hex characters,
`bytes.fromhex`, require 32 decoded bytes, raise `ProtocolV11GuardError` on every
failure with a distinct message. The key must not be reachable from the artifact, the
function arguments, or the module source.

### 8.3 The frozen loader

`load_protocol_v11` inverts its state gate:

```text
expected_state (C5a, draft)            -> expected_state (C5, frozen)
frozen_semantic_sha256 == UNASSIGNED      frozen_semantic_sha256 == V11_FROZEN_SEMANTIC_SHA256
protocol_status == DRAFT_UNFROZEN_...     protocol_status == V11_FROZEN_STATUS
scoring_permission == NONE_UNTIL_FROZEN   scoring_permission == V11_SCORING_PERMISSION
```

Then, and this is the part C5a deliberately omitted, it computes the digest and refuses
to return a mismatched document:

```text
projection = hash_scope_projection(document)      # 48 keys, own hash excluded
canonical  = canonical_semantic_json(projection)
digest     = sha256(canonical.encode("utf-8")).hexdigest()
digest != V11_FROZEN_SEMANTIC_SHA256  -> ProtocolV11DraftError naming expected and got
```

`ProtocolV11` gains `semantic_sha256: str`. C5a's test asserted that attribute was
*absent*; §10.7 flips it. Keep `canonical_projection_json`, keep the private
`_canonical_document_json`, keep `to_dict` returning a detached copy, keep
`frozen=True, slots=True`.

Every existing fail-closed behaviour survives unchanged: duplicate top-level keys,
duplicate nested keys, floats at any depth, non-string mapping keys, duplicate
`series_id`, duplicate ladder features, non-UTF-8 input, and non-mapping roots all still
raise `ProtocolV11DraftError`. `hash_scope_projection`, `coverage_report`,
`longest_missing_run`, `YearCoverage`, and `CoverageReport` keep their current
signatures and behaviour.

Constraints: standard library plus `yaml` only; no `numpy`; no float in any signature or
computation path; no filesystem access beyond the single protocol path argument; every
public function keeps a docstring naming the frozen clause it implements.

## 9. Required spec changes — `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`

The spec is the human-readable half of the freeze. Three edits, plus one repair that
H3 made unavoidable.

### 9.1 Close the H3 machine-key gap

H3 found twelve keys whose machine names appear nowhere in the spec:
`deferred_change_set`, `estimator_binding`, `exclusion_reason_vocabulary`,
`fit_failure_propagation`, `frozen_date`, `ladder_widths`,
`optional_family_retention`, `outcome_states`, `point_in_time`,
`replication_gate_2025`, `semantic_hash_scope`, `target_endpoint_buffer_2026`.

The content exists under prose headings; only the key names are missing. Add each key
name to the section that already carries its content — a parenthetical such as
"(YAML key: `point_in_time`)" after the heading or in the section's first sentence is
enough. Do not restate the content and do not move sections.

This is the one edit that improves the *next* audit rather than this one: after C5, an
auditor can grep the spec for any machine key and land in the governing section. Do not
skip it because it looks cosmetic.

### 9.2 Flip the header block and §12 from draft to frozen

The header block at spec lines 3–12, verified verbatim at `c2e1a8d`, currently reads:

```text
Protocol id:            quantara-protocol-v1_1
Protocol status:        DRAFT_UNFROZEN_SUCCESSOR
Draft date:             2026-09-01
Supersedes:             quantara-protocol-v1
Predecessor hash:       91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a
Authorizing audit:      docs/superpowers/reviews/2026-09-01-protocol-v1-three-reviewer-deep-audit.md
Frozen semantic hash:   NOT_YET_ASSIGNED_PENDING_PACKET_C5
Scoring permission:     NONE_UNTIL_FROZEN
```

Three lines change, and the spec must carry the **literal values**, not the Python
constant names: `Protocol status` becomes `FROZEN_BEFORE_2022_2024_SCORING`, `Frozen
semantic hash` becomes the digest, and `Scoring permission` becomes
`AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED` — all three matching
§5.1 rows 1–3 and the YAML string-for-string. Add `Frozen date: 2026-09-02`. Keep
`Draft date: 2026-09-01`, `Protocol id`, `Supersedes`, `Predecessor hash`, and
`Authorizing audit` exactly as they are.

Line 1's title, `# Quantara Protocol v1.1 — Draft Successor Scientific Protocol
Specification`, and line 14's opening sentence, "This is a complete standalone draft
successor to Protocol v1", both still say *draft*. Drop that word from both. Nothing
greps for the title string (`grep -rn "Draft Successor"` across `tests src configs`
returns nothing), so this edit is safe and it keeps the document from contradicting its
own header.

Lines 14–16 continue: "While the protocol status is `DRAFT_UNFROZEN_SUCCESSOR`, no
scoring of any period, and no 2025 access, is authorized." That premise is now false and
must be rewritten. The rewrite has to preserve the sealed truth while dropping the draft
premise: 2022–2024 scoring is authorized once the threshold fixture exists, and **2025
remains sealed** because `sealed_2025.scoring_permission` is
`FORBIDDEN_UNTIL_GATE_PASS_AND_PROTOCOL_FREEZE`, a conjunction whose gate half is still
unsatisfied (§5.4). Two tests assert the old literals — see §10.7 L336-337 — and must be
re-pointed at whatever sentence you write. Write the sentence first, then fix the tests
to match it; do not weaken the sentence to keep an old assertion alive.

§12 "Draft semantic-hash state" becomes the frozen semantic-hash state. Its projection
language stays (48 of 49, own hash the sole exclusion, `predecessor_semantic_sha256`
still in scope), its canonicalization sentence stays verbatim, and its closing two
lines, verified at `c2e1a8d` as

```text
The state remains `NOT_YET_ASSIGNED_PENDING_PACKET_C5`, and C5 owns the value,
synchronized fixture, and freeze. Until then, scoring permission remains
`NONE_UNTIL_FROZEN`.
```

become a statement that C5 computed the value, naming
`tests/fixtures/protocol_v1_1_expected.json` as the independent render and stating the
digest. The section heading itself should lose the word "Draft".

§11's deferred table row (spec line 898) must change from

```text
| Coverage and final freeze | `DEFERRED` | C5 | Coverage/exclusion reporting and claim
scope per candidate; synchronization of spec, YAML, and fixture; new semantic SHA-256;
and repeated tamper, future-mutation, boundary, solver, bootstrap, and 2025-seal tests. |
```

to `IMPLEMENTED` / `C5` with a one-sentence description in the same voice as the C5a
row above it at line 897. It is a single physical line in the file; the wrap above is
this plan's, not the spec's. The test at `tests/test_protocol_v11_draft_contract.py:434`
matches the prefix `| Coverage and final freeze | \`DEFERRED\` | C5 |` — §10.7 updates
it, so the new prefix must be exactly
`| Coverage and final freeze | \`IMPLEMENTED\` | C5 |`.

§9's sentence at spec lines 866–868, "Their predecessor digests are not recopied into
this unfrozen draft. Each binding is recorded as `INHERITED_FROM_PROTOCOL_V1` pending the
C5 synchronized fixture and semantic freeze," must become a statement that the eight
digests are now recorded, since §5.1 rows 4–11 do exactly that.

### 9.3 Pin the post-edit spec digest

v1's precedent: `EXPECTED_SPEC_SHA256` in
`tests/test_protocol_document_contract.py:43`, computed as UTF-8 decode → CRLF/CR
folded to LF → UTF-8 re-encode → `sha256`. C5 adds the v1.1 equivalent,
`EXPECTED_V11_SPEC_SHA256`, in the new §10 test file.

**Compute it after the §9.1/§9.2 edits are final.** H8's `4c72d2e6…` is the pre-edit
digest and pasting it produces a test that fails immediately. Recompute, paste, rerun.

### 9.4 Master-plan bookkeeping is already done

`docs/superpowers/plans/2026-09-01-protocol-v11-successor-master-plan.md` is updated
and committed by Hermes **before** this packet runs, moving C5a to
`ACCEPTED (PR #9, c2e1a8d)` and C5 to `NEXT`. It is outside the allowlist (§7.3). Do
not edit it.

## 10. Required tests

Tests first, with genuine red output captured before implementation. A report without
verbatim red output is `INCOMPLETE`.

New file `tests/test_protocol_v11_frozen_contract.py` holds §10.1–§10.6. §10.7 edits
the two existing v1.1 test files.

### 10.1 The one hash in five places

```text
test_frozen_digest_is_identical_in_every_recorded_location
```

The digest must be byte-identical in all five:

```text
1  tests/fixtures/protocol_v1_1_expected.json  -> semantic_sha256
2  configs/protocols/quantara-protocol-v1_1.yaml -> frozen_semantic_sha256
3  src/quantara/protocol_v11.py -> V11_FROZEN_SEMANTIC_SHA256
4  docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md -> header + §12
5  this test file -> EXPECTED_V11_SEMANTIC_SHA256, a literal
```

Location 5 is a hardcoded literal, mirroring v1's `EXPECTED_SEMANTIC_SHA256` and its
comment "lives OUTSIDE the mutable JSON fixture and is never derived at test runtime
from the YAML or the fixture." Deriving it at runtime from any of locations 1–4 would
make the test tautological. Also assert 64 lowercase hex characters and that the value
is **not** `V11_UNASSIGNED_HASH`, and pin `EXPECTED_V11_SPEC_SHA256` per §9.3.

### 10.2 Independent re-derivation, from the fixture and from the YAML

```text
test_fixture_expected_semantic_hashes_to_the_frozen_digest
test_yaml_projection_hashes_to_the_frozen_digest
test_fixture_and_yaml_projection_are_equal_key_by_key
test_fixture_declares_the_48_in_scope_keys_in_sorted_order
test_frozen_loader_returns_the_frozen_digest
```

The first recomputes `sha256(json.dumps(fixture["expected_semantic"], sort_keys=True,
separators=(',',':'), ensure_ascii=True).encode("utf-8"))` **without importing
`quantara.protocol_v11`** and compares to the §10.1 literal. The second uses
`hash_scope_projection` + `canonical_semantic_json` on the YAML. The third compares
per key and names the first differing key on failure. Both paths must reach the same
number by different routes; that is the whole point of the fixture.

### 10.3 Tamper probes on the frozen state

```text
test_frozen_loader_rejects_every_single_key_mutation   (parametrized, ALL 48 in-scope keys)
test_frozen_loader_rejects_the_unassigned_sentinel
test_frozen_loader_rejects_a_wrong_but_well_formed_digest
test_frozen_loader_rejects_draft_status_or_draft_scoring_permission
test_frozen_loader_rejects_nested_audit_reference_digest_tampering
test_out_of_scope_key_edit_does_not_change_the_digest
```

The parametrized case is the strongest test in the packet: for **each** of the 48
in-scope keys, mutate that key alone and assert `load_protocol_v11` raises. Mutation
must be type-appropriate — append a sentinel to strings, add a sentinel member to
mappings and lists, increment integers — so it is a real value change, not a type
error caught earlier by validation. 48 parametrized cases, none skipped; a skip means
a key is silently outside the hash.

The last test is the complement: editing `frozen_semantic_sha256` itself (the sole
excluded key) must **not** change the projection digest, which is what "excluded from
its own hash" means operationally. It still fails the loader's state check, so assert
the projection digest directly rather than through the loader.

### 10.4 The future-mutation gap (H7's real hole)

```text
test_appending_a_future_row_does_not_change_any_earlier_feature
test_backward_as_of_join_never_selects_an_equal_or_later_eligibility_ts
test_forbidden_join_modes_are_closed_and_asserted
```

`point_in_time.join_rule` states "All joins are backward as-of joins on
`eligibility_ts`; `eligibility_ts < prediction_ts` without exception" and
`point_in_time.forbidden` lists exactly `nearest_joins`, `forward_joins`,
`unfinished_bars`, `future_revisions`, `same_timestamp_equality` (verified). Nothing
executable enforces any of it.

Build a small synthetic as-of resolver **inside the test file** — a few lines over
sorted `(eligibility_ts, value)` tuples — and prove three properties:

```text
1  resolve(rows, prediction_ts) is unchanged after appending rows with
   eligibility_ts >= prediction_ts, for every prediction_ts in the grid
2  a row with eligibility_ts exactly == prediction_ts is NEVER selected
   (strict inequality; same_timestamp_equality is forbidden)
3  the five forbidden mode strings are exactly the document's list, so a future
   packet cannot quietly drop one
```

Property 1 is the future-revision guarantee. Property 2 is the `T+2ms` ordering tick's
reason for existing. Do not import project code for the resolver; a stdlib
`bisect`-based helper is the point — the test must be able to fail.

### 10.5 Boundary arithmetic for every source, and cross-protocol isolation

```text
test_every_source_boundary_offset_is_arithmetically_correct  (parametrized, 4 sources)
test_funding_same_boundary_is_eligible_and_others_are_already_eligible
test_v1_gate_artifact_cannot_authorize_v11_and_v11_artifact_cannot_authorize_v1
test_pre_gate_operations_match_the_document_and_reject_artifacts
test_score_2025_requires_a_valid_hmac_artifact_and_seven_true_criteria
test_score_2025_rejects_five_criteria_wrong_type_bad_mac_and_missing_env_key
```

`boundary_test_rule` is the literal string "universal convention change; boundary-test
every source", and H7 found only funding has arithmetic. Parametrize all four with
`datetime`/`timedelta` arithmetic against `T = 2024-03-01 00:00:00 UTC`:

```text
kline    C + 1 ms        C = T - 1ms  -> eligible at T,          < T+2ms  OK
funding  F + 1 ms        F = T       -> eligible at T + 1ms,    < T+2ms  OK
oi       O + 5 minutes   O = T - 5min -> eligible at T,          < T+2ms  OK
kraken   K + 1 hour      K = T - 1h  -> eligible at T,          < T+2ms  OK
```

Each case asserts `eligibility_ts < prediction_ts` where `prediction_ts = T + 2ms`,
and that funding is the only source whose eligibility falls strictly after `T` —
which is exactly what `same_boundary_effect` claims in prose.

The isolation tests use a v1-typed artifact (`quantara-protocol-v1-gate-result`)
against the v1.1 guard and a v1.1-typed artifact against `guard_protocol_operation`,
asserting both raise. Set the HMAC env key with `monkeypatch.setenv` to a synthetic
64-hex value; never a real key, never committed.

### 10.6 Label, count, and vocabulary pins

```text
test_the_three_previously_untested_labels_are_pinned
test_quantile_holds_thirteen_keys_with_ten_method_keys_byte_identical
test_top_level_counts_and_scope_clause_remain_48_of_49
test_sealed_2025_is_byte_identical_to_the_parent_commit
test_deferred_change_set_is_complete_with_c5_implemented
test_exclusions_and_standing_rejections_survive_the_freeze
```

The first closes §5.6: pin `fixture_status`, `fixture_owner_packet`, and
`holm_threshold_context` to their post-freeze values so they cannot drift untested
again. The second pins `target.quantile` at thirteen keys (twelve plus §5.2) and
asserts the ten method keys equal their `c2e1a8d` values. The third re-asserts
`in_scope_key_count == 48`, `total_key_count == 49`, `len(document) == 49`, and that
the module constants agree with the clause. The fourth asserts `sealed_2025` is
unchanged — a freeze must not quietly unseal 2025. The last covers `exclusions`
(`forbidden_families` + `rules`) and the four-member closed `standing_rejections`
mapping, both of which C5a already touched but which must survive the freeze.

### 10.7 Update the two existing v1.1 test files

These edits are mandatory, not optional cleanup: the freeze makes the current
assertions false, and leaving them is a red suite.

```text
tests/test_protocol_v11_draft_contract.py
  L21          UNASSIGNED_V11_HASH stays as a constant but changes role: it is now the
               value the frozen document must NOT carry. Add FROZEN_V11_HASH alongside it
  L104         test_v11_draft_identity_status_and_hash_state — rename (it is no longer a
               draft identity) and update its body:
  L107           protocol_status DRAFT_UNFROZEN_SUCCESSOR -> V11_FROZEN_STATUS
  L110           frozen_semantic_sha256 UNASSIGNED_V11_HASH -> FROZEN_V11_HASH
  L111           scoring_permission NONE_UNTIL_FROZEN -> V11_SCORING_PERMISSION
  L117           `set(all_hash_tokens) <= {PREDECESSOR_SHA256}` must now admit the frozen
                 digest and the eight §5.1 audit digests
  L118-120       the FROZEN_HASH_POSITION_RE loop asserts *no* digest sits at the
                 frozen-hash position. It inverts: a digest MUST be present there
  L206-220     test_v11_yaml_has_no_floats_duplicate_top_level_keys_or_missing_deferred_packets
               keeps the float and duplicate-key checks unchanged; only L220,
               `deferred["C5"] == {"owner_packet": "C5", "status": "DEFERRED"}`, becomes
               `IMPLEMENTED_PACKET_C5` — matching the C5a row's shape on L215-218
  L336-337     test_v11_spec_records_intentional_lineage_and_future_experiment_boundary
               asserts the literal spec strings "no scoring of any period" and
               "no 2025 access". §9.2 rewrites the sentence containing both, so these two
               assertions go red. Re-point them at whatever sealed-2025 sentence §9.2
               actually writes, and keep the four lineage assertions on L332-335 as-is
  L343-344     test_v11_c4_contract_literals_and_terminal_states_are_exact: same two state
               flips as L107/L110. Its `len(document) == 49` on L342 must stay 49 — §5.2
               adds a nested key, not a top-level one
  L429         test_v11_c4_spec_status_is_implemented_while_c5_stays_deferred — the name is
               now false. Rename it, and on L434 change
               "| Coverage and final freeze | `DEFERRED` | C5 |" to `IMPLEMENTED`,
               matching the §9.2 spec edit character-for-character. Leave the C4 assertion
               (L431-432) and the C5a assertion (L435) untouched
  L484-488     test_v11_has_only_the_predecessor_digest_and_no_c5_fixture: both assertions
               invert. L487's exact-set equality must widen to the frozen digest plus the
               eight audit digests, and L488's `assert not (...).exists()` becomes
               `assert (...).exists()`. Rename the test accordingly

tests/test_protocol_v11_loader_coverage.py
  L95-103      test_draft_loader_exposes_no_digest_or_digest_literal: inverts. The
               protocol object now MUST expose semantic_sha256, the module text MUST
               contain a 64-hex literal, and the "no str attribute is a 64-hex digest"
               loop on L101-103 must permit exactly one — V11_FROZEN_SEMANTIC_SHA256.
               Rename the test
  L111         to_dict()["protocol_status"] -> V11_FROZEN_STATUS. The detached-copy
               semantics on L106-110 are unchanged
  L114-130     test_draft_state_tampering_is_rejected: its three parameters
               (frozen_semantic_sha256="a"*64, protocol_status="FROZEN",
               scoring_permission="ALLOWED") were tampering *because* the draft carried
               sentinels. Post-freeze, "a"*64 is still tampering but the other two are
               merely wrong strings. Re-point all three at the frozen state: a wrong
               digest, a status that is not V11_FROZEN_STATUS, and a permission that is
               not V11_SCORING_PERMISSION. Keep the ProtocolV11DraftError expectation only
               if §8 keeps that exception name; otherwise update it
  L188-202     test_draft_guard_refuses_every_operation: the guard no longer refuses
               everything, and the `match=V11_UNASSIGNED_HASH` on L201 can no longer hold.
               Rewrite as: the five pre-gate operations (file_inventory,
               cryptographic_hashes, parser_compatibility, expected_boundaries,
               mechanical_corruption) are allowed; score_2025 requires a valid artifact;
               unknown_operation is still refused. Update every call site for the new
               (protocol_hash, operation, *, gate_result_artifact) signature
  L205-208     test_v1_loader_remains_isolated_from_v11 stays as-is and must still pass
```

The line numbers are from `c2e1a8d` and are navigation aids, not a patch script.
Verify each site before editing. Every other test in both files must keep passing
unmodified; if one cannot, report it explicitly rather than deleting it.

## 11. Verification gates

Run all of these and paste the real output.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c5-freeze

# Focused gate.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  -p no:randomly \
  tests/test_protocol_v11_frozen_contract.py \
  tests/test_protocol_v11_loader_coverage.py \
  tests/test_protocol_v11_draft_contract.py

# Regression gate: the frozen predecessors must not move.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  -p no:randomly \
  tests/test_protocol.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol_guardrails.py \
  tests/test_bootstrap_b4.py \
  tests/test_estimator_c3.py \
  tests/test_replication_c4.py \
  tests/test_training_metrics_logistic.py \
  tests/test_evaluation_metrics.py \
  tests/test_aggregation.py

# Full suite, serial. Baseline at c2e1a8d: 1129 passed, 16 deselected, ~23 minutes.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q

# Full suite under CI parallelism (H11). CI runs `uv run pytest -n 4`; an
# order-dependent test passes serially and fails here.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q -n 4

# Repository-wide lint. MUST match the CI gate exactly. A lint scoped to only the new
# files is NOT sufficient: it passes while an *edited* file regresses, which is how C4
# shipped 4 over-length lines past a clean scoped run.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check src tests benchmarks

# Whitespace hygiene.
git diff --check
```

The full suite must report at least **1129 passed** plus the new tests. A lower number
means something was lost, not that something was cleaned up.

## 12. Byte-identity gates

All nine must print **nothing**. Any output is a failed packet.

```bash
git diff --stat c2e1a8d -- docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md
git diff --stat c2e1a8d -- configs/protocols/quantara-protocol-v1.yaml
git diff --stat c2e1a8d -- tests/fixtures/protocol_v1_expected.json
git diff --stat c2e1a8d -- src/quantara/protocol.py
git diff --stat c2e1a8d -- src/quantara/bootstrap_b4.py src/quantara/estimator_c3.py src/quantara/replication_c4.py
git diff --stat c2e1a8d -- src/quantara/training_metrics_logistic.py src/quantara/evaluation_metrics.py src/quantara/aggregation.py
git diff --stat c2e1a8d -- pyproject.toml .github/workflows/ci.yml configs/datasets kernel
git diff --stat c2e1a8d -- tests/test_protocol.py tests/test_protocol_guardrails.py tests/test_protocol_document_contract.py
git diff --stat c2e1a8d -- tests/test_replication_c4.py tests/test_estimator_c3.py tests/test_bootstrap_b4.py
```

Then confirm every blob id in §7.3 with `git rev-parse c2e1a8d:<path>` against
`git hash-object <path>`. `src/quantara/protocol.py` must still be
`d61577861d2ab2caabf39d217ee7d3d7a110d13e` — it has held that value since `3c77610`
and C5 has no exception. Confirm `tests/test_estimator_c3.py` still contains
`PACKET_PARENT_ESTIMATOR_BLOB = "f2a0a8111d4231105b45b7eb22486965495c0d1c"`.

Also confirm the v1 semantic identity is untouched:

```text
FROZEN_SEMANTIC_SHA256 == 91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a
EXPECTED_SPEC_SHA256   == 9aaa9d76557d76ced7a5c0cff20a02dbb7f735f555a8e696c3289dfe3963ec68
load_protocol(v1 yaml).semantic_sha256 == FROZEN_SEMANTIC_SHA256
```

And confirm this plan and the master plan are absent from the packet diff. **Note the
different base commit here.** The other nine gates compare against `c2e1a8d`, but Hermes
committed both plan documents in a docs commit *on top of* `c2e1a8d` — that commit's
entire content is a change under `docs/superpowers/plans/`, so comparing against
`c2e1a8d` would list both files and is the wrong base. Compare against your own starting
SHA, which is that docs commit and is the value you report in §14 item 1:

```bash
git diff --stat <your starting SHA> -- docs/superpowers/plans/
```

That must print nothing. If it lists this plan or
`2026-09-01-protocol-v11-successor-master-plan.md`, you have edited a document that is
outside the allowlist — revert that edit. Do **not** resolve it by reverting or amending
the docs commit itself.

## 13. Commit

Stage only the seven allowlisted files. Commit locally with exactly:

```text
feat(protocol): freeze Protocol v1.1 semantic identity
```

Use a plain `git commit` — no `core.hooksPath` flag (H10). Then **stop**. Do not push,
do not open a PR, do not begin Stage 2.

## 14. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA, and the single commit SHA. The starting SHA is Hermes's
   docs commit, whose parent is `c2e1a8d`; it is **not** `c2e1a8d` itself.
2. Exact list of changed files — expect seven, two created and five modified.
3. Raw red output captured before implementation.
4. Raw green focused gate, raw green regression gate, the serial full-suite pass count,
   and the `-n 4` full-suite pass count. Both full-suite numbers must be ≥ 1129 plus
   the new tests.
5. Raw output of all nine byte-identity `git diff --stat` commands, every §7.3 blob-id
   comparison, `git diff --stat <your starting SHA> -- docs/superpowers/plans/`, and
   `git diff --check`.
6. Ruff result for `src tests benchmarks`.
7. **The frozen digest, stated once, plus proof it appears identically in all five
   §10.1 locations.**
8. **The independence narrative, in detail.** State explicitly: that
   `expected_semantic` was rendered from the spec and §5 without importing project code
   or reading the v1.1 YAML; which 16 keys were inherited from the v1 fixture and the
   per-key proof they are equal; that the four 2025 seeds were derived by the C2 rule
   rather than transcribed, with the four derived values; and the exact canonical byte
   length you measured, compared against the 42,300–42,900 expectation.
9. **Every fixture-vs-YAML mismatch found in §6.5**, with the resolution and which side
   was wrong. If there were zero mismatches, say so plainly and explain how you know
   the fixture was not derived from the YAML — zero on the first attempt is the
   suspicious outcome, not the reassuring one.
10. All eight audit-reference digests as *you* recomputed them, with the basis used, and
    whether each matched H5.
11. Confirmation that `sealed_2025` is byte-identical and that 2025 remains sealed, with
    the exact `sealed_2025.scoring_permission` value quoted.
12. Confirmation that the guard uses the seven `success_gate` criteria, not the five
    replication criteria, and that v1 and v1.1 artifacts cannot cross-authorize, naming
    the artifact type and env var for each.
13. The final top-level key count, in-scope count, and `target.quantile` key count, plus
    proof the `semantic_hash_scope` clause's own counts match the document containing
    it.
14. The post-edit `EXPECTED_V11_SPEC_SHA256` you computed, and confirmation it is not
    `4c72d2e672d7f46ef9af8b7fb30d3263d6b0a5cb0e52216256aaefb7965ef150`.
15. Confirmation that all 48 single-key tamper cases ran and none was skipped.
16. Confirmation that the §10.4 future-mutation tests are genuinely capable of failing —
    show that inverting the resolver's inequality makes them red.
17. Confirmation that `src/quantara/protocol.py` was **not** touched, with its blob id.
18. Confirmation that no 2025 or 2026 data was read, opened, enumerated, globbed, or
    listed; that every fixture and grid is synthetic; that no network call was made; and
    that no HMAC key value appears in any committed file.
19. Confirmation that no dependency was added and `numpy` was not used.
20. Confirmation that no rejected reviewer invention was reintroduced, naming each item
    in prohibition 9 and how its absence was verified.
21. An explicit mapping of which of H0–H11 each new test reproduces.
22. Test count and any residual risk.

A green suite alone is not `COMPLETE`. Hermes performs the independent audit — including
re-deriving the digest from the fixture, from the YAML, and from the spec by a third
path — and is the only role that may mark this packet `ACCEPTED`.

## 15. Execution prompt

```text
Read D:\PROJECT\Quantara-worktrees\protocol-v11-c5-freeze\docs\superpowers\plans\2026-09-02-protocol-v11-c5-freeze.md
and execute that packet only. Hand-render the 48-key fixture from the specification
first, without importing project code or reading the v1.1 YAML; compute the semantic
SHA-256 once from that fixture; then prove the YAML canonicalizes to the same value and
report every mismatch you had to resolve. Tests first with real red output. Run every
gate, including the -n 4 full suite and the repository-wide ruff. Commit only the seven
allowlisted files with a plain git commit. Do not push, merge, or advance to Stage 2.
```
