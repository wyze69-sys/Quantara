# Slice 015-extended-b — Acquire 2023 + 015b Multi-Year Validation on 2022+2023+2024

**Status:** COMPLETE — all gates G1–G5 closed. Verdict:
STOP-regime-conditioning (B5) with a REDESIGN flag from 2022.
Result: `docs/research/015b-multi-year-results-2022-2023-2024.md`

**Post-closure follow-on (2026-08-30):** the closed report was audited and
corrected — see its §9. The `SD > 0.20` stability gate is **retracted** (it
measures fold geometry, not skill), and `p = 0.0000` is restated as
`p <= 1/(B+1)`. The B5 next-step recorded above is **superseded**: B5 would have
selected on IC measured under artifact-prone geometry. The replacement test —
pre-registered in `docs/research/015c-phase-auc-prereg.md` and answered in
`docs/research/015c-phase-auc-results.md` — returned **TERMINATE** for the
OHLCV-only 24h-direction line, and located this slice's artifact as the 72-bar
fold windowing rather than the 24h label overlap.
**Date:** 2026-08-29 (closed 2026-08-30)
**Starting HEAD:** `14717883564073e6df6757702eefab7c76d228d3` (main, clean, synced with origin)

**Executed deviation (owner-approved, "Path A"):** G4 §4's single concatenated
26,304-row run at `min_train_size=8,760` / 243 folds is **not executable** — the
frozen `load_validation_descriptor` rejects `min_train_size: 8760` as
`unsupported_parameter` and rejects any multi-year period, and the 012 KILL
commit's recorded `fold_count: 117` proves the frozen model used
`min_train_size=336`. The plan's "012 unchanged" and "min_train_size=8,760"
requirements contradict each other. Executed instead as three independent
per-year runs at the genuinely frozen parameters: **349 folds
(116 + 116 + 117)**, all at one code revision `47e4026`. See report §0.1.
**Provenance:** this slice implements the GPT-recommended path out of the 015-extended
report's three options. The 2020-2021 headerless-archive blocker (see
`docs/research/per-year-feature-distribution-2020-2022.md` §9) is real and
correctly requires a spec amendment to resolve; that amendment is deferred to a
later slice. The 2022+2023+2024 corpus is **headered, acquirable now, and gives
three distinct regimes** (bear/recovery/bull) which is what 015b actually needs to
answer the cross-year question.

## 0. Owner authorization (read first)

This slice **acquires one additional year of OHLCV (2023) into the existing data
store**, then runs the frozen 012 logistic model on the resulting
**2022+2023+2024 = 26,304 1h-row corpus** using expanding-window walk-forward.

The 2023 acquisition follows the same `Acquirer` path the 015-extended slice used
for 2020-2022. The 015b run uses the same 012 pipeline code unchanged
(`λ=1`, 4 features, logistic IRLS, test_size=72, embargo=24). **No model
configuration changes, no new features, no regime filter, no spec amendment.**

No rights-record change is required. v3 already covers "data.binance.vision public
archives" generically. Private research evidence only; no customer display, no
redistribution, no commercial production use, no live trading.

## 1. Why 2023, not 2020-2021 (or 2022+2024 only)

The 015-extended report §9 offered three options. The reasoning for picking 2023:

- **Option 1 (positional-schema amendment for 2020-2021)** is the correct long-term
  fix but is multi-day, touches identity (re-pinning all downstream artifacts), and
  doesn't change the answer to 015b's question.
- **Option 2 (2022+2024 only, 121 folds)** gives bear + bull but no recovery. The
  narrow-evidence problem this slice exists to fix is not solved.
- **Option 3 (add 2023, 243 folds across bear/recovery/bull)** is the cheapest path
  to a genuinely multi-regime test. 2023 is headered, so no spec amendment needed.
  The corpus gains a third distinct regime (recovery from the 2022 bear) which
  materially changes what 015b can conclude.

