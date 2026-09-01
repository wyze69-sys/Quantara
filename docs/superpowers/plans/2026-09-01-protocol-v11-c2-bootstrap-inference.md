# Protocol v1.1 — Packet C2: Frozen Bootstrap Inference (audit finding B4)

**Status:** `NEXT` — not started
**Date:** 2026-09-01
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c2-bootstrap`
**Branch:** `protocol-v11-c2-bootstrap`
**Packet parent commit:** `5f4348d` (branch tip; descends from `main` merge commit `9a9196e`)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists

Packet C1 landed the Protocol v1.1 draft (version identity, lineage, `T+2ms`
ordering, nearest-rank Q80, exact purge inequality) and merged as PR #5. C1
deliberately left inference untouched: the v1.1 draft still carries the
Protocol-v1 bootstrap text (168-hour blocks, 2,000 resamples, seed `20260831`)
with `successor_repair_status: DEFERRED` and `successor_repair_owner_packet: C2`.

Audit finding **B4 — "Bootstrap is not executable reproducibly"** is the blocker
this packet repairs. The v1 text does not uniquely determine a result: it never
says whether blocks are circular, how missing hours are handled, how years are
pooled, which PRNG produces which stream, what the CI convention is, or how the
null distribution is constructed. Two correct implementations of the v1 sentence
can disagree on pass/fail. That makes the success gate non-reproducible.

This packet freezes exactly one complete algorithm, implements it in exact
arithmetic, and pins it with golden fixtures.

This is a **specification repair, not a scientific reset.** No new feature, no
new model, no target change, no unsealing.

## 2. Absolute prohibitions

Violating any of these is an automatic `BLOCKED`. Stop and report instead.

1. **Do not modify, move, reformat, or re-hash any Protocol v1 artifact.** These
   must stay byte-identical to the packet parent:
   - `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`
   - `configs/protocols/quantara-protocol-v1.yaml`
   - `tests/fixtures/protocol_v1_expected.json`
   - `tests/test_protocol_document_contract.py`
   - `tests/test_protocol.py`
   - `tests/test_protocol_guardrails.py`
   - `src/quantara/protocol.py`
2. **Do not compute, invent, declare, or freeze a Protocol v1.1 semantic
   SHA-256.** That is packet C5. Any literal 64-hex string presented as the v1.1
   frozen hash is a defect. The existing draft-contract test enforces this and
   must keep passing.
3. **Do not make Protocol v1.1 loadable by `quantara.protocol.load_protocol`.**
   That loader stays pinned to the frozen v1 hash. v1.1 remains a draft.
4. **Do not implement C3/C4/C5 content.** Specifically forbidden here:
   - no `M2K` model, no renaming of any ladder entry;
   - no Holm family definition, no "three fixed optional hypotheses", no
     multiplicity procedure changes — C2 may reference Holm only as `DEFERRED`;
   - no exact-Decimal IRLS binding, no both-class or calibration-failure rules;
   - no OI timestamp resolution, no final pre-2025 refit rule, no 2026 endpoint
     buffer, no one-year `REPLICATED` gate;
   - no coverage/exclusion reporting, no claim-scope table.
5. **Do not touch** `src/quantara/training_pipeline.py`,
   `src/quantara/training_metrics_logistic.py`,
   `src/quantara/ic_stability_diagnostic.py`,
   `src/quantara/phase_auc_diagnostic.py`, any canonical data, any manifest, any
   current pointer, or anything under `data/`.
   The two existing diagnostic bootstraps are **separate frozen preregistrations
   for different questions** (per-fold IC stability; phase-AUC). They are not the
   B4 gate bootstrap. Do not "unify", refactor, or re-seed them.
6. **Do not run the bootstrap on any real Quantara data.** This packet delivers
   the algorithm plus synthetic golden fixtures only. No scoring is authorized
   while `protocol_status` is `DRAFT_UNFROZEN_SUCCESSOR`.
7. **Do not read, enumerate, or open any 2025 or 2026 data.** Sealed.
8. **Do not add a third-party dependency.** `numpy` is *not* installed in this
   venv and must not be added. Declared runtime deps are Python `>=3.11,<3.12`
   and `pyyaml==6.0.2`. Use the standard library only.
9. **Do not push, merge, rebase, reset, stash, clean, or create a PR.** Commit
   locally and stop.
10. **If any scientific detail below is ambiguous, stop `BLOCKED`.** Never invent
    a scientific constant.

## 3. Environment

The shared editable install points at `D:\PROJECT\Quantara`, so this worktree
must override the import path explicitly:

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c2-bootstrap
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q <targets>
```

