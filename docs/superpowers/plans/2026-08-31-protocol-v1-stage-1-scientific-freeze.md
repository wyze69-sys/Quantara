# Quantara Protocol v1 — Stage 1: Scientific Protocol Freeze

**Status:** IN PROGRESS — P00 accepted; P01 is next
**Date:** 2026-08-31
**Project root:** `D:\PROJECT\Quantara`
**Planning baseline:** `main` at `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`
**Dependency:** None; this is the first stage.
**Implementation worker:** Zcode, exactly one packet per invocation
**Acceptance auditor:** Hermes

## Execution prompt contract

Never execute this entire stage automatically. The user supplies one packet id. Zcode must execute
that packet only, commit locally, avoid push/merge, report evidence, and stop. Hermes audits before
the next packet.

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-31-protocol-v1-stage-1-scientific-freeze.md and execute <PACKET_ID> only.
Use a dedicated branch/worktree. Preserve unrelated work. Run every packet gate.
Commit only the packet allowlist. Do not push, merge, or auto-advance.
Return COMPLETE / BLOCKED / INCOMPLETE with raw commands, outputs, changed files, hashes, and risks.
STOP after the report.
```

## 2. Goal

Freeze a scientifically defensible Protocol v1, then turn the frozen 2020–2024 raw inventory into
immutable, exact, point-in-time canonical datasets and a locked hourly research table. Only after
those artifacts pass independent audit may Quantara run the pre-registered 2022–2024 experiment.
The plan must remain capable of reporting an honest null result.
## 3. State and inventory boundary

### 3.1 Already canonical

1. Binance USD-M BTCUSDT perpetual traded-price OHLCV, 2020–2024, at 1m/1h/1d.

This lane is immutable input. Packets in this plan may read it but may not alter its published
identities, pointers, descriptors, parser identity, manifests, quality evidence, or canonical bytes.

### 3.2 Frozen remaining inventory — exactly 13 source series

BTC:

1. Settled funding.
2. Open interest snapshots.
3. Mark-price 1m klines.
4. Index-price 1m klines.
5. Native premium-index 1m klines.
6. Binance spot 1m klines.
7. Kraken XBT/USD spot 1h OHLCVT.

ETH:

8. Perpetual traded-price 1m klines.
9. Settled funding.
10. Open interest snapshots, beginning 2021-12-01 only.
11. Mark-price 1m klines.
12. Index-price 1m klines.
13. Native premium-index 1m klines.

### 3.3 Frozen exclusions

Do not add liquidations, options, long/short ratios, taker ratios, altcoins, order books, macro,
on-chain, sentiment, news, or technical-indicator searches. Incidental columns in the Binance
metrics archive may be retained in the immutable raw object but are not canonical Protocol-v1
series and must not enter any feature table.

The older
`docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md` is superseded for
Protocol v1. In particular, its top-trader and taker-ratio scope, guessed completeness rules, and
combined metrics feature direction are not authorized here.
## 4. Scientific contract to freeze in P00

### 4.1 Research question

Can pre-registered BTC derivatives, spot/perpetual divergence, ETH cross-market state, and one
independent BTC venue improve probability forecasts of unusually large BTCUSDT 24-hour moves
beyond a strong causal volatility-persistence baseline?

### 4.2 Target

For hourly origin `t`, using canonical BTCUSDT perpetual traded closes:

```text
r24_t  = log(P[t+24h] / P[t])
sigma_t = sqrt(sum_{j=0}^{23} r[t-j]^2)
Z_t    = abs(r24_t) / sigma_t
Y_t    = 1[Z_t > k]
k       = empirical Q80(Z_t) on eligible 2020–2021 design origins only
```

An origin enters the Q80 calculation only when its complete forward label ends no later than
2021-12-31 23:59:59.999 UTC. No 2022 value may enter threshold design.

### 4.3 Baselines and frozen model ladder

```text
B0 — training-only climatology
B1 — logistic model using causal log(RV_1d)
B2 — HAR-style logistic model using log(RV_1d), log(RV_7d), log(RV_30d)
M1 — B2 + BTC funding_24h_sum + BTC dlog_oi_24h + BTC native_premium_1h_mean
M2 — M1 + log(BTC perpetual close / Binance BTC spot close)
M3 — M2 + frozen ETH family, excluding ETH OI
M3b — M3 + ETH dlog_oi_24h on the identical post-2021-12-01 common sample
M4 — M3 + frozen Kraken cross-venue family
```

`RV_H = sqrt(sum of squared eligible hourly log returns over H hours)` for H = 24, 168, 720.
A zero or incomplete window is invalid; no epsilon replacement is permitted.

M3 adds exactly:

- ETH 1h log return.
- ETH 24h realized volatility.
- ETH settled funding 24h sum.
- ETH native-premium 1h mean.
- ETH/BTC 24h relative log return.

M3b adds exactly ETH 24h change in log open interest and changes nothing else.

M4 adds exactly:

- Kraken 1h log return.
- Kraken 24h realized volatility.
- Binance-spot minus Kraken 1h return divergence.
- `log(Binance BTCUSDT spot close / Kraken XBT/USD close)` with no invented USD/USDT FX
  conversion. The feature is explicitly a cross-venue, cross-quote dislocation and may include
  USDT-versus-USD effects.

At information cutoff `T`, exact feature formulas are:

```text
funding_24h_sum(T) = sum settled rates with T-24h < settlement_ts <= T
dlog_oi_24h(T) = log(OI_snapshot_ending_T / OI_snapshot_ending_T_minus_24h)
native_premium_1h_mean(T) = arithmetic mean of the 60 native-premium 1m closes ending in (T-1h, T]
spot_perp_dislocation(T) = log(BTC_perp_close_T / Binance_BTC_spot_close_T)
eth_ret_1h(T) = log(ETH_perp_close_T / ETH_perp_close_T_minus_1h)
eth_rv_24h(T) = sqrt(sum of the 24 eligible ETH hourly log returns ending at T)
eth_funding_24h_sum(T) = ETH form of funding_24h_sum
eth_native_premium_1h_mean(T) = ETH form of native_premium_1h_mean
eth_btc_relative_ret_24h(T) = ETH_ret_24h(T) - BTC_ret_24h(T)
eth_dlog_oi_24h(T) = ETH form of dlog_oi_24h
kraken_ret_1h(T) = log(Kraken_close_T / Kraken_close_T_minus_1h)
kraken_rv_24h(T) = sqrt(sum of the 24 eligible Kraken hourly log returns ending at T)
binance_kraken_ret_divergence_1h(T) = Binance_spot_ret_1h(T) - Kraken_ret_1h(T)
binance_kraken_cross_quote_log_ratio(T) = log(Binance_spot_close_T / Kraken_close_T)
```

Every formula requires its full endpoint/path window. Funding requires a cadence-complete settlement
window; OI requires the exact five-minute snapshots ending at both endpoints and no intervening
gap; 1m premium means require all 60 minutes; return/RV windows crossing any invalid source interval
are null. There is no stale-value tolerance, interpolation, nearest timestamp, or alternate horizon.

Native Binance premium is the pre-registered primary futures-dislocation feature. Constructed
`mark/index - 1` and `mark/spot - 1` are diagnostics only and never enter M1–M4. Mark and index are
canonicalized because they verify source integrity and support diagnostics, not because they earn
independent model stages.

All probability models use the repository's exact-Decimal logistic-IRLS discipline with these
frozen constants: L2 penalty `lambda = 1`, unpenalized intercept, train-window z-score
standardization, `max_iterations = 50`, convergence tolerance `0.000000000001`, eta clamp `24`,
probability clamp `0.000000000001`, and Gaussian elimination with partial pivoting. There is no
regularization search, feature clipping, post-hoc probability calibration, tree model, or model
family search in Protocol v1. Calibration is evaluated on the raw logistic probabilities.

For every paired candidate comparison, refit the comparator on exactly the same training rows and
score exactly the same test timestamps as the candidate. A larger baseline sample may be reported
separately but cannot be used for the paired incremental claim.

### 4.4 Point-in-time contract

Every canonical record preserves:

```text
provider
venue
market_type
instrument_id
provider_symbol
series_id
native_interval
source_file
source_sha256
event_ts
interval_open_ts
interval_close_ts
settlement_or_snapshot_ts
archive_publication_ts
ingestion_ts
eligibility_ts
quality_flags
```

Rules:

- An hourly information cutoff `T` is an exact UTC hour boundary. `prediction_ts = T + 1 ms`.
  `P[t]` is the BTC perpetual 1h bar close at `T - 1 ms`; its future endpoint is the bar close at
  `T + 24h - 1 ms`. This one-millisecond computational convention orders already-completed data; it
  is not a claim about exchange network latency.
- For a kline with source close time `C`, nominal `eligibility_ts = C + 1 ms`.
- For settled funding with source calculation/settlement time `F`, nominal
  `eligibility_ts = F + 1 ms`.
- For a five-minute OI row whose source timestamp is interval start `O`, nominal
  `eligibility_ts = O + 5 minutes`.
- For Kraken hourly OHLCVT whose source timestamp is interval start `K`, nominal
  `eligibility_ts = K + 1 hour`.
- `eligibility_ts < prediction_ts` without exception.
- All joins are backward as-of joins on `eligibility_ts`.
- Nearest joins, forward joins, unfinished bars, future revisions, and same-timestamp equality are
  forbidden.
- Completed klines become nominally eligible after interval close.
- Settled funding becomes nominally eligible after its settlement timestamp.
- OI becomes nominally eligible only after the end of its five-minute snapshot interval.
- Archive publication time is ex-post provenance, not the real-time availability of observations.
- Protocol v1 claims nominal historical point-in-time safety, not reconstruction of historical
  network latency. This limitation must appear in every result report.

### 4.5 Missing and duplicate policy

- Missing is null, never zero.
- No price, mark, index, premium, OI, or venue gap is interpolated.
- A feature is invalid when a required lookback crosses a missing native interval.
- A label is invalid when its required BTC price endpoints/path are unavailable.
- Known pre-archive periods remain null and receive no fabricated regime flag.
- Exact duplicate source rows may be deterministically deduplicated only after byte comparison,
  with source-row count, distinct-row count, duplicate count, and duplicate hashes preserved.
- Same-key conflicting rows block publication.
- ETH OI before 2021-12-01 is null and never enters M3.

### 4.6 Validation and gate

Outer folds:

```text
Fold 1: train 2020-09-01..2021-12-31; test 2022
Fold 2: train 2020-09-01..2022-12-31; test 2023
Fold 3: train 2020-09-01..2023-12-31; test 2024
```

Remove training origins whose 24-hour labels cross a boundary. Use a 24-hour purge. Apply only the
frozen train-window z-score and fixed regularization described above. No clipping or post-hoc
calibration is allowed. Never use random K-fold.

Primary metric: pooled prediction-level Brier score and Brier skill versus B2:

```text
BS(model) = mean((p-y)^2)
BSS_B2(model) = 1 - BS(model) / BS(B2)
loss_improvement_i = loss_B2_i - loss_model_i
probability_bias = mean(p-y)
```

Calibration intercept and slope are obtained diagnostically by unpenalized logistic regression of
`y` on `logit(p)` with an intercept, after clamping only for the logarithm to
`[0.000000000001, 0.999999999999]`. The fitted intercept is calibration intercept and the fitted
coefficient is calibration slope. These calculations do not alter predictions.

Inference: paired moving-block bootstrap over hourly loss differentials, 168-hour blocks, 2,000
resamples, 95% interval, resampled within year and then pooled. Freeze the RNG seed in P00.

The frozen candidate may unlock 2025 only if all hold:

1. Pooled `BSS_B2 >= 0.02`.
2. Bootstrap 95% lower bound for `BS_B2 - BS_candidate` is greater than zero.
3. Positive Brier improvement in at least two validation years.
4. No year has `BSS_B2 < -0.02`.
5. Pooled absolute probability bias is at most 0.02.
6. Pooled calibration slope is between 0.8 and 1.2.
7. Yearly absolute probability bias is at most 0.04.

Log loss, ROC-AUC, PR-AUC, calibration bias/intercept, and calibration slope are diagnostics. AUC
cannot pass the gate.

M1 and M2 are reported as the frozen BTC core ladder; M2 is the mandatory primary candidate. M2
must pass the complete gate versus paired B2 before 2025 can unlock. Starting from M2, evaluate the
ETH block and then the Kraken block as the only optional additions. Retain an optional block only
when pooled relative Brier improvement versus the currently retained model is at least 1%, its
unadjusted two-sided 95% paired-bootstrap interval has a lower bound above zero, its one-sided
bootstrap p-value passes Holm at family-wise alpha 0.05 across these two optional-family tests, at
least two years improve, and no year is worse than -2%. If ETH is rejected, compare Kraken against
M2, not against an ETH-containing model. A rejected block receives no alternative
transformation search. M3b/ETH OI is a secondary diagnostic and can never alter the retained
candidate. The resulting candidate must still pass the complete 2%-versus-B2 and calibration gate
before 2025.

### 4.7 Sealed 2025

Before the final gate, 2025 may be checked only for file inventory, cryptographic hashes, parser
compatibility, expected boundaries, and mechanical corruption. Forbidden: labels, feature
distributions, model scores, conditional outcome inspection, or protocol adaptation. If the gate
passes, run exactly one frozen 2025 evaluation. Failure is reported as `DID_NOT_REPLICATE`; never
redesign and retest on 2025.
## 6. Global executor rules

For every packet:

1. Work on a dedicated branch/worktree, never directly on shared dirty `main`.
2. Record starting HEAD and `git status --porcelain=v1 -uall`.
3. Preserve all pre-existing untracked `temp/*.md`; do not stage, delete, rename, or rewrite them.
4. Read packet dependencies and stop if an earlier packet lacks Hermes `ACCEPTED` status.
5. Write failing tests first and include the observed red output.
6. Implement only the packet allowlist.
7. Run focused tests, then the packet integration command if named.
8. Run `git diff --check` and inspect `git diff --stat` plus the complete diff.
9. Stage explicit paths only; `git add .` and `git add -A` are forbidden.
10. Commit locally with the packet commit message; do not push, merge, rebase, reset, clean, stash,
    or start another packet.
11. Report exact commands, outputs, files, hashes, row/gap/duplicate counts, and status.

Any unexpected source drift, rights ambiguity, conflicting duplicate, checksum failure, unapproved
quality warning, 2025 access, or need to expand scope is `BLOCKED`, not permission to improvise.

The existing default suite has a long runtime. Use focused tests during a packet and
`.venv/Scripts/python.exe -m pytest -n 4` only at phase gates. Ruff formatting has known pre-existing failures; run
ruff only on changed Python files and never reformat unrelated files.

## Stage 1 packets

### P00 — Freeze the documentary and machine-readable protocol

**Status:** `ACCEPTED` at commit `8eeb3b71b4d8595f00f332666e2ffbc74d849a0b`.

**Depends on:** A1–A10 complete.

**Create:**

- `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`
- `configs/protocols/quantara-protocol-v1.yaml`
- `tests/fixtures/protocol_v1_expected.json`
- `tests/test_protocol_document_contract.py`

**Modify:** none.

Tasks:

1. Transcribe §3–§4 of this plan without semantic change.
2. Include exact inventory, formulas, logistic constants, no-search/no-calibration rules, RNG seed
   `20260831`, folds, purge, bootstrap, mandatory-M2/optional-family Holm rule, calibration gates,
   2025 rules, and null/duplicate rules.
3. Include SHA-256 references to A7–A10 reports and sidecars.
4. Freeze `native_premium` as primary and mark/index basis as diagnostic.
5. Freeze ETH OI as M3b common-sample only.
6. Mark Protocol v1 `FROZEN_BEFORE_2022_2024_SCORING`.
7. Independently render the expected semantic JSON fixture without importing production code.

**Tests:** document/YAML key equality, no forbidden families, no `2025` execution permission, and
fixed expected semantic SHA-256 computed by an independent fixture script.

**Acceptance:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_document_contract.py`. This test may use
PyYAML and independent literal expectations only; it must not import the future production loader.

**Commit:** `docs(protocol): freeze Quantara Protocol v1`

**Stop:** Hermes must compare the two representations and explicitly mark P00 `ACCEPTED`.
### P01 — Protocol loader, validator, and semantic hash

**Depends on:** P00 accepted.

**Create:** `src/quantara/protocol.py`, `tests/test_protocol.py`.
**Modify:** `src/quantara/cli.py` only to add a read-only `--validate-protocol` route if needed.

Tests first:

- Unknown keys rejected at every nesting level.
- Inventory must equal the frozen 14-series list.
- Every formula, fold, metric, gate, family, seed, and 2025 rule validated exactly.
- Duplicate feature names and unfrozen parameters rejected.
- Floats in hash semantics rejected; decimal thresholds render as strings.
- YAML key order/formatting does not alter semantic hash.
- The semantic hash equals P00’s independent fixture.
- Existing CLI routes and all existing descriptor tests remain unchanged.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol.py tests/test_cli.py`
**Commit:** `feat(protocol): validate and hash Protocol v1`
### P02 — Protocol tamper and 2025 guard tests

**Depends on:** P01 accepted.

**Create:** `tests/test_protocol_guardrails.py`.
**Modify:** `src/quantara/protocol.py` only if a real guard defect is found.

Test mutations of target threshold, feature family, venue, fold date, bootstrap size, success gate,
ETH OI role, native premium role, and 2025 state. Every mutation must fail before data access.
Expose a guard API that accepts a protocol hash and operation name and denies `score_2025` unless an
authenticated, hash-bound local gate-result artifact says every v1 criterion passed.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol.py tests/test_protocol_guardrails.py`
**Phase gate:** `.venv/Scripts/python.exe -m pytest -n 4`
**Commit:** `test(protocol): enforce freeze and sealed-2025 guardrails`
## 11. Phase-gate audit requirements

Hermes performs these after P02, D07, each source C packet, H07, E02, E03, and E04:

1. Inspect complete diff and commit content.
2. Verify file allowlist and no ownership contamination.
3. Rerun focused and full tests independently.
4. Run real acquisition/publication in a separate temporary data root.
5. Verify source hashes, row counts, gaps, duplicates, exact Decimal paths, and manifests.
6. Verify all current pointers and authenticated graph closure.
7. Verify old BTC kline/research/training identities did not move.
8. Search for forbidden 2025 reads, forward/nearest joins, fills, floats, feature columns, and source
   fallbacks.
9. Confirm `HEAD` remains unpushed until acceptance.
10. Return `ACCEPTED`, `CORRECTION_REQUIRED`, or `BLOCKED` with evidence.

## Stage completion gate

**COMPLETE:** P00–P02 are accepted; the human-readable and machine-readable protocol match; the semantic hash is frozen; tamper tests and the sealed-2025 guard pass; the full suite passes.

**BLOCKED:** Any scientific ambiguity, rights failure, integrity mismatch, unexplained source drift,
quality finding without Hermes approval, protocol-hash mismatch, forbidden 2025 access, or need to
expand scope.

**INCOMPLETE:** Code or documents exist but any required test, live run, audit, commit, or acceptance
remains unfinished. A green unit test alone is never COMPLETE.

## First action

Execute **P00 only** and stop for Hermes audit.
