# Quantara Protocol v1 — Deep Audit of GPT, Claude, and Gemini Reviews

**Date:** 2026-09-01  
**Status:** COMPLETE REVIEW SYNTHESIS — no frozen protocol artifact changed  
**Decision:** Create an explicitly authorized successor protocol before Stage 2; do not execute any reviewer answer verbatim

## 1. Scope and evidence

This audit checks the three responses in `answer.txt` against:

- `docs/superpowers/specs/2026-08-31-quantara-protocol-v1.md`
- `configs/protocols/quantara-protocol-v1.yaml`
- Frozen semantic hash `91457d3f1497abfd4e20cf4624768a5d9e9ba4b4478008fb4c7f65c17d90c65a`
- `docs/superpowers/plans/2026-08-31-a9-second-btc-venue-kraken.md`
- `docs/superpowers/plans/2026-08-31-a10-live-acquisition-consolidation.md`
- The committed exact-Decimal implementation at `HEAD:src/quantara/training_metrics_logistic.py`
- Independent timestamp arithmetic executed locally
- Current official-source search results for Binance OI/funding and Kraken OHLCVT

The three responses were treated as untrusted technical proposals. Agreement among models was not treated as proof.

## 2. Executive conclusion

All three reviewers reached the correct high-level verdict:

```text
PROCEED_WITH_SUCCESSOR_VERSION
```

Protocol v1 has a sound narrow confirmatory design, but it is not deterministic enough to execute unchanged. A successor version is required because the current frozen artifacts do not uniquely define several result-determining operations.

The required successor is a specification repair, not a model reset. It does not require:

- A new target family.
- A new model family.
- A feature search.
- Removing signed ETH or Kraken returns.
- Adding a volatility floor.
- Tuning lambda on 2022–2024.
- Unsealing 2025.

No reviewer supplied a fully valid executable successor specification. Each mixed correct defect detection with arbitrary or incorrect proposed constants.

## 3. Reliability of the three reviews

### GPT

**Strongest overall issue detection and timestamp arithmetic.**

Correctly identified:

- Funding boundary contradiction.
- Q80 underspecification.
- Exact purge inequality.
- Bootstrap underspecification and need for null centering.
- Unnamed `M2 + Kraken` branch.
- Optional-selection claim limitation.
- Final refit boundary.
- Missing 2025 replication rule.
- Signed returns are not a validity defect.

Material weaknesses:

- Invented 80-digit estimator precision despite an existing 50-digit committed contract.
- Invented a near-zero pivot threshold.
- Proposed zeroing constant columns instead of preserving the existing fail-closed rule.
- Claimed current Binance OI documentation establishes a period-end timestamp, which was not established by the accessible official evidence and does not prove the historical archive schema.
- Proposed a 2025 bias threshold of 0.04 rather than the existing pooled 0.02 concept.
- Missed the 2026 endpoint buffer needed for all 2025 origins.

**Use:** primary issue checklist, not executable patch.

### Claude

**Strong logical defect detection, weaker statistical prescriptions.**

Correctly identified:

- Funding contradiction.
- Quantile ambiguity.
- Bootstrap incompleteness.
- Estimator incompleteness.
- Purge equality.
- `M2K` naming need.
- Optional-selection claim limitation.

Material weaknesses:

- Proposed a branch-dependent full-alpha gatekeeping scheme without establishing strong family-wise error control.
- Its own F-07 and D.9 disagree about whether Kraken is tested after ETH passes.
- Its bootstrap p-value direction and null construction are incomplete.
- Suggested excluding a failed fit from a fold, which is not fail-closed and can favorably omit evidence.
- Proposed reusing all seven multi-year gates in one 2025 year, which is impossible literally.
- Elevated an already disclosed USD/USDT interpretation limitation to a protocol-validity defect.

**Use:** issue checklist only.

### Gemini

**Useful defect discovery, weakest proposed correction set.**

Correctly identified:

- Funding contradiction.
- Quantile ambiguity.
- Bootstrap incompleteness.
- `M2K` naming need.
- Missing final refit and replication rules.
- Need for estimator failure behavior.

Material errors:

- Bootstrap p-value resamples the raw empirical distribution without a properly imposed null.
- Calls a branch-dependent ordered test “Holm” when it is not ordinary Holm.
- Gives the final training cutoff as `2024-12-30 23:00`, one hour too early.
- Invents easier 2025 thresholds: 1.5% BSS, bias 0.03, and slope 0.75–1.25.
- Incorrectly declares signed returns a validity defect.
- Proposes a denominator floor that changes the target and violates the frozen no-epsilon rule.
- Mixes IEEE-754 floats with the exact-Decimal estimator contract.
- Makes unsupported archive-immutability and network-latency claims.

**Use:** defect checklist only; do not adopt its change set.

## 4. Verified BLOCKER findings

### B1 — Funding at `T` is contradictory

Frozen rules say:

```text
funding window:       T-24h < settlement_ts <= T
funding eligibility:  F + 1 ms
prediction time:      T + 1 ms
join:                 eligibility_ts < prediction_ts
```

For `F = T`:

```text
T + 1 ms < T + 1 ms  => false
```

The feature formula includes the settlement while the point-in-time join excludes it.

**Accepted diagnosis:** all three.

**Chosen successor correction:**

```text
boundary event time:       F = T
nominal eligibility:       T + 1 ms
prediction time:           T + 2 ms
join:                      eligibility_ts < prediction_ts
funding feature window:    T-24h < settlement_ts <= T
```

Why this correction:

- Preserves the intended closed upper funding window.
- Preserves the rule that funding becomes eligible only after settlement.
- Preserves strict `<` eligibility.
- Uses milliseconds as logical ordering ticks, not as a claim about historical network latency.

Production use still requires measured live publication/ingestion latency. If live latency exceeds the decision schedule, same-boundary funding must shift to the next live decision.

Rejected alternatives:

- `eligibility_ts = F`: coherent but removes the frozen “after settlement” ordering tick.
- Change window to `< T`: causal and conservative but changes the intended feature by delaying boundary settlements one hour.

Second-round qualification: `< T` is a legitimate smaller textual correction, but an exactly-at-`T` settlement would first appear at the next hourly origin and is therefore delayed one hourly decision relative to the frozen `(T-24h,T]` intent. Moving the universal nominal prediction ordering to `T+2ms` is a broader convention change, so Protocol v1.1 must name it explicitly and boundary-test every source. Under the current contracts, completed klines, five-minute OI, and Kraken hourly candles are already eligible no later than `T`; the added tick therefore changes current same-boundary inclusion for funding, not those other series.

### B2 — Exact Q80 algorithm is absent

“Empirical Q80” does not uniquely determine `k`.

**Chosen successor correction:** nearest-rank inverse empirical CDF.

For sorted eligible design values:

```text
Z_(1) <= ... <= Z_(N)
j = ceil(0.80 * N)
k = Z_(j)
Y_t = 1[Z_t > k]
```

Rules:

- Compute `Z` under the existing 50-digit `ROUND_HALF_EVEN` Decimal context.
- Do not interpolate.
- Do not round `k` to 8 decimals.
- Preserve the canonical full Decimal string for `k`.
- Ties require no timestamp tie-break because tied values are numerically equal.
- Add a synthetic quantile fixture and an actual frozen `k` fixture/hash before any 2022–2024 scoring.
- Keep `k` fixed through every fold and sealed 2025.

Type 7 and Type 8 are defensible alternatives, but neither is scientifically required. Nearest-rank is chosen because it matches the generalized inverse empirical-CDF meaning of “empirical quantile” and introduces no interpolated threshold.

### B3 — Purge boundary lacks exact inequalities

For first test origin `S`, the chosen rule is:

```text
training origin O is eligible iff O + 24h <= S
last eligible training origin = S - 24h
first test origin = S
```

Under the frozen close convention, origin `S-24h` requires the future close at `S-1ms`, which is available before the prediction after `S`.

Verified examples:

```text
Fold 1 S:                  2022-01-01 00:00 UTC
last training origin:      2021-12-31 00:00 UTC
last required label close: 2021-12-31 23:59:59.999 UTC

2025 S:                    2025-01-01 00:00 UTC
last training origin:      2024-12-31 00:00 UTC
last required label close: 2024-12-31 23:59:59.999 UTC
```

Gemini’s `2024-12-30 23:00` cutoff is wrong by one hour and is rejected.

No post-test embargo is required for the anchored expanding-window design.

### B4 — Bootstrap is not executable reproducibly

The successor must freeze one complete algorithm.

**Chosen algorithm:**

1. For every candidate/comparator pair, form paired hourly Brier-loss improvements:

   ```text
   d_t = loss_comparator,t - loss_candidate,t
   ```

   Positive favors the candidate.

