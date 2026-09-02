# Quantara Protocol v1.1 — Successor Scientific Protocol Specification

```text
Protocol id:            quantara-protocol-v1_1
Protocol status:        FROZEN_BEFORE_2022_2024_SCORING
Draft date:             2026-09-01
Frozen date:            2026-09-02 (`frozen_date`)
Supersedes:             quantara-protocol-v1
Predecessor hash:       91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a
Authorizing audit:      docs/superpowers/reviews/2026-09-01-protocol-v1-three-reviewer-deep-audit.md
Frozen semantic hash:   12dd3445365fdaa9e35cdcf93cae3e79a88b6b4d72d3d703b921359d1e917a9b
Scoring permission:     AUTHORIZED_2022_2024_AFTER_THRESHOLD_FIXTURE_2025_REMAINS_SEALED
```

This is a complete standalone successor to Protocol v1. 2022–2024 scoring is
authorized only after the synthetic quantile fixture and frozen `k` fixture/hash are
committed; 2025 remains sealed until the seven-criterion success gate passes. The
machine-readable counterpart is
`configs/protocols/quantara-protocol-v1_1.yaml`. This packet repairs version,
lineage, prediction ordering, quantile, and purge semantics only. The remaining
accepted change-set items are explicitly deferred in §11.

## 1. Research question

Can pre-registered BTC derivatives, spot/perpetual divergence, ETH cross-market
state, and one independent BTC venue improve probability forecasts of unusually
large BTCUSDT 24-hour moves beyond a strong causal volatility-persistence baseline?

## 2. State and inventory boundary

### 2.1 Already canonical

Binance USD-M BTCUSDT perpetual traded-price OHLCV, 2020–2024, at 1m/1h/1d. This
lane is immutable input. Protocol packets may read it but may not alter its
published identities, pointers, descriptors, parser identity, manifests, quality
evidence, or canonical bytes.

### 2.2 Frozen remaining inventory — exactly 13 source series

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

Together with the already-canonical BTC perpetual price lane this is the frozen
14-series Protocol-v1.1 inventory inherited from Protocol v1.

### 2.3 Frozen exclusions

Do not add liquidations, options, long/short ratios, taker ratios, altcoins, order
books, macro, on-chain, sentiment, news, or technical-indicator searches.
Incidental columns in the Binance metrics archive may be retained in the immutable
raw object but are not canonical Protocol-v1.1 series and must not enter any feature
table.

The older `docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md`
is superseded for Protocol v1.1. In particular, its top-trader and taker-ratio
scope, guessed completeness rules, and combined metrics feature direction are not
authorized here.

## 3. Target

For hourly origin `t`, using canonical BTCUSDT perpetual traded closes:

```text
r24_t  = log(P[t+24h] / P[t])
sigma_t = sqrt(sum_{j=0}^{23} r[t-j]^2)
Z_t    = abs(r24_t) / sigma_t
Z_(1) <= ... <= Z_(N)
j       = ceil(0.80 * N)
k       = Z_(j)
Y_t     = 1[Z_t > k]
```

Compute `Z` under the existing 50-digit `ROUND_HALF_EVEN` Decimal context. Do not
interpolate. Do not round `k` to 8 decimals. Preserve the canonical full Decimal
string for `k`. Ties need no timestamp tie-break because tied values are numerically
equal.

A synthetic quantile fixture and an actual frozen `k` fixture/hash are required
before any 2022–2024 scoring. That requirement is `DEFERRED` in this packet: do not
generate `k`, and do not read design data. Once frozen, `k` stays fixed through every
fold and through sealed 2025.

An origin enters the `k` design set only when its complete forward label ends no
later than 2021-12-31 23:59:59.999 UTC. No 2022 value may enter threshold design.
Type 7 and Type 8 are defensible alternatives but are not scientifically required;
nearest-rank is chosen because it matches the generalized inverse empirical-CDF
meaning and introduces no interpolated threshold.

## 4. Baselines and frozen model ladder (YAML key: `ladder_widths`)

```text
B0 — training-only climatology
B1 — logistic model using causal log(RV_1d)
B2 — HAR-style logistic model using log(RV_1d), log(RV_7d), log(RV_30d)
M1 — B2 + BTC funding_24h_sum + BTC dlog_oi_24h + BTC native_premium_1h_mean
M2 — M1 + log(BTC perpetual close / Binance BTC spot close)
M2K — M2 + frozen four-column Kraken block
M3 — M2 + frozen ETH family, excluding ETH OI
M3b — M3 + ETH dlog_oi_24h on the identical post-2021-12-01 common sample
M4 — M3 + frozen Kraken cross-venue family
```

| Model | Frozen width |
| --- | ---: |
| B1 | 1 |
| B2 | 3 |
| M1 | 6 |
| M2 | 7 |
| M2K | 11 |
| M3 | 12 |
| M3b | 13 |
| M4 | 16 |