Verify at the start that `git status --short` is empty and that the merged C1
commit is an ancestor of `HEAD`:

```bash
git merge-base --is-ancestor 9a9196ed6663046f12d20f5458dfcf319c7b56aa HEAD && echo ok
```

`HEAD` is the Hermes commit that recorded C1 as accepted plus this plan document.
That is expected.

## 4. File allowlist

**Create exactly these three files:**

1. `src/quantara/bootstrap_b4.py`
2. `tests/test_bootstrap_b4.py`
3. `tests/fixtures/bootstrap_b4_golden.json`

**Modify exactly these three files:**

4. `configs/protocols/quantara-protocol-v1_1.yaml` — replace the deferred
   `validation.bootstrap` block with the frozen contract of §6.
5. `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md` — replace the
   deferred inference paragraph (currently lines ~323–327) and the C2 row of the
   §11 deferred table.
6. `tests/test_protocol_v11_draft_contract.py` — the C2 status transition of §8.4.

**Delete:** none. Anything else requires stopping `BLOCKED` with an explanation.

## 5. The frozen algorithm

This is the complete, result-determining specification. Implement it exactly.

### 5.1 Estimand and paired differences

For an ordered pair `(candidate, comparator)` form the hourly paired Brier-loss
improvement:

```text
d_t = loss_comparator,t - loss_candidate,t
```

Positive favours the candidate. The estimand is the **pooled hourly mean** of
`d_t`, not a mean of per-year means.

### 5.2 The nominal grid and the null pattern

Build the complete nominal hourly UTC grid **separately for each calendar year**.
Candidate and comparator use identical timestamps. Store `d_t` on paired-valid
hours and `null` on every other hour. **Never fill a missing loss value.**

`H_y` is the nominal number of calendar hours in year `y`, derived with real
`datetime` arithmetic, never hardcoded. Verified values Codex must reproduce, not
assume:

```text
2020 -> 8784    2021 -> 8760    2022 -> 8760
2023 -> 8760    2024 -> 8784    2025 -> 8760
```

### 5.3 Non-circular moving blocks

Block length `L = 168` consecutive **clock hours** (not 168 valid observations).
Blocks retain their observed null pattern.

```text
eligible block starts: 0 ... H_y - L        (count = H_y - L + 1)
blocks drawn per year: n_blocks_y = ceil(H_y / L)
```

For `L = 168` this gives `n_blocks_y = 53` for every year 2020–2025, and eligible
start counts `8593` (`H=8760`) or `8617` (`H=8784`).

Sample `n_blocks_y` starts **with replacement**, concatenate the blocks including
their nulls, and **truncate to exactly `H_y` clock-hour positions**. Since
`53 * 168 = 8904 > H_y`, the final block is always partially consumed.

Implementation note, and a required test: truncating the concatenation is
arithmetically identical to consuming `min(L, remaining)` positions from the
final block's *start*. Codex may implement either form but must prove the
equivalence in a test.

### 5.4 Pooling

```text
D* = ( sum_y sum over non-null resampled positions d*_(y,i) )
     / ( sum_y n*_valid,y )
```

Each year is resampled separately; pooling is by **resampled paired-valid
count**, not by year count and not by nominal hours.

The observed statistic uses the same pooling over the un-resampled grid:

```text
D_obs = ( sum_y sum over non-null observed d_(y,t) ) / ( sum_y n_valid,y )
```

### 5.5 Resample count `B = 20000`

