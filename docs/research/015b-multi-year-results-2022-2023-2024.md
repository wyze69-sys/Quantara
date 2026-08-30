# Slice 015b — Frozen-Model Multi-Year Validation on 2022 + 2023 + 2024

> **CORRECTION NOTICE (2026-08-30, post-closure).** §4 of this report applies a
> pre-registered `SD > 0.20` stability gate that has since been shown to measure
> fold geometry rather than model instability. The three `STOP_PUBLISH_NEGATIVE`
> verdicts in §4 are **retracted as gate verdicts**. The overall STOP conclusion
> **stands and is strengthened** on independent grounds. §9 is the correction
> record and supersedes §4 wherever they disagree. No number in §§1–3 changes.

## 0. Provenance

- Date: 2026-08-30
- Slice: 015-extended-b (G4 + G5)
- Corpus: 2022 (8,760) + 2023 (8,760) + 2024 (8,784) = 26,304 1h rows
- Model: 012 frozen — logistic IRLS, `λ=1`, 4 features
  (`f_ret_1`, `f_roc_60`, `f_rvol_20`, `f_volratio_20`), target `l_fwddir_24`,
  `test_size=72`, embargo=24, `min_train_size=336`, expanding-window walk-forward
- Folds: **349** = 116 (2022) + 116 (2023) + 117 (2024)
- Code revision for all three arms: `47e40269970f175f858b16893dc2c4f8f08705a0`
- Rights record: `configs/legal/binance-usdm-provider-rights.v3.yaml`
  (`model_train_internal: OWNER_APPROVED_PENDING_COUNSEL`)

### 0.1 Execution shape — Path A, and why

The plan (§4 G4) specified a single concatenated 26,304-row run with
`min_train_size=8,760` producing 243 folds. **That run is not executable against
the frozen validators**, and the defect is in the plan, not the data:

- `load_validation_descriptor` rejects `min_train_size: 8760` as
  `unsupported_parameter`. The only approved value is `336`.
- The same validator rejects any period that does not match a single approved
  base-year identity, so a 2022-01-01 → 2025-01-01 period is rejected outright.
- The frozen 012 KILL commit itself recorded `fold_count: 117`, which is
  `floor((8784 − 336 − 24) / 72)` — proof that the frozen model used
  `min_train_size=336`, not 8,760. The plan's own "012 unchanged" requirement
  therefore contradicts its "min_train_size=8,760" requirement.

Path A (chosen by the owner) runs three independent per-year chains at the
genuinely frozen parameters. This preserves "012 unchanged" — the requirement
that actually matters — and sacrifices only the pooled-fold framing, which was
never reachable without amending a frozen validator.

Fold arithmetic, verified against each committed `quality_identity`:

| Year | Rows | `floor((rows − 336 − 24) / 72)` | Recorded `fold_count` |
|---|---|---|---|
| 2022 | 8,760 | floor(8,400 / 72) = 116 | 116 |
| 2023 | 8,760 | floor(8,400 / 72) = 116 | 116 |
| 2024 | 8,784 | floor(8,424 / 72) = 117 | 117 |
| **Total** | **26,304** | — | **349** |

349 folds, not 243. The 243 figure in the plan was derived from the
unreachable `min_train_size=8,760`.

### 0.2 Code-drift control

The 2024 arm was originally run at revision `79f6a75`; 2022/2023 ran at
`47e4026`. The only source delta between them is additive 2023 identity-table
registration in `descriptor.py` (26 insertions, 3 deletions, no shared code
path). To remove the caveat rather than argue it away, the 2024 logistic arm was
**re-executed at `47e4026`** and its 117 per-fold ICs verified byte-identical to
the frozen sidecar (two independent reruns, both `IDENTICAL_TO_FROZEN=True`).
All three arms are therefore comparable at one revision.

## 1. Per-year outcome table (PRIMARY OUTPUT)

| Year | Regime | Folds | Mean direction IC | Within-year IC SD | Accuracy | Train-window majority baseline | Log-loss | Brier |
|---|---|---|---|---|---|---|---|---|
| 2022 | full bear (LUNA/FTX) | 116 | −0.036035220107766154 | 0.308066543775181283 | 0.518584146160487831 | 0.507449088689223463 | 0.703652372374689632 | 0.254166614144309991 |
| 2023 | recovery | 116 | +0.115794271396887318 | 0.301098722815922707 | 0.504968869731800766 | 0.514996408045977012 | 0.707897322419930482 | 0.256218322165448205 |
| 2024 | bull (halving/ETF) | 117 | +0.178590194880741058 | 0.265557258490338503 | 0.515063433784091061 | 0.535090887203563260 | 0.695523361523936980 | 0.251148463739147642 |
| **Cross** | mixed | **349** | +0.086116415389954074 (mean of per-year means) | **cross-year SD: 0.110347625903883550** | — | — | — | — |

