# Quantara Protocol v1 — Stage 4: Point-in-Time Research Table and Locked Evaluation

**Status:** BLOCKED — Stage 3 is not yet accepted
**Date:** 2026-08-31
**Project root:** `D:\PROJECT\Quantara`
**Planning baseline:** `main` at `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`
**Dependency:** Stage 3 accepted; all 14 frozen raw series are canonical and independently verified.
**Implementation worker:** Zcode, exactly one packet per invocation
**Acceptance auditor:** Hermes

## Execution prompt contract

Never execute this entire stage automatically. The user supplies one packet id. Zcode must execute
that packet only, commit locally, avoid push/merge, report evidence, and stop. Hermes audits before
the next packet.

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-31-protocol-v1-stage-4-research-and-evaluation.md and execute <PACKET_ID> only.
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
## 5. Architecture boundary

Do not generalize the existing BTCUSDT kline-v1 classes in place. They contain published hard-coded
identities and must remain byte-compatible. Introduce additive Protocol-v1 modules:

```text
src/quantara/protocol.py
src/quantara/series_descriptor.py
src/quantara/series_acquisition.py
src/quantara/series_parsing.py
src/quantara/series_canonical.py
src/quantara/series_quality.py
src/quantara/series_pipeline.py
src/quantara/series_backfill.py
src/quantara/protocol_hourly.py
src/quantara/protocol_features.py
src/quantara/protocol_labels.py
src/quantara/protocol_models.py
src/quantara/protocol_evaluation.py
src/quantara/protocol_run.py
```

Two additive canonical schema families are allowed:

1. `quantara.kline-series/v1`: exact-decimal OHLCV/OHLCVT with explicit temporal envelope and
   designed gap mask. It allows honest missing intervals but never null payload values in present
   rows.
2. `quantara.scalar-series/v1`: exact-decimal scalar observations for settled funding and OI with
   explicit settlement/snapshot semantics.

Use a new hash-domain separator and schema fingerprint for each family. Do not modify
`hash_contract_v1` or any existing canonical hash.
## 6. Global executor rules

For every packet:

1. Work on a dedicated branch/worktree, never directly on shared dirty `main`.
2. Record starting HEAD and `git status --porcelain=v1 -uall`.
3. Preserve all pre-existing untracked `temp/*.md`; do not stage, delete, rename, or rewrite them.
4. Read packet dependencies and stop if an earlier packet lacks Hermes `ACCEPTED` status.
5. Write failing tests first and include the observed red output, except E03/E04 are explicitly
   result-only packets: they may not author tests and must rerun the already-accepted pre-run gates.
6. Implement only the packet allowlist.
7. Run focused tests, then the packet integration command if named.
8. Run `git diff --check` and inspect `git diff --stat` plus the complete diff.
9. Stage explicit paths only; `git add .` and `git add -A` are forbidden.
10. Commit locally with the packet commit message; do not push, merge, rebase, reset, clean, stash,
    or start another packet.
11. Report exact commands, outputs, files, hashes, row/gap/duplicate counts, and status.

Any unexpected source drift, rights ambiguity, conflicting duplicate, checksum failure, unapproved
quality warning, unauthorized or premature 2025 access, or need to expand scope is `BLOCKED`, not
permission to improvise.

The existing default suite has a long runtime. Use focused tests during a packet and
`.venv/Scripts/python.exe -m pytest -n 4` only at phase gates. Ruff formatting has known pre-existing failures; run
ruff only on changed Python files and never reformat unrelated files.

## Stage 4 hourly research-data packets

### H00 — Point-in-time hourly alignment substrate

**Depends on:** Stage 3 accepted.

**Create only:** `src/quantara/protocol_hourly.py`, `tests/test_protocol_hourly.py`.

Build an hourly origin index from canonical BTC perpetual data. Join each source backward on
`eligibility_ts`; emit source age, validity, and gap-crossing masks. Test equality rejection,
forward/nearest rejection, unfinished bars, duplicate conflicts, source prehistory, all A8/Kraken
gaps, and ETH OI prehistory. No features or labels yet.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_hourly.py`
**Commit:** `feat(protocol): build point-in-time hourly alignment`

### H01 — Target and B0/B1/B2 inputs

**Depends on:** H00 accepted.

**Create only:** `src/quantara/protocol_labels.py`, `tests/test_protocol_labels.py`.
**May also create:** `src/quantara/protocol_features.py` for RV functions only.

Implement hourly log returns, RV windows, sigma, Z, design-only Q80, binary target, label validity,
and no-2022 threshold proof. Freeze independent golden vectors with values rendered to 18 decimal
places. Do not fit a model.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_labels.py`
**Commit:** `feat(protocol): build frozen target and HAR inputs`

### H02 — M1 BTC derivatives features

**Depends on:** H01 accepted.

**Modify only:** `src/quantara/protocol_features.py`.
**Create only:** `tests/test_protocol_features.py`.