`RV_H = sqrt(sum of squared eligible hourly log returns over H hours)` for
H = 24, 168, 720. A zero or incomplete window is invalid; no epsilon replacement
is permitted.

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
- `log(Binance BTCUSDT spot close / Kraken XBT/USD close)` with no invented
  USD/USDT FX conversion. The feature is explicitly a cross-venue, cross-quote
  dislocation and may include USDT-versus-USD effects.

M2K adds the same frozen four-column Kraken block to M2: `kraken_ret_1h`,
`kraken_rv_24h`, `binance_kraken_ret_divergence_1h`, and
`binance_kraken_cross_quote_log_ratio`. It adds no feature and performs no
transformation search beyond that already frozen block.

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

Every formula requires its full endpoint/path window. Funding requires a
cadence-complete settlement window; OI requires the exact five-minute snapshots
ending at both endpoints and no intervening gap; 1m premium means require all 60
minutes; return/RV windows crossing any invalid source interval are null. There is
no stale-value tolerance, interpolation, nearest timestamp, or alternate horizon.

Native Binance premium is the pre-registered primary futures-dislocation feature.
Constructed `mark/index - 1` and `mark/spot - 1` are diagnostics only and never enter
M1-M4. Mark and index are canonicalized because they verify source integrity and
support diagnostics, not because they earn independent model stages.

Protocol v1.1 binds every probability-model fit (YAML key: `estimator_binding`) to
the committed exact-Decimal
implementation `src/quantara/training_metrics_logistic.py`, entry point
`fit_logistic_irls`. It does not define or permit a second solver. The bound
contract is:

```text
Decimal precision:         50
rounding:                  ROUND_HALF_EVEN
storage quantum:           0.000000000000000001
standardization:           train-window z-score, population denominator n
initial coefficients:      all zero
model L2 lambda:           1
intercept:                 unpenalized
convergence:               every abs(beta_new - beta_old) < 0.000000000001
maximum updates:           50
linear solver:             Gaussian elimination with partial pivoting
pivot failure:             exact-zero pivot, fail closed
constant train feature:    exact-zero train std, fail closed
non-convergence:           fail closed
binary float inputs:       forbidden
eta clamp:                 24
probability clamp:         0.000000000001
```

Every training outcome supplied to a fit must contain both classes. The C3 binding
checks this before calling `fit_logistic_irls`; a single-class window fails the
affected candidate comparison closed. The frozen `fit_failure_propagation` rule is
that any fit failure fails the affected candidate comparison and never silently drops
a fold, year, or candidate from pooling. The
seven named fail-closed causes are exactly:

```text
single_class_training_outcome
constant_train_feature
zero_pivot
non_convergence
binary_float_input
calibration_single_class_outcome
calibration_degenerate_logit
```

The eta clamp at 24 is a recorded diagnostic, not a model-fit failure. Every
positive `eta_clamp_count` is reported alongside the fit result. For calibration
only, a positive count fails the calibration gate as
`calibration_degenerate_logit`, because a clamped calibration linear predictor
means the reported slope is not the fitted slope over the observed logit range.
There is no coefficient-magnitude separation threshold.

There is no regularization search, no post-hoc probability calibration, no feature
clipping, no tree model, and no model family search in Protocol v1.1. Calibration
is evaluated on raw logistic probabilities.

For every paired candidate comparison, refit the comparator on exactly the same
training rows and score exactly the same test timestamps as the candidate. A larger
baseline sample may be reported separately but cannot be used for the paired
incremental claim.

## 5. Point-in-time contract (YAML key: `point_in_time`)

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

The repaired ordering is exactly:

```text
boundary event time:       F = T
nominal eligibility:       T + 1 ms
prediction time:           T + 2 ms
join:                      eligibility_ts < prediction_ts
funding feature window:    T-24h < settlement_ts <= T
```

The Protocol-v1 defect was that `prediction_ts = T + 1 ms` and funding eligibility
`F + 1 ms` made a settlement exactly at `F = T` compare as
`T + 1 ms < T + 1 ms`, which is false. The feature formula included the settlement
while the point-in-time join excluded it. Protocol v1.1 repairs that contradiction
by moving the prediction to `T + 2 ms`.

All other eligibility rules keep their Protocol-v1 form and are measured against
`prediction_ts = T + 2 ms`:

- For a kline with source close `C`, `eligibility_ts = C + 1 ms`.
- For settled funding with settlement `F`, `eligibility_ts = F + 1 ms`.
- For five-minute OI with provider timestamp `O` and role
  `UNRESOLVED_CONSERVATIVE`, `eligibility_ts = O + 5 minutes`.
- For Kraken hourly OHLCVT with interval-start `K`,
  `eligibility_ts = K + 1 hour`.

### Open-interest provider timestamp role (YAML key: `oi_timestamp_resolution`)

