# Protocol v1.1 — Packet C1: Version, Lineage, and Time Semantics

**Status:** `NEXT` — not started
**Date:** 2026-09-01
**Project root:** `D:\PROJECT\Quantara`
**Worktree for this packet:** `D:\PROJECT\Quantara-worktrees\protocol-v11-c1-time-semantics`
**Branch:** `protocol-v11-c1-time-semantics`
**Packet parent commit:** `3208a840c6f826837a1e7e9c5c15f09dc332f2ac` (`main`)
**Implementation worker:** Codex, exactly one packet per invocation
**Acceptance auditor:** Hermes

## 1. Why this packet exists

Protocol v1 is frozen at semantic SHA-256
`91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a` but **cannot be
executed unchanged**. The independent audit at
`docs/superpowers/reviews/2026-09-01-protocol-v1-three-reviewer-deep-audit.md`
records nine verified BLOCKER findings, of which this packet repairs exactly three
(B1, B2, B3) plus the lineage record (change-set item 14).

This is a **specification repair, not a scientific reset**. It does not introduce a
new target family, a new model family, a feature search, a volatility floor, or any
change to the sealed-2025 rules.

## 2. Absolute prohibitions

Violating any of these is an automatic `BLOCKED` result. Stop and report instead.

1. **Do not modify, move, reformat, or re-hash any Protocol v1 artifact.** These
   files must remain byte-identical to the packet parent:
   - `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`
   - `configs/protocols/quantara-protocol-v1.yaml`
   - `tests/fixtures/protocol_v1_expected.json`
   - `tests/test_protocol_document_contract.py`
   - `tests/test_protocol.py`
   - `tests/test_protocol_guardrails.py`
   - `src/quantara/protocol.py`
2. **Do not compute, invent, declare, or freeze a Protocol v1.1 semantic SHA-256.**
   The v1.1 hash is frozen in packet C5, only after C2, C3, and C4 land. Any literal
   64-hex string presented as the v1.1 frozen hash is a defect.
3. **Do not make Protocol v1.1 loadable by `quantara.protocol.load_protocol`.** That
   loader is pinned to the frozen v1 hash and must stay pinned. v1.1 is a draft.
4. **Do not implement C2/C3/C4/C5 content.** Specifically: no bootstrap algorithm, no
   20,000-resample change, no `M2K`/Holm content, no estimator binding, no final-refit
   rule, no 2026 buffer, no `REPLICATED` gate. Reference them only as `DEFERRED`.
5. **Do not touch** `src/quantara/training_pipeline.py`,
   `src/quantara/training_metrics_logistic.py`, any canonical data, any manifest, any
   current pointer, or anything under `data/`.
6. **Do not push, merge, rebase, reset, stash, clean, or create a PR.** Commit locally
   and stop.
7. **Do not read, enumerate, or open any 2025 or 2026 data.** Sealed.
8. **If any scientific detail below is ambiguous, stop `BLOCKED`.** Never invent a
   scientific constant.

## 3. Environment