Frozen at **20,000** resamples for Protocol v1.1, superseding v1's 2,000.

This is a deliberate inferential strengthening and must be disclosed as a
successor-version design change, not presented as completion of an omitted
detail. The justification, which the spec text must carry:

At the smallest first-step Holm threshold `0.05/3`, with `p = 0.05/3` and
`z = 1.96`, the normal-approximation two-sided 95% Monte Carlo half-width
`z * sqrt(p(1-p)/B)` is:

```text
B =  2000  ->  0.005610684252190438
B = 20000  ->  0.001774254146896035
```

A half-width no greater than `0.002` requires `B >= 15739.888...`, i.e. at least
`15740` resamples. `20000` is the frozen round-number choice above that bound.

These three literals are exact and must appear in the spec and be asserted by a
test. Reproduce them with `Decimal` arithmetic, not floats.

### 5.6 Frozen PRNG

A seed alone is insufficient. Freeze algorithm, implementation, and
comparison-specific stream derivation.

**Algorithm — SplitMix64**, exact 64-bit unsigned integer arithmetic:

```text
MASK   = 2**64 - 1
GOLDEN = 0x9E3779B97F4A7C15

next_u64():
    state = (state + GOLDEN) & MASK
    z = state
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)
```

`random.Random` is **forbidden** for this bootstrap: it is a CPython
implementation detail, not a frozen cross-version contract. (The two existing
diagnostic modules keep their own preregistered `random.Random` usage untouched —
see prohibition 5.)

**Unbiased bounded draw** — rejection sampling, never a bare modulo:

```text
below(bound):
    limit = 2**64 - (2**64 mod bound)
    loop:
        x = next_u64()
        if x < limit: return x mod bound
```

**Comparison-specific stream derivation.** One independent stream per
`(comparison_id, year)`:

```text
payload = "quantara-protocol-v1_1|bootstrap-b4|" + comparison_id + "|" + str(year)
seed    = int.from_bytes(sha256(payload.encode("utf-8")).digest()[:8], "big")
```

The payload string, the `|` separator, the UTF-8 encoding, the leading 8 digest
bytes, and big-endian order are all frozen. `comparison_id` is an opaque
caller-supplied ASCII label; C2 does **not** define the family of comparisons
(that is C3). Draw order within a replicate is years ascending, then blocks in
index order.

### 5.7 Exact arithmetic

No floats anywhere in the statistic path.

- `d_t` enters as an integer scaled by the frozen `1e-18` storage quantum, or as
  a `Decimal` that is exactly representable at that quantum. Reject any input
  that is not.
- Sums are Python integers (unbounded, exact).
- Ratios are `fractions.Fraction`, so `D*`, `D_obs`, CI bounds, and comparisons
  are exact.
- Only the final reported rendering quantizes, using the repository's existing
  18-decimal-place convention (`ROUND_HALF_EVEN`, quantum `1e-18`).

### 5.8 Percentile CI — nearest rank

Two-sided 95% percentile interval over the raw-bootstrap pooled means:

```text
sort the B replicate means ascending (exact Fraction comparison)
j(q) = ceil(q * B)                    # 1-indexed rank
lower = sorted[j(0.025) - 1]          # j = 500   at B = 20000
upper = sorted[j(0.975) - 1]          # j = 19500 at B = 20000
```

No interpolation. The same nearest-rank convention as the C1 Q80 repair.

### 5.9 Null-centred one-sided p-value

```text
d0_t = d_t - D_obs                    (on paired-valid hours only; nulls stay null)
p    = (1 + count(D0*_b >= D_obs)) / (B + 1)
```

`D0*` is generated by the **identical** bootstrap — same streams, same block
starts — applied to the null-centred series.

**Verified exact identity, which the implementation may exploit and a test must
prove:** because centring subtracts the same constant from every paired-valid
observation and pooling divides by the resampled valid count,

```text
D0*_b = D*_b - D_obs      exactly, for every replicate b
```