Pooled across all 349 folds treated as one sample: mean IC
`+0.086381383239497876`, per-fold SD `0.304911515359093589`.

Whole-year label base rates (`l_fwddir_24`, computed directly from the research
parquets): 2022 up-rate `0.469436813186813187`; 2023 `0.526785714285714286`;
2024 `0.537214611872146119`. A 6.8-point swing — confirming the plan's §6 note
that the global 0.5349 K1 bar is a 2024-specific artifact.

## 2. Pre-registered per-year outcome mapping

Applying plan §6 (`IC > 0.10` survives / `IC ∈ [0, 0.10]` weakens / `IC < 0` inverts):

- **2022: INVERTS.** IC = −0.0360. Mapping → REDESIGN; the feature set is wrong
  for the bear regime.
- **2023: SURVIVES.** IC = +0.1158 (> 0.10).
- **2024: SURVIVES.** IC = +0.1786 (> 0.10).

Two of three survive, but the surviving pair is exactly the two years with
rising price. The sign of the signal tracks the direction of the market.

## 3. Per-year accuracy vs per-fold majority baseline

| Year | Accuracy | Majority baseline | Delta | Verdict (plan §6) |
|---|---|---|---|---|
| 2022 | 0.518584146160487831 | 0.507449088689223463 | **+0.011135057471264368** | skill |
| 2023 | 0.504968869731800766 | 0.514996408045977012 | **−0.010027538314176246** | anti-skill |
| 2024 | 0.515063433784091061 | 0.535090887203563260 | **−0.020027453419472199** | anti-skill |

This is the most damaging row in the report, and it runs opposite to §2. The one
year where IC inverts (2022) is the only year the model beats its trivial
baseline. Both years where IC "survives" are years the model loses to
"predict the training-window majority class." IC positivity and
better-than-trivial accuracy do not co-occur in any year. A signal that cannot
put those two facts in the same year is not a signal.

Brier is above the 0.25 kill ceiling in all three years, and in every year it is
worse than the climatology baseline (2022: 0.2542 vs 0.2506; 2023: 0.2562 vs
0.2549; 2024: 0.2511 vs 0.2500). The model is worse-calibrated than a constant
base-rate forecast in all three regimes.

## 4. Cross-year B3.5b verdict

Pre-registered gate inputs:

- Cross-year IC SD: **0.110347625903883550**
- B3.5 within-2024 SD: 0.265557258490338503
- Scaling factor: 1.0 (pre-registered)
- Threshold: 0.265557258490338503
- Cross-year SD vs threshold: **0.1103 < 0.2656 → passes this one comparison**

**That pass does not carry, and reporting it as a pass alone would be
misleading.** Three reasons, each independently sufficient:

1. **n = 3.** The cross-year SD is the standard deviation of three numbers, with
   2 degrees of freedom. It cannot distinguish "stable across regimes" from
   "not sampled enough to see instability." The statistic is
   under-powered by construction, not reassuring.
2. **The interval spans zero.** Per-year mean IC runs −0.036 → +0.116 → +0.179.
   A low SD around a mean of +0.086 is describing a distribution that includes
   sign inversion. Magnitude stability is the wrong question when the sign flips.
3. **Every year independently fails the B3.5 gate.** Re-running the frozen
   `ic_stability_diagnostic` gate per year:

| Year | Within-year SD | Bootstrap 95% CI | Permutation p | Gate verdict |
|---|---|---|---|---|
| 2022 | 0.308066543775181283 | (−0.091155211770409859, +0.019806460738069430) | 0.205400000000000000 | STOP_PUBLISH_NEGATIVE |
| 2023 | 0.301098722815922707 | (+0.062059419872473456, +0.170567500717519791) | 0.000000000000000000 | STOP_PUBLISH_NEGATIVE |
| 2024 | 0.265557258490338503 | (+0.131419909239496108, +0.227143758299265875) | 0.000000000000000000 | STOP_PUBLISH_NEGATIVE |

All three trip the `SD > 0.20` arm. 2022 additionally has a CI containing zero
and p = 0.2054 — on 2022 alone the signal is statistically indistinguishable
from noise.