**2022 + 2023 + 2024 covers:**
- 2022: full bear (LUNA + FTX collapses, base rate 0.4694 down-majority)
- 2023: recovery (BTC ~$16k → ~$42k, mixed regime)
- 2024: bull (halving + ETF approval, base rate 0.5372 up-majority)

**Three distinct regimes, 243 folds, 26,304 rows.** That's the answer to "does
the 012 model generalize across regimes?" — not 121 folds and not 365 (which
requires the spec amendment).

## 2. Goal

Extend the verified data store from {2022, 2024} to {2022, 2023, 2024}, then run
the frozen 012 logistic IRLS model on the combined corpus with the pre-registered
gates and per-year outcome mapping. The slice produces:

- 1 new approved identity table in `descriptor.py` for 2023
- 3 new 1m/1h/1d descriptor YAMLs for 2023 (if needed; the 012 pipeline only
  needs 1h, but the per-year distribution report needs 1m and 1d for symmetry)
- 12 monthly 2023 ZIPs acquired and content-addressed
- 1h, 1d 2023 canonical content published (1m if 2023 also has zero-volume candles
  needing a quality approval; if 0 zero-volume, no approval YAML needed)
- 015b model run on {2022, 2023, 2024} 1h corpus
- Per-year outcome table (year × {IC, accuracy, log-loss, Brier, per-year IC SD})
- B3.5b cross-year decision gate verdict (PROCEED / PROCEED_WITH_CAVEAT / STOP /
  REDESIGN)

## 3. Verified facts (oracle check 2026-08-29)

- `data/datasets/binance/usdm/klines/BTCUSDT/1m/year=2024/month=01/` exists with
  full-year canonical content (1m = 525,600 rows, 1h = 8,784 rows, 1d = 366 rows).
- `data/datasets/binance/usdm/klines/BTCUSDT/1m/year=2022/month=01/` exists with
  full-year canonical content (1m = 525,600 rows, 1h = 8,760 rows, 1d = 365 rows).
- 2022 1h K1 base rate is **0.4694368131868** (down-majority), independently
  verified by reading the parquet and computing forward 24h direction.
- 2024 1h K1 base rate is **0.537214611872** (up-majority), from the 012 model
  work and confirmed by the 015-extended report.
- 2020/2021 archives are headerless (24 monthly ZIPs lack the CSV header row that
  the approved exact-header parser requires) — see 015-extended report §9.
- The V2 year-identity check at `descriptor.py:351` already accepts the 2024
  identity table via the `V2_YEAR_APPROVED_IDENTITIES` constant; the 015-extended
  slice added 2020/2021/2022 tables at lines 78-95. Adding 2023 follows the same
  pattern.
- 2023 is a headered year (Binance Vision changed format ~2022-01; 2022-01
  through present are headered, 2020/2021 are headerless). Confirmed by the
  015-extended report's "boundary is exact and clean" finding.

## 4. Pre-registered gates

### G1 — 2023 identity-table expansion

- New `V2_YEAR_APPROVED_IDENTITIES_2023` constant in `descriptor.py`, mirroring
  the 2020/2021/2022 patterns added by 015-extended
- New `V2_YEAR_DESCRIPTOR_KEYS_2023` constant with the same key set
- V2 year-identity check at `descriptor.py:351` updated to accept the 2023
  dataset_id (`binance_usdm_btcusdt_klines_1m_2023`)
- 1 new round-trip test in `tests/test_descriptor.py` with frozen JCS digest
- 1 new period-coverage test in `tests/test_rights_and_periods.py`
- All existing tests still pass (regression)

**Pass criterion:** all 5 conditions hold.

### G2 — 2023 acquisition (12 monthly ZIPs)

- HTTP 200 on all 12 `https://data.binance.vision/.../BTCUSDT-1m-2023-MM.zip`
- HTTP 200 on all 12 `.CHECKSUM` files
- Local SHA-256 == official digest for all 12
- Content-addressed under `data/objects/raw/sha256/<official_digest>`
- `AcquisitionEvidence` recorded per ZIP: zip_sha256, zip_size, reused_zip,
  reused_checksum, http_statuses, redirect_hops, retry_evidence

