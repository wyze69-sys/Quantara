# Quantara Protocol v1 — Frozen Scientific Protocol Specification

**Protocol status:** `FROZEN_BEFORE_2022_2024_SCORING`
**Frozen date:** 2026-08-31
**Planning baseline:** `main` at `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`
**Source of authority:** `docs/superpowers/plans/2026-08-31-protocol-v1-stage-1-scientific-freeze.md` §3–§4
**Machine-readable counterpart:** `configs/protocols/quantara-protocol-v1.yaml`
**Expected semantic fixture:** `tests/fixtures/protocol_v1_expected.json`

This document transcribes plan §3–§4 without semantic change. The machine-readable
YAML and this document are dual representations of the same frozen protocol; a
contract test pins the YAML to the independently rendered expected semantic fixture
and its SHA-256. Neither representation may be edited after freeze except through a
new, explicitly authorized protocol version.

## 1. Research question

Can pre-registered BTC derivatives, spot/perpetual divergence, ETH cross-market state, and one independent BTC venue improve probability forecasts of unusually large BTCUSDT 24-hour moves beyond a strong causal volatility-persistence baseline?

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
14-series Protocol-v1 inventory.

### 2.3 Frozen exclusions

Do not add liquidations, options, long/short ratios, taker ratios, altcoins, order
books, macro, on-chain, sentiment, news, or technical-indicator searches.
Incidental columns in the Binance metrics archive may be retained in the immutable
raw object but are not canonical Protocol-v1 series and must not enter any feature
table.

The older `docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md`
is superseded for Protocol v1. In particular, its top-trader and taker-ratio scope,
guessed completeness rules, and combined metrics feature direction are not
authorized here.

## 3. Target

For hourly origin `t`, using canonical BTCUSDT perpetual traded closes:

```text
r24_t  = log(P[t+24h] / P[t])
sigma_t = sqrt(sum_{j=0}^{23} r[t-j]^2)
Z_t    = abs(r24_t) / sigma_t
Y_t    = 1[Z_t > k]
k       = empirical Q80(Z_t) on eligible 2020-2021 design origins only
```

An origin enters the Q80 calculation only when its complete forward label ends no
later than 2021-12-31 23:59:59.999 UTC. No 2022 value may enter threshold design.

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
Constructed `mark/index - 1` and `mark/spot - 1` are diagnostics only and never enter M1-M4. Mark and index are canonicalized because they verify source integrity
and support diagnostics, not because they earn independent model stages.

All probability models use the repository's exact-Decimal logistic-IRLS discipline
with these frozen constants: L2 penalty `lambda = 1`, unpenalized intercept,
train-window z-score standardization, `max_iterations = 50`, convergence tolerance
`0.000000000001`, eta clamp 24, probability clamp `0.000000000001`, and Gaussian elimination with partial pivoting.
There is no regularization search, no post-hoc probability calibration, no feature clipping, no tree model, and no model family
search in Protocol v1. Calibration is evaluated on the raw logistic probabilities.

For every paired candidate comparison, refit the comparator on exactly the same
training rows and score exactly the same test timestamps as the candidate. A
larger baseline sample may be reported separately but cannot be used for the
paired incremental claim.

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

Rules:

- An hourly information cutoff `T` is an exact UTC hour boundary.
  `prediction_ts = T + 1 ms`. `P[t]` is the BTC perpetual 1h bar close at
  `T - 1 ms`; its future endpoint is the bar close at `T + 24h - 1 ms`. This
  one-millisecond computational convention orders already-completed data; it is
  not a claim about exchange network latency.
- For a kline with source close time `C`, nominal `eligibility_ts = C + 1 ms`.
- For settled funding with source calculation/settlement time `F`, nominal
  `eligibility_ts = F + 1 ms`.
- For a five-minute OI row whose source timestamp is interval start `O`, nominal
  `eligibility_ts = O + 5 minutes`.
- For Kraken hourly OHLCVT whose source timestamp is interval start `K`, nominal
  `eligibility_ts = K + 1 hour`.
- `eligibility_ts < prediction_ts` without exception.
- All joins are backward as-of joins on eligibility_ts.
- Nearest joins, forward joins, unfinished bars, future revisions, and
  same-timestamp equality are forbidden.
- Completed klines become nominally eligible after interval close.
- Settled funding becomes nominally eligible after its settlement timestamp.
- OI becomes nominally eligible only after the end of its five-minute snapshot
  interval.
- Archive publication time is ex-post provenance, not the real-time availability
  of observations.
- Protocol v1 claims nominal historical point-in-time safety, not reconstruction of historical
  network latency. This limitation must appear in every result
  report.

## 6. Missing and duplicate policy

- Missing is null, never zero.
- No price, mark, index, premium, OI, or venue gap is interpolated.
- A feature is invalid when a required lookback crosses a missing native interval.
- A label is invalid when its required BTC price endpoints/path are unavailable.
- Known pre-archive periods remain null and receive no fabricated regime flag.
- Exact duplicate source rows may be deterministically deduplicated only after
  byte comparison, with source-row count, distinct-row count, duplicate count,
  and duplicate hashes preserved.
- Same-key conflicting rows block publication.
- ETH OI before 2021-12-01 is null and never enters M3.

