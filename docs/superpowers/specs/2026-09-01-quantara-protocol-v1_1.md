# Quantara Protocol v1.1 — Draft Successor Scientific Protocol Specification

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

This is a complete standalone draft successor to Protocol v1. While the protocol
status is `DRAFT_UNFROZEN_SUCCESSOR`, no scoring of any period, and no 2025 access,
is authorized. The machine-readable counterpart is
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

## 4. Baselines and frozen model ladder

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

All probability models use the repository's exact-Decimal logistic-IRLS discipline
with these frozen constants: L2 penalty `lambda = 1`, unpenalized intercept,
train-window z-score standardization, `max_iterations = 50`, convergence tolerance
`0.000000000001`, eta clamp 24, probability clamp `0.000000000001`, and Gaussian
elimination with partial pivoting. There is no regularization search, no post-hoc
probability calibration, no feature clipping, no tree model, and no model family
search in Protocol v1.1. Calibration is evaluated on raw logistic probabilities.

For every paired candidate comparison, refit the comparator on exactly the same
training rows and score exactly the same test timestamps as the candidate. A larger
baseline sample may be reported separately but cannot be used for the paired
incremental claim.

## 5. Point-in-time contract

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
- For five-minute OI with source timestamp `O`,
  `eligibility_ts = O + 5 minutes`.
- For Kraken hourly OHLCVT with interval-start `K`,
  `eligibility_ts = K + 1 hour`.

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

Calibration intercept and slope are obtained diagnostically by unpenalized logistic
regression of `y` on `logit(p)` with an intercept, after clamping only for the
logarithm to `[0.000000000001, 0.999999999999]`. The fitted intercept is calibration
intercept and the fitted coefficient is calibration slope. These calculations do
not alter predictions.

Inference retains the Protocol-v1 draft basis pending its separately owned repair:
paired moving-block bootstrap over hourly loss differentials, 168-hour blocks,
2,000 resamples, 95% interval, resampled within year and then pooled. The RNG seed
is `20260831`. The complete repaired successor bootstrap contract is `DEFERRED` to
packet C2; none of the C2 algorithm or fixture changes is implemented here.

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
Starting from M2, evaluate the ETH block and then the Kraken block as the only
optional additions. Retain an optional block only when pooled relative Brier
improvement versus the currently retained model is at least 1%, its unadjusted
two-sided 95% paired-bootstrap interval has a lower bound above zero, its one-sided
bootstrap p-value passes Holm at family-wise alpha 0.05 across these two
optional-family tests, at least two years improve, and no year is worse than -2%.
If ETH is rejected, compare Kraken against M2, not against an ETH-containing model.
A rejected block receives no alternative transformation search. M3b/ETH OI is a
secondary diagnostic and can never alter the retained candidate. The resulting
candidate must still pass the complete 2%-versus-B2 and calibration gate before
2025.

The repaired optional-family decision contract is `DEFERRED` to packet C3; this
packet does not add `M2K`, hypotheses, estimator binding, calibration-failure rules,
or selection-evidence labelling.

## 8. Sealed 2025

Before the final gate, 2025 may be checked only for file inventory, cryptographic
hashes, parser compatibility, expected boundaries, and mechanical corruption.
Forbidden: labels, feature distributions, model scores, conditional outcome
inspection, or protocol adaptation. If the gate passes, run exactly one frozen 2025
evaluation. Failure is reported as `DID_NOT_REPLICATE`; never redesign and retest on
2025. The additional endpoint buffer and replication-gate details are `DEFERRED` to
packet C4 and are not implemented here.

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

Their predecessor digests are not recopied into this unfrozen draft. Each binding is
recorded as `INHERITED_FROM_PROTOCOL_V1` pending the C5 synchronized fixture and
semantic freeze. Earlier A1–A6 per-file bindings remain inherited subject to the A10
correction register's interpretation.

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

## 11. Deferred change-set items

| Item | Status | Owning packet | Deferred scope |
| --- | --- | --- | --- |
| Bootstrap and inference | `DEFERRED` | C2 | Complete non-circular year-stratified 168-clock-hour moving-block bootstrap, null-centred p-value, percentile CI, exact PRNG, 20,000 resamples, and fixtures. |
| Estimator and optional-family contract | `DEFERRED` | C3 | Binding to the committed exact-Decimal IRLS contract, both-class and calibration-failure rules, `M2K` plus the three fixed optional hypotheses under ordinary Holm across all three, and labelling optional-block 2022–2024 results as selection evidence rather than independent replication. |
| Timestamp, refit, buffer, and replication contract | `DEFERRED` | C4 | Archive-specific OI timestamp resolution or conservative unknown-role handling, exact final pre-2025 refit sample and failure state, sealed BTC target-only endpoint buffer through `2026-01-01 22:59:59.999 UTC` for all 8,760 calendar-2025 hourly origins under the same controls, and the exact one-year 2025 `REPLICATED` gate. |
| Coverage and final freeze | `DEFERRED` | C5 | Coverage/exclusion reporting and claim scope per candidate; synchronization of spec, YAML, and fixture; new semantic SHA-256; and repeated tamper, future-mutation, boundary, solver, bootstrap, and 2025-seal tests. |

Standing rejections carried forward from the audit are unchanged: no signed-return
replacement, no sigma denominator floor, no arbitrary 98% coverage cutoff, and no
new feature search.

## 12. Draft semantic-hash state

Protocol v1.1 has no frozen semantic hash in this packet. Its state is
`NOT_YET_ASSIGNED_PENDING_PACKET_C5`. Packet C5 owns synchronization, fixture
creation, semantic hashing, and freeze. Until then, scoring permission remains
`NONE_UNTIL_FROZEN`.
