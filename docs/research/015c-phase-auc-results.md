# Slice 015c — Result: Phase-Partitioned AUC on Frozen 012 Predictions

## 0. Provenance

- Date: 2026-08-30
- Pre-registration: `docs/research/015c-phase-auc-prereg.md`, committed `c42fa5e`
- Result commit: this document — strictly after `c42fa5e`, as required
- Implementation: `src/quantara/phase_auc_diagnostic.py` (22 unit tests)
- Data consumed: **none new.** Frozen per-fold sidecars only. 2025 untouched;
  2020/2021 untouched. No model refit.

Parity check: the verdict was first produced by a disposable exploratory script,
then re-derived by the shipped module. Both agree bit-for-bit on `T`, all three
per-year mean AUCs, the bootstrap lower bound, and every value in the §6
geometry table — to all 18 decimal places. The exploratory script has been
deleted; the module and its tests are what remain.

## 1. Verdict

**TERMINATE the OHLCV-only 24h-direction line.**

Both pre-registered conditions fail:

| Condition (prereg §6) | Required | Observed | Result |
|---|---|---|---|
| 1 — one-sided 95% bootstrap LB on `T` | > 0 | −0.025092879246826405 | **FAIL** |
| 2 — year mean AUC ≥ 0.50 in all 3 years | all ≥ 0.50 | 0.4873 / 0.4922 / 0.5041 | **FAIL** (2 of 3 below) |

## 2. Primary statistic

All 72 (year, phase) cells were defined; none dropped, none undefined.

```
T = mean(AUC − 0.5) over 72 cells = −0.005471554813268876
implied mean AUC                  =  0.494528445186731114
```

Per-year mean AUC across that year's 24 phases:

| Year | Regime | Mean AUC | vs 0.50 |
|---|---|---|---|
| 2022 | full bear | 0.487310716952808642 | −0.0127 |
| 2023 | recovery | 0.492218420422540326 | −0.0078 |
| 2024 | bull | 0.504056198184844373 | +0.0041 |

The point estimate is *below* chance overall. 2024 is the only year above 0.50
and clears it by 0.4 AUC points — well inside the bootstrap noise band
(SD 0.0122).

## 3. Bootstrap

Paired circular moving-block, 168-bar (7-day) blocks, 10,000 replicates,
seed 20260830, as frozen in prereg §5.

- bootstrap mean `T`: −0.005017935894815507
- bootstrap SD: 0.012247723502817193
- one-sided 95% lower bound: **−0.025092879246826405**
- two-sided 95% CI: (−0.028926201267647, +0.018938279734389)
- fraction of replicates ≤ 0: 0.658

The interval comfortably contains zero and is centred slightly negative. There
is no evidence of ranking skill, and equally no evidence of exploitable
*inverse* skill — the result is consistent with pure noise.

## 4. Input accounting

| Year | Folds | Test bars | Flat bars excluded | Bars per phase | Up-rate |
|---|---|---|---|---|---|
| 2022 | 116 | 8,375 | 0 | 348–349 | 0.469970 |
| 2023 | 116 | 8,376 | 0 | 349 | 0.514924 |
| 2024 | 117 | 8,397 | 0 | 349–350 | 0.538049 |

Zero flat bars is expected: an exact close-to-close tie at 18-decimal precision
is essentially impossible on hourly BTC. The 2022 phase-count spread (348 vs 349)
is the 8,375 ÷ 24 remainder, not a defect.

### 4.1 Declared deviation from prereg §3

Prereg §3 states: *"Bars whose `label` is exactly `0` (flat close-to-close) are
excluded."* **That instruction is wrong as written and was not followed
literally.** It is recorded here rather than quietly reinterpreted.

The sidecar `label` field is the *binarised training target*
(`training_metrics_logistic.py`: `1 if direction == 1 else 0`), so `label == 0`
means "down **or** flat" — it is every down bar in the dataset. The three-way
sign lives in the separate `direction` field (−1 / 0 / +1). Executing §3
literally would have deleted every down bar, leaving all 72 cells single-class
and every AUC undefined.

Resolution: flatness is tested on `direction == 0`, which is what §3 plainly
intended ("flat close-to-close"). The loader additionally cross-checks
`direction` against `label` on every row and raises on disagreement; all 25,148
rows agreed.

Effect on the verdict: **none.** Zero bars are flat under either reading, so the
excluded set is empty and the statistic is identical. The deviation is disclosed
because a reader reproducing from the prereg alone would otherwise hit an
all-undefined result and not know why.

## 5. Secondary cut (prereg §7 — diagnostic only)

Restricted to the back half of folds per year, where training sets run from
~4,300 to ~8,625 rows instead of starting at 336:

```
T_mature = +0.005983758673292139   implied mean AUC = 0.505983758673292150
   2022 mean AUC = 0.469334040891413673
   2023 mean AUC = 0.525432249438221866
   2024 mean AUC = 0.523184985690240856
```

`T_mature` flips positive, and 2023/2024 reach ~0.524. **This does not change
the verdict**, and prereg §7 forbids it from doing so. Recording it honestly:

- It is a *subset* of the failing primary, not an independent test. Choosing it
  post hoc is exactly the selection the pre-registration exists to prevent.