2. Build the complete nominal hourly UTC grid separately for each calendar year. Candidate and comparator use identical timestamps. Store `d_t` on paired-valid hours and null on every other hour; never fill a missing loss value.

3. Use non-circular overlapping blocks of exactly 168 consecutive **clock hours** on that full grid. Blocks retain their observed null pattern. Eligible starts are `0 ... H_y-L`, where `H_y` is the nominal number of calendar hours in year `y`.

4. Sample `ceil(H_y/L)` block starts with replacement, concatenate the blocks including nulls, and truncate to exactly `H_y` clock-hour positions.

5. For each resampled year, calculate the loss-difference sum and paired-valid count using only non-null positions. Resample each year separately and pool by the resampled paired-valid count:

   ```text
   D* = sum_y sum_valid_i d*_(y,i) / sum_y n*_valid,y
   ```

6. Use exactly 20,000 resamples in the successor version. Freeze one exact PRNG algorithm, implementation version, comparison-specific stream derivation, and golden resampled-index fixture. A seed alone is insufficient.

   This increase from the already-frozen 2,000 is a deliberate inferential strengthening, not merely completion of an omitted detail. At the smallest first-step Holm threshold `0.05/3`, the normal-approximation 95% Monte Carlo half-width is approximately `0.005610684252190438` with 2,000 resamples and `0.001774254146896035` with 20,000. Achieving a half-width no greater than `0.002` requires approximately 15,740 resamples, so 20,000 is the frozen round-number choice. This must be disclosed as a successor-version design change.

7. Two-sided 95% CI: percentile interval from the raw-bootstrap pooled means, using a frozen nearest-rank empirical-quantile convention.

8. One-sided null test for positive improvement:

   ```text
   D_obs = mean_pooled(d)
   d0_t  = d_t - D_obs
   p     = (1 + count(D0*_b >= D_obs)) / (B + 1)
   ```

   where `D0*` is generated by the identical bootstrap from the null-centered series.

9. If an observed year has fewer than 168 paired-valid observations, or a replicate has no paired-valid observation in any required year, inference fails closed for that comparison.

10. Add golden fixtures for indices, pooled statistic, CI, and p-value.

Gemini’s raw-bootstrap count at or below zero is rejected as an inadequately specified null test. Claude’s “favorable resamples” formula is rejected as directionally ambiguous.

This year-stratified 168-clock-hour moving-block procedure is also the explicit
dependence correction for the overlapping 24-hour labels at hourly origins.
Consecutive origins are not treated as IID for inference. The pooled hourly mean
remains the estimand, while blocks preserve the serial dependence of the paired
loss differential. Non-overlapping 24-hour origin subsampling is rejected for the
primary test because it discards information and makes the result depend on an
arbitrary hourly phase; it may be reported only as a frozen diagnostic if a
successor protocol explicitly authorizes it before scoring.

### B5 — Deterministic estimator details are underbound in the protocol

The repository already contains a tested exact-Decimal contract. Do not invent another solver.

The successor should bind to the committed implementation contract:

```text
Decimal precision:        50
rounding:                 ROUND_HALF_EVEN
storage quantum:          1e-18
standardization variance: population denominator n
initial coefficients:     all zero
lambda:                    1
intercept:                 unpenalized
convergence:               every abs(beta_new-beta_old) < 1e-12
maximum updates:           50
pivot failure:             exact-zero pivot
constant train feature:    fail closed
non-convergence:           fail closed
binary float inputs:       forbidden
```

Additional successor rules:

- Training outcomes must contain both classes; otherwise fail closed.
- Any fit failure fails the affected candidate comparison; never omit the fold or candidate from pooling.
- Calibration regression uses an unpenalized two-parameter Decimal logistic fit on `x = logit(p)`. If the shared IRLS routine standardizes `x` to `z=(x-mu_x)/sd_x`, call it with `lambda=0` and convert the fitted standardized coefficients back to the required raw-logit scale:

  ```text
  calibration_slope     = beta_z / sd_x
  calibration_intercept = beta_0 - beta_z * mu_x / sd_x
  ```

  The calibration gate applies to this raw-logit slope. A single-class outcome, zero-variance `logit(p)`, undefined logit, singular solve, separation, or non-convergence fails the calibration gate.