The shared editable install points at `D:\PROJECT\Quantara`, so this worktree must
override the import path explicitly:

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c1-time-semantics
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q <targets>
```

Verify at the start that `git status --short` is empty and that the frozen-artifact
baseline commit `3208a840c6f826837a1e7e9c5c15f09dc332f2ac` is an ancestor of `HEAD`:

```bash
git merge-base --is-ancestor 3208a840c6f826837a1e7e9c5c15f09dc332f2ac HEAD && echo ok
```

`HEAD` itself is the Hermes specification commit that added this plan document, and is
one commit ahead of that baseline. That is expected.

## 4. File allowlist

**Create exactly these three files:**

1. `docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md`
2. `configs/protocols/quantara-protocol-v1_1.yaml`
3. `tests/test_protocol_v11_draft_contract.py`

**Modify:** none. **Delete:** none.

If the work appears to require modifying an existing file, stop `BLOCKED` and explain.

## 5. Required content — Protocol v1.1 draft specification

`docs/superpowers/specs/2026-09-01-quantara-protocol-v1_1.md` is a **complete
standalone successor specification**, not a diff. Transcribe every section of the v1
spec unchanged except where §5.1–§5.4 below require a change, and carry the deferred
markers of §5.5.

### 5.0 Header block

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

State plainly that no scoring of any period, and no 2025 access, is authorized while
status is `DRAFT_UNFROZEN_SUCCESSOR`.

### 5.1 B1 — Prediction ordering moves to `T+2ms`

Replace the v1 point-in-time cutoff convention with exactly:

```text
boundary event time:       F = T
nominal eligibility:       T + 1 ms
prediction time:           T + 2 ms
join:                      eligibility_ts < prediction_ts
funding feature window:    T-24h < settlement_ts <= T
```

The v1 defect being repaired, which must be stated in the document: with
`prediction_ts = T + 1 ms` and funding eligibility `F + 1 ms`, a settlement exactly at
`F = T` gave `T + 1 ms < T + 1 ms`, which is false — so the feature formula included
the settlement while the point-in-time join excluded it.

All other eligibility rules keep their v1 form and are now measured against
`prediction_ts = T + 2 ms`:

- kline with source close `C`: `eligibility_ts = C + 1 ms`
- settled funding with settlement `F`: `eligibility_ts = F + 1 ms`
- five-minute OI with source timestamp `O`: `eligibility_ts = O + 5 minutes`
- Kraken hourly OHLCVT with interval-start `K`: `eligibility_ts = K + 1 hour`

`P[t]` remains the BTC perpetual 1h bar close at `T - 1 ms`, and its future endpoint
remains the bar close at `T + 24h - 1 ms`. The millisecond ticks are logical ordering
conventions over already-completed data, **not** claims about exchange network
latency.

Required explicit statements:

- The added tick changes same-boundary inclusion **for funding only**. Completed
  klines, five-minute OI, and Kraken hourly candles are already eligible no later than
  `T` under the contracts above, so their inclusion is unchanged.
- This is a universal convention change and must be boundary-tested per source.
- Production use still requires measured live publication/ingestion latency; if live
  latency exceeds the decision schedule, same-boundary funding must shift to the next
  live decision.
- Record the two rejected alternatives and why: `eligibility_ts = F` (coherent but
  removes the frozen after-settlement ordering tick) and narrowing the window to
  `< T` (causal but delays boundary settlements one hourly decision, changing the
  intended `(T-24h,T]` feature).

### 5.2 B2 — Q80 becomes nearest-rank inverse empirical CDF

Replace `k = empirical Q80(...)` with exactly:

```text
Z_(1) <= ... <= Z_(N)
j = ceil(0.80 * N)
k = Z_(j)
Y_t = 1[Z_t > k]
```

Rules, all required verbatim in substance:

- Compute `Z` under the existing 50-digit `ROUND_HALF_EVEN` Decimal context.
- Do not interpolate.
- Do not round `k` to 8 decimals.
- Preserve the canonical full Decimal string for `k`.
- Ties need no timestamp tie-break because tied values are numerically equal.
- A synthetic quantile fixture and an actual frozen `k` fixture/hash are required
  before any 2022–2024 scoring. **In this packet, record that requirement as
  `DEFERRED` — do not generate `k`, and do not read design data.**
- `k` stays fixed through every fold and through sealed 2025.
- The eligibility rule is unchanged from v1: an origin enters the `k` design set only
  when its complete forward label ends no later than
  `2021-12-31 23:59:59.999 UTC`; no 2022 value may enter threshold design.
- Note that Type 7 and Type 8 are defensible alternatives but not scientifically
  required; nearest-rank is chosen because it matches the generalized inverse
  empirical-CDF meaning and introduces no interpolated threshold.

### 5.3 B3 — Exact purge inequality

Replace the prose 24-hour purge with exactly:

```text
training origin O is eligible iff O + 24h <= S
last eligible training origin = S - 24h
first test origin = S
```

Include both verified examples:

```text
Fold 1 S:                  2022-01-01 00:00 UTC
last training origin:      2021-12-31 00:00 UTC
last required label close: 2021-12-31 23:59:59.999 UTC