Implement exactly funding 24h sum, dlog OI 24h, and native premium 1h mean. Diagnostic mark/index
basis may be emitted into a separate diagnostics artifact but cannot appear in the model matrix.
Test gap invalidation, settlement strictness, OI common-start behavior, and column allowlist.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_features.py`
**Commit:** `feat(protocol): add frozen BTC derivatives family`

### H03 — M2 Binance spot divergence

**Depends on:** H02 accepted.

**Modify only:** `src/quantara/protocol_features.py`, `tests/test_protocol_features.py`.

Add exactly `log(BTC perpetual close / Binance BTC spot close)` when both aligned bars and required
windows are valid. Test every A8 gap boundary and no interpolation.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_features.py`
**Commit:** `feat(protocol): add frozen Binance spot divergence`

### H04 — M3 ETH family excluding OI

**Depends on:** H03 accepted.

**Modify only:** `src/quantara/protocol_features.py`, `tests/test_protocol_features.py`.

Add exactly the five M3 columns in §4.3. Test that no ETH OI column or missingness indicator exists.
All BTC-only and BTC+ETH comparisons must expose an identical-timestamp mask.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_features.py`
**Commit:** `feat(protocol): add frozen ETH cross-market family`

### H05 — M3b ETH OI common-sample ablation

**Depends on:** H04 accepted.

**Modify only:** `src/quantara/protocol_features.py`, `tests/test_protocol_features.py`.

Add exactly ETH dlog OI 24h. The comparison mask begins no earlier than 2021-12-02 after lookback and
uses identical rows for both models. Test that prehistory cannot encode a calendar regime.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_features.py`
**Commit:** `feat(protocol): add secondary ETH OI ablation`

### H06 — M4 Kraken family

**Depends on:** H05 accepted.

**Modify only:** `src/quantara/protocol_features.py`, `tests/test_protocol_features.py`.

Add exactly the four Kraken features in §4.3. Test the explicit USD-versus-USDT quote-identity
disclosure, same-origin validity, 20 audited missing hours, no forward fill, and identical comparison
rows. Do not add an external FX or stablecoin series.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_features.py`
**Commit:** `feat(protocol): add frozen Kraken cross-venue family`

### H07 — Immutable research-table publication

**Depends on:** H06 accepted.

**Create only:** `src/quantara/protocol_run.py`, `tests/test_protocol_run.py`.

Publish the hourly table, validity masks, diagnostics, protocol hash, parent dataset commit hashes,
feature allowlists, and label contract through a new immutable lane. Call the accepted Protocol v1
publication APIs without modifying the Stage 2/3 source modules. Verify exact read-back, lineage
closure, no-op rerun, and absence of 2025.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_run.py`
**Phase gate:** `.venv/Scripts/python.exe -m pytest -n 4` plus a real indexed-repository E2E run.
**Commit:** `feat(protocol): publish Protocol v1 hourly research table`

## Stage 4 evaluation packets

### E00 — Frozen folds, models, calibration, and metrics

**Depends on:** H07 accepted.

**Create only:** `src/quantara/protocol_models.py`, `src/quantara/protocol_evaluation.py`,
`tests/test_protocol_models.py`, `tests/test_protocol_evaluation.py`.

Implement B0–M4 only, exact-Decimal logistic IRLS only, and the frozen constants from P00. Apply
training-only z-score standardization, exact outer folds, purge, prediction alignment, Brier, log
loss, AUC diagnostics, calibration diagnostics, and family masks. There is no hyperparameter search,
clipping, post-hoc calibration, or tree model in Protocol v1.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_models.py tests/test_protocol_evaluation.py`
**Commit:** `feat(protocol): implement frozen model and metric ladder`

### E01 — Paired bootstrap, Holm correction, and decision engine

**Depends on:** E00 accepted.

**Modify only:** `src/quantara/protocol_evaluation.py`, `tests/test_protocol_evaluation.py`.

Implement deterministic 168h/2,000-resample paired bootstrap with seed 20260831, within-year
resampling then pooling, Holm correction across the ETH and Kraken optional-family tests, the
mandatory M2-versus-B2 gate, per-year guardrails, and a pure decision engine returning PASS/FAIL
plus every reason. Golden-test with synthetic vectors where each gate fails independently.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_evaluation.py`
**Commit:** `feat(protocol): enforce locked statistical decision gate`

### E02 — Design-period rehearsal only

**Depends on:** E01 accepted.

**Modify only:** `src/quantara/protocol_run.py`, `src/quantara/cli.py`,
`tests/test_protocol_run.py`.
**Create only:** `tests/test_protocol_cli.py`, `tests/test_integration_protocol_rehearsal.py`,
`docs/superpowers/audits/protocol-v1/design-period-rehearsal.md`.

Complete the frozen evaluation orchestrator and add a backward-compatible `protocol-run` CLI route
with exactly the `locked-2022-2024` and `conditional-2025` modes used below. The route requires
explicit data and new-empty output roots, preserves every legacy descriptor invocation, validates
the protocol/seal before dispatch, and fails closed on unknown modes or unsatisfied guards. Test the
CLI red-to-green, including legacy compatibility, dirty/incorrect commit rejection, E03-FAIL denial,
and prevention of a second 2025 run.

