# Slice 015c — Pre-Registration: Phase-Partitioned AUC Test on Frozen 012 Predictions

## 0. Status

**PRE-REGISTRATION. Written and committed BEFORE the statistic is computed.**

If this document's git commit does not strictly precede the commit containing
any result, the test is void and must be discarded. That ordering is the entire
point of the document.

- Date written: 2026-08-30
- Author: post-closure audit of slice 015b
- Prerequisite: `docs/research/015b-multi-year-results-2022-2023-2024.md` §9
- Data consumed: **none new.** Reads only the frozen per-fold sidecars already
  committed under `data/diagnostic/training/`.

## 1. The one question this test answers

Does the frozen 012 model carry **any** genuine ranking (discrimination)
information about 24-hour direction, when measured on a geometry that does not
suffer the 24h label-overlap artifact?

This is the single unresolved question left by 015b. 015b established that 012's
*probabilities* are worse than a coin flip (§9.3, pooled, artifact-free — that
finding is final and is not retested here). It did **not** establish whether
weak ranking survives underneath those bad probabilities, because every IC
number in 015b was computed on 72-bar folds against labels that overlap 23 of
24 hours.

Explicitly out of scope: recalibration, feature changes, hyperparameter changes,
regime conditioning, volatility targets. This test only asks whether there is
anything there to recalibrate.

## 2. Why phase partitioning

`l_fwddir_24[t] = sign(close[t+24] − close[t])`. Consecutive bars therefore share
23 of 24 hours of their label window. Any statistic computed over consecutive
bars inherits that dependence.

Partition each year's test bars by `row_index mod 24` into 24 **phases**. Within
one phase, consecutive observations are 24 bars apart, so their label windows are
**exactly adjacent and non-overlapping**. This removes label overlap by
construction rather than by correction.

Chosen over the alternative (pooled Spearman over all test bars) because pooling
removes only the within-window centering artifact and leaves the overlap
dependence fully intact. Phase partitioning attacks the root cause.

AUC is chosen over IC because 012 is trained on a binary target, and AUC measures
binary discrimination without requiring calibrated probabilities — which is
precisely the property still in question. 015b §9.1 showed the shipped IC was
Pearson-against-binary-label, so a rank metric on the same binary target is the
honest continuation.

## 3. Data

Frozen per-fold sidecars, unmodified:

| Year | Sidecar | Folds | Test bars |
|---|---|---|---|
| 2022 | `per_fold_20260830T023315Z-ffa40b89-….json` | 116 | 8,375 |
| 2023 | `per_fold_20260830T024137Z-e78fe778-….json` | 116 | 8,376 |
| 2024 | `per_fold_20260830T032001Z-3a4d41aa-….json` | 117 | 8,397 |

Each prediction record supplies `row_index`, `probability`, `label`. Only these
three fields are used. Bars whose `label` is exactly `0` (flat close-to-close)
are excluded — AUC is undefined without two classes, and the exclusion count is
reported per phase.

2025 is **not** touched. 2020/2021 are **not** touched.

## 4. Primary statistic

For year `y` and phase `o ∈ {0..23}`, let `S_{y,o}` be all test bars with
`row_index mod 24 == o`, scored by frozen `probability` against binary `label`.

Compute `AUC_{y,o}` = Mann-Whitney U / (n_up × n_down), with tied scores
receiving 0.5 credit.

The primary statistic is the unweighted mean excess over chance across all 72
cells:

```
T = (1/72) × Σ_{y} Σ_{o=0..23} (AUC_{y,o} − 0.5)
```

All 24 phases enter with equal weight. **No phase is selected, dropped, or
reweighted after inspection.** No best-offset search. If any cell is undefined
(a phase with only one class present), the run is reported as degenerate and the
cell count is stated explicitly rather than silently dropped.

## 5. Null and interval

`H₀: T ≤ 0` — no directional discrimination.

Interval: **paired circular moving-block bootstrap**, 10,000 replicates, seed
`20260830`, resampling contiguous **7-day (168-bar)** blocks within each year,
carrying each bar's `(probability, label)` pair together so the pairing is never
broken.

Block length 168 is frozen here, before computation, and is chosen to exceed both
the 24h label horizon and the 60h longest feature lookback (`f_roc_60`). It is
not claimed to be optimal — only that it was fixed in advance.

Report the one-sided 95% lower bound on `T`.

## 6. Decision rule (FROZEN)

**CONTINUE** the 24h-direction line only if **both** hold:

1. one-sided 95% bootstrap lower bound on `T` is **> 0**; and
2. year-level mean AUC (mean of that year's 24 phase AUCs) is **≥ 0.50 in all
   three years**.

**Otherwise TERMINATE** the OHLCV-only 24h-direction line. Not "revisit", not
"try with different folds" — terminate.

Prohibited regardless of outcome, because each would convert this test into a
search:

- tuning `λ`
- changing fold size, `min_train_size`, or embargo
- adding, removing, or transforming features
- switching to a different rank metric after seeing this result
- re-running with a different block length after seeing this result
- computing the statistic on 2025 or 2020/2021

## 7. Secondary cut (declared in advance, reported regardless)

Because `72 = 3 × 24`, every fold contributes exactly 3 bars to each phase, and
the 116/117 contributing models span training sets from 336 rows to ~8,625 rows.
Early folds fit 5 parameters on 336 highly autocorrelated rows and are close to
noise.

Secondary statistic `T_mature`: identical computation restricted to the **back
half of folds** per year (fold_index ≥ ⌈n_folds/2⌉).

**This is a diagnostic, not a second chance.** It is reported alongside the
primary whatever both say. If the primary fails and `T_mature` passes, the
verdict is still TERMINATE — the pass is recorded as a hypothesis for a future
pre-registered design with a higher `min_train_size`, nothing more. Reversing the
verdict on `T_mature` after a primary failure is exactly the practice this
document exists to prevent.

## 8. Interpretation limits, stated before the result

- **A pass does not validate 012.** 2022–2024 were used to diagnose the 015b
  measurement defects and to choose this replacement statistic. They are spent
  as confirmatory evidence. A pass means only: ranking information plausibly
  exists, and one pre-registered attempt with genuinely new information
  (funding rate, open interest, taker flow, cross-asset) is licensed, to be
  judged once on sealed 2025.
- **A pass does not rehabilitate the probabilities.** 015b §9.3 stands
  independently: pooled Brier is worse than a constant 0.500 forecast in all
  three years. A model that ranks but cannot state a probability is not usable
  as-is.
- **A fail is decisive.** It ends the OHLCV-only direction line and 015b's
  negative becomes the final word on it.
- This test can **kill** 012 on spent data. It cannot **confirm** it on spent
  data. That asymmetry is deliberate and is why it is worth running.

## 9. Endpoint

Research artifact. Not live trading, not production-eligible, not
customer-facing, not redistributable.