2025 S:                    2025-01-01 00:00 UTC
last training origin:      2024-12-31 00:00 UTC
last required label close: 2024-12-31 23:59:59.999 UTC
```

State that no post-test embargo is required for the anchored expanding-window design,
and that a `2024-12-30 23:00` cutoff is wrong by one hour and is rejected. The three
outer folds themselves are unchanged from v1.

### 5.4 Protocol lineage and intentional supersession

Add a dated lineage section recording that an earlier Quantara recommendation dated
2026-08-24 proposed a materially different MVP: BTCUSDT perpetual decisions every
completed 15-minute candle, a fixed one-hour executable immediate-entry policy,
regularized logistic regression or simple return regression as primary model,
LightGBM as designated secondary model, and both predictive and after-cost economic
metrics.

Record that Protocol v1 **intentionally superseded** that proposal — changing the
estimand from an executable directional one-hour policy to the probability of an
unusually large *undirected* 24-hour BTC move, changing cadence from 15 minutes to
hourly, removing the trading-policy/PnL layer, and freezing an exact-Decimal logistic
ladder — and that Protocol v1.1 inherits that supersession.

Record that reintroducing LightGBM, XGBoost, return regression, directional actions,
or economic gates requires a **separately preregistered successor experiment** and may
never be presented as a Protocol-v1 or v1.1 correction.

### 5.5 Deferred change-set items

Include a table of the remaining accepted change-set items with status `DEFERRED` and
their owning packet, so the draft is auditable for completeness without implementing
them:

- C2 — complete non-circular year-stratified 168-clock-hour moving-block bootstrap,
  null-centred p-value, percentile CI, exact PRNG, 20,000 resamples, fixtures.
- C3 — binding to the committed exact-Decimal IRLS contract, both-class and
  calibration-failure rules, `M2K` plus the three fixed optional hypotheses under
  ordinary Holm across all three, optional-block 2022–2024 results labelled selection
  evidence rather than independent replication.
- C4 — archive-specific OI timestamp resolution or explicitly conservative
  unknown-role handling, exact final pre-2025 refit sample and failure state, sealed
  BTC target-only endpoint buffer through `2026-01-01 22:59:59.999 UTC` covering all
  8,760 calendar-2025 hourly origins under the same seal/hash/no-inspection controls,
  and the exact one-year 2025 `REPLICATED` gate.
- C5 — coverage/exclusion reporting and claim scope per candidate, synchronization of
  spec/YAML/fixture, new semantic SHA-256, and the repeated tamper, future-mutation,
  boundary, solver, bootstrap, and 2025-seal test suite.

Also record the standing rejections carried forward from the audit: no signed-return
replacement, no sigma denominator floor, no arbitrary 98% coverage cutoff, and no new
feature search.

## 6. Required content — Protocol v1.1 draft YAML

`configs/protocols/quantara-protocol-v1_1.yaml` is the machine-readable counterpart of
the same draft. Requirements:

1. Mirror the v1 YAML top-level key structure so C5 can diff them mechanically, and
   add only the keys required by this packet.
2. `protocol_id: quantara-protocol-v1_1`, `protocol_status: DRAFT_UNFROZEN_SUCCESSOR`.
3. Carry `supersedes`, `predecessor_semantic_sha256`, `authorizing_audit`, and
   `frozen_semantic_sha256: NOT_YET_ASSIGNED_PENDING_PACKET_C5`.
4. Encode the §5.1 `T+2ms` ordering, the §5.2 nearest-rank quantile algorithm, and the
   §5.3 `O + 24h <= S` inequality as explicit fields, not free prose alone.
5. **No floats anywhere.** Every decimal constant is a quoted exact string, matching
   the v1 float prohibition.
6. No duplicate mapping keys.
7. Include a `deferred_change_set` mapping recording the §5.5 items and their packets.
8. Must be loadable by `yaml.safe_load`.

## 7. Required content — draft contract test

`tests/test_protocol_v11_draft_contract.py` must use PyYAML and independent literal
expectations. It **must not** import `quantara.protocol` for the purpose of validating
v1.1 semantics, except in the one negative test required by §7.2.

### 7.1 Protocol v1 must be provably untouched

- Assert the v1 spec, v1 YAML, and v1 fixture files exist.
- Assert the v1 fixture's `semantic_sha256` still equals
  `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`.
- Assert the v1 YAML still canonicalizes to that same SHA-256 using the frozen method
  `json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)` over
  its projected top-level keys, computed independently in the test.

### 7.2 Protocol v1.1 must be fail-closed and unloadable

- `quantara.protocol.load_protocol` applied to
  `configs/protocols/quantara-protocol-v1_1.yaml` must raise
  `ProtocolValidationError`. This is the required negative test: a draft successor
  must never authenticate as the frozen v1 protocol.

### 7.3 Draft identity and status

- `protocol_id == "quantara-protocol-v1_1"`.
- `protocol_status == "DRAFT_UNFROZEN_SUCCESSOR"`.
- `supersedes == "quantara-protocol-v1"`.
- `predecessor_semantic_sha256` equals the v1 literal above.
- `frozen_semantic_sha256 == "NOT_YET_ASSIGNED_PENDING_PACKET_C5"`.
- No 64-character lowercase hex string anywhere in the v1.1 YAML or v1.1 spec is
  presented as the v1.1 frozen hash. Implement this as a real regex scan that permits
  the predecessor hash literal and rejects any other 64-hex token in a
  `frozen_semantic_sha256`-like position.

### 7.4 Time semantics

- The v1.1 YAML encodes prediction ordering `T + 2 ms`.
- Funding eligibility remains `F + 1 ms` and the funding window remains
  `T-24h < settlement_ts <= T`.
- The join rule remains `eligibility_ts < prediction_ts`.
- Kline `C + 1 ms`, OI `O + 5 minutes`, and Kraken `K + 1 hour` are all still present.
- A boundary case test proves the v1 contradiction is resolved: for `F = T`, the pair
  `(eligibility = T + 1 ms, prediction = T + 2 ms)` satisfies strict `<`, whereas the
  v1 pair `(T + 1 ms, T + 1 ms)` does not. Compute this arithmetically in the test
  from integer millisecond offsets; do not assert it as a string.

### 7.5 Quantile and purge

- The v1.1 YAML encodes `j = ceil(0.80 * N)` nearest-rank selection with
  `k = Z_(j)` and `Y_t = 1[Z_t > k]`, no interpolation, and no rounding of `k`.
- The v1.1 YAML encodes `O + 24h <= S`.
- A purge arithmetic test derives `last eligible training origin = S - 24h` for
  `S = 2022-01-01 00:00 UTC` and `S = 2025-01-01 00:00 UTC` using real `datetime`
  arithmetic, and asserts the last required label close is `S - 1ms - ...` consistent
  with the two verified examples in §5.3. Assert that `2024-12-30 23:00 UTC` is **not**
  the last training origin for the 2025 fold.

### 7.6 Float prohibition and structure

- Recursively assert no Python `float` appears anywhere in the loaded v1.1 YAML.
- Assert no duplicate top-level keys and that the deferred change-set mapping names
  packets C2, C3, C4, and C5.

### 7.7 Lineage

- Assert the v1.1 spec records the 2026-08-24 superseded MVP proposal, names
  LightGBM as an earlier recommendation rather than an omitted v1 candidate, and
  requires a separately preregistered experiment to reintroduce it.

## 8. Execution order

1. Confirm clean worktree at the packet parent commit.
2. **Tests first.** Write `tests/test_protocol_v11_draft_contract.py` before the v1.1
   artifacts exist and capture the **real red output**. Paste it verbatim in the
   report. A report without genuine red output is `INCOMPLETE`.
3. Write the v1.1 draft spec.
4. Write the v1.1 draft YAML.
5. Iterate until the focused gate is green.

## 9. Gates — all required

```bash
cd /d/PROJECT/Quantara-worktrees/protocol-v11-c1-time-semantics