- 2022 gets **worse** (0.4693), so the "mature models are better" reading
  requires ignoring the bear year — the same regime-dependence that already sank
  015b.
- No bootstrap interval was computed for it, so its magnitude is unbounded by
  any uncertainty estimate.

What it is worth: a *hypothesis* for some future pre-registered design — that
`min_train_size=336` is too small and early folds inject noise. That hypothesis
would need its own pre-registration and its own untouched data. It is not
evidence today.

## 6. Why 015b's IC looked positive and this does not

Descriptive follow-up, same predictions, three geometries:

| Year | Within-fold (72 bars) | Pooled whole-year | Phase-partitioned |
|---|---|---|---|
| 2022 | 0.479857454 (SD 0.212386394, n=113) | 0.488218685 | 0.487310717 |
| 2023 | **0.573804499** (SD 0.201942617, n=116) | 0.492390114 | 0.492218420 |
| 2024 | **0.611049245** (SD 0.183764616, n=116) | 0.502466317 | 0.504056198 |

`n` is the number of folds with a defined AUC. 2022 loses 3 of 116 folds
(indices 48, 58, 98) to single-class test windows — each is 72 consecutive hours
in which every bar's 24h-forward move was **down**. That is itself a symptom of
the same problem: inside a 72-bar window the label often barely varies, or does
not vary at all.

The 2023/2024 within-fold AUCs of 0.574 and 0.611 look like real skill. They
collapse to ~0.492 and ~0.502 the moment the 72-bar window is removed — a drop
of 8.1 and 10.9 AUC points. Pooling and phase-partitioning agree with each other
to within 0.2 AUC points in all three years.

This isolates the artifact precisely: **it lives in the 72-bar windowing, not in
the 24h label overlap.** Pooled retains the full label overlap and still reads
~0.49–0.50; only removing the window moves the number. Within a 72-bar fold, both
the smooth model output (logit lag-1 autocorrelation 0.83–0.95) and the smooth
label series drift together, and ranking a monotone drift against a monotone
drift scores well above 0.5 without any predictive content.

An implication worth stating: the phase partition — this slice's own headline
design, chosen to defeat label overlap — turns out to have been unnecessary for
that purpose. Pooling alone would have sufficed. The pre-registration's stated
rationale for preferring phase-AUC over Claude's pooled Spearman (prereg §2,
"pooling leaves the overlap dependence fully intact") is not supported by this
table. The verdict is unaffected, since both geometries agree, but the reasoning
behind the design choice was wrong and the reviewer's simpler proposal was
adequate.

This also explains 015b §2's central puzzle — why IC "survived" in exactly the
two rising-price years while accuracy lost to the majority baseline in those
same years. Both facts are the same artifact seen twice: in a trending year the
within-window drift is stronger, so the windowed statistic inflates more.

## 7. What is now settled

- **012 does not rank.** Phase-partitioned mean AUC 0.4945, 95% lower bound
  −0.0251. *(this slice)*
- **012 does not calibrate.** Pooled Brier 0.254103 / 0.256172 / 0.251171 —
  worse than a constant 0.500 forecast in all three years. *(015b §9.3)*
- **012 does not beat trivial baselines.** Loses to the training-window majority
  class in 2023 and 2024. *(015b §3)*
- **015b's apparent IC was fold geometry.** Quantified in §6 above; the stability
  gate that produced its formal verdicts was separately invalidated in 015b §9.2.

Ranking and calibration were the last two independent ways this model could have
been salvaged. Both are closed. The four-feature OHLCV logistic direction model
is finished, and no variation of its measurement will revive it.

## 8. What this does not settle

- Whether 24h direction is predictable **at all** from richer information —
  funding rate, open interest, taker flow, cross-asset. Untested. This slice
  kills one model on one feature family, not a hypothesis about markets.
- Whether volatility is predictable beyond persistence. Separate line, needs its
  own pre-registration.
- 2020/2021 remain parser-blocked; 2025 remains a sealed canary. Neither was
  spent here.

Two engineering defects found during the 015b audit remain **open in code**, and
this slice did not touch them:

- `ic_stability_diagnostic.FOLD_COUNT = 117` raises on the 116-fold 2022/2023
  years, so 015b's published gate rows for those years cannot be reproduced by
  the shipped module at all (015b §9.2).
- The shipped permutation null flips per-fold IC signs independently, but 2023
  fold ICs have lag-1 autocorrelation ≈ +0.22, so folds are not exchangeable and
  the null is too narrow (015b §9.4).

Neither affects this slice's verdict — 015c uses neither function. They are
recorded so the next reader does not mistake them for fixed.

**Data-snooping status:** 2022–2024 are now spent as confirmatory evidence for
direction prediction. They diagnosed the 015b defects, chose this replacement
statistic, and delivered this verdict. Any future direction model must be judged
on data untouched by all of that.

## 9. Endpoint

Research artifact. Not live trading, not production-eligible, not
customer-facing, not redistributable.

The shippable result of 015c is a **clean, pre-registered kill**: a negative
that was specified before it was measured, run on data that cost nothing, and
that explains the earlier false positive rather than merely contradicting it.