The historical metrics archive preserves the provider field `create_time` as `O`.
Its archive-specific meaning is unresolved: A10 superseded A2's earlier open-bar
claim, and the categorical claim that it denotes a period end is also rejected as
unproven. The protocol therefore does not relabel `O` as either
`interval_open_ts` or `interval_close_ts`, and no semantic claim is permitted while
the role remains `UNRESOLVED_CONSERVATIVE`.

The unchanged arithmetic is safe under both readings. Under the start reading, a
row stamped `O` covers `[O, O + 5 minutes)` and becomes complete exactly at
`O + 5 minutes`; under the end reading it is already complete at `O`, so the same
rule is five minutes conservative. With
`eligibility_ts < prediction_ts = T + 2 ms`, the latest eligible row at an hourly
boundary is consequently `O = T - 5 minutes`.

Before any OI canonicalization, an archive-specific `create_time` semantics check
must be completed and its measured or cited evidence written into the source
contract. Until then every result report using an OI feature must disclose this
uncertainty and conservative treatment. Kraken is deliberately asymmetric: A9
documents its candle timestamps as starts, so its role is
`DOCUMENTED_INTERVAL_START` and its `K + 1 hour` eligibility remains frozen.

`P[t]` remains the BTC perpetual 1h bar close at `T - 1 ms`, and its future
endpoint remains the bar close at `T + 24h - 1 ms`. The millisecond ticks are
logical ordering conventions over already-completed data, not claims about exchange
network latency.

The added tick changes same-boundary inclusion for funding only. Completed klines,
five-minute OI, and Kraken hourly candles are already eligible no later than `T`
under the contracts above, so their inclusion is unchanged. This universal
convention change must be boundary-tested per source.

Production use still requires measured live publication/ingestion latency. If live
latency exceeds the decision schedule, same-boundary funding must shift to the next
live decision.

Two alternatives are rejected:

- `eligibility_ts = F` is coherent but removes the frozen after-settlement ordering
  tick.
- Narrowing the funding window to `< T` is causal but delays boundary settlements
  one hourly decision, changing the intended `(T-24h,T]` feature.

All joins remain backward as-of joins. Nearest joins, forward joins, unfinished bars,
future revisions, and same-timestamp equality are forbidden. Archive publication
time is ex-post provenance, not the real-time availability of observations.
Protocol v1.1 claims nominal historical point-in-time safety, not reconstruction of
historical network latency. This limitation must appear in every result report.

## 6. Missing and duplicate policy

- Missing is null, never zero.
- No price, mark, index, premium, OI, or venue gap is interpolated.
- A feature is invalid when a required lookback crosses a missing native interval.
- A label is invalid when its required BTC price endpoints/path are unavailable.
- Known pre-archive periods remain null and receive no fabricated regime flag.
- Exact duplicate source rows may be deterministically deduplicated only after byte
  comparison, with source-row count, distinct-row count, duplicate count, and
  duplicate hashes preserved.
- Same-key conflicting rows block publication.
- ETH OI before 2021-12-01 is null and never enters M3.

## 7. Validation and gate

The three outer folds are unchanged from Protocol v1:

```text
Fold 1: train 2020-09-01..2021-12-31; test 2022
Fold 2: train 2020-09-01..2022-12-31; test 2023
Fold 3: train 2020-09-01..2023-12-31; test 2024
```

The exact purge contract is:

```text
training origin O is eligible iff O + 24h <= S
last eligible training origin = S - 24h
first test origin = S
```

Verified boundary examples:

```text
Fold 1 S:                  2022-01-01 00:00 UTC
last training origin:      2021-12-31 00:00 UTC
last required label close: 2021-12-31 23:59:59.999 UTC

2025 S:                    2025-01-01 00:00 UTC
last training origin:      2024-12-31 00:00 UTC
last required label close: 2024-12-31 23:59:59.999 UTC
```

### Final pre-2025 refit (YAML key: `final_refit`)

Only after the frozen 2022–2024 gate passes, refit the candidate retained by the C3
retention graph and paired comparator B2 on the identical origin set: the retained
candidate's point-in-time complete-case origins. B2 receives no larger sample even
though it uses fewer features. The nominal boundary is:

```text
refit train start:          2020-09-01 00:00:00.000 UTC
origin rule:                O + 24h <= 2025-01-01 00:00:00.000 UTC
last eligible origin:       2024-12-31 00:00:00.000 UTC
last required label close:  2024-12-31 23:59:59.999 UTC
nominal origin count:       37969
excluded tail count:        23
excluded tail range:        2024-12-31 01:00 .. 2024-12-31 23:00 UTC
```

`37969` is the nominal count of hourly origins satisfying the purge inequality,
not the realized eligible complete-case count. The latter is smaller and remains
unknown until execution. Recompute the z-score means and population standard
deviations on exactly those final refit rows; no fold standardization carries over.
Target `k`, feature set, `ridge_lambda`, `ETA_CLAMP`, `MU_CLAMP`, maximum iterations,
estimator entry point, and probability treatment remain unchanged. In particular,
`k` stays the value frozen from the pre-2022 design set and is never recomputed.