- Add golden coefficient, probability, and failure fixtures for variable-width Protocol-v1 models.

Rejected reviewer inventions:

- 80-digit precision.
- IEEE-754 float arithmetic.
- Condition-number threshold `1e14`.
- Pivot threshold `1e-40`.
- Coefficient-magnitude separation threshold 50.
- Silently fixing constant columns to zero.
- Dropping a failed fold from the pooled result.

### B6 — Optional-family graph is not fixed

Name both Kraken candidates:

```text
M2K = M2 + frozen four-column Kraken block
M4  = M3 + frozen four-column Kraken block
```

Freeze and compute all three optional hypotheses before making retention decisions:

```text
H_ETH:    M3  vs M2
H_K_M2:   M2K vs M2
H_K_M3:   M4  vs M3
```

Apply ordinary Holm at family-wise alpha 0.05 across all three p-values. Holm thresholds are assigned after sorting observed p-values, not permanently assigned to model names.

Retention path:

```text
If H_ETH passes all statistical/effect/year gates:
    retain M3;
    retain M4 only if H_K_M3 also passes all gates.
Else:
    retain M2;
    retain M2K only if H_K_M2 passes all gates.
```

The unused branch is still computed and multiplicity-controlled but receives no retention authority on that path.

This is more conservative and easier to audit than an incompletely specified branch-dependent gatekeeping procedure.

### B7 — Final 2025 refit is absent

Before the one-time 2025 score:

- Identify the retained candidate under the frozen 2022–2024 rules.
- Refit the retained candidate and paired B2 on identical retained-candidate complete-case origins.
- Use all origins from the frozen training start satisfying:

  ```text
  O + 24h <= 2025-01-01 00:00 UTC
  ```

- Therefore the last possible training origin is:

  ```text
  2024-12-31 00:00 UTC
  ```

- Fit means and standard deviations only on those rows.
- Keep target `k`, features, lambda, clamps, estimator, and probability treatment unchanged.
- A final-fit failure emits `FINAL_FIT_FAILURE`; it does not permit tuning or rerunning 2025.

### B8 — A full 2025 origin set requires a 2026 label buffer

This was omitted by all three original reviewers.

The final calendar-2025 hourly origin is:

```text
2025-12-31 23:00 UTC
```

Its 24-hour target requires the BTC perpetual close at:

```text
2026-01-01 22:59:59.999 UTC
```

The successor must choose one rule before unsealing:

**Chosen rule:** enumerate and provide label support for all 8,760 calendar-2025 hourly origins, then score only the retained candidate's point-in-time complete-case eligible origins. Acquire a sealed BTC-target-only endpoint buffer through `2026-01-01 22:59:59.999 UTC`. No 2026 feature origin is scored, and no non-target 2026 feature data is needed for the 2025 origins.

The endpoint buffer must be covered by the same seal, hash, and no-inspection rules as 2025.

### B9 — `REPLICATED` is undefined

For the complete retained candidate versus paired B2 on all eligible calendar-2025 origins:

```text
REPLICATED iff all hold:
1. BSS_B2 >= 0.02
2. two-sided 95% bootstrap CI lower bound for BS_B2 - BS_candidate > 0
3. abs(mean(p-y)) <= 0.02
4. calibration slope is in [0.8, 1.2]
5. calibration regression is defined and converges

Otherwise: DID_NOT_REPLICATE
```

The multi-year rules “positive in two of three years” and “no year below -2%” do not apply to one calendar year.

Claim scope:

- `REPLICATED` means the complete retained frozen model replicated aggregate probability-forecast improvement versus paired B2 in calendar 2025.
- It does not prove every ETH or Kraken feature independently replicated.
- The frozen component chain should also be scored once in 2025 as claim-specific diagnostics. ETH or Kraken may be described as individually replicated only if its frozen parent comparison independently satisfies the same applicable one-year gate.

Gemini’s weaker 1.5%/0.03/0.75–1.25 gate is rejected. GPT’s 0.04 bias threshold is rejected. Claude’s literal reuse of all seven multi-year conditions is impossible and rejected.

## 5. Verified HIGH finding: OI timestamp semantics

The frozen protocol calls the five-minute OI timestamp an interval start. The authoritative A10 consolidation says:

```text
create_time semantics are not frozen as “bar open”; use conservative eligibility
```

Current accessible official Binance search results expose a `timestamp` field but did not establish start-versus-end semantics. The current REST endpoint schema also does not prove the historical `data.binance.vision` metrics archive’s `create_time` semantics.