> **RETRACTED — see §9.** The `SD > 0.20` arm is invalid: a skill-free process
> matched to the model's own output autocorrelation produces per-fold SD of
> 0.330 / 0.331 / 0.264, so the gate fails smooth predictors regardless of
> skill. The `p = 0.0000` entries are also misreported (see §9.4) and the
> provenance sentence above is wrong (see §9.5). The 2022 CI-includes-zero
> finding survives intact.

**Verdict: STOP — regime-conditioning (B5), carrying a REDESIGN flag from 2022.**

The pre-registered 4-way resolves to STOP-regime-conditioning: the signal's sign
is conditional on regime, which is precisely what B5 exists to test. The 2022
inversion also satisfies the §6 REDESIGN trigger. These are not in conflict —
2022 says the current 4-feature set is wrong for bear markets, which is a
regime-conditioning finding stated in feature-design terms.

What is *not* claimed: that the model works in bull markets. It does not. In
2024, its best year, it is 2.0 accuracy points below a trivial predictor and
worse-calibrated than climatology.

## 5. Findings handed to B3.5b / B5

- **Does any year invert?** Yes — 2022, the only full bear year. Sign inversion
  is regime-aligned, not random.
- **Does any year weaken dramatically?** No year is strong to begin with. The
  spread in mean IC (−0.036 to +0.179) is smaller than the within-year fold SD in
  every year (0.27–0.31). Fold-to-fold noise dominates regime effects by roughly
  3×. Any regime-conditioning design must clear that noise floor first.
- **Does the per-fold IC distribution change across years?** Only in centre, not
  in width. SD is 0.27–0.31 in all three years; positive-fold share moves
  50/116 (43%) → 74/116 (64%) → 83/117 (71%), tracking regime. The distribution
  shifts; it never tightens.
- **Directional-accuracy skill is anti-correlated with IC across years.** Any B5
  design that selects on IC will select against accuracy. This needs resolving
  before a regime filter is built, or the filter will optimise the wrong metric.

## 6. What this does NOT answer

- Whether the signal works on 2020/2021 — headerless monthly archives vs the
  approved exact-header parser; amendment deferred, ZIPs retained
  content-addressed.
- Whether 014 derivatives features add value — deferred, and per the original
  GPT/Claude agreement cheap features had to clear multi-year data first. They
  have now been tested on three years and did not clear.
- Whether the model works on 2025 — untouched OOS canary.
- Anything about live trading. This is a research artifact. No artifact in this
  slice is commercially production-eligible, customer-facing, or redistributable.

## 7. Frozen-state verification (T5)

- 012 KILL attempt manifest `a8cacc8a3687d560ce7fbbd5adf416c23854611ec7c6fc514b7a1d20d07b756f`
  present and byte-identical (`20260829T064246Z-0bbd6069-…json`).
- 2022 1h klines canonical content hash
  `96c877600badd376a75b96c8c12d09cc5a52f7c167066b8a04a46217a87e4b3d` — match
  confirmed.
- All 19 live `current.json` pointers snapshotted before the 2024 rerun and
  verified byte-identical after (`POINTERS IDENTICAL to snapshot`). The rerun
  required temporarily repointing three 2024 lanes to their full-year commits;
  all three were restored.
- All three per-year training attempts recorded
  `terminal_result: KILL_CRITERIA_FAILED`, `training_artifact: not_written`,
  `pointer_replaced: false`. No KILL run mutated a live pointer.
- 2023 rerun idempotency: 1m/1h/1d byte-identical on re-execution.

## 8. Post-slice state

`{2022, 2023, 2024}` is the verified corpus: 26,304 1h rows, three regimes, one
code revision, 349 folds, full SHA-256 provenance chain.

The shippable result of 015b is the **multi-year honest negative**: the frozen
012 model does not carry a usable directional signal in any of bear, recovery, or
bull, and its apparent 2024 IC does not survive contact with either a trivial
accuracy baseline or a second and third year of data. Per plan §12 the next slice
is B5 (regime conditioning, no-future-info design), with 2022's inversion as the
concrete design target — and with the §5 accuracy/IC anti-correlation resolved
before any filter is built.

> **SUPERSEDED by §9.8.** The next step is not B5. B5 would condition on regime
> using IC as its selection signal, and §9.2 shows every IC number here was
> measured under an artifact-prone fold geometry. The phase-partitioned AUC test
> resolves whether any ranking signal exists at all; B5 is only meaningful if it
> does.

