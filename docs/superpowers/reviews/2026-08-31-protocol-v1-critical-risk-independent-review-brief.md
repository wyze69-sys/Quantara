# Quantara Protocol v1 — Independent Critical-Risk Review Brief

**Prepared:** 2026-08-31  
**Purpose:** Independent scientific, statistical, and point-in-time audit before Protocol v1 execution proceeds  
**Audience:** GPT, Claude, and Gemini in separate review conversations  
**Status:** REQUEST FOR CRITIQUE — not an implementation authorization

## Reviewer instruction

Act as an independent scientific and technical reviewer. Evaluate the protocol from first principles. Do not assume that the project owner, protocol author, or another reviewer is correct. Do not optimize for agreement or encouragement.

Prioritize defects that could cause:

- Look-ahead or target leakage.
- Invalid out-of-sample claims.
- An unfair baseline comparison.
- Misleading inference from overlapping labels or dependent observations.
- Accidental model-shopping or multiplicity errors.
- A result driven by missingness, calendar regime, exchange artifacts, or quote-currency effects.
- An ambiguous candidate-selection or final-2025 procedure.
- Irreproducible thresholds, estimators, p-values, or pass/fail outcomes.

Distinguish:

- **BLOCKER:** the protocol cannot be executed or interpreted uniquely and validly without correction.
- **HIGH:** material risk of invalid or misleading scientific conclusions.
- **MEDIUM:** important limitation or robustness issue that does not invalidate the primary execution.
- **DEFENSIBLE:** a deliberate choice with an acceptable trade-off.

If you recommend a change, specify the smallest exact correction. Do not respond with a broad menu of possible models or features.

## Authority and protocol state

The authoritative repository artifacts are:

```text
docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md
configs/protocols/quantara-protocol-v1.yaml
tests/fixtures/protocol_v1_expected.json
```

Frozen semantic SHA-256:

```text
91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a
```

Protocol v1 is marked `FROZEN_BEFORE_2022_2024_SCORING`. No Protocol v1 predictive score has been produced for 2022–2024, Stage 2 acquisition has not started, and sealed 2025 outcomes have not been inspected.

The frozen specification says any semantic change requires a **new, explicitly authorized protocol version** and new semantic hash. Do not recommend silently editing Protocol v1 in place.

---

# Part I — Frozen scientific design

## 1. Research question

> Can preregistered BTC derivatives, spot/perpetual divergence, ETH cross-market state, and one independent BTC venue improve probability forecasts of unusually large BTCUSDT 24-hour moves beyond a strong causal volatility-persistence baseline?

The frozen primary comparison is **M2 versus paired B2**. ETH and Kraken are conditional optional-family tests and cannot substitute for a failing M2 under the current rules.

## 2. Frozen data inventory

Already canonical and immutable:

```text
Binance USD-M BTCUSDT perpetual traded-price OHLCV
Coverage: 2020–2024
Resolutions: 1m, 1h, 1d
```

Frozen additional series:

```text
BTC
1. Settled funding
2. Five-minute open-interest snapshots
3. Mark-price 1m klines
4. Index-price 1m klines
5. Native premium-index 1m klines
6. Binance BTCUSDT spot 1m klines
7. Kraken XBT/USD spot 1h OHLCVT

ETH
8. ETHUSDT perpetual traded-price 1m klines
9. Settled funding
10. Five-minute open-interest snapshots
11. Mark-price 1m klines
12. Index-price 1m klines
13. Native premium-index 1m klines
```

Together with canonical BTC perpetual OHLCV, this is a 14-series inventory.

Frozen coverage and missingness rules include:

- ETH OI is available only from `2021-12-01`.
- ETH OI before that date is null and never enters M3.
- Known pre-archive periods remain null and receive no fabricated regime indicator.
- Missing is null, never zero.
- Price, mark, index, premium, OI, or venue gaps are never interpolated.
- A feature is invalid when a required path or lookback crosses a missing native interval.
- Funding requires a cadence-complete settlement window.
- OI requires the exact five-minute snapshots at both endpoints with no intervening gap.
- A one-hour native-premium mean requires all 60 one-minute closes.
- Return and realized-volatility windows crossing an invalid source interval are null.
- There is no stale-value tolerance, alternate horizon, nearest match, or gap-filling fallback.
- Same-key conflicting rows block publication.