Therefore:

- Reject GPT’s categorical “period end” claim as unproven for this archive.
- Reject the earlier A2 “bar open” claim because A10 superseded it.
- Before OI canonicalization, perform an archive-specific semantics check.
- If start/end meaning remains unresolved, preserve the native provider timestamp without falsely labeling it open or close and use the frozen conservative eligibility `provider_timestamp + 5 minutes`.
- At an hourly decision boundary, the latest eligible grid row is then the latest row satisfying that conservative rule.
- Record the uncertainty and measured/cited evidence in the source contract.

This can remain causally safe even if conservative, but it must not make a false semantic claim.

## 6. Source-semantics decisions

### Kraken

The authoritative A9 audit states that Kraken documents candle timestamps as interval starts. Preserve the interval-start timestamp and derive close eligibility after one full interval. GPT and Claude were wrong to treat this as wholly unverified against the project evidence.

### Funding

The archive represents settled/effective funding events, but historical network publication latency is not reconstructed. The successor supports only nominal historical point-in-time claims. Production requires measured live replay.

### Kliness, mark, index, premium, and spot

Use completed source-native bars only after source close and the frozen nominal ordering delay. Preserve all native gaps and block any feature window crossing an invalid required interval.

### Revision/immutability claims

Do not claim that Binance or Kraken data has no revision risk. Preserve source bytes and hashes, detect re-fetch mutations, and treat archive publication as provenance rather than original event-time availability.

## 7. Rejected proposed scientific changes

### Signed return transformations

Do not replace signed ETH or Kraken returns merely because the target is unsigned.

A signed predictor can capture asymmetric response: large negative ETH moves may carry different information from equally large positive moves. The model also contains realized-volatility features for magnitude. Inability of one signed linear term to encode a symmetric U-shape is a model-capacity limitation, not a validity defect.

Gemini’s absolute/log-absolute replacements and epsilon are rejected for this protocol.

### Volatility denominator floor

Do not add a Q01 or epsilon floor. It changes the target and contradicts the frozen zero/incomplete-window invalidation rule.

Allowed non-selective diagnostic:

- Report the trailing-sigma distribution.
- Report target prevalence by sigma decile.
- Report whether the lowest sigma decile dominates positive labels.

These diagnostics cannot alter Protocol v1.1 after scored-period access.

### Arbitrary 98% coverage threshold

Do not add an unsupported 98% pass threshold.

Require instead:

- Candidate-eligible rows and percentage by year.
- Exclusion reasons.
- Longest missing run.
- Explicit claim that the result applies to candidate-complete timestamps.
- At least 168 paired observations per year for the selected bootstrap.

Any later minimum-coverage threshold needs separate justification and preregistration.

### Kraken USD/USDT confound

This is an interpretation limitation already disclosed by the frozen protocol, not leakage or a validity blocker. A passing Kraken family supports a cross-venue and cross-quote family, not pure venue price discovery.

Do not add a new stablecoin data family merely to relabel the claim. A future protocol may investigate that mechanism.

## 8. ETH decisions

Keep the current M3 feature block unchanged:

```text
ETH 1h signed log return
ETH 24h realized volatility
ETH settled funding 24h sum
ETH native-premium 1h mean
ETH/BTC relative 24h log return
```

Keep ETH OI (`M3b`) diagnostic-only on the frozen identical post-2021-12-01 common sample. It receives no retention rights in this experiment.

Optional attribution diagnostics may report:

- ETH market-state sub-block.
- ETH derivatives sub-block.
- ETH/BTC relative-return sub-block.

They must be explicitly descriptive, non-selective, outside candidate retention, and unable to trigger feature changes or 2025 access.

## 9. Development and claim policy

The fixed `lambda=1`, no-search Protocol v1 design is valid for a narrow claim:

> whether this exact preregistered model and information-family ladder improves probability forecasts beyond paired B2.

A failure does not prove that no linear or nonlinear signal exists. It proves only that this frozen recipe did not satisfy its gate.

The correct sequence is:

1. Repair deterministic ambiguities in Protocol v1.1 before scoring.
2. Execute Protocol v1.1 once on 2022–2024.
3. Preserve each gate independently.
4. If desired afterward, treat 2020–2024 as opened development data for a separately preregistered successor model.
5. Keep 2025 and its 2026 endpoint buffer sealed until one final model is frozen.
6. Evaluate 2025 once.

