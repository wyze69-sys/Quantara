# Protocol v1.1 — Packet C5a: Loader, Hash Scope, and Coverage/Claim-Scope Contract (audit item 12, item 13)

**Status:** `NEXT` — not started
**Date:** 2026-09-01
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c5a-coverage-loader`
**Branch:** `protocol-v11-c5a-coverage-loader`
**Packet parent commit:** `3c77610` (`main`, the C4 merge commit)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists

C1 froze version identity and `T+2ms` ordering. C2 froze inference (`B4`). C3 bound
the estimator and the three-hypothesis optional family. C4 froze OI timestamp role,
the final pre-2025 refit, the sealed 2026 target-only buffer, and the one-year 2025
`REPLICATED` gate. One deferred item remains:

- `deferred_change_set["C5"].status == "DEFERRED"`
- spec §11: `| Coverage and final freeze | DEFERRED | C5 |`
- spec §12: `frozen_semantic_sha256` is `NOT_YET_ASSIGNED_PENDING_PACKET_C5`

That single item bundles six obligations of two different kinds:

```text
contract obligations   coverage/exclusion reporting, claim scope, a v1.1 loader,
                       an explicit hash-scope rule, and the guardrail test suite
freeze obligations     spec/YAML/fixture synchronization and the new semantic SHA-256
```

**This packet takes the contract obligations only.** The freeze obligations stay
with C5. The split exists because a semantic hash freezes whatever scope is in
force at the moment it is computed, and right now that scope is undefined: the
draft carries 46 top-level keys, one of which is `frozen_semantic_sha256` itself.
Hashing a document that contains its own hash field is not a well-posed operation
until a projection rule says which keys are in scope. Freezing first and defining
scope afterwards would mean the frozen number does not provably correspond to any
stated rule. C5a defines and test-enforces the scope; C5 then computes the number
once, against a contract that is already green.

This is a **specification repair, not a scientific reset.** No new feature, no new
target, no new model family, no unsealing, no threshold search, and **no hash**.

## 2. Hermes pre-verified findings

Measured in this exact worktree against committed code at `3c77610` before this
plan was written. Codex must **reproduce each one as a test**, not trust this
document.

**H0 — the baseline is green and the tree is clean.**

```text
git rev-parse --abbrev-ref HEAD        protocol-v11-c5a-coverage-loader
git rev-parse HEAD                     3c776107e0d38fa74660ca39a0b9892c35e906c2
git status --porcelain                 (empty)
git merge-base --is-ancestor 85c52d4 3c77610   -> YES_C4_MERGED  (PR #8 MERGED)
focused protocol gate                  174 passed in 27.27s
full suite                             1092 passed, 16 deselected, 1 warning in 1310.41s
ruff check src tests benchmarks        All checks passed!
git diff --check                       (empty)
```

The full suite takes ~22 minutes single-process. Budget for it; do not skip it.

**H1 — the v1.1 draft has 46 top-level keys and one of them is its own hash
field.** Written key order in the YAML, all 46:

```text
protocol_id protocol_status frozen_date draft_date supersedes
predecessor_semantic_sha256 authorizing_audit frozen_semantic_sha256
scoring_permission planning_baseline research_question inventory
canonical_lane_immutability canonical_record_fields exclusions target
realized_volatility feature_formulas feature_window_completeness dislocation_roles
model_ladder ladder_widths model_mandates cross_quote_dislocation_policy
logistic_constants estimator_binding fail_closed_causes fit_failure_propagation
calibration search_and_calibration_restrictions point_in_time
missing_and_duplicate_policy validation success_gate optional_family_retention
sealed_2025 audit_reference_hash_basis audit_references lineage
deferred_change_set standing_rejections oi_timestamp_resolution final_refit
target_endpoint_buffer_2026 replication_gate_2025 outcome_states
```

Frozen v1 has 27 keys and **no** `frozen_semantic_sha256` key at all: its digest
lives outside the document, in `tests/fixtures/protocol_v1_expected.json` and as a
literal in `tests/test_protocol_document_contract.py`. v1.1 broke that pattern by
carrying a placeholder inside the document, which is why the projection rule is now
mandatory rather than implied. Excluding that one key leaves **45 keys in scope**.

**H2 — no hash-scope rule exists anywhere.**

```text
grep -n "hash_scope|hashed projection|projection excludes"  spec + YAML  ->  no match
```

The v1 fixture records the canonicalization method as
`json.dumps(projected_semantic, sort_keys=True, separators=(',',':'), ensure_ascii=True)`
with `hash_algorithm: sha256`, and `src/quantara/protocol.py::canonical_semantic_json`
implements exactly that. The *method* is therefore inherited and settled. What is
missing is the *projection*: which keys `projected_semantic` contains.

**H3 — a v1.1 loader does not exist.** `src/quantara/protocol.py` is v1-only: it
hard-fails any document whose digest is not
`91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`, so the v1.1
draft is unloadable by construction and
`test_v11_draft_is_fail_closed_and_unloadable_by_frozen_v1_loader` asserts that.
Nothing can currently load, validate, or guard the v1.1 draft. Its only enforcement
is assertion-by-assertion inside `tests/test_protocol_v11_draft_contract.py`.

**H4 — coverage reporting is scoped to the 2025 gate only, and has no per-year
breakdown.**

```text
coverage_reporting lives at replication_gate_2025.coverage_reporting  (not top level)
required: [candidate_eligible_rows, candidate_eligible_percentage,
           exclusion_reasons, longest_missing_run]
minimum_coverage_threshold: NONE_BY_DESIGN
applicability: candidate-complete timestamps only
only by_year string in the whole YAML: "blocks_per_year: n_blocks_y = ceil(H_y / L)"
```

Audit §7 requires "Candidate-eligible rows and percentage **by year**" and applies
the requirement to **every candidate**, not only to the 2025 replication candidate.
Both scope and granularity are unmet.

**H5 — `exclusion_reasons` has no vocabulary and `longest_missing_run` has no
definition or implementation.**

```text
grep exclusion_reason_vocabulary        YAML  ->  no match
longest_missing_run defined with a value  ->  no  (appears only inside the required list)
grep -rl longest_missing_run src/       ->  NONE
```

A required report field with no closed vocabulary and no definition is not
executable: two runs could report different things under the same key and both
claim compliance.

**H6 — the whole test suite contains exactly one coverage assertion.**

```text
tests/test_protocol_v11_draft_contract.py:412
    assert gate["coverage_reporting"]["minimum_coverage_threshold"] == "NONE_BY_DESIGN"
```

**H7 — `standing_rejections` is asserted nowhere, and `exclusions` is asserted only
as a key name.**

```text
grep -rl standing_rejections tests/                                  ->  NONE
grep -n forbidden_families tests/test_protocol_v11_draft_contract.py ->  NONE
"exclusions" in that file appears once, inside V1_TOP_LEVEL_KEYS (line 31)
```

Measured content facts that tests must pin:

```text
v1.exclusions.forbidden_families == v11.exclusions.forbidden_families   True  (11 members)
v1.exclusions.rules             == v11.exclusions.rules                 False (both len 2)
standing_rejections: 4 entries, every value REJECTED
v1 has standing_rejections at all:                                      False
```

The differing `rules` is deliberate — v1.1 adds the data-slice-013 supersession —
so the test must assert *both* that families are identical and that rules
intentionally differ, or a future edit could silently converge them.

**H8 — no v1.1 fixture and no v1.1 spec digest pin exist.**

```text
tests/fixtures/protocol_v1_1_expected.json exists      False
EXPECTED_V11_SPEC_SHA256 pinned in any test            False
tests/fixtures/ protocol fixtures present              protocol_v1_expected.json only
```

Both are **C5's** deliverables, not C5a's. They are listed here so the auditor can
confirm C5a did not create them.

**H9 — the C4 plan's commit instruction is wrong for this repository.**

```text
git config --get core.hooksPath      (unset)
ls -1d .githooks                     No such file or directory
git ls-files | grep hooks            (empty)
```

The C4 plan §4 says to commit with `git -c core.hooksPath=.githooks commit`. There
is no `.githooks` directory and no configured hooks path, so that flag points at
nothing. C5a must use a plain `git commit` and this plan must not propagate the
stale instruction.

**H10 — the master plan's C4 status line is stale.** It reads "C4 `ACCEPTED` by
Hermes audit, PR #8 open awaiting user merge". `gh pr list --state all` reports PR
#8 `MERGED` at `2026-09-01T17:04:31Z` and `85c52d4` is an ancestor of `main`. C5a
corrects that line as a bookkeeping edit.

**H11 — CI is the real gate and it is stricter than a local run.**
`.github/workflows/ci.yml` runs on Windows/Python 3.11 with
`uv run ruff check src tests benchmarks`, `cargo test --locked` on `kernel/`, and
`uv run pytest -n 4`. Two consequences: the repository-wide lint is the gate (per
master-plan invariant 8), and the suite must pass under `-n 4` parallelism, not only
serially. `pyproject.toml` sets `addopts = -m "not integration"`, so the 16
deselected tests are the networked integration set and stay deselected.

## 3. Standing prohibitions

Violating any of these fails the packet regardless of test results.

1. **Do not compute, derive, print, guess, or write any Protocol v1.1 semantic
   SHA-256.** Not in code, not in a comment, not in the report, not as an
   "informational" value. `frozen_semantic_sha256` stays the literal string
   `NOT_YET_ASSIGNED_PENDING_PACKET_C5`. Any 64-hex string presented as the v1.1
   hash fails the packet.
2. **Do not create `tests/fixtures/protocol_v1_1_expected.json`.** That artifact is
   C5's, and creating it early would fix a projection before its rule is audited.
3. **Do not change `protocol_status`.** It stays `DRAFT_UNFROZEN_SUCCESSOR`.
   `scoring_permission` stays `NONE_UNTIL_FROZEN`. `frozen_date` stays
   `NOT_APPLICABLE_DRAFT`.
4. **Do not set `deferred_change_set["C5"]` to implemented.** C5a adds a `C5a`
   entry and leaves `C5` `DEFERRED`.
5. **Protocol v1 artifacts stay byte-identical.** The v1 spec, v1 YAML, v1 fixture,
   and the v1 hash `91457d3f…c65a` never change.
6. **Do not touch frozen packet machinery**: `bootstrap_b4.py`, `estimator_c3.py`,
   `replication_c4.py`, `training_metrics_logistic.py`, `evaluation_metrics.py`,
   `aggregation.py`. C5a *imports* and *wraps*; it reimplements nothing.
7. **No new dependency, and no `numpy`.** Decimal/Fraction/int arithmetic only. No
   float anywhere in protocol hash semantics.
8. **2025 and 2026 stay sealed.** Do not read, open, enumerate, glob, or list any
   2025 or 2026 data path. No network call. Every fixture and fit is synthetic.
9. **Do not add a minimum-coverage threshold.** The audit rejected the 98% cutoff
   and any arbitrary substitute. `minimum_coverage_threshold` stays
   `NONE_BY_DESIGN`. C5a adds *reporting* obligations, never a *pass* threshold.
10. **Do not reintroduce any rejected reviewer invention**: signed-return
    replacement, sigma denominator floor, arbitrary coverage cutoff, new feature
    search, LightGBM, XGBoost, return regression, directional actions, economic
    gates, a new stablecoin family to relabel the Kraken confound, Gemini's weaker
    gate, or Claude's seven-condition one-year reuse.
11. **Do not edit this plan document** or the master plan beyond the single
    bookkeeping correction in §9.3.

## 4. Preconditions

Run these first, in the worktree. If any fails, stop and report `BLOCKED`.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c5a-coverage-loader

# Right worktree, right branch, clean tree.
git rev-parse --abbrev-ref HEAD      # must print protocol-v11-c5a-coverage-loader
git status --short                   # must print nothing

# The packet parent is an ancestor of HEAD, and C4 really is merged.
git merge-base --is-ancestor 3c77610 HEAD && echo PARENT_OK
git merge-base --is-ancestor 85c52d4 3c77610 && echo C4_MERGED_OK

# The regression baseline is green before you change anything.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  -p no:randomly \
  tests/test_protocol.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol_guardrails.py \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_bootstrap_b4.py \
  tests/test_estimator_c3.py \
  tests/test_replication_c4.py
```

The last command must report `174 passed`. `PYTHONPATH="$PWD/src"` is mandatory in
every Python invocation in this worktree.

Commit with a plain `git commit`. Per H9 there is no `.githooks` directory in this
repository and `core.hooksPath` is unset; do not copy the C4 plan's
`-c core.hooksPath=.githooks` flag.

## 5. The contract C5a must freeze

Every clause below is normative. Section numbers map to the YAML edits in §8, the
spec edits in §9, and the tests in §10.

### 5.1 Semantic-hash scope — `semantic_hash_scope`

This is the keystone clause. It must state, in machine-readable form, exactly what a
v1.1 semantic hash will cover when C5 computes it.

```text
basis:                  utf8_text_normalized_to_lf_before_sha256   (inherited, audit refs)
canonicalization:       json.dumps(projected, sort_keys=True,
                                   separators=(',',':'), ensure_ascii=True)
hash_algorithm:         sha256
projection_rule:        every top-level key EXCEPT the excluded set
excluded_keys:          [frozen_semantic_sha256]
in_scope_key_count:     45
total_key_count:        46
float_policy:           FORBIDDEN at every depth
duplicate_key_policy:   FORBIDDEN, fail closed at load
key_order_relevance:    NONE   (sort_keys=True makes written order non-semantic)
owner_packet_for_value: C5
```

Required properties:

1. `frozen_semantic_sha256` is excluded because a document cannot contain its own
   digest. This is stated as a **rule with a reason**, not an unexplained exclusion
   list.
2. The exclusion set is **exactly one key**. Nothing else may be excluded. A future
   packet widening it must amend this clause, which changes the hash, which is the
   intended tripwire.
3. `in_scope_key_count: 45` and `total_key_count: 46` are asserted literally so that
   adding or deleting any top-level key breaks a test rather than silently changing
   the hash scope.
4. Mapping order, comments, and YAML formatting are outside the identity — same
   posture as v1, and the v1 test
   `test_yaml_key_order_and_formatting_do_not_change_hash` already proves the
   mechanism works.
5. The clause records that **the value** is C5's to compute. C5a states scope; C5
   fills scope with a number.
6. `predecessor_semantic_sha256` **is in scope** and must stay
   `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`. The
   predecessor's digest is a semantic fact about lineage; only the *own*-hash field
   is excluded.

### 5.2 Coverage and claim scope — `coverage_and_claim_scope`

A new **top-level** key. The existing `replication_gate_2025.coverage_reporting`
stays exactly as C4 froze it; this clause generalizes the obligation to every
candidate and every scored period, and the gate clause becomes the 2025-specific
instance of it.

```text
applies_to:                  every candidate in the frozen ladder and every
                             optional-family hypothesis, in every scored period
required_per_candidate:      candidate_eligible_rows
                             candidate_eligible_percentage
                             exclusion_reasons
                             longest_missing_run
required_granularity:        by_year AND pooled
minimum_coverage_threshold:  NONE_BY_DESIGN
threshold_addition_rule:     any future minimum requires separate justification
                             and preregistration; never a v1/v1.1 correction
claim_applicability:         candidate-complete timestamps only
paired_comparison_rule:      coverage is reported on the paired sample actually
                             scored, never on a larger comparator sample
minimum_paired_per_year:     168      (binds to the frozen B4 fail-closed rule)
```

Required properties:

1. **By year and pooled, both.** Audit §7 says "by year"; the bootstrap pools
   across years, so a pooled figure is also needed. Reporting only one of the two
   permits a coverage cliff in a single year to hide inside a healthy pool.
2. `minimum_coverage_threshold` stays `NONE_BY_DESIGN` and the clause explicitly
   records *why*: the audit rejected the 98% cutoff as unsupported. Recording the
   rejection reason prevents a later reader from reading `NONE_BY_DESIGN` as an
   oversight and "fixing" it.
3. `minimum_paired_per_year: 168` is **not a new rule**. It restates the frozen
   `validation.bootstrap.fail_closed.observed_year` condition ("fewer than 168
   paired-valid observations in any required year") so the coverage report and the
   inference fail-closed rule cannot drift apart. The clause must reference the
   frozen source rather than redefine the number.
4. Coverage is reported on the **paired** sample. The frozen
   `search_and_calibration_restrictions.paired_comparison_rule` already forbids
   using a larger baseline sample for the incremental claim; this makes the
   reporting consequence explicit.
5. The clause must not introduce any *pass/fail* semantics. It creates reporting
   duties only.

### 5.3 Exclusion-reason vocabulary — `exclusion_reason_vocabulary`

Closed vocabulary, derived from causes the frozen protocol already recognizes. Do
not invent new exclusion physics.

```text
missing_native_interval        a required lookback crosses a missing native interval
incomplete_feature_window      a formula's full endpoint/path window is unavailable
funding_cadence_incomplete     the settlement window is not cadence-complete
oi_snapshot_gap                a required five-minute OI snapshot is missing
                               or an intervening gap exists
invalid_label_endpoint         a required BTC price endpoint or path is unavailable
buffer_bar_missing             a required 2026 target-only buffer bar is absent
pre_archive_period             a known pre-archive period, null and unflagged
eth_oi_pre_2021_12_01          ETH OI before 2021-12-01, never entering M3
same_key_conflict              conflicting same-key rows block publication
```

Required properties:

1. The vocabulary is **closed**. An unrecognized reason string is a hard failure,
   not a passthrough.
2. Every member traces to an existing frozen clause —
   `missing_and_duplicate_policy`, `feature_window_completeness`,
   `target_endpoint_buffer_2026.missing_data_rule`, or the ETH OI rule. The plan's
   test must assert that traceability, not merely the string list.
3. Reasons are **mutually exclusive per excluded row** and the row's reason is the
   first applicable member in the order above, so two runs on the same data produce
   the same report.
4. Counts by reason must sum to total excluded rows. This is an arithmetic identity
   the tests must exercise, including the zero-exclusion case.

### 5.4 `longest_missing_run` definition

Currently a required field with no definition (H5). Freeze it exactly:

```text
unit:              consecutive nominal hourly origin positions
domain:            the candidate's nominal hourly grid for the period
counted_state:     positions that are NOT candidate-eligible
                   (missing, invalid, or excluded for any vocabulary reason)
value_when_none:   0
boundary_rule:     runs do not span a year boundary; report per year and pooled
                   as the maximum of the per-year runs
tie_rule:          report the length only; no start timestamp is required
```

Required properties:

1. Defined on the **nominal** grid (the same grid the frozen B4 bootstrap uses, per
   `validation.bootstrap.nominal_grid`), not on the compacted eligible-row list.
   Measuring gaps on a list with the gaps removed is meaningless.
2. `0` when there are no ineligible positions — not null, not absent.
3. Per-year runs do not span year boundaries, matching the year-stratified design.
   The pooled figure is the maximum across years, not a recomputed cross-boundary
   run.
4. It is a **diagnostic**. It never changes eligibility, pooling weights, or any
   gate outcome.

### 5.5 Draft loader contract — `protocol_v11.py`

C5a delivers the first executable v1.1 loader. It is a **draft** loader: it must
work while `frozen_semantic_sha256` is still a placeholder, and it must refuse to
pretend the draft is frozen.

```text
load_protocol_v11(path)     -> ProtocolV11
  validates:                   UTF-8 read, duplicate-key rejection, float rejection,
                               non-string mapping key rejection, duplicate series,
                               duplicate ladder features
  projects:                    all top-level keys except frozen_semantic_sha256
  computes:                    canonical JSON of the projection  (bytes, not a digest)
  asserts draft state:         frozen_semantic_sha256 == NOT_YET_ASSIGNED_PENDING_PACKET_C5
                               protocol_status        == DRAFT_UNFROZEN_SUCCESSOR
                               scoring_permission     == NONE_UNTIL_FROZEN
  refuses:                     any operation guard while unfrozen
```

Required properties:

1. **Reuse, do not fork.** Import `_validate_hash_value`, `canonical_semantic_json`,
   and the duplicate-key loader behaviour from `src/quantara/protocol.py`. If a
   helper is currently private and needs sharing, promote it to a public name in
   `protocol.py` **without changing its behaviour**, and keep the v1 tests green as
   proof. Do not copy-paste the logic into a second file, or v1 and v1.1 will drift.
2. **No digest is computed.** The loader may produce the canonical projection
   *bytes* and expose them, because that is what makes the scope testable, but it
   must not hash them and must not expose a `semantic_sha256` attribute. Enforce
   this with a test that the returned object has no such attribute.
3. **`guard_protocol_v11_operation` refuses everything while unfrozen.** Every
   operation — including the five v1 pre-gate checks — raises. Rationale: v1's
   pre-gate allowance exists because v1 *is* frozen and its hash is a real trust
   anchor. A draft with a placeholder hash has no trust anchor, so there is nothing
   to authorize against. The refusal message must name
   `NOT_YET_ASSIGNED_PENDING_PACKET_C5` as the cause.
4. **`to_dict()` returns a detached copy** so callers cannot mutate the validated
   identity, mirroring the v1 `Protocol.to_dict()` contract.
5. The v1 loader is **unchanged in behaviour**: `load_protocol` still rejects the
   v1.1 draft, and `test_v11_draft_is_fail_closed_and_unloadable_by_frozen_v1_loader`
   still passes.
6. The module must expose the scope constants —
   `V11_HASH_EXCLUDED_KEYS = ("frozen_semantic_sha256",)`,
   `V11_IN_SCOPE_KEY_COUNT = 45`, `V11_TOTAL_KEY_COUNT = 46`,
   `V11_UNASSIGNED_HASH = "NOT_YET_ASSIGNED_PENDING_PACKET_C5"` — so the YAML clause
   and the code cannot disagree without a test failing.

### 5.6 Coverage computation — same module

Pure, synthetic-testable functions. No I/O, no data paths.

```text
coverage_report(eligibility_by_year)  -> CoverageReport
  input:   {year: sequence of per-position eligibility, length == nominal_hours(year)}
  output:  per-year and pooled: eligible_rows, eligible_percentage (18dp string),
           longest_missing_run, exclusion counts by reason
  raises:  on wrong grid length, unknown exclusion reason, float input
```

Required properties:

1. **Grid length is validated against `bootstrap_b4.nominal_hours(year)`**, the
   frozen function. Reject any year whose sequence length differs. This is the same
   guard `bootstrap_b4` already applies, reused rather than reimplemented.
2. **Percentages render at 18 decimal places via the frozen
   `bootstrap_b4.render_fraction_18`** using exact `Fraction` inputs. No float ever
   touches the path. Verified example to reproduce as a fixture:
   `Fraction(8737*100, 8760)` renders `99.737442922374429224`, and
   `Fraction(8760*100, 8760)` renders `100.000000000000000000`.
3. **Pooled percentage is computed from pooled counts**, not as a mean of per-year
   percentages. With unequal year lengths (2024 has 8784 hours) averaging
   percentages is wrong; the tests must include a mixed-length case that would
   distinguish the two.
4. `longest_missing_run` follows §5.4 exactly, including the per-year boundary rule
   and the pooled maximum.
5. Exclusion counts by reason sum to total ineligible positions. Test the
   all-eligible (`longest_missing_run == 0`, zero exclusions) and all-ineligible
   edge cases.
6. Unknown reason strings raise. Float inputs raise.

## 6. File allowlist

**Create exactly these two files:**

1. `src/quantara/protocol_v11.py` — draft loader, scope constants, operation guard,
   and coverage computation. Wraps frozen machinery; reimplements nothing.
2. `tests/test_protocol_v11_loader_coverage.py`

**Modify exactly these three files:**

3. `configs/protocols/quantara-protocol-v1_1.yaml`
4. `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`
5. `tests/test_protocol_v11_draft_contract.py`

**Delete:** none.

**Explicitly forbidden to touch:** `src/quantara/protocol.py` beyond a
behaviour-preserving helper promotion (§5.5 property 1);
`tests/fixtures/protocol_v1_expected.json`; any v1 artifact; `bootstrap_b4.py`;
`estimator_c3.py`; `replication_c4.py`; `training_metrics_logistic.py`;
`evaluation_metrics.py`; `aggregation.py`; `pyproject.toml`;
`.github/workflows/ci.yml`; anything under `configs/datasets/`; `kernel/`; this plan
document; and
`docs/superpowers/plans/2026-09-01-protocol-v11-successor-master-plan.md`. The last
two were already committed by Hermes in the preceding plan commit on this branch, so
they are outside the packet diff.

Anything else requires stopping `BLOCKED` with an explanation.

## 7. Required module contract

`src/quantara/protocol_v11.py`:

```python
V11_UNASSIGNED_HASH: str            # "NOT_YET_ASSIGNED_PENDING_PACKET_C5"
V11_HASH_EXCLUDED_KEYS: tuple       # ("frozen_semantic_sha256",)
V11_IN_SCOPE_KEY_COUNT: int         # 45
V11_TOTAL_KEY_COUNT: int            # 46
EXCLUSION_REASONS: tuple            # the 9 §5.3 members, in the §5.3 order

class ProtocolV11DraftError(ValueError): ...
class ProtocolV11GuardError(PermissionError): ...

@dataclass(frozen=True, slots=True)
class ProtocolV11:
    source: Path
    canonical_projection_json: str   # canonical JSON of the 45-key projection
    def to_dict(self) -> dict: ...   # detached copy
    # NOTE: deliberately no semantic_sha256 attribute

@dataclass(frozen=True, slots=True)
class CoverageReport:
    per_year: Mapping[int, YearCoverage]
    pooled: YearCoverage

def load_protocol_v11(path) -> ProtocolV11: ...
def hash_scope_projection(document: Mapping) -> dict: ...
def guard_protocol_v11_operation(operation: str) -> NoReturn: ...   # always raises
def coverage_report(eligibility_by_year, *, exclusions_by_year=None) -> CoverageReport: ...
def longest_missing_run(flags: Sequence[bool]) -> int: ...
```

Constraints: standard library plus `yaml` only; no float in any signature or
computation path; every public function has a docstring stating its frozen source
where it wraps one.

## 8. Required YAML changes

Edit `configs/protocols/quantara-protocol-v1_1.yaml`. Add **three** new top-level
keys and amend **two** existing ones. Nothing else changes.

**Add `semantic_hash_scope`** per §5.1, placed immediately after
`scoring_permission` so the identity block stays contiguous.

**Add `coverage_and_claim_scope`** per §5.2, placed immediately after
`missing_and_duplicate_policy` so it sits with the other data-completeness clauses.

**Add `exclusion_reason_vocabulary`** per §5.3, placed immediately after
`coverage_and_claim_scope`, with each member carrying a `source_clause` field naming
the frozen clause it derives from, and a `longest_missing_run` definition block per
§5.4.

**Amend `deferred_change_set`**: add a `C5a` entry and leave `C5` alone.

```yaml
C5a:
  owner_packet: C5a
  status: IMPLEMENTED_PACKET_C5A
C5:
  owner_packet: C5
  status: DEFERRED
```

**Amend `replication_gate_2025.coverage_reporting`**: add a single back-reference
field binding it to the general clause. Do not change its existing four required
fields, its `NONE_BY_DESIGN` threshold, or its `applicability` string.

```yaml
general_contract: coverage_and_claim_scope
```

Hard constraints:

- After the edits the YAML has **49 top-level keys**, of which **48 are in hash
  scope**. `semantic_hash_scope.total_key_count` and `in_scope_key_count` must be
  written as `49` and `48`, **not** the 46/45 values measured before the edit. §5.1
  quotes the pre-edit numbers so Codex can verify the starting point; the committed
  clause must describe the post-edit document. A test asserts the clause matches the
  document it lives in, so an inconsistency here fails loudly.
- No floats. Decimal-like values are exact quoted strings.
- No duplicate top-level keys.
- `frozen_semantic_sha256`, `protocol_status`, `scoring_permission`, `frozen_date`,
  `predecessor_semantic_sha256`, and every C1–C4 clause are byte-unchanged.

## 9. Required spec changes

### 9.1 New §12 content

Replace the current §12 "Draft semantic-hash state" body so it states the scope rule
in prose, keeping the state itself unchanged. It must say: the projection is every
top-level key except `frozen_semantic_sha256`; the count is 48 of 49; the
canonicalization is the inherited `json.dumps(..., sort_keys=True,
separators=(',',':'), ensure_ascii=True)` over UTF-8 with `sha256`; mapping order and
formatting are outside the identity; the state remains
`NOT_YET_ASSIGNED_PENDING_PACKET_C5`; and **C5 owns the value**.

### 9.2 New coverage section

Add a section covering §5.2–§5.4 in prose: the per-candidate and per-year reporting
duty, the closed exclusion vocabulary with its nine members, the
`longest_missing_run` definition, why there is no minimum coverage threshold, and
the claim-scope limitation to candidate-complete timestamps. Extend the §11 deferred
table with a `C5a` row marked `IMPLEMENTED` and **leave the C5 row exactly as it is**
— `test_v11_c4_spec_status_is_implemented_while_c5_stays_deferred` asserts the
literal string `| Coverage and final freeze | \`DEFERRED\` | C5 |`, so that row must
survive verbatim. The C5a row is an addition, not a replacement.

### 9.3 Master-plan bookkeeping — already done by Hermes

`docs/superpowers/plans/2026-09-01-protocol-v11-successor-master-plan.md` is **not**
in the packet allowlist. Hermes committed its bookkeeping alongside this plan in the
preceding commit on this branch, matching the C4 precedent
(`1730960 docs(protocol): add C4 packet plan and mark C3 accepted in master plan`).
Two edits were made there and Codex must not touch the file:

1. Status line: C4 recorded as `ACCEPTED` **and merged** (PR #8, merge commit
   `3c77610`), with C5a as `NEXT`.
2. Packet-sequence table: a `C5a` row inserted before `C5` covering loader, hash
   scope, coverage/claim scope, and the guardrail suite (findings "items 12, 13",
   status `NEXT`); the existing `C5` row narrowed to spec/YAML/fixture
   synchronization plus the semantic SHA-256 freeze; the C5a plan path added to the
   packet-plans list.

The standing invariants, the workflow-scope section, and the execution prompt are
unchanged.

## 10. Required tests

Write tests **first** and capture genuine red output before implementing. Two files.

### 10.1 `tests/test_protocol_v11_loader_coverage.py` (new)

Reproduce every Hermes finding as an assertion:

1. **H1/H2 scope, from the document**: load the YAML, count top-level keys, assert
   49 total and 48 in scope, assert the excluded set is exactly
   `("frozen_semantic_sha256",)`, and assert the YAML clause's own
   `total_key_count`/`in_scope_key_count` equal the measured counts. This is the test
   that makes the clause self-checking.
2. **Projection correctness**: `hash_scope_projection(document)` omits exactly the
   excluded key and preserves every other key's value identically.
3. **Order independence**: rewriting the YAML with permuted top-level key order
   yields an identical canonical projection string. Mirror
   `test_yaml_key_order_and_formatting_do_not_change_hash` in spirit.
4. **No digest leaks**: `ProtocolV11` has no `semantic_sha256` attribute; no module
   member returns a 64-hex string; a regex scan of `protocol_v11.py` source finds no
   64-hex literal.
5. **Draft-state enforcement**: a tampered copy with a real-looking 64-hex
   `frozen_semantic_sha256`, or `protocol_status: FROZEN`, or
   `scoring_permission: ALLOWED`, is rejected by `load_protocol_v11`.
6. **Fail-closed loading**: duplicate top-level key, duplicate nested key, a float
   anywhere, a non-string mapping key, duplicate `series_id`, and duplicate ladder
   feature each raise. Use `tmp_path` copies; never mutate the committed YAML.
7. **Guard refuses everything**: all five v1 pre-gate operation names, `score_2025`,
   and an unknown operation each raise `ProtocolV11GuardError`, and the message names
   `NOT_YET_ASSIGNED_PENDING_PACKET_C5`.
8. **v1 isolation**: `load_protocol` still raises on the v1.1 draft; loading the v1
   YAML still yields `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`.
9. **H5/§5.4 `longest_missing_run`**: all-eligible → `0`; all-ineligible → the full
   year length; leading run, trailing run, and interior run cases; two equal-length
   runs; and a per-year vs pooled case proving the pooled value is the maximum of
   per-year runs and never spans a boundary.
10. **§5.6 coverage arithmetic**: wrong grid length raises (assert against
    `nominal_hours(year)`, including the 8784-hour 2024 case); percentages render at
    18dp via `render_fraction_18` with the two verified literals from §5.6; pooled
    percentage comes from pooled counts, demonstrated with a mixed 8760/8784 case
    where a mean-of-percentages would give a different answer; exclusion counts sum
    to total ineligible; unknown reason raises; float input raises.
11. **§5.3 vocabulary**: `EXCLUSION_REASONS` has exactly the nine members in order,
    matches the YAML list exactly, and every member's `source_clause` names a key
    that actually exists in the document.
12. **No 2025/2026 access**: the module source contains no data path, and the tests
    construct every grid synthetically.

### 10.2 `tests/test_protocol_v11_draft_contract.py` (extend)

Add, without weakening any existing assertion:

13. **H7 `exclusions`**: v1.1 `forbidden_families` equals v1's exactly (11 members,
    same order) **and** `exclusions.rules` intentionally differs from v1's while both
    have length 2, with the v1.1-only data-slice-013 supersession rule asserted by
    substring.
14. **H7 `standing_rejections`**: exactly four entries —
    `signed_return_replacement`, `sigma_denominator_floor`,
    `arbitrary_98_percent_coverage_cutoff`, `new_feature_search` — every value
    `REJECTED`, and v1 has no such key.
15. **H4 coverage generalization**: `coverage_and_claim_scope` exists at top level,
    requires the four fields, requires `by_year` and pooled granularity, keeps
    `minimum_coverage_threshold: NONE_BY_DESIGN`, and
    `replication_gate_2025.coverage_reporting.general_contract` points at it while
    that gate clause's four required fields and threshold are unchanged.
16. **Deferred set**: keys are exactly `{C2, C3, C4, C5a, C5}`; `C5a` is
    `IMPLEMENTED_PACKET_C5A`; `C5` is still `{owner_packet: C5, status: DEFERRED}`.
17. **Spec table**: the C4 `IMPLEMENTED` row and the literal
    `| Coverage and final freeze | \`DEFERRED\` | C5 |` row both still present, plus a
    new C5a `IMPLEMENTED` row.
18. **No v1.1 hash anywhere**: scan the v1.1 spec and YAML for 64-hex strings and
    assert the only match is `predecessor_semantic_sha256`'s v1 digest.
19. **No v1.1 fixture**: assert `tests/fixtures/protocol_v1_1_expected.json` does
    **not** exist, proving C5a did not do C5's job.

## 11. Verification gates

Run all of these and paste the real output.

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c5a-coverage-loader

# Focused gate.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  -p no:randomly \
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

# Full suite, serial. Baseline was 1092 passed, 16 deselected, ~22 minutes.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q

# Full suite under CI parallelism. CI runs `uv run pytest -n 4`; a test that
# depends on execution order passes serially and fails here.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q -n 4

# Repository-wide lint. MUST match the CI gate exactly. A lint scoped to only the
# new files is NOT sufficient: it passes while an *edited* file regresses, which is
# exactly how C4 shipped 4 over-length lines past a clean scoped run.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check src tests benchmarks

# Whitespace hygiene.
git diff --check
```

Capture the **red** output of the focused gate before implementing and the green
output after. A report without genuine verbatim red output is `INCOMPLETE`. The full
suite must report at least `1092 passed` plus the new tests; a lower number means
something was lost.

## 12. Byte-identity gates

All seven must print **nothing**. Any output is a failed packet.

```bash
git diff --stat 3c77610 -- docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md
git diff --stat 3c77610 -- configs/protocols/quantara-protocol-v1.yaml
git diff --stat 3c77610 -- tests/fixtures/protocol_v1_expected.json
git diff --stat 3c77610 -- src/quantara/bootstrap_b4.py src/quantara/estimator_c3.py src/quantara/replication_c4.py
git diff --stat 3c77610 -- src/quantara/training_metrics_logistic.py src/quantara/evaluation_metrics.py src/quantara/aggregation.py
git diff --stat 3c77610 -- pyproject.toml .github/workflows/ci.yml configs/datasets kernel
git diff --stat 3c77610 -- tests/test_replication_c4.py tests/test_estimator_c3.py tests/test_bootstrap_b4.py
```

Also confirm, against parent `3c77610`, that these blobs are unchanged:

```text
docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md  72322b09be800b4002aab507b4d142545ccd4c10
configs/protocols/quantara-protocol-v1.yaml                f26b4a747f098befb4014ba72f78aeb3a447dba5
tests/fixtures/protocol_v1_expected.json                   6a885d73d7bfed1c4eec182c8d19fe1deed86d71
src/quantara/bootstrap_b4.py                               491611b247449438753f5c49a13aaa271ef5077c
src/quantara/estimator_c3.py                               b2dace357cc04117c85c33e91a04ed39419e3142
src/quantara/replication_c4.py                             1092883e153f2e39a0df5009544d9115d6fe3485
src/quantara/training_metrics_logistic.py                  f2a0a8111d4231105b45b7eb22486965495c0d1c
tests/test_replication_c4.py                               07c2dc1c28f3ce7df8d305fa152ca14b76fcb40f
pyproject.toml                                             57d8921b833e5f13e3c82c9d923d9373d8f1d679
.github/workflows/ci.yml                                   31a6e9cda89b73ae2400985222f181bd2a492871
```

Verify with `git rev-parse 3c77610:<path>` and `git hash-object <path>`. Confirm
`tests/test_estimator_c3.py` still contains
`PACKET_PARENT_ESTIMATOR_BLOB = "f2a0a8111d4231105b45b7eb22486965495c0d1c"` and was
not edited.

If §5.5 property 1 required promoting a private helper in
`src/quantara/protocol.py`, that file is the **only** permitted exception to the
frozen-machinery rule, the diff must be rename-only with no behaviour change, and
`tests/test_protocol.py`, `tests/test_protocol_document_contract.py`, and
`tests/test_protocol_guardrails.py` must all stay green unmodified. If the promotion
cannot be done without touching behaviour, stop `BLOCKED` instead of improvising.

## 13. Commit

Stage only the five allowlisted files. Commit locally with exactly:

```text
feat(protocol): bind v1.1 loader, hash scope, and coverage claim contract
```

Use a plain `git commit` — no `core.hooksPath` flag (H9). Then **stop**. Do not push,
do not open a PR, do not begin C5.

## 14. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA.
2. The single commit SHA.
3. Exact list of changed files.
4. Raw red output captured before implementation.
5. Raw green focused-gate output, raw green regression-gate output, the serial full
   suite's pass count, and the `-n 4` full suite's pass count.
6. Raw output of all seven byte-identity `git diff --stat` commands, the ten blob-id
   comparisons, and `git diff --check`.
7. Ruff result for `src tests benchmarks`.
8. Confirmation that **no v1.1 semantic hash was computed, derived, printed, or
   written**, that `frozen_semantic_sha256` is still
   `NOT_YET_ASSIGNED_PENDING_PACKET_C5`, and that `protocol_status`,
   `scoring_permission`, and `frozen_date` are unchanged.
9. Confirmation that `tests/fixtures/protocol_v1_1_expected.json` does not exist.
10. Confirmation that `deferred_change_set["C5"]` is still `DEFERRED` and that the
    spec's literal `| Coverage and final freeze | \`DEFERRED\` | C5 |` row survives
    verbatim.
11. The final top-level key count and in-scope count, plus proof that the
    `semantic_hash_scope` clause's own counts match the document containing it.
12. The exact nine-member `exclusion_reason_vocabulary` as committed, with each
    member's `source_clause`, so the auditor can check no new exclusion physics was
    invented.
13. Confirmation that no 2025 or 2026 data was read, opened, enumerated, globbed, or
    listed, and that every fixture and grid is synthetic.
14. Confirmation that no data was acquired and no network call was made.
15. Confirmation that no dependency was added and `numpy` was not used.
16. Confirmation that no rejected reviewer invention was introduced, naming each of
    the eleven items in prohibition 10 and how its absence was verified.
17. An explicit mapping of which of H0–H11 each new test reproduces.
18. Whether `src/quantara/protocol.py` was touched; if yes, the exact diff and the
    argument that it is rename-only.
19. Test count and any residual risk.

A green unit test alone is not `COMPLETE`. Hermes performs the independent audit and
is the only role that may mark this packet `ACCEPTED`.

## 15. Execution prompt

```text
Read D:\PROJECT\Quantara-worktrees\protocol-v11-c5a-coverage-loader\docs\superpowers\plans\2026-09-01-protocol-v11-c5a-coverage-loader.md
and execute that packet only. Tests first with real red output. Run every packet gate,
including the -n 4 full suite and the repository-wide ruff. Commit only the packet
allowlist with a plain git commit. Do not compute any v1.1 semantic hash. Do not push,
merge, or auto-advance to C5.
```