## 9. Correction record (post-closure measurement audit)

Added 2026-08-30 after closure, following an internal audit and two independent
adversarial reviews. Everything below was recomputed from the frozen per-fold
sidecars listed in §0; no model was refit and no new data was touched.

### 9.1 What the shipped `direction_ic` actually is

`training_metrics_logistic.direction_ic` (line 396) is
**Pearson(predicted up-probability, binary label)** — not Spearman against the
continuous forward return. Reproduced exactly from the sidecars:

| Year | Shipped `direction_ic` mean | Recomputed Pearson(prob, label) |
|---|---|---|
| 2022 | −0.036035220107766154 | −0.036035220107766150 |
| 2023 | +0.115794271396887318 | +0.115794271396887263 |
| 2024 | +0.178590194880741058 | +0.178590194880741016 |

The Spearman-against-forward-return variant gives materially different numbers
(−0.047388339, +0.147422399, +0.213265628) and is **not** what any gate in this
report was applied to. Any future audit must state which of the two it uses.

### 9.2 The `SD > 0.20` gate measures fold geometry, not instability

Model logit lag-1 autocorrelation, computed from the frozen predictions:
2022 `0.950155215`, 2023 `0.953868739`, 2024 `0.825003453`. Matched skill-free
AR(1) surrogates at each year's own phi, scored with the shipped IC definition
under the shipped fold layout (300 surrogates, seed 20260830):

| Year | Model per-fold SD | Null SD @ own phi (95%) | Null SD @ phi=0 | Ratio model/null |
|---|---|---|---|---|
| 2022 | 0.308066544 | 0.329937933 (0.297, 0.363) | 0.116716033 | 0.934 |
| 2023 | 0.301098723 | 0.330650509 (0.301, 0.362) | 0.118575241 | 0.911 |
| 2024 | 0.265557258 | 0.263829439 (0.232, 0.289) | 0.117999375 | 1.007 |

White noise passes the gate at ~0.117; every smooth null fails it. The threshold
sits between the two and therefore discriminates predictor smoothness, not
skill. **The §4 gate verdicts are retracted.**

The converse claim — that the model is *more stable than chance* because
0.27–0.31 < 0.33–0.40 — is **also rejected**. At the shipped IC definition and
the model's own phi the ratios are 0.93 / 0.91 / 1.01: 2024 is marginally
*looser* than its matched null. No stability claim in either direction is
supported.

### 9.3 The calibration negative is genuine, and is not a regularisation artifact

One review proposed that `λ=1` shrinks probabilities toward 0.5, mechanically
explaining the Brier gap without any signal failure. The frozen predictions
refute this:

| Year | Predicted probability range | Mean prediction | Realized up-rate | Pooled Brier |
|---|---|---|---|---|
| 2022 | 0.224922440 – 0.984959467 | 0.475163 | 0.469970 | 0.254103 |
| 2023 | 0.235087072 – 0.984768043 | 0.544957 | 0.514924 | 0.256172 |
| 2024 | 0.295677300 – 0.754622681 | 0.546022 | 0.538049 | 0.251171 |

2022 and 2023 span nearly the full unit interval — there is no shrinkage toward
0.5 to appeal to. Mean prediction tracks the realized base rate closely. Pooled
Brier is worse than realized-rate climatology **and worse than a constant 0.500
forecast** in all three years. The model issues confident forecasts and is wrong
often enough to lose to a coin flip. This is measured on pooled test bars with
no windowing, so none of the fold-geometry artifacts above can touch it.

**This is the finding that carries the STOP.** It is independent of IC, of fold
geometry, and of the retracted gate.

### 9.4 `p = 0.0000` is not a reportable value, and its null is too narrow

Two defects in the §4 permutation column:

1. **Reporting.** With 10,000 permutations the smallest expressible result is
   `p ≤ 1/(B+1)`. `0.000000000000000000` implies a precision the experiment
   cannot produce. Correct form: `p ≤ 0.0001`.
2. **Null width.** `permutation_test` (line 167) flips the sign of each per-fold
   IC *independently*, which assumes fold ICs are exchangeable. The 2023 per-fold
   IC series has lag-1 autocorrelation `+0.224600`, so that assumption fails
   there. Widening to a block sign-flip null (20,000 permutations, seed
   20260829):