Do not silently convert Protocol v1.1 into iterative 2020–2024 model search.

### 9.1 Protocol lineage and intentional supersession

An earlier Quantara recommendation dated 2026-08-24 proposed a materially
different MVP: BTCUSDT perpetual decisions every completed 15-minute candle, a
fixed one-hour executable immediate-entry policy, regularized logistic regression
or simple return regression as the primary model, LightGBM as a designated
secondary model, and both predictive and after-cost economic metrics.

Protocol v1 intentionally supersedes that proposal. It changes the estimand from
an executable directional one-hour policy to the probability of an unusually
large *undirected* 24-hour BTC move, changes cadence from 15 minutes to hourly,
removes the trading-policy/PnL layer, and freezes an exact-Decimal logistic model
ladder to isolate the incremental value of preregistered information families.
LightGBM was therefore a real earlier recommendation, but it is not an omitted
Protocol-v1 candidate. Reintroducing LightGBM, XGBoost, return regression,
directional actions, or economic gates requires a separately preregistered
successor experiment and may not be interpreted as a Protocol-v1 correction.

## 10. Final accepted successor-version change set

A single successor protocol should contain all of the following before Stage 2 begins:

1. Prediction ordering changed to `T+2ms`, preserving funding eligibility at `F+1ms` and funding window `(T-24h,T]`.
2. Nearest-rank Q80 under the 50-digit Decimal contract, with actual and synthetic fixtures.
3. Exact train-boundary rule `O+24h <= S`.
4. Complete non-circular year-stratified 168-clock-hour moving-block bootstrap on full hourly grids with preserved null patterns, null-centered p-value, percentile CI, exact PRNG, 20,000 resamples, and fixtures.
5. Protocol binding to the existing committed exact-Decimal IRLS contract plus explicit both-class and calibration-failure rules.
6. Named `M2K` and three fixed optional hypotheses with Holm across all three.
7. Optional-block 2022–2024 results labeled selection evidence, not independent replication.
8. Archive-specific OI timestamp resolution or explicitly conservative unknown-role handling before canonicalization.
9. Exact final pre-2025 refit sample and failure state.
10. Sealed BTC target buffer through `2026-01-01 22:59:59.999 UTC` for all 2025 origins.
11. Exact one-year 2025 `REPLICATED` gate.
12. Coverage/exclusion reporting and claim scope for every candidate.
13. No signed-return replacement, sigma floor, arbitrary coverage cutoff, or new feature search.
14. A dated protocol-lineage record stating that Protocol v1 intentionally supersedes the earlier 15-minute/one-hour executable-policy proposal and its secondary LightGBM model.

Because these are semantic changes, the successor requires:

- New version identifier.
- Updated human specification.
- Updated machine YAML.
- Updated independent expected fixture.
- New semantic SHA-256.
- Repeated tamper, future-mutation, boundary, solver, bootstrap, and 2025-seal tests.
- Independent Hermes audit before Zcode proceeds.

## 11. Final verdict

```text
GPT:    useful and strongest, but not executable verbatim
Claude: useful issue detector, but several invalid prescriptions
Gemini: useful issue detector, but substantial correction required

Protocol decision: PROCEED_WITH_SUCCESSOR_VERSION
Scientific reset:  NO
Feature redesign:   NO
Unseal 2025:        NO
Stage 2 unchanged:  BLOCKED until successor protocol is authorized and frozen
```

## 12. Second-round reviewer response

The completed audit was returned to GPT, Claude, and Gemini for criticism.

- **Gemini:** accepted the correction set and repeated its principal contracts without identifying a new BLOCKER/HIGH defect.
- **GPT:** accepted the audit as superseding its earlier proposal, explicitly conceding the 50-digit estimator contract, unresolved archive-specific OI timestamp role, 0.02 bias gate, and missing 2026 target buffer.
- **Claude:** conceded the invalid fallback multiplicity procedure, internal branch inconsistency, missing null-centered bootstrap, invalid one-year reuse of multi-year gates, and unsafe failed-fit omission. Its funding and resample-count qualifications are addressed above.

No second-round response establishes a new BLOCKER or HIGH defect in the accepted correction set. This does not itself freeze Protocol v1.1: the next review target must be the actual updated human specification, machine YAML, fixtures, semantic hash, and executable tests.