**Pass criterion:** all 12 ZIPs pass with SHA-256 chain verified.

### G3 — 2023 normalization

- 1m canonical content: 525,600 rows (calendar math: 365 days × 1440 = 525,600)
- 1h aggregated content: 8,760 rows
- 1d aggregated content: 365 rows
- 1h → 1d reconciliation: 0 mismatches across all 365 days
- Reruns are `VERIFIED_NO_OP` with byte-identical pointers
- Per-year zero-volume candle count: determine from the data; if 0, no quality
  approval YAML is needed (policy 1). If >0, create approval YAML per 015-extended
  pattern.

**Pass criterion:** row counts match calendar math, 1h→1d reconciliation clean.

### G4 — 015b run on {2022, 2023, 2024}

- 012 logistic IRLS model run UNCHANGED (`λ=1`, 4 features, IRLS, test_size=72,
  embargo=24, min_train_size=8,760, expanding-window walk-forward)
- 243 expanding-window folds across 26,304 1h rows
- Per-fold IC computed, per-year IC computed, cross-year IC SD computed
- Per-year outcome table produced (the primary output, per the post-B3.5 review)
- Pre-registered per-year outcome mapping applied (from 015-extended report §4
  and this plan §6 below)

**Pass criterion:** per-year table committed, all 4 metrics × 3 years populated.

### G5 — B3.5b cross-year decision gate

- Cross-year IC SD computed across the 243 folds
- Threshold = B3.5 within-2024 SD (0.2656) × scaling_factor (pre-registered = 1.0)
- 4-way verdict: PROCEED (to B4) / PROCEED_WITH_CAVEAT / STOP-regime-conditioning
  (B5) / REDESIGN (014 derivatives)
- Per-year outcome mapping applied
- Verdict documented with full evidence

**Pass criterion:** verdict committed, audit trail complete.

## 5. Files changed (allowlist)

- `src/quantara/descriptor.py` — add `V2_YEAR_APPROVED_IDENTITIES_2023` and
  `V2_YEAR_DESCRIPTOR_KEYS_2023` constants (~10 lines)
- `configs/datasets/binance-usdm-btcusdt-1m-2023.yaml` — new file (mirror of 2022)
- `configs/datasets/binance-usdm-btcusdt-1h-2023-derived.yaml` — new file
- `configs/datasets/binance-usdm-btcusdt-1d-2023-derived.yaml` — new file
- `configs/quality/approvals/binance-usdm-btcusdt-1m-2023-zero-volume.v1.yaml` —
  new file (only if 2023 has zero-volume candles; otherwise not created)
- `tests/conftest.py` — add 2023 helper (~5 lines)
- `tests/test_descriptor.py` — add 1 round-trip test
- `tests/test_rights_and_periods.py` — add 1 period test
- `docs/research/015b-multi-year-results-2022-2023-2024.md` — new report (the
  015b output, per-year table, B3.5b verdict)
- `data/attempts/training/<timestamp>-<uuid>.json` — 015b attempt manifest
  (untracked, but written to the data store)

**Files NOT changed:**
- `data/datasets/.../commits/` of 2020/2021/2022/2024 (existing canonical content
  is byte-identical at exit)
- `configs/legal/*` (v3 already covers 2023)
- `src/quantara/{training_pipeline,training_metrics_logistic,acquisition,
  derive_pipeline,pipeline}.py` (existing code handles 2023 without modification)
- `src/quantara/ic_stability_diagnostic.py` (existing B3.5 module is reused;
  no code changes)
- 2020/2021 descriptors or data (headered-format amendment deferred to a
  separate slice)
- 2025 (still untouched)

## 6. Pre-registered per-year outcome mapping (carried from 015-extended)

For the per-year IC value:

| Per-year IC | Verdict | Next move |
|---|---|---|
| IC > 0.10 | survives | 015b holds; if 2 of 3 years pass, B5 may be skipped |
| IC ∈ [0, 0.10] | weakens | STOP at global level; regime conditioning (B5) required |
| IC < 0 | inverts | REDESIGN; current feature set is wrong for that regime |

For the per-year accuracy (against per-fold majority class, NOT the global 0.5349 bar):

| Per-year accuracy | Verdict | Note |
|---|---|---|
| accuracy > majority class baseline | skill | model adds value over trivial |
| accuracy ≈ majority class baseline | no skill | model matches trivial predictor |
| accuracy < majority class baseline | anti-skill | model is worse than trivial |

**The global 0.5349 K1 bar is NOT a valid cross-year target.** It was a 2024-specific
artifact. The base rate ranges from 0.4694 (2022) to 0.5372 (2024), an 11-point
swing. Per-year baselines are derived from each year's training-window majority
class.

## 7. What this slice explicitly does NOT do

- **Does NOT add 014 derivatives features.** Both GPT and Claude agreed: cheap
  features must be validated on multi-year data first.
- **Does NOT touch the 2020-2021 headerless archives.** Spec amendment deferred.
- **Does NOT amend the descriptor for headerless variants.** Same as above.
- **Does NOT touch 2025 data.** Remains the OOS canary.
- **Does NOT tune the 012 model.** `λ=1` is frozen; if results suggest
  under-regularization, that is a finding for a follow-up slice, not a fix here.
- **Does NOT add a regime classifier or filter.** If 2022 inverts in 015b, B5 is
  the next slice, with a no-future-info regime-input design.
- **Does NOT change the rights record.** v3 already covers this.
- **Does NOT train any model other than 012.** No ridge, no new model classes.

## 8. T-criteria (executor T-checks)

- **T0 — unit tests pass:** `uv run pytest -m "not integration" -q` → expected
  ~867+ pass (864 baseline + 2-3 new tests for 2023)
- **T1 — descriptor changes verified:** `uv run pytest tests/test_descriptor.py
  tests/test_rights_and_periods.py -q` → all pass including the 1 new test
- **T2 — acquisition verification:** all 12 2023 monthly ZIPs acquired, all
  SHA-256s match, all content-addressed
- **T3 — normalization verification:** 1m 525,600 / 1h 8,760 / 1d 365 rows;
  1h→1d reconciliation 0 mismatches
- **T4 — 015b run on 3-year corpus:** 243 folds, per-year table complete,
  cross-year SD computed
- **T5 — frozen state unchanged:** 012 KILL attempt manifest
  (`a8cacc8a3687d560ce7fbbd5adf416c23854611ec7c6fc514b7a1d20d07b756f`) byte-identical;
  2022 1h cch (`96c877600badd376a75b96c8c12d09cc5a52f7c167066b8a04a46217a87e4b3d`)
  byte-identical; all 7 (now 8) live pointers byte-for-byte restored at exit
- **T6 — repo hygiene:** `git ls-files data` returns 0; `uv run ruff check .`
  all checks pass; `git diff --check` clean; no file > 100 KB

## 9. Per-slice output (015b report structure)

`docs/research/015b-multi-year-results-2022-2023-2024.md` should have this structure:

```
# Slice 015b — Frozen-Model Multi-Year Validation on 2022+2023+2024

## 0. Provenance
- Date: 2026-08-29
- Slice: 015-extended-b
- Corpus: 2022 (8,760) + 2023 (8,760) + 2024 (8,784) = 26,304 1h rows
- Model: 012 frozen (lambda=1, 4 features, logistic IRLS, test_size=72, embargo=24)
- Walk-forward: expanding window, min_train_size=8,760
- Folds: 243 (= floor((26,304 - 8,760 - 24) / 72))

## 1. Per-year outcome table (PRIMARY OUTPUT)
| Year | Regime | N | Per-year IC | Per-year IC SD | Accuracy | Per-fold majority baseline | Log-loss | Brier |
| 2022 | full bear (LUNA/FTX) | 8,760 | ? | ? | ? | 0.4694 | ? | ? |
| 2023 | recovery             | 8,760 | ? | ? | ? | ?      | ? | ? |
| 2024 | bull (halving/ETF)   | 8,784 | ? | ? | ? | 0.5372 | ? | ? |
| Cross | mixed                | 26,304 | ? | cross-year SD: ? | ? | — | ? | ? |

## 2. Pre-registered per-year outcome mapping
For each year: which bucket does the IC fall into?
- 2022: [survives / weakens / inverts]?
- 2023: [survives / weakens / inverts]?
- 2024: [survives / weakens / inverts]?

## 3. Per-year accuracy vs per-fold majority baseline
For each year: is the model better than, equal to, or worse than the trivial
"predict the training-window majority class" baseline?

## 4. Cross-year B3.5b verdict
- Cross-year IC SD: ?
- B3.5 within-2024 SD: 0.2656
- Scaling factor: 1.0 (pre-registered)
- Threshold: 0.2656
- Verdict: [PROCEED / PROCEED_WITH_CAVEAT / STOP-regime-conditioning / REDESIGN]

## 5. Findings handed to B3.5b / B5
- Does any year invert? (informs whether B5 is needed)
- Does any year weaken dramatically? (informs B5 design)
- Does the per-fold IC distribution change across years?

## 6. What this does NOT answer
- Whether the signal works on 2020/2021 (headerless, deferred)
- Whether derivatives features (014) add value (deferred)
- Whether the model works on 2025 (untouched OOS canary)
```

## 10. Risks and unknowns

- **2023 zero-volume count.** Need to acquire first. If 2023 has zero-volume
  candles (likely in some maintenance windows), a quality approval YAML is needed
  for that year. If 0, no approval.
- **Acquisition time.** 12 ZIPs, similar to 2022 acquisition (~30-60 min). 1h→1d
  aggregation similar.
- **Model runtime.** 243 folds × ~10 sec/fold = ~40 min. Slightly longer than 012
  on 2024 alone because 3× the corpus.
- **2023 K1 base rate.** Unknown until acquired. Most likely in the 0.50-0.54
  range (recovery year, mixed regime).

## 11. Time budget

| Sub-task | Estimate |
|---|---|
| Descriptor + tests (2023) | 0.25 day |
| 3 config YAMLs (2023 1m/1h/1d) | 0.1 day |
| 12 monthly ZIP acquisition | 0.5-1 day |
| 1m/1h/1d normalization + verification | 0.5 day |
| Quality approval (if needed) | 0.1 day |
| 015b run on 3-year corpus | 0.5-1 day (compute) |
| Per-year table + B3.5b verdict | 0.5 day |
| T6 final-gate suite | 0.5 day |
| **Total** | **3-4 days** |

Same as 015-extended estimate. The model-run half is new work but well-bounded
by the existing 012 pipeline.

## 12. Post-slice state

When 015-extended-b closes:
- HEAD advances with: descriptor changes, 2023 configs (and possibly 1 approval),
  015b attempt manifest, 015b report committed
- {2022, 2023, 2024} is the new verified corpus
- 015b's per-year table is the basis for the next move:
  - If verdict is PROCEED: B4 (decision layer) is the next slice
  - If verdict is STOP-regime-conditioning: B5 is the next slice
  - If verdict is REDESIGN: 014 derivatives backfill is the next slice
  - If verdict is "all years weaken": ship the multi-year honest-negative
- 2020/2021 headerless-archive amendment is deferred to its own slice

## 13. What does NOT change

- 012 KILL verdict (still 0.5151 accuracy, 0.2511 Brier on 2024)
- B3.5 STOP_PUBLISH_NEGATIVE on 2024 alone
- The 2020-2021 headerless-archive blocker is documented and deferred, not
  hidden or papered over
- 2025 untouched
- The 015-extended report at `docs/research/per-year-feature-distribution-2020-2022.md`
  is unchanged