Then run the full pipeline on eligible 2020–2021 origins with synthetic held-out blocks solely to
prove runtime, artifacts, determinism, and guardrails. Do not compute or report 2022–2024 scores.
After E02 acceptance, any formula or code change requires a protocol amendment and a new semantic
hash before E03.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_protocol_run.py tests/test_protocol_cli.py tests/test_protocol_evaluation.py`
**Integration gate:** `.venv/Scripts/python.exe -m pytest -q -m integration tests/test_integration_protocol_rehearsal.py`
**Phase gate:** `.venv/Scripts/python.exe -m pytest -n 4`
**Commit:** `test(protocol): complete result-blind design rehearsal`

### E03 — Locked 2022–2024 execution

**Depends on:** E02 accepted and a clean accepted commit with unchanged semantic hash.

**Create only:** `docs/superpowers/audits/protocol-v1/locked-2022-2024-result.md`.
**Prohibited:** Any source, test, configuration, protocol, or model change. Runtime result artifacts
remain under the configured ignored data/output root and are referenced by cryptographic identity.

Run once from a new empty output root. Write fold predictions and aggregate metrics atomically so a
crash cannot expose a selectively inspectable partial result. Preserve every prediction, loss, fold
fit, standardization fit, bootstrap seed, environment hash, protocol hash, dataset-parent hash, and
gate reason. A mechanical failure with no completed score may be corrected only through a separate,
audited, result-blind amendment that leaves scientific semantics unchanged. Once a completed
2022–2024 score artifact exists, do not change code or protocol and rerun based on its result. Report
PASS or FAIL honestly.

**Pre-run identity gate:** `git status --porcelain=v1 -uno` is empty; `git rev-parse HEAD`
equals the accepted E02 commit; the Protocol v1 semantic hash and all accepted dataset-parent hashes
match their authenticated manifests; and the output root is new and empty.
**Pre-run test gate:** `.venv/Scripts/python.exe -m pytest -n 4`
**Locked command:** `.venv/Scripts/quantara.exe protocol-run --mode locked-2022-2024 --data-root <accepted-data-root> --output-root <new-empty-output-root>`
**Commit:** `results(protocol): record locked 2022-2024 verdict`

### E04 — Conditional one-time 2025 evaluation

**Depends on:** E03 accepted. Before invocation, `git rev-parse HEAD` must equal the exact accepted
E03 result commit; `git status --porcelain=v1 -uno` must be empty; the executable source tree must
match accepted E02; the Protocol v1 semantic hash, accepted dataset-parent hashes, and sealed 2025
manifest must all verify unchanged; and the output root must be new and empty. Execution access
additionally requires E03's complete verdict to be `PASS`; otherwise only the denial path may run.

**Create only:** `docs/superpowers/audits/protocol-v1/conditional-2025-result.md`.
**Prohibited:** Any source, test, configuration, protocol, model, threshold, or feature change.
Runtime result artifacts remain under the configured ignored data/output root.

Validate every precondition and invoke the guard exactly once. If E03 did not pass, the command must
exit `4`, emit `DENIED_AS_DESIGNED`, create no 2025 prediction/metric artifact, and leave only the
denial evidence needed for the report; this is the successful denial-path gate. If E03 passed, the
command may read 2025 only after all validations succeed, must exit `0`, and records exactly one
`REPLICATED` or `DID_NOT_REPLICATE` artifact. Any other exit or partial artifact is `BLOCKED` and
cannot be retried once 2025 outcome access began. No second run after redesign.

**Guarded command:** `.venv/Scripts/quantara.exe protocol-run --mode conditional-2025 --data-root <accepted-data-root> --output-root <new-empty-output-root>`
**Commit:** `results(protocol): record conditional 2025 verdict`
## 11. Phase-gate audit requirements

Hermes performs these after P02, D07, each source C packet, H07, E02, E03, and E04:

1. Inspect complete diff and commit content.
2. Verify file allowlist and no ownership contamination.
3. Rerun focused and full tests independently.
4. Run real acquisition/publication in a separate temporary data root.
5. Verify source hashes, row counts, gaps, duplicates, exact Decimal paths, and manifests.
6. Verify all current pointers and authenticated graph closure.
7. Verify old BTC kline/research/training identities did not move.
8. Search for unauthorized or premature 2025 reads, forward/nearest joins, fills, floats, feature
   columns, and source fallbacks.
9. Confirm `HEAD` remains unpushed until acceptance.
10. Return `ACCEPTED`, `CORRECTION_REQUIRED`, or `BLOCKED` with evidence.

## Stage completion gate

**COMPLETE:** H00–H07 are accepted; E00–E02 pass; E03 has exactly one completed locked 2022–2024 result; E04 is either correctly denied or executed exactly once after a complete PASS, with all artifacts hash-bound.

**BLOCKED:** Any scientific ambiguity, rights failure, integrity mismatch, unexplained source drift,
quality finding without Hermes approval, protocol-hash mismatch, unauthorized or premature 2025
access, or need to expand scope.

**INCOMPLETE:** Code or documents exist but any required test, live run, audit, commit, or acceptance
remains unfinished. A green unit test alone is never COMPLETE.

## First action

After Stage 3 is accepted, execute **H00 only** and stop for Hermes audit.