A failure emits terminal state `FINAL_FIT_FAILURE` under exactly the seven frozen
C3 `fail_closed_causes`. It permits no tuning, feature change, lambda change,
different estimator, or retry on different rows; it forbids the 2025 evaluation
and cannot be reported as `DID_NOT_REPLICATE` because no 2025 score exists. It never
drops a fold, year, or candidate from pooling. These three terminal labels are the
closed `outcome_states` vocabulary.

No post-test embargo is required for this anchored expanding-window design. A
`2024-12-30 23:00` cutoff is wrong by one hour and is rejected.

Apply only the frozen train-window z-score and fixed regularization described above.
No clipping or post-hoc calibration is allowed. Never use random K-fold.

Primary metric: pooled prediction-level Brier score and Brier skill versus B2:

```text
BS(model) = mean((p-y)^2)
BSS_B2(model) = 1 - BS(model) / BS(B2)
loss_improvement_i = loss_B2_i - loss_model_i
probability_bias = mean(p-y)
```

Calibration is an unpenalized two-parameter Decimal logistic fit of `y` on
`x = logit(p)` with an intercept, computed through the same committed
`fit_logistic_irls` implementation with `lambda = 0`. Before taking the logarithm,
`clamp_mu` mandatorily clamps every probability to
`[0.000000000001, 0.999999999999]`:

```text
x_i                   = ln(p_i / (1 - p_i))
calibration_slope     = beta_z / sd_x
calibration_intercept = beta_0 - beta_z * mu_x / sd_x
```

Here `beta_0` and `beta_z` are the fitted intercept and standardized-logit
coefficient, and `mu_x` and `sd_x` are the train-window mean and population
standard deviation returned by the bound solver. The success-gate band
`[0.8, 1.2]` applies to the back-transformed raw-logit `calibration_slope`, never
to `beta_z`.

Calibration fails closed on: a single-class calibration outcome; zero-variance
`logit(p)`, which surfaces as exact-zero standard deviation or zero pivot; an
undefined logit, which is reachable only if the mandatory clamp is bypassed; a
singular solve, which surfaces as zero pivot; separation, identified by positive
`eta_clamp_count`; or non-convergence within 50 updates. Calibration is a diagnostic
of predictions. These calculations do not alter predictions, refit a candidate, or
enter the pooled Brier estimand.

### Frozen Protocol-v1.1 B4 bootstrap inference

This procedure **supersedes the Protocol-v1 inference text**. For each ordered pair
`(candidate, comparator)`, form the hourly paired Brier-loss improvement

```text
d_t = loss_comparator,t - loss_candidate,t
```

so positive values favour the candidate. The estimand is the pooled hourly mean of
`d_t`, not a mean of per-year means.

Build the complete nominal hourly UTC grid separately for every required calendar
year. Candidate and comparator use identical timestamps. Store `d_t` on paired-valid
hours and `null` everywhere else; never fill a missing loss value. Derive the nominal
hour count `H_y` with UTC `datetime` arithmetic. The verified calendar geometry is:

```text
2020 -> 8784    2021 -> 8760    2022 -> 8760
2023 -> 8760    2024 -> 8784    2025 -> 8760
```

Use non-circular moving blocks of `L = 168` consecutive clock hours, not 168 valid
observations. Blocks retain their observed null pattern.

```text
eligible block starts: 0 ... H_y - L        (count = H_y - L + 1)
blocks drawn per year: n_blocks_y = ceil(H_y / L)
```

For `L = 168`, every listed year draws 53 blocks; eligible-start counts are 8,593
when `H_y = 8760` and 8,617 when `H_y = 8784`. Draw starts with replacement,
concatenate the blocks including nulls, and truncate to exactly `H_y` clock-hour
positions. Because `53 * 168 = 8904`, consume only the first
`min(L, remaining)` positions of the final block. No block wraps across a year.

Each year is resampled separately and then pooled by the resampled paired-valid
count:

```text
D* = (sum_y sum over non-null resampled positions d*_(y,i))
     / (sum_y n*_valid,y)

D_obs = (sum_y sum over non-null observed positions d_(y,t))
        / (sum_y n_valid,y)
```

Pooling by year count or nominal-hour count is forbidden.

Protocol v1.1 freezes `B = 20000` resamples, superseding Protocol v1's 2,000. This
increase is a disclosed successor-version design change and inferential
strengthening, not completion of an omitted implementation detail. At the smallest
first-step Holm threshold across the three-test family, with
`p = 0.05/3` and `z = 1.96`, the normal-approximation two-sided 95% Monte Carlo
half-width `z * sqrt(p(1-p)/B)` is:

```text
B =  2000  ->  0.005610684252190438
B = 20000  ->  0.001774254146896035
```

A half-width no greater than `0.002` requires
`B >= 15739.888888888888888888888888888888888888888888889`, so at least `15740`
resamples. `20000` is the frozen round-number choice above that bound. These values
are reproduced with Decimal arithmetic, never floats.