so `count(D0*_b >= D_obs)` equals `count(D*_b >= 2 * D_obs)`. Hermes confirmed
this identity holds exactly over 200 replicates in exact `Fraction` arithmetic.
Whichever form is implemented, the test must assert both agree.

Rejected alternatives, to be recorded: Gemini's raw-bootstrap count at or below
zero (inadequately specified null) and Claude's "favorable resamples" formula
(directionally ambiguous).

### 5.10 Fail-closed rules

Inference fails closed for a comparison — it does **not** return a value, and it
does not silently drop a year — when either holds:

1. an observed year has fewer than `168` paired-valid observations;
2. a replicate has **no paired-valid observation in any required year** (per-year
   check, not merely a zero pooled denominator).

Raise a dedicated exception carrying the offending year and replicate index.
Fail-closed is a protocol outcome, not a crash: it must be a named error type in
`src/quantara/errors.py` style, reachable and asserted by tests.

### 5.11 Dependence rationale (spec text)

The year-stratified 168-clock-hour moving-block procedure is the explicit
dependence correction for the overlapping 24-hour labels at hourly origins.
Consecutive origins are not treated as IID. The pooled hourly mean stays the
estimand; blocks preserve the serial dependence of the paired loss differential.

Non-overlapping 24-hour origin subsampling is **rejected** for the primary test:
it discards information and makes the result depend on an arbitrary hourly phase.
It may be reported only as a frozen diagnostic if a successor protocol explicitly
authorizes it before scoring.

## 6. Required YAML change

In `configs/protocols/quantara-protocol-v1_1.yaml`, replace the whole
`validation.bootstrap` mapping (currently `method`, `block_hours`, `resamples`,
`interval`, `resampling`, `rng_seed`, `successor_repair_status`,
`successor_repair_owner_packet`) with the frozen contract. Requirements:

1. Every decimal constant is a **quoted exact string**. No floats anywhere —
   the existing recursive float assertion must keep passing.
2. Encode as explicit fields, not prose alone: block length, circularity
   (`non_circular`), eligible-start range, blocks-per-year formula, truncation
   rule, null-preservation rule, pooling formula, `resamples: 20000`, the CI
   convention with its rank formula, the p-value formula, the fail-closed rules,
   the PRNG algorithm/derivation payload, and the arithmetic contract.
3. Record the Monte Carlo justification literals of §5.5 as exact strings.
4. Remove `rng_seed: 20260831` from this block and state that a bare seed is
   superseded by the frozen derivation. Do **not** remove it from the v1 YAML.
5. `successor_repair_status: IMPLEMENTED_PACKET_C2` with a
   `supersedes_v1_inference: true` marker and an explicit
   `disclosed_design_change` note for the 2,000 → 20,000 increase.
6. Keep the `deferred_change_set` mapping's four keys, but set the `C2` entry's
   `status` to `IMPLEMENTED_PACKET_C2` (see §8.4). C3/C4/C5 stay `DEFERRED`.
7. Still loadable by `yaml.safe_load`, no duplicate mapping keys.

## 7. Required spec change

In `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`:

1. Replace the deferred inference paragraph with the complete §5 algorithm in
   prose plus formula blocks: paired differences, per-year nominal grid, null
   preservation, non-circular blocks and eligible starts, `ceil(H_y/L)` draws,
   truncation, pooled-by-valid-count estimand, `B = 20000` with the three exact
   Monte Carlo literals and the `15740` bound, SplitMix64 with the exact
   derivation payload, exact-arithmetic contract, nearest-rank CI with ranks
   `500`/`19500`, the null-centred p-value with the exact identity, both
   fail-closed rules, the §5.11 dependence rationale, and both rejected
   alternatives.
2. State plainly that this **supersedes the Protocol-v1 inference text** and that
   the resample increase is a disclosed successor-version design change.
3. Update the §11 deferred-table `C2` row to `IMPLEMENTED` naming this packet.
   Leave C3, C4, C5 rows untouched.
4. Do not alter the header block, the `NOT_YET_ASSIGNED_PENDING_PACKET_C5` hash
   state, the scoring-permission text, or any C1 section.