| Year | Observed \|mean IC\| | block=1 (shipped) | block=2 | block=4 | block=8 |
|---|---|---|---|---|---|
| 2022 | 0.036035220 | z=1.26, p≤0.2116 | z=1.39 | z=1.38 | z=1.08 |
| 2023 | 0.115794271 | z=3.84, p≤0.0001 | z=3.32, p≤0.0008 | z=2.90, p≤0.0022 | z=2.48, p≤0.0090 |
| 2024 | 0.178590195 | z=6.03, p≤0.0001 | z=5.28 | z=4.29 | z=3.23, p≤0.0002 |

Significance survives block-widening in 2023 and 2024 — it is attenuated, not
eliminated. 2022 is insignificant under every block size. The shipped p-values
are directionally right but overstated.

### 9.5 §4's provenance sentence is wrong

§4 states the per-year rows come from "re-running the frozen
`ic_stability_diagnostic` gate per year". That is not possible as written:
`ic_stability_diagnostic.FOLD_COUNT` is hardcoded to `117` and the module raises
`IC diagnostic requires exactly 117 folds` on any other input. 2022 and 2023
have 116 folds each, so the shipped module rejects both.

The **numbers themselves are correct**. Patching `FOLD_COUNT` to the true
per-year count reproduces every published value bit-for-bit — 2022 CI
`(−0.091155211770409859, +0.019806460738069430)`, p `0.205400000000000000`;
2023 CI `(+0.062059419872473456, +0.170567500717519791)`. Only the provenance
claim is inaccurate: the 2022/2023 rows required an out-of-band fold-count
override that was never recorded. `FOLD_COUNT` should become a parameter rather
than a module constant.

### 9.6 Two previously-flagged leakage risks are cleared

- **Climatology is causal.** `climatology_probability(up_count, down_count)`
  (line 504) draws its counts from `train_directions` only. No future
  information enters the baseline. The §3 comparison is fair.
- **The 24-bar embargo is sufficient, not marginal.** `folds.py:120` sets
  `train_end = test_start - 24`. The last training row at `test_start − 25`
  carries label `sign(close[test_start−1] − close[test_start−25])`, which
  resolves strictly before the test window opens. Zero overlap. Earlier
  characterisations of this as "minimum possible, zero margin" were alarmist.

### 9.7 Claims withdrawn from the surrounding analysis

- *"Base rates 47–54% means direction is near-coin-flip by construction."*
  **Withdrawn.** Unconditional class balance constrains a constant classifier
  only; it says nothing about whether `P(Y=1|X)` carries structure. A perfectly
  predictable binary process can sit at exactly 50%.
- *"72 bars = 3 independent label observations."* **Softened to intuition.**
  Effective sample size depends on the full autocorrelation structure of the
  binary labels, not on `N / horizon`.
- *"Unpassable for any smooth predictor."* **Softened.** Demonstrated for
  several relevant smooth nulls (phi 0.83–0.98); not proven as a general
  theorem.
- The §3 IC-vs-accuracy rank inversion is **downgraded from a finding to an
  observation**. With n=3, a perfect rank inversion arises by chance with
  probability 1/6 under independence, and the rising base rate (0.4694 → 0.5268
  → 0.5372) mechanically makes the majority baseline harder to beat.

### 9.8 Corrected verdict

**STOP stands.** Restated on surviving evidence only:

- The frozen 012 model's probability forecasts are worse than both
  realized-rate climatology and a constant 0.500 forecast in all three years,
  measured pooled with no windowing. *(§9.3, decisive)*
- It fails to beat the training-window majority baseline in 2023 and 2024.
  *(§3, unchanged)*
- 2022's mean IC is statistically indistinguishable from noise under every null
  tested. *(§4 CI + §9.4)*
- The stability gate that produced three formal `STOP_PUBLISH_NEGATIVE`
  verdicts was invalid and contributes nothing. *(§9.2)*

**Genuinely unresolved:** whether weak ranking information survives underneath
the failed probabilities. Every IC number in this report is computed on 72-bar
folds against 24h-overlapping labels, a geometry §9.2 shows is artifact-prone.
That question is addressed by the pre-registered phase-partitioned AUC test
(`docs/research/015c-phase-auc-prereg.md`), which must be committed before the
statistic is computed.

**Data-snooping limit.** 2022–2024 were used to diagnose these defects and to
choose the replacement measurement. They can no longer serve as confirmatory
evidence. A pass on the phase-AUC test licenses one pre-registered attempt with
genuinely new information, judged once on sealed 2025 — it does not validate
012.