Frozen exclusions include liquidations, options, long/short ratios, taker ratios, order books, altcoins, macro, on-chain data, sentiment, news, and open-ended technical-indicator searches.

## 3. Target

For hourly origin `t`:

```text
r24_t   = log(P[t+24h] / P[t])
sigma_t = sqrt(sum_{j=0}^{23} r[t-j]^2)
Z_t     = abs(r24_t) / sigma_t
Y_t     = 1[Z_t > k]
```

`P[t]` is the completed BTCUSDT perpetual hourly close defined by the timing convention below. The returns in `sigma_t` are causal past hourly BTC returns. A zero or incomplete volatility window is invalid; no epsilon replacement is permitted.

Threshold:

```text
k = empirical Q80(Z_t) on eligible 2020–2021 design origins only
```

An origin enters threshold design only if its complete forward label ends no later than:

```text
2021-12-31 23:59:59.999 UTC
```

No 2022 value may enter threshold design.

### Target questions requiring review

1. Is the volatility-normalized absolute 24-hour move a coherent and sufficiently interpretable primary target?
2. Can dividing by trailing 24-hour realized volatility create unstable labels in very quiet conditions even when zero windows are invalid?
3. Is a design-period Q80 threshold scientifically defensible for the intended event frequency and available effective sample size?
4. Must `k` remain fixed across all outer folds and the 2025 score?
5. Does designing `k` from all eligible 2020–2021 origins conflict with model folds that begin at `2020-09-01`?
6. The protocol does not specify the exact empirical-quantile algorithm. Must a successor version freeze:
   - Order-statistic or interpolation convention.
   - Index calculation.
   - Tie behavior.
   - Decimal precision and rounding.
   - A byte-reproducible expected `k` fixture?

---

# Part II — Temporal integrity

## 4. Point-in-time record contract

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

Hourly cutoff convention:

```text
T             = exact UTC hour boundary
prediction_ts = T + 1 millisecond
P[t]          = completed BTC hourly close at T - 1 millisecond
future close  = completed BTC hourly close at T + 24h - 1 millisecond
```

Nominal source eligibility:

```text
Kline close time C:
  eligibility_ts = C + 1 ms

Settled funding time F:
  eligibility_ts = F + 1 ms

Five-minute OI row timestamped at interval start O:
  eligibility_ts = O + 5 minutes

Kraken hourly row timestamped at interval start K:
  eligibility_ts = K + 1 hour
```

Join rule:

```text
eligibility_ts < prediction_ts
```

All joins are backward as-of joins on `eligibility_ts`. Nearest joins, forward joins, unfinished bars, future revisions, and same-timestamp equality are forbidden.

Archive publication time is treated as ex-post provenance, not as the real-time availability of each observation. Protocol v1 claims nominal historical point-in-time safety, not reconstruction of historical network latency.

## 5. Funding-at-boundary inconsistency requiring explicit review

The frozen funding feature formula is:

```text
funding_24h_sum(T)
  = sum settled rates with T-24h < settlement_ts <= T
```

But the frozen timing rules also state:

```text
funding settled at F = T
eligibility_ts       = T + 1 ms
prediction_ts        = T + 1 ms
required             = eligibility_ts < prediction_ts
same-time equality   = forbidden
```

Therefore, funding settled exactly at `T` appears to be included by the feature formula but excluded by the eligibility rule.

The reviewer must determine whether this is a true semantic contradiction and prescribe one exact correction, such as changing the funding window endpoint, changing the prediction ordering convention, or changing equality treatment. The correction must apply consistently to BTC and ETH funding and must not permit use before actual settlement availability.

## 6. Source-specific availability questions

For each source, determine whether its timestamp and eligibility rule is sufficient and evidence-supported:

- Binance perpetual traded-price klines.
- Binance mark-price klines.
- Binance index-price klines.
- Binance native premium-index klines.
- Binance spot klines.
- Settled BTC and ETH funding.
- Five-minute BTC and ETH OI snapshots.
- Kraken hourly OHLCVT.

Specifically review:

1. Whether archived OI timestamps truly mean interval start.
2. Whether funding timestamps mean calculation, settlement, publication, or another event.
3. Whether every kline source uses close-time semantics consistently.
4. Whether historical revisions can alter a record after nominal eligibility.
5. Whether the one-millisecond convention is internally valid and unambiguous.
6. Whether cross-venue alignment requires a conservative source delay beyond interval close.
7. Whether nominal historical availability without empirical network latency is sufficient for the claim.
8. Whether every state-like feature has a frozen maximum age or complete-window rule that prevents indefinite stale carry-forward.
9. Whether modifying all future source rows after time `t` can be required to leave every feature at or before `t` byte-identical.

---

# Part III — Labels, folds, and dependent inference

## 7. Frozen outer folds

```text
Fold 1
  train: 2020-09-01 through 2021-12-31
  test:  calendar 2022

Fold 2
  train: 2020-09-01 through 2022-12-31
  test:  calendar 2023

Fold 3
  train: 2020-09-01 through 2023-12-31
  test:  calendar 2024
```

Rules:

- Training origins whose 24-hour labels cross a boundary are removed.
- A 24-hour purge is used.
- Train-window z-score standardization is fit only on training rows.
- Random K-fold and shuffled splits are forbidden.
- No 30-day purge is added solely because a causal feature has a 30-day historical lookback.

### Boundary definition requiring review

The phrase “24-hour purge” may be insufficient unless exact inequalities are frozen.

For first test origin `S`, define:

- The exact last eligible training origin.
- Whether a training origin whose target endpoint equals `S` is retained or removed.
- The exact first eligible test origin.
- Whether every label used for fitting is nominally available before the first test prediction.
- The half-open or closed interval conventions used by implementation.

Determine whether a post-test embargo is needed in an anchored expanding-window design.

## 8. Frozen dependence-aware inference

Paired hourly loss differences are evaluated with a moving-block bootstrap:

```text
block length: 168 hours
resamples:    2,000
confidence:   95%
seed:         20260831
resampling:   within calendar year, then pooled
```

The frozen artifacts do not fully specify the algorithm. Determine whether reproducibility requires freezing:

- Circular versus non-circular moving blocks.
- Eligible block-start indices.
- Handling of partial blocks at year-end.
- Number of resampled observations per year.
- Pooling and weighting across years.
- Handling of missing timestamps and candidate-specific gaps.
- Percentile, basic, studentized, or another confidence interval.
- One-sided p-value formula.
- Finite-resample p-value correction.
- Strict versus inclusive threshold comparisons.
- A deterministic synthetic golden fixture.

Also assess:

1. Whether 168 hours is a defensible primary block length for 24-hour overlapping labels and volatility clustering.
2. Whether a preregistered block-length sensitivity check is useful as a non-selective diagnostic.
3. Whether year-stratified resampling followed by pooling supports the intended confidence interval and p-value claims.
4. Whether 2,000 resamples are sufficient for the Holm-adjusted decisions being made.

---

# Part IV — Models and feature families

## 9. Frozen baseline and candidate ladder

```text
B0 — training-only climatology

B1 — logistic model using causal log(RV_1d)

B2 — HAR-style logistic model using
     log(RV_1d), log(RV_7d), log(RV_30d)

M1 — B2
     + BTC funding_24h_sum
     + BTC dlog_oi_24h
     + BTC native_premium_1h_mean

M2 — M1
     + log(BTC perpetual close / Binance BTC spot close)

M3 — M2
     + ETH 1h log return
     + ETH 24h realized volatility
     + ETH funding_24h_sum
     + ETH native-premium 1h mean
     + ETH/BTC relative 24h log return

M3b — M3
      + ETH dlog_oi_24h
      on an identical post-2021-12-01 common sample

M4 — M3
     + Kraken 1h log return
     + Kraken 24h realized volatility
     + Binance-spot minus Kraken 1h return divergence
     + log(Binance BTCUSDT spot / Kraken XBT/USD spot)
```