# Focused gate: new draft contract plus all three existing protocol suites,
# which prove v1 is untouched.
PYTHONPATH="$PWD/src" D:/PROJECT/Quantara/.venv/Scripts/python.exe -m pytest -q \
  tests/test_protocol_v11_draft_contract.py \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py

# Byte-identity proof for every v1 artifact and the two src files.
git diff --stat 3208a840c6f826837a1e7e9c5c15f09dc332f2ac -- \
  docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md \
  configs/protocols/quantara-protocol-v1.yaml \
  tests/fixtures/protocol_v1_expected.json \
  tests/test_protocol_document_contract.py \
  tests/test_protocol.py \
  tests/test_protocol_guardrails.py \
  src/quantara/protocol.py \
  src/quantara/training_pipeline.py \
  src/quantara/training_metrics_logistic.py

# Whitespace hygiene.
git diff --check

# Scoped lint, if ruff is available.
D:/PROJECT/Quantara/.venv/Scripts/python.exe -m ruff check tests/test_protocol_v11_draft_contract.py
```

The `git diff --stat` command above must print **nothing**. Any output is a failed
packet.

## 10. Commit

Stage only the three allowlisted files. Commit locally with exactly:

```text
docs(protocol): draft v1.1 version, lineage, and time semantics
```

Then **stop**. Do not push, do not open a PR, do not begin C2.

## 11. Report contract

Return `COMPLETE`, `BLOCKED`, or `INCOMPLETE` with:

1. Starting SHA and ending SHA.
2. The single commit SHA.
3. Exact list of changed files.
4. Raw red output captured before implementation.
5. Raw green focused-gate output.
6. Raw output of the byte-identity `git diff --stat` command, and of `git diff --check`.
7. Ruff result.
8. Confirmation that no v1.1 semantic hash was computed or declared.
9. Confirmation that no 2025 or 2026 data was read or enumerated.
10. Test count and any residual risk.

A green unit test alone is not `COMPLETE`. Hermes performs the independent audit and
is the only role that may mark this packet `ACCEPTED`.