## 7. Validation and gate

Outer folds:

```text
Fold 1: train 2020-09-01..2021-12-31; test 2022
Fold 2: train 2020-09-01..2022-12-31; test 2023
Fold 3: train 2020-09-01..2023-12-31; test 2024
```

Remove training origins whose 24-hour labels cross a boundary. Use a 24-hour purge.
Apply only the frozen train-window z-score and fixed regularization
described above. No clipping or post-hoc calibration is allowed. Never use random
K-fold.

Primary metric: pooled prediction-level Brier score and Brier skill versus B2:

```text
BS(model) = mean((p-y)^2)
BSS_B2(model) = 1 - BS(model) / BS(B2)
loss_improvement_i = loss_B2_i - loss_model_i
probability_bias = mean(p-y)
```

Calibration intercept and slope are obtained diagnostically by unpenalized
logistic regression of `y` on `logit(p)` with an intercept, after clamping only
for the logarithm to `[0.000000000001, 0.999999999999]`. The fitted intercept is
calibration intercept and the fitted coefficient is calibration slope. These
calculations do not alter predictions.

Inference: paired moving-block bootstrap over hourly loss differentials,
168-hour blocks, 2,000 resamples, 95% interval, resampled within year and then
pooled. The RNG seed is frozen at `20260831`.

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
candidate. M2 must pass the complete gate versus paired B2 before 2025 can
unlock. Starting from M2, evaluate the ETH block and then the Kraken block as the
only optional additions. Retain an optional block only when pooled relative Brier
improvement versus the currently retained model is at least 1%, its unadjusted
two-sided 95% paired-bootstrap interval has a lower bound above zero, its
one-sided bootstrap p-value passes Holm at family-wise alpha 0.05 across these
two optional-family tests, at least two years improve, and no year is worse than
-2%. If ETH is rejected, compare Kraken against M2, not against an
ETH-containing model. A rejected block receives no alternative transformation
search. M3b/ETH OI is a secondary diagnostic and can never alter the retained
candidate. The resulting candidate must still pass the complete 2%-versus-B2 and
calibration gate before 2025.

## 8. Sealed 2025

Before the final gate, 2025 may be checked only for file inventory, cryptographic hashes, parser
compatibility, expected boundaries, and mechanical corruption.
Forbidden: labels, feature distributions, model scores, conditional outcome
inspection, or protocol adaptation. If the gate passes, run exactly one frozen
2025 evaluation. Failure is reported as `DID_NOT_REPLICATE`; never redesign and
retest on 2025.

## 9. Acquisition audit references (A7–A10)

Protocol v1 depends on the completed A1–A10 acquisition audits (planning baseline
commit `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`). SHA-256 references for the
A7–A10 reports and sidecars use the frozen hash basis
`utf8_text_normalized_to_lf_before_sha256`: decode strict UTF-8, replace CRLF with
LF, replace any remaining CR with LF, re-encode as UTF-8, then compute SHA-256.
This preserves content binding while making checkout-created line endings irrelevant.

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| A7 report | `docs/superpowers/plans/2026-08-31-a7-ethusdt-perpetual.md` | `379a70250630f1e914618eda33131f6d396535126cbedbde7955a4216e7b2f72` |
| A7 sidecar | `temp/audit_a7_a8/a7_ethusdt_probe_v1.json` | `3b3b6ea81b3e1d91a9c10140333b2e01ab39929ff9022d0573878defd043ff58` |
| A8 report | `docs/superpowers/plans/2026-08-31-a8-btcusdt-spot.md` | `548ad0c2c6d766f49d5bb41de0fa1fecd0e928ec8939d253db5a1d31e55a9919` |
| A8 sidecar | `temp/audit_a7_a8/a8_btcusdt_spot_probe_v1.json` | `08f972fcbc9776d5a6cdc028a2d7523d24355887b204dddc2277a540c22a2c52` |
| A9 report | `docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md` | `225793a4723c1f55345084fe0a5be5c68273181798ce96ba61ac3283adaf5fb5` |
| A9 sidecar | `temp/audit_a9_kraken/a9_kraken_range_probe_v1.json` | `808c1a17c0b710187c36254c31992d2b645cc2533b7fec4b4c0d05b7d42f7c14` |
| A10 report | `docs/superpowers/plans/2026-08-31-a10-live-acquisition-consolidation.md` | `61881d940dca4810293b487cb172427fc5c18d1936724ba28939eabc4a88e9ee` |
| A10 sidecar | `temp/audit_a10_corrections/a3a4_reprobe_v2.json` | `621c5781df4d94810dbfc2fa61f9a78767f6b735ed9d42c421d2cfc5e10cfe86` |

Earlier A1–A6 per-file hashes remain in their sidecars, subject to the A10
correction register's interpretation.

## 10. Frozen semantic hash

The machine-readable representation `configs/protocols/quantara-protocol-v1.yaml`
must yield, after projecting its top-level keys in frozen fixture order, exactly
the structure in `tests/fixtures/protocol_v1_expected.json`
(`expected_semantic`), whose canonical JSON serialization
(`json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)`)
has SHA-256:

```text
91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a
```

Any change to protocol semantics requires a new frozen protocol version and a new
hash; it must never be made by editing this protocol in place.