Under the frozen gate, improvement over B0 alone cannot satisfy the primary M2-versus-B2 claim.

Native Binance premium is the primary futures-dislocation feature. Constructed mark/index and mark/spot measures are diagnostics only. Mark and index series are canonicalized for integrity and diagnostics, not as independent model stages.

The Binance/Kraken level ratio intentionally mixes BTC venue dislocation with possible USD-versus-USDT quote effects; no invented FX conversion is used.

## 10. ETH scientific questions

The question is not whether BTC and ETH are correlated. It is whether ETH information available at time `t` adds out-of-sample BTC skill after BTC volatility, derivatives state, and spot/perpetual dislocation are already present.

Review the frozen M3 block without presuming that more features are better:

1. Is the five-feature ETH block coherent, parsimonious, and sufficient to test the stated incremental-information claim?
2. Does signed ETH 1-hour return have a clear role for an absolute-move BTC target?
3. Does ETH/BTC relative 24-hour return adequately represent cross-asset divergence?
4. Does omitting ETH volume create a material specification defect?
5. Can the linear standardized logistic model already represent useful funding and premium differences from the included BTC and ETH columns, or would explicit differences materially alter regularization and interpretation?
6. Would rolling correlation, beta, volatility ratios, or multiple lag horizons correct a real validity gap, or merely expand the transformation search space?
7. Would preregistered, non-selective sub-block diagnostics materially improve attribution without controlling candidate retention?
8. If sub-block diagnostics are reported, what multiplicity or descriptive-only rule is necessary?
9. Can ETH OI support candidate retention through a valid identical-common-sample design, or is its frozen diagnostic-only role the safer interpretation?

If recommending an ETH change, provide one exact successor-version ladder. Do not provide a feature menu.

## 11. Missingness and candidate-specific estimands

Every paired comparison refits the comparator on the candidate’s exact training rows and scores identical test timestamps.

This protects paired attribution but means each candidate may estimate performance on a different eligible timestamp population.

Determine whether a successor version must require:

- Coverage counts and percentages by year.
- Explicit reasons for row exclusion.
- Coverage by major market regime without using regimes for selection.
- A minimum eligible-coverage threshold.
- A predeclared response when missingness leaves a materially nonrepresentative sample.
- Separate larger-sample baseline reporting that is clearly excluded from the paired incremental claim.

Assess whether complete-case evaluation could favor unusually clean market periods and thereby change the estimand.

---

# Part V — Estimation, development, and selection

## 12. Frozen estimator

Every probability model uses exact-Decimal logistic IRLS:

```text
L2 lambda:             1
intercept:             unpenalized
standardization:       training-window z-score
maximum iterations:    50
convergence tolerance: 0.000000000001
eta clamp:             24
probability clamp:     0.000000000001
solver:                Gaussian elimination with partial pivoting
```

Forbidden:

- Regularization search.
- Model-family search.
- Feature clipping.
- Post-hoc probability calibration.
- Tree models.

Raw logistic probabilities are scored.

### Deterministic estimator questions

Determine whether a uniquely reproducible and fail-closed estimator also requires freezing:

- Decimal context precision and rounding mode.
- Z-score variance denominator.
- Coefficient initialization.
- Exact convergence statistic and norm.
- Behavior at the iteration limit.
- Singular or near-zero pivot handling.
- Constant feature handling.
- Complete or quasi-separation handling.
- Non-convergent calibration-regression handling.
- Golden coefficient and probability fixtures.

No implementation should be permitted to silently omit a failed fit or calibration gate.

## 13. Development-policy question

Protocol v1 is a narrow preregistered execution:

1. Target, features, lambda, estimator, folds, and gates are frozen before 2022–2024 scoring.
2. No regularization, feature, model-family, clipping, or calibration search is allowed.
3. A completed 2022–2024 result cannot be used to alter and rerun Protocol v1.
4. Only a passing candidate may unlock sealed 2025.

Assess whether this design contains a BLOCKER or HIGH scientific defect. In particular:

- Does fixed `lambda = 1` and no calibration make the experiment an arbitrary recipe test rather than a meaningful test of the information families?
- Is the one-shot design a valid confirmatory experiment if its claim is kept narrow?
- Would controlled 2020–2024 development be better treated as a separate successor protocol rather than retrofitted into v1?
- If iterative 2020–2024 development is necessary, what exact nested or rolling algorithm would prevent severe development overfitting, and what claims about 2022–2024 would then be prohibited?

Recommend controlled 2020–2024 development only if necessary to correct a validity problem; otherwise classify it as a separate future protocol option and state Protocol v1’s claim limitation.

## 14. Optional-family and multiplicity procedure

Frozen optional-family policy:

- M2 is the mandatory primary candidate and must pass the full gate versus paired B2.
- ETH is tested first and Kraken second.
- Retention requires:
  - At least 1% pooled relative Brier improvement versus the currently retained model.
  - Unadjusted two-sided paired-bootstrap 95% interval lower bound above zero.
  - One-sided bootstrap p-value passing Holm family-wise alpha 0.05 across two optional-family tests.
  - Improvement in at least two validation years.
  - No year worse than -2% relative Brier skill.
- If ETH is rejected, Kraken is compared against M2.
- A rejected block receives no alternate transformation search.

### Candidate-path ambiguity

The named M4 candidate is `M3 + Kraken`, but the fallback rule requires a candidate equivalent to `M2 + Kraken` when ETH is rejected. No such candidate is named in the frozen ladder.

Review whether a successor version must:

1. Name the `M2 + Kraken` candidate explicitly.
2. Freeze the two Holm hypotheses before outcomes are observed.
3. Freeze each hypothesis’s comparator, test statistic, and p-value construction.
4. Prevent the second hypothesis from changing identity after the ETH result.
5. Define whether optional-family tests use the same or conditional samples.

Also determine whether the protocol must formalize:

- The exact formula for pooled relative Brier improvement.
- The exact yearly relative-improvement formula.
- Strict versus inclusive inequalities.
- Behavior if comparator Brier score is zero.
- Whether using outer-fold outcomes both to retain optional blocks and to evaluate the retained candidate requires nested selection or limits the claim.
- Whether non-selective ETH diagnostics expand the Holm family.
- Whether M2 must pass before optional blocks are considered, or whether that is an unnecessarily restrictive claim chain.

---

# Part VI — Metrics and decision rules

## 15. Frozen 2022–2024 success gate

Primary quantities:

```text
BS(model)         = mean((p-y)^2)
BSS_B2(model)     = 1 - BS(model) / BS(B2)
loss_improvement  = loss_B2 - loss_candidate
probability_bias  = mean(p-y)
```

Diagnostics include log loss, ROC-AUC, PR-AUC, calibration intercept, and calibration slope. AUC cannot pass the protocol.

A candidate may unlock 2025 only if all hold:

1. Pooled `BSS_B2 >= 0.02`.
2. Bootstrap 95% lower bound for `BS_B2 - BS_candidate` is greater than zero.
3. Positive Brier improvement in at least two validation years.
4. No year has `BSS_B2 < -0.02`.
5. Pooled absolute probability bias is at most 0.02.
6. Pooled calibration slope is between 0.8 and 1.2.
7. Yearly absolute probability bias is at most 0.04.

Calibration intercept and slope are diagnostic fits from an unpenalized regression of outcome on `logit(p)` with an intercept. Clamping is allowed only for taking the logarithm and does not modify predictions.

Review:

- Practical meaning and power of the 2% Brier-skill threshold.
- Whether both an effect-size threshold and positive confidence lower bound are appropriate.
- Stability of calibration slope 0.8–1.2 at the effective sample size.
- Fairness of prohibiting calibration while using calibration as a hard gate.
- Whether “two of three years positive and none below -2%” adequately protects against regime concentration.
- Whether yearly results are properly descriptive rather than treated as independent replications.
- What happens when pooled or yearly calibration regression is undefined, separated, or non-convergent.
- Whether PR-AUC should remain diagnostic for an approximately 20% event.