5. Success-gate criterion 2 keeps its meaning (bootstrap 95% lower bound for
   `BS_B2 - BS_candidate > 0`); it now resolves against this frozen procedure.
   Do not renumber or re-threshold any gate criterion.

## 8. Required tests

`tests/test_bootstrap_b4.py`, standard library plus `pytest` and `PyYAML` only.
Independent literal expectations — do not import the module's own constants to
assert the module's own behaviour where a literal is the point.

### 8.1 PRNG contract

- SplitMix64 reproduces a golden first-`k` `next_u64` sequence from a fixed seed
  (fixture literals).
- Stream derivation is exact: the SHA-256 payload for a known
  `(comparison_id, year)` yields the recorded seed literal.
- Different `comparison_id`s and different years give different streams; the same
  inputs reproduce bit-identically across two independent constructions.
- `below(bound)` never returns `>= bound`; the rejection limit is correct for a
  non-power-of-two bound; and a forced near-limit draw is rejected rather than
  folded (drive this by seeding to hit the rejection branch, or assert the limit
  arithmetic directly).

### 8.2 Sampling geometry

- `H_y` derived from `datetime` equals `8784/8760/8760/8760/8784/8760` for
  2020–2025.
- `n_blocks_y == 53` and eligible starts `== 8593` or `8617` as applicable.
- No sampled block start exceeds `H_y - 168`; no wraparound index is ever
  produced (proves non-circularity).
- Concatenated length before truncation is `8904`; after truncation exactly
  `H_y`.
- Truncate-the-concatenation and consume-`min(L, remaining)` produce identical
  numerator, denominator, and index multiset.

### 8.3 Statistics

- On a small hand-computable series with a deliberate null pattern, `D_obs`
  equals an independently computed exact `Fraction`.
- Nulls are never imputed: inserting extra nulls changes the denominator, never
  the numerator.
- Pooling is by resampled valid count, not by nominal hours — construct two years
  with different valid counts and show the pooled mean differs from the mean of
  per-year means.
- Nearest-rank CI: on a synthetic replicate set with known order statistics, the
  bounds are exactly ranks `ceil(0.025*B)` and `ceil(0.975*B)`, 1-indexed, with
  no interpolation.
- Null-centred identity: `D0*_b == D*_b - D_obs` exactly for every replicate in a
  reduced-`B` run, and the two p-value formulations agree.
- p-value bounds: `p >= 1/(B+1)` always; a series with `D_obs` far above the null
  gives the minimum `p`; a symmetric-noise series does not.
- Monte Carlo literals: recompute `0.005610684252190438`,
  `0.001774254146896035`, and the `15740` bound with `Decimal` and assert exact
  string equality against the spec and YAML.
- Determinism: two full runs with identical inputs are bit-identical; changing
  only `comparison_id` changes the replicates.

### 8.4 Protocol-artifact synchronization

Extend `tests/test_protocol_v11_draft_contract.py` minimally:

- `deferred_change_set["C2"]["status"] == "IMPLEMENTED_PACKET_C2"`, while C3, C4,
  C5 remain `DEFERRED`. The current test asserts all four are `DEFERRED` and
  **will fail** once the YAML changes — that failure is expected and must be
  repaired by this narrow edit, not by weakening the assertion to a wildcard.
- The YAML bootstrap block encodes `block_hours: 168`, `resamples: 20000`,
  non-circularity, the nearest-rank CI convention, the null-centred p-value, and
  both fail-closed rules.
- The recursive no-float assertion still passes over the modified YAML.
- Every C1 assertion still passes unchanged.

### 8.5 Fail-closed

- A year with 167 paired-valid observations raises, naming that year.
- A constructed replicate with zero paired-valid observations **in one required
  year** raises, naming year and replicate index, even when the pooled
  denominator is positive from other years.
- Neither failure returns a partial statistic.

### 8.6 Golden fixture

`tests/fixtures/bootstrap_b4_golden.json` pins a reduced-`B` end-to-end run
(`B = 200`, two synthetic years, a documented deterministic generator embedded in
the test) with:

- the resampled index multiset digest per year,
- `D_obs`, CI lower, CI upper as exact 18-dp strings,
- the p-value as an exact rational string,
- the derived seeds.

The fixture must be regenerable by the test file alone and must fail loudly if
the algorithm changes. Use synthetic data only; no repository data, no 2025.

## 9. Performance budget

Hermes measured the prefix-sum technique in this exact venv: 20,000 resamples
over five years of hourly data completed in **6.57 s**; the 2022–2024 three-year
case in **3.23 s**; a single year in **1.27 s**. A naive per-hour inner loop is
roughly 168× slower and is not acceptable.

Prefix-sum the value array and the paired-valid indicator array per year so each
sampled block costs `O(1)`. Exactness is preserved because the prefixes are
integer sums of scaled integers.

The full `B = 20000` path must be exercised at least once in the test suite and
must finish well inside 60 s. Keep the rest of the suite on reduced `B`.

## 10. Execution order

1. Confirm clean worktree at the packet parent, with C1 an ancestor.
2. **Tests first.** Write `tests/test_bootstrap_b4.py` before
   `src/quantara/bootstrap_b4.py` exists and capture the **real red output**.
   Paste it verbatim in the report. A report without genuine red output is
   `INCOMPLETE`.
3. Implement `src/quantara/bootstrap_b4.py`.
4. Generate `tests/fixtures/bootstrap_b4_golden.json` from the frozen algorithm.
5. Apply the YAML change (§6), then the spec change (§7), then the narrow
   draft-contract test change (§8.4).
6. Iterate until the focused gate is green.

## 11. Gates — all required

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c2-bootstrap

# Focused gate: new bootstrap suite plus every protocol suite, proving v1 intact
# and the v1.1 draft still fail-closed.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_bootstrap_b4.py \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py

# Regression gate: the two pre-existing diagnostic bootstraps must be untouched
# and still green.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_ic_stability_diagnostic.py \
  tests/test_phase_auc_diagnostic.py \
  tests/test_integration_ic_stability.py

# Byte-identity proof for every v1 artifact and the protected src files.
git diff --stat 9a9196ed6663046f12d20f5458dfcf319c7b56aa -- \
  docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md \
  configs/protocols/quantara-protocol-v1.yaml \
  tests/fixtures/protocol_v1_expected.json \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py \
  src/quantara/protocol.py \
  src/quantara/training_pipeline.py \
  src/quantara/training_metrics_logistic.py \
  src/quantara/ic_stability_diagnostic.py \
  src/quantara/phase_auc_diagnostic.py

# Whitespace hygiene.
git diff --check

# Scoped lint.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check \
  src/quantara/bootstrap_b4.py tests/test_bootstrap_b4.py

# No stray dependency was added.
git diff --stat 9a9196ed6663046f12d20f5458dfcf319c7b56aa -- pyproject.toml
```

Both `git diff --stat` commands must print **nothing**. Any output is a failed
packet.

## 12. Commit

Stage only the six allowlisted files. Commit locally with exactly:

```text
feat(protocol): freeze v1.1 bootstrap inference contract
```

Then **stop**. Do not push, do not open a PR, do not begin C3.

## 13. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA.
2. The single commit SHA.
3. Exact list of changed files.
4. Raw red output captured before implementation.
5. Raw green focused-gate output and raw green regression-gate output.
6. Raw output of both byte-identity `git diff --stat` commands and of
   `git diff --check`.
7. Ruff result.
8. Wall-clock time of the `B = 20000` test.
9. Confirmation that no v1.1 semantic hash was computed or declared.
10. Confirmation that no 2025 or 2026 data was read or enumerated, and that the
    bootstrap was run only on synthetic data.
11. Confirmation that no dependency was added and `numpy` was not used.
12. Test count and any residual risk.

A green unit test alone is not `COMPLETE`. Hermes performs the independent audit
and is the only role that may mark this packet `ACCEPTED`.