The frozen PRNG is SplitMix64 with exact unsigned 64-bit arithmetic:

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

`random.Random` is forbidden for this bootstrap. The distinct frozen diagnostic
bootstraps retain their own preregistered RNG contracts unchanged. Bounded draws use
rejection sampling, never bare modulo:

```text
below(bound):
    limit = 2**64 - (2**64 mod bound)
    loop:
        x = next_u64()
        if x < limit: return x mod bound
```

Use one independent stream per `(comparison_id, year)`:

```text
payload = "quantara-protocol-v1_1|bootstrap-b4|" + comparison_id + "|" + str(year)
seed    = int.from_bytes(sha256(payload.encode("utf-8")).digest()[:8], "big")
```

The separator, UTF-8 encoding, leading eight digest bytes, and big-endian conversion
are frozen. `comparison_id` is an opaque caller-supplied ASCII label; C2 does not
define the comparison family. Within each replicate, draw in ascending year order
and then block-index order.

No floats may enter the statistic path. Each `d_t` is either an integer scaled by
the frozen `1e-18` storage quantum or a Decimal exactly representable at that
quantum. Reject all other inputs. Use unbounded Python integers for sums and
`fractions.Fraction` for `D*`, `D_obs`, interval bounds, p-values, and comparisons.
Only final reporting quantizes to 18 decimal places using `ROUND_HALF_EVEN`.

The two-sided 95% percentile interval is the nearest-rank interval over raw-bootstrap
pooled means:

```text
sort the B replicate means ascending using exact Fraction comparison
j(q) = ceil(q * B)
lower = sorted[j(0.025) - 1]     # rank 500 at B = 20000
upper = sorted[j(0.975) - 1]     # rank 19500 at B = 20000
```

Do not interpolate. The one-sided p-value uses a null-centred series:

```text
d0_t = d_t - D_obs                         # paired-valid hours; nulls stay null
p    = (1 + count(D0*_b >= D_obs)) / (B + 1)
```

Apply the identical streams and block starts to the centred series. Exact pooling
gives the verified identity

```text
D0*_b = D*_b - D_obs
count(D0*_b >= D_obs) = count(D*_b >= 2 * D_obs)
```

Gemini's raw-bootstrap count at or below zero is rejected because it does not specify
an adequate null. Claude's "favorable resamples" formula is rejected because its
direction is ambiguous.

Inference fails closed for the comparison, returning no partial statistic, if any
observed required year has fewer than 168 paired-valid observations or if any
replicate has no paired-valid observation in any one required year. The named error
records the offending year and, for a replicate failure, its replicate index. A
positive denominator pooled from other years does not override the per-year failure.

The year-stratified 168-clock-hour moving-block procedure is the explicit dependence
correction for overlapping 24-hour labels at hourly origins. Consecutive origins are
not treated as IID: the blocks preserve serial dependence in the paired loss
differential while the pooled hourly mean remains the estimand. Non-overlapping
24-hour origin subsampling is rejected for the primary test because it discards
information and makes the result depend on an arbitrary hourly phase. It may appear
only as a frozen diagnostic in a separately preregistered successor protocol.

The frozen candidate may unlock 2025 only if all hold:

1. Pooled `BSS_B2 >= 0.02`.
2. Bootstrap 95% lower bound for `BS_B2 - BS_candidate` is greater than zero.
3. Positive Brier improvement in at least two validation years.
4. No year has `BSS_B2 < -0.02`.
5. Pooled absolute probability bias is at most 0.02.
6. Pooled calibration slope is between 0.8 and 1.2.
7. Yearly absolute probability bias is at most 0.04.

Log loss, ROC-AUC, PR-AUC, calibration bias/intercept, and calibration slope are
diagnostics. AUC cannot pass the gate.

M1 and M2 are reported as the frozen BTC core ladder; M2 is the mandatory primary
candidate. M2 must pass the complete gate versus paired B2 before 2025 can unlock.

The `optional_family_retention` family has exactly three fixed hypotheses, all
computed before any
retention decision:

```text
H_ETH:   M3  vs M2   comparison_id "H_ETH|M3_vs_M2"
H_K_M2:  M2K vs M2   comparison_id "H_K_M2|M2K_vs_M2"
H_K_M3:  M4  vs M3   comparison_id "H_K_M3|M4_vs_M3"
```

Each uses the frozen C2 bootstrap and its `comparison_id` as the stream-derivation
input. All three p-values are computed even when the realized retention path can
use only two of them. An unused branch remains multiplicity-controlled but has no
retention authority on that path.

Ordinary step-down Holm controls the family-wise alpha `1/20` across all three.
Sort the observed one-sided bootstrap p-values ascending and assign thresholds by
sorted rank, never by model name:

```text
p_(1) <= 1/60
p_(2) <= 1/40
p_(3) <= 1/20
```