---

# Part VII — Sealed 2025

## 16. Frozen seal rules

Before unlocking, 2025 allows only:

- File inventory.
- Cryptographic hashes.
- Parser compatibility.
- Expected temporal boundaries.
- Mechanical corruption checks.

Forbidden before unlocking:

- Labels.
- Feature-distribution inspection for design decisions.
- Model scores.
- Conditional outcome inspection.
- Protocol adaptation.

On gate pass, the protocol says:

```text
run exactly one frozen 2025 evaluation
```

If it fails:

```text
DID_NOT_REPLICATE
never redesign and retest on 2025
```

## 17. Final-fit procedure is not fully specified

The frozen artifacts do not explicitly define the estimator-fit and sample procedure immediately before 2025 scoring.

Determine whether a successor protocol must freeze:

- How the retained candidate is identified.
- Whether it is refit on all eligible 2020–2024 origins.
- Candidate-specific complete-case training rows.
- Standardization parameters fit only from those rows.
- Treatment of the 24-hour boundary at the end of 2024.
- Convergence and failure handling.
- The paired comparator’s final refit.
- Confirmation that `k`, feature formulas, lambda, and probability treatment remain unchanged.

## 18. The 2025 replication decision is not fully specified

The protocol names `REPLICATED` and `DID_NOT_REPLICATE` outcomes operationally, but the frozen scientific artifact does not provide a complete 2025 pass/fail criterion.

Determine whether a successor version must freeze before unsealing:

- Primary 2025 comparator.
- Primary effect-size threshold.
- 2025 uncertainty procedure.
- Calibration requirements.
- Per-period or subperiod diagnostics.
- Whether the complete 2022–2024 gate is reused unchanged.
- Exact mapping to `REPLICATED` versus `DID_NOT_REPLICATE`.
- Handling of a previously unknown 2025 source defect discovered before versus after outcome access begins.
- The strongest claim supported by one calendar year of successful confirmation.

---

# Required reviewer output

## A. Executive verdict

Choose one:

```text
PROCEED_UNCHANGED
PROCEED_WITH_SUCCESSOR_VERSION
REDESIGN_BEFORE_EXECUTION
```

Explain in no more than ten sentences.

## B. BLOCKER and HIGH findings

For each finding:

```text
ID:
Severity: BLOCKER | HIGH
Protocol area:
Exact problem:
Failure mechanism:
Smallest exact correction:
Must change before: Stage 2 acquisition | Stage 4 feature build | 2022–2024 scoring | 2025 scoring
```

If an area has no BLOCKER or HIGH issue, do not invent one.

MEDIUM findings are optional and capped at five.

## C. Consolidated successor-version change set

Provide one exact, internally consistent change set. Separate:

- Required validity fixes.
- Strongly recommended scientific improvements.
- Optional non-selective diagnostics.
- Ideas to defer beyond this experiment.

Do not provide competing plans.

## D. Explicit decisions

Answer each directly:

1. Is the target and Q80 design valid? What exact quantile convention is required?
2. How must the funding-at-`T` inconsistency be resolved?
3. What exact inequality defines the last eligible training origin before test origin `S`?
4. Is the point-in-time contract sufficient for each source?
5. What complete moving-block bootstrap and p-value algorithm should be frozen?
6. Is the fixed no-search estimator design valid for the narrow Protocol v1 claim?
7. Does M3 require any validity-critical change, and should ETH sub-blocks remain non-selective diagnostics?
8. Can ETH OI ever control candidate retention?
9. What fixed optional-family/Holm hypotheses and named Kraken fallback candidate are required?
10. What deterministic estimator failure behavior must be frozen?
11. What exact final training sample and refit procedure must precede 2025?
12. What exact rule maps the one-time 2025 result to `REPLICATED` or `DID_NOT_REPLICATE`?
13. What are the three most plausible false-positive mechanisms even after these controls?
14. List every reviewed area in which you found no BLOCKER or HIGH defect.

## End of brief

Review only the protocol summarized here. If a necessary fact is absent, identify it as missing rather than assuming a favorable implementation.