Reject in order while the ranked p-value is at most its exact rational threshold;
stop at the first failure and accept every remaining null. Exact
`fractions.Fraction` comparisons are mandatory. Ties follow the frozen hypothesis
order `[H_ETH, H_K_M2, H_K_M3]`. This three-test family is a disclosed
successor-version correction of the draft's two-test family.

At `B = 20000`, the minimum attainable p-value `1/20001` clears `1/60`. The largest
exceedance count that clears the first step is 332:
`p(332) = 333/20001 = 111/6667 <= 1/60`, while
`p(333) = 334/20001 > 1/60`.

Each hypothesis passes its retention gate only when all five conditions hold:

1. Pooled relative Brier improvement versus the currently retained model is at
   least `0.01`.
2. The unadjusted two-sided 95% paired-bootstrap CI lower bound is greater than
   zero.
3. Its one-sided bootstrap p-value passes ordinary Holm across the three-test
   family.
4. At least two validation years improve.
5. No validation year is worse than `-0.02`.

The retention graph is fixed:

```text
if H_ETH passes its gate:
    retain M3
    retain M4 instead only if H_K_M3 also passes its gate
else:
    retain M2
    retain M2K instead only if H_K_M2 also passes its gate
```

If ETH is rejected, compare Kraken against M2, not against an ETH-containing model.
A rejected block receives no alternative transformation search. M3b/ETH OI is a
secondary diagnostic on the identical post-2021-12-01 common sample and can never
alter the retained candidate. The retained candidate must still pass the complete
seven-criterion `success_gate` versus paired B2 before 2025 unlocks.

Every optional-block result computed on 2022–2024 is classified
`selection_evidence`, not independent replication, because the same validation
data choose among the candidates and therefore condition the improvement estimate
on that selection. The only independent replication source is the sealed 2025
evaluation. Any retained optional-block claim must say
"selected on 2022–2024 development evidence". The preregistered mandatory primary
candidate M2 is unaffected and its 2022–2024 gate keeps its existing status.

### Coverage and claim scope

Every candidate in the frozen ladder and every optional-family hypothesis must
report coverage for every scored period, both by year and pooled. Each report
contains `candidate_eligible_rows`, `candidate_eligible_percentage`,
`exclusion_reasons`, and `longest_missing_run`. Coverage is computed on the paired
sample actually scored, never on a larger comparator sample, and claims apply only
to candidate-complete timestamps. The pooled percentage is computed from pooled
eligible and nominal counts rather than by averaging yearly percentages.

The `exclusion_reason_vocabulary` is closed and ordered:

1. `missing_native_interval`
2. `incomplete_feature_window`
3. `funding_cadence_incomplete`
4. `oi_snapshot_gap`
5. `invalid_label_endpoint`
6. `buffer_bar_missing`
7. `pre_archive_period`
8. `eth_oi_pre_2021_12_01`
9. `same_key_conflict`

Each excluded row receives exactly one reason: the first applicable member in that
order. Unknown reasons fail closed, and reason counts must equal the total number
of ineligible nominal-grid positions. These reasons trace only to the already
frozen missing/duplicate, feature-window, target-buffer, and ETH-OI clauses; they
introduce no new exclusion physics.

`longest_missing_run` is the greatest number of consecutive nominal hourly origin
positions that are not candidate-eligible because they are missing, invalid, or
excluded for any vocabulary reason. It is `0` when every position is eligible.
Runs never span a year boundary; the pooled report is the maximum of the per-year
runs. The value is diagnostic only and changes neither eligibility, pooling
weights, nor any gate outcome.

There is no minimum coverage threshold by design. The audit rejected the arbitrary
98 percent cutoff as unsupported. Any future threshold requires separate
justification and preregistration and cannot be presented as a Protocol-v1 or
Protocol-v1.1 correction. The existing minimum of 168 paired-valid observations
per required year remains the frozen B4 fail-closed inference rule, not a newly
introduced coverage pass threshold.

## 8. Sealed 2025

Before the final gate, 2025 may be checked only for file inventory, cryptographic
hashes, parser compatibility, expected boundaries, and mechanical corruption.
Forbidden: labels, feature distributions, model scores, conditional outcome
inspection, or protocol adaptation. If the gate passes, run exactly one frozen 2025
evaluation. Failure is reported as `DID_NOT_REPLICATE`; never redesign and retest on
2025.

### 2026 target-only endpoint buffer (YAML key: `target_endpoint_buffer_2026`)

The endpoint buffer supplies 24-hour label endpoints for the 23 calendar-2025
origins from `2025-12-31 01:00:00.000 UTC` through
`2025-12-31 23:00:00.000 UTC`. It is `SEALED` under the same allowed pre-gate checks
and forbidden operations stated above. Its permitted series set has exactly one
member: BTCUSDT perpetual traded-price klines, with role `target_only`. No 2026
feature origin is scored, and no 2026 funding, OI, mark, index, native premium,
Binance spot, Kraken, or ETH series is acquired, parsed, or joined.

The exact permitted geometry is:

```text
calendar-2025 hourly origins supported: 8760
buffer-dependent origins:              23
required 1h bars:                       23
first 1h open:                          2026-01-01 00:00:00.000 UTC
last 1h open:                           2026-01-01 22:00:00.000 UTC
first 1h close:                         2026-01-01 00:59:59.999 UTC
last 1h close:                          2026-01-01 22:59:59.999 UTC
required 1m rows:                       1380
first 1m open:                          2026-01-01 00:00:00.000 UTC
last 1m open:                           2026-01-01 22:59:00.000 UTC
buffer end inclusive epoch-ms:          1767308399999
refused 1h open epoch-ms:               1767308400000
```

Target-only status is derived rather than promised. Since
`prediction_ts = T + 2 ms` and the join is strict, every eligible feature row for a
2025 origin has `eligibility_ts <= T + 1 ms`; no 2026 row can therefore enter a
2025 feature vector.

After parsing and before aggregation, discard every 1m row whose open is outside
`[2026-01-01 00:00:00.000, 2026-01-01 22:59:00.000] UTC` inclusive. Count and report
discarded rows and never use them. Derive the 23 hourly bars with the frozen
`multi_timeframe_aggregation`: every bar requires 60 contiguous complete minutes,
has `close_time_ms = open + 3600000 - 1`, and has
`nominal_available_ms = open + 3600000`. `IncompleteGroup` is a hard failure; no
padding, interpolation, or short bar is permitted. Any 1h bar opening at or after
`2026-01-01 23:00:00.000 UTC` must be refused. The buffer cannot widen for
convenience. If a required bar is missing, the affected label is invalid and its
origin is excluded as incomplete; no shorter horizon, nearest bar, or 1d bar may
replace it.

### One-year 2025 replication gate (YAML key: `replication_gate_2025`)

Compare the complete retained candidate with paired B2 on all point-in-time
complete-case eligible calendar-2025 origins. The outcome is `REPLICATED` if and
only if all five conditions hold:

```text
1. pooled BSS_B2(candidate) >= 0.02
2. two-sided 95% bootstrap CI lower bound for (BS_B2 - BS_candidate) > 0
3. abs(mean(p - y)) <= 0.02
4. calibration slope is within the frozen C3 helper default band
5. the calibration regression is defined and converges
```

Otherwise the single permitted evaluation returns `DID_NOT_REPLICATE`; there is no
redesign, rescore, or second look. The multi-year criterion requiring at least two
improving years is unattainable in one year and is dropped. The multi-year worst
year `-0.02` condition is implied by criterion 1, and the yearly `0.04` bias
condition is implied by criterion 3, so neither is restated. This reduction rejects
Gemini's weaker `1.5% / 0.03 / 0.75–1.25` gate, GPT's `0.04` one-year bias bound,
and Claude's arithmetically impossible literal reuse of all seven multi-year
conditions.

Inference reuses the frozen C2 bootstrap unchanged: `B = 20000`, `L = 168`
non-circular clock hours, null-centred p-value, nearest-rank percentile interval,
and fail-closed behaviour below 168 paired-valid observations. The single-year
geometry is:

```text
H_2025:                       8760
n_blocks = ceil(H/L):         53
concatenated hours:           8904
eligible block starts:        0 .. 8592
distinct eligible starts:     8593
CI lower rank at B = 20000:   500
CI upper rank at B = 20000:   19500
```

The comparison identifiers are `REPLICATION_2025|M2_vs_B2`,
`REPLICATION_2025|M2K_vs_B2`, `REPLICATION_2025|M3_vs_B2`, and
`REPLICATION_2025|M4_vs_B2`; their 2025 streams are derived by the frozen C2 rule.
Calibration reuses the frozen C3 Decimal fit, mandatory clamp, back-transform,
raw-logit slope band, and six failure conditions. It uses `lambda = 0`, clamps
probabilities to `[0.000000000001, 0.999999999999]` before the logarithm, and
reports `slope = beta_z / sd_x` and
`intercept = beta_0 - beta_z * mu_x / sd_x`. The band is read from
`estimator_c3.calibration_slope_passes` defaults and applies to the raw-logit slope,
never `beta_z`; criterion 5 passes only when none of the six frozen calibration
failure conditions occurs. No new inference or tolerance is introduced.

`REPLICATED` means only that the complete retained frozen model replicated
aggregate probability-forecast improvement versus paired B2 in calendar 2025. It
does not establish replication of an individual ETH or Kraken feature. A block
claim requires its own frozen parent comparison to pass the same five criteria;
the component chain is scored once as claim-specific diagnostics. Report eligible
row count and percentage, exclusion reasons, and the longest missing run. There is
no minimum coverage pass threshold by design, and the result applies only to
candidate-complete timestamps. `FINAL_FIT_FAILURE` remains a distinct terminal
state and is never conflated with `DID_NOT_REPLICATE`.

## 9. Acquisition audit references (A7–A10)

Protocol v1.1 inherits Protocol v1's completed A1–A10 acquisition-audit bindings and
the hash basis `utf8_text_normalized_to_lf_before_sha256`. The A7–A10 paths are:

- `docs/superpowers/plans/2026-08-31-a7-ethusdt-perpetual.md`
- `temp/audit_a7_a8/a7_ethusdt_probe_v1.json`
- `docs/superpowers/plans/2026-08-31-a8-btcusdt-spot.md`
- `temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json`
- `docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md`
- `temp/audit_a9_kraken/a9_kraken_range_probe_v1.json`
- `docs/superpowers/plans/2026-08-31-a10-live-acquisition-consolidation.md`
- `temp/audit_a10_corrections/a3a4_reprobe_v2.json`

Their eight predecessor digests are now recorded in `audit_references` under the
declared normalized-LF hash basis and bound by the C5 synchronized fixture and semantic
freeze. Earlier A1–A6 per-file bindings remain inherited subject to the A10 correction
register's interpretation.

## 10. Protocol lineage and intentional supersession

An earlier Quantara recommendation dated 2026-08-24 proposed a materially different
MVP: BTCUSDT perpetual decisions every completed 15-minute candle, a fixed one-hour
executable immediate-entry policy, regularized logistic regression or simple return
regression as the primary model, LightGBM as a designated secondary model, and both
predictive and after-cost economic metrics.

Protocol v1 intentionally superseded that earlier recommendation. It changed the
estimand from an executable directional one-hour policy to the probability of an
unusually large undirected 24-hour BTC move, changed cadence from 15 minutes to
hourly, removed the trading-policy/PnL layer, and froze an exact-Decimal logistic
ladder. Protocol v1.1 inherits that intentional supersession.

LightGBM was therefore an earlier recommendation, not an omitted Protocol-v1
candidate. Reintroducing LightGBM, XGBoost, return regression, directional actions,
or economic gates requires a separately preregistered successor experiment and may
never be presented as a Protocol-v1 or Protocol-v1.1 correction.

## 11. Deferred change-set items (YAML key: `deferred_change_set`)

| Item | Status | Owning packet | Deferred scope |
| --- | --- | --- | --- |
| Bootstrap and inference | `IMPLEMENTED` | C2 | Packet C2 freezes the complete non-circular year-stratified 168-clock-hour moving-block bootstrap, null-centred p-value, nearest-rank percentile CI, exact SplitMix64 streams, 20,000 resamples, fail-closed rules, and synthetic golden fixtures. |
| Estimator and optional-family contract | `IMPLEMENTED` | C3 | Packet C3 binds the committed exact-Decimal IRLS contract, both-class and calibration-failure rules, `M2K` plus the three fixed optional hypotheses under ordinary Holm across all three, and labels optional-block 2022–2024 results as selection evidence rather than independent replication. |
| Timestamp, refit, buffer, and replication contract | `IMPLEMENTED` | C4 | Archive-specific OI timestamp resolution or conservative unknown-role handling, exact final pre-2025 refit sample and failure state, sealed BTC target-only endpoint buffer through `2026-01-01 22:59:59.999 UTC` for all 8,760 calendar-2025 hourly origins under the same controls, and the exact one-year 2025 `REPLICATED` gate. |
| Loader, hash scope, and coverage/claim contract | `IMPLEMENTED` | C5a | Packet C5a binds the fail-closed draft loader, the every-key-except-own-hash projection, per-candidate by-year and pooled coverage reporting, closed exclusion vocabulary, and candidate-complete claim scope without assigning a v1.1 semantic hash. |
| Coverage and final freeze | `IMPLEMENTED` | C5 | Packet C5 synchronizes the spec, YAML, and independent 48-key fixture; assigns the frozen semantic SHA-256; authorizes only the guarded protocol paths; and adds repeated tamper, future-mutation, boundary, solver, bootstrap, and 2025-seal tests. |

Standing rejections carried forward from the audit are unchanged: no signed-return
replacement, no sigma denominator floor, no arbitrary 98% coverage cutoff, and no
new feature search.

## 12. Frozen semantic-hash state (YAML key: `semantic_hash_scope`)

Protocol v1.1 has a frozen semantic hash in this packet. The semantic-hash projection
is every top-level key except `frozen_semantic_sha256`: exactly 48 of
the document's 49 top-level keys are in scope. The own-hash field is the sole
exclusion because a document cannot contain its own digest; in particular,
`predecessor_semantic_sha256` remains in scope.

Canonicalization inherits
`json.dumps(projected, sort_keys=True, separators=(',',':'), ensure_ascii=True)`
over UTF-8 followed by `sha256`. Mapping order, comments, and YAML formatting are
outside the semantic identity. C5 computed
`12dd3445365fdaa9e35cdcf93cae3e79a88b6b4d72d3d703b921359d1e917a9b` from the
independent render at `tests/fixtures/protocol_v1_1_expected.json`, synchronized the
machine document to that fixture, and froze the value.
