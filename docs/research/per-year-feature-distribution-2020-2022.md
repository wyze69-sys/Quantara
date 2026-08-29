# Per-Year Feature Distribution (2020–2022) — Multi-Year Validation Setup

**Slice:** 015-extended (data half)
**Date:** 2026-08-29
**Starting HEAD:** `41b327c` (plan commit); descriptor/config commit `79f6a75`
**Rights:** `configs/legal/binance-usdm-provider-rights.v3.yaml` — all five internal
operations `OWNER_APPROVED_PENDING_COUNSEL`. Private research evidence only: no
customer display, no redistribution, no commercial production use, no live trading.
**Model state:** unchanged. No model was trained, no frozen slice was touched, and
the 012 `KILL_CRITERIA_FAILED` attempt manifest
(`data/attempts/training/20260829T064246Z-…json`,
SHA-256 `a8cacc8a3687d560ce7fbbd5adf416c23854611ec7c6fc514b7a1d20d07b756f`) is
byte-unchanged.

## 0. Headline

All 36 monthly archives (2020-01 … 2022-12) were acquired and checksum-verified
(gate G2 passes, 36/36). **Only 2022 reached canonical publication.** The 24
official 2020 and 2021 archives ship **without the CSV header row**, so the
approved exact-header parser (`src/quantara/parsing.py`, spec §3 header contract)
rejects them and gate G3 blocks for those two years. This is a real source-format
discontinuity in Binance Vision, not a defect in this slice, and it is a
governance decision for the owner — not something to paper over.

Consequently the per-year distribution table below has two evidence tiers:

| Year | Acquisition (G2) | Canonical publication (G3) | Distribution evidence tier |
|---|---|---|---|
| 2020 | pass (12/12) | **blocked** — headerless source | provisional (not lineage-bound) |
| 2021 | pass (12/12) | **blocked** — headerless source | provisional (not lineage-bound) |
| 2022 | pass (12/12) | pass — published, `VERIFIED_NO_OP` on rerun | canonical |
| 2024 | (pre-existing) | pre-existing | canonical (baseline) |

Provisional numbers were computed with the same aggregation and the same
slice 003b feature/label engines over the same retained, checksum-verified ZIP
bytes, using an explicit header-free field mapping. They carry **no** canonical
content hash and **no** commit lineage. They are sufficient to answer 015b's
engine-spec questions and insufficient to be quoted as canonical.

## 1. Provenance

- Source: `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`
- Retained content-addressed at `data/objects/raw/sha256/<official_digest>`;
  checksum documents at `data/objects/checksum/sha256/<doc_sha256>` (36/36 present).
- Pipeline: unchanged `src/quantara/pipeline.py` (1m) and
  `src/quantara/derive_pipeline.py` (1m → 1h, 1d), transformation
  `multi_timeframe_aggregation` v1.
- Features/labels: unchanged `src/quantara/features.py`, parameters
  `roc_window=60, vol_window=20, volume_window=20, label_horizon=24`.

Published 2022 identities:

| Layer | dataset_id | rows | quality | canonical_content_hash |
|---|---|---|---|---|
| 1m | `binance_usdm_btcusdt_klines_1m_2022` | 525,600 | `WARN_APPROVED` (raw `WARN_BLOCKED`) | `84e4147fdffa096930ae6b1a2d440b5587b568f9798c5e8db49da8d9c419882b` |
| 1h | `binance_usdm_btcusdt_klines_1h_2022` | 8,760 | `PASS` | `96c877600badd376a75b96c8c12d09cc5a52f7c167066b8a04a46217a87e4b3d` |
| 1d | `binance_usdm_btcusdt_klines_1d_2022` | 365 | `PASS` | `96ab46349892a39764faa9161f5757d1fb2d161de2735f30f9cb5cdbd5222365` |

2024 baseline (pre-existing, unchanged): 1h `binance_usdm_btcusdt_klines_1h_2024`,
8,784 rows, `WARN_APPROVED`, cch `9129f9ac1a5ad2f21b8e74d4512ed334871d1cee22a1d99275ad8db74b29f39e`.

## 2. Row count sanity (G3)

Calendar math derived independently (`days_in_month × 1440 / × 24 / × 1`):

| Year | 1m rows | 1h rows | 1d rows | Calendar check | State |
|---|---|---|---|---|---|
| 2020 | 527,040 (parsed) | 8,784 (aggregated) | — | 527,040 / 8,784 / 366 (leap) | provisional; not published |
| 2021 | 525,600 (parsed) | 8,760 (aggregated) | — | 525,600 / 8,760 / 365 | provisional; not published |
| 2022 | 525,600 | 8,760 | 365 | 525,600 / 8,760 / 365 | published |

Every one of the 36 months matched its own calendar expectation exactly
(`days_in_month × 1440`), including 2020-02 = 41,760 (leap February) and
2021-02 = 2022-02 = 40,320. No month was short, long, duplicated, or gapped.

For the published 2022 lane the 1h→1d reconciliation was verified independently
of the pipeline: for all 365 days, the daily bar's open/high/low/close,
`trade_count`, and all four volume fields equal the exact aggregate of its 24
hourly constituents. Mismatches: 0.

## 3. Per-year feature distribution (1h TF)

Exact-Decimal statistics (`prec=50`, `ROUND_HALF_EVEN`), rendered to 12
fractional digits. `n` is the count of non-null values (warm-up nulls excluded:
`f_ret_1` 1, `f_roc_60` 60, `f_rvol_20` 20, `f_volratio_20` 19; trailing label
nulls 24).

### f_ret_1 (1-bar return)

| Year | n | mean | std | p01 | p99 | min | max |
|---|---|---|---|---|---|---|---|
| 2020* | 8,783 | 0.000191648791 | 0.008042526580 | −0.020706325190 | 0.020872741504 | −0.187090644924 | 0.162706841682 |
| 2021* | 8,759 | 0.000095352721 | 0.009187787677 | −0.025523630944 | 0.026133470639 | −0.094253898010 | 0.126652665205 |
| 2022 | 8,759 | −0.000095243936 | 0.006803027312 | −0.021147383370 | 0.020548877296 | −0.070387186638 | 0.065678681989 |
| 2024 | 8,783 | 0.000105601992 | 0.005616226903 | −0.017194322366 | 0.017088933285 | −0.045551728876 | 0.042934324161 |

### f_roc_60 (60-bar rate of change)

| Year | n | mean | std | p01 | p99 | min | max |
|---|---|---|---|---|---|---|---|
| 2020* | 8,724 | 0.011174117726 | 0.056955334001 | −0.137105241969 | 0.169157279841 | −0.496033778931 | 0.311554090807 |
| 2021* | 8,700 | 0.005115141267 | 0.065510785918 | −0.150991170163 | 0.173458947597 | −0.230756792182 | 0.307326036307 |
| 2022 | 8,700 | −0.005823006236 | 0.051535039641 | −0.169640763441 | 0.130212426978 | −0.275569278271 | 0.199337004158 |
| 2024 | 8,724 | 0.006045845711 | 0.042181840148 | −0.091890421689 | 0.108937346437 | −0.185339714484 | 0.222223743506 |

### f_rvol_20 (20-bar realized volatility)

| Year | n | mean | std | p01 | p99 | min | max |
|---|---|---|---|---|---|---|---|
| 2020* | 8,764 | 0.005961453202 | 0.005452048121 | 0.001273285825 | 0.024456133745 | 0.000847364738 | 0.079899259484 |
| 2021* | 8,740 | 0.008188478734 | 0.004198510194 | 0.003165640005 | 0.024605949858 | 0.002039294175 | 0.037845197470 |
| 2022 | 8,740 | 0.005857461047 | 0.003475834518 | 0.001098639676 | 0.019433420422 | 0.000447879180 | 0.029352320726 |
| 2024 | 8,764 | 0.005034950142 | 0.002511698412 | 0.001223231166 | 0.013159570564 | 0.000769297433 | 0.022146576918 |

### f_volratio_20 (20-bar volume ratio)

| Year | n | mean | std | p01 | p99 | min | max |
|---|---|---|---|---|---|---|---|
| 2020* | 8,765 | 1.023968150315 | 0.786955256627 | 0.287594944366 | 4.200411809910 | 0.153723577736 | 9.597067297336 |
| 2021* | 8,741 | 1.017862266011 | 0.632292015194 | 0.329585266928 | 3.445269443268 | 0.004704192981 | 6.778150758204 |
| 2022 | 8,741 | 1.032882575519 | 0.789026589541 | 0.243824791060 | 3.999204600578 | 0.132281879301 | 9.691029963836 |
| 2024 | 8,765 | 1.046833470258 | 0.877667302303 | 0.192022249141 | 4.478363387582 | 0.000000000000 | 8.648590639536 |

### l_fwdret_24 (24-bar forward return)

| Year | n | mean | std | p01 | p99 | min | max |
|---|---|---|---|---|---|---|---|
| 2020* | 8,760 | 0.004500384826 | 0.036441134064 | −0.092283721176 | 0.112742857513 | −0.473560025241 | 0.348864970501 |
| 2021* | 8,736 | 0.002279482398 | 0.043825199298 | −0.115786611596 | 0.125611175899 | −0.204025627470 | 0.234006854233 |
| 2022 | 8,736 | −0.002315279450 | 0.033110348166 | −0.097867970660 | 0.093188802910 | −0.191158715308 | 0.168876822852 |
| 2024 | 8,760 | 0.002504768049 | 0.026870462566 | −0.063927247647 | 0.075457997747 | −0.184198453270 | 0.127468864350 |

`*` provisional (unpublished lane; see §0).

## 4. Per-year K1 bar (base rate of l_fwddir_24)

| Year | defined | up | down | flat | up fraction (K1 bar) |
|---|---|---|---|---|---|
| 2020* | 8,760 | 5,075 | 3,685 | 0 | 0.579337899543 |
| 2021* | 8,736 | 4,575 | 4,161 | 0 | 0.523695054945 |
| 2022 | 8,736 | 4,101 | 4,634 | 1 | **0.469436813187** |
| 2024 | 8,760 | 4,706 | 4,051 | 3 | 0.537214611872 |

Pooled across all four years: 18,457 / 34,992 = **0.527463420210**.
Pooled across the two *published* years only (2022 + 2024): 8,807 / 17,496 =
**0.503372199360**.

The 012 pre-registered `directional_accuracy_min` is `0.534900284900284900`
(= 4,506/8,424, the 2024-Q1 walk-forward majority rate). **This is the single most
consequential finding in this report.** That bar is a 2024-specific artifact. In
2022 the majority class *inverts* (down-majority, 0.4694), so a model that
learned "predict up" would score ≈0.47 there while the same trivial rule scores
0.5372 in 2024 and 0.5793 in 2020. Any cross-year accuracy comparison against a
single global 0.5349 bar is measuring regime drift, not skill.

## 5. Per-year zero-volume candles (1m TF)

All rows preserved; no interpolation, no drops. Every zero-volume row has both
base and quote volume exactly zero and `trade_count == 0`. All hard invariants
(row count, boundaries, uniqueness, strict ascent, 60,000 ms adjacency, OHLC
bounds, strict positive prices, non-negative volumes/counts, close-time relation,
taker-buy bounds, `source_ignore == "0"`) pass for all three years.

| Year | Count | Contributing UTC days | Calendar comment |
|---|---|---|---|
| 2020 | 2 | 2020-09-27 (2) | not the March COVID crash — that period trades continuously |
| 2021 | 59 | 2021-03-02 (59) | one ~1-hour window, 01:01–01:59 UTC |
| 2022 | 64 | 2022-05-01 (29), 2022-05-28 (35) | May 2022; not the LUNA (2022-05-09+) or FTX (2022-11) collapse windows |
| 2024 | 89 | 2024-10-28 (89) | pre-existing, approved in slice 010A |

Notably, the risk register's expectation that 2020-03 (COVID) and 2022-11 (FTX)
would carry elevated no-trade counts is **falsified**: both months contain zero
such candles. High-stress months traded continuously; the gaps sit in ordinary
maintenance-shaped windows.

Approval record created (2022 only, because only 2022 published):
`configs/quality/approvals/binance-usdm-btcusdt-1m-2022-zero-volume.v1.yaml`,
record_id `binance-usdm-btcusdt-1m-2022-zero-volume-v1`, record_sha256
`90468329d08b9cf8b485f67227b85926a7cefbbac02a646caaa007e2392adcbb`, binding
exactly one `zero_volume_candle` finding with count 64 and canonical finding
digest `bbae226b53c735e0c8caaf5ba02265478365d71eaf494bf9cf3638c8bb3fdbd2`.
The raw state stays visibly `WARN_BLOCKED`; the effective state is authenticated
`WARN_APPROVED`, never a fabricated `PASS`. No approval record was written for
2020 or 2021 — writing one would bind hashes for content that does not exist in
the store.

## 6. Cross-year distribution shift (G4 screen)

Shift measured in 2024-baseline standard deviations; std ratio is raw dispersion
relative to 2024.

| feature | year | mean shift (σ) | std ratio | p01 shift (σ) | p99 shift (σ) |
|---|---|---|---|---|---|
| f_ret_1 | 2020 | 0.015 | 1.432 | −0.625 | 0.674 |
| f_ret_1 | 2021 | −0.002 | 1.636 | −1.483 | 1.610 |
| f_ret_1 | 2022 | −0.036 | 1.211 | −0.704 | 0.616 |
| f_roc_60 | 2020 | 0.122 | 1.350 | −1.072 | 1.428 |
| f_roc_60 | 2021 | −0.022 | 1.553 | −1.401 | 1.530 |
| f_roc_60 | 2022 | −0.281 | 1.222 | −1.843 | 0.504 |
| f_rvol_20 | 2020 | 0.369 | 2.171 | 0.020 | **4.498** |
| f_rvol_20 | 2021 | 1.256 | 1.672 | 0.773 | **4.557** |
| f_rvol_20 | 2022 | 0.327 | 1.384 | −0.050 | 2.498 |
| f_volratio_20 | 2020 | −0.026 | 0.897 | 0.109 | −0.317 |
| f_volratio_20 | 2021 | −0.033 | 0.720 | 0.157 | −1.177 |
| f_volratio_20 | 2022 | −0.016 | 0.899 | 0.059 | −0.546 |
| l_fwdret_24 | 2020 | 0.074 | 1.356 | −1.055 | 1.388 |
| l_fwdret_24 | 2021 | −0.008 | 1.631 | −1.930 | 1.866 |
| l_fwdret_24 | 2022 | −0.179 | 1.232 | −1.263 | 0.660 |

**Flagged at >3σ:** `f_rvol_20` p99 in 2020 (+4.50σ) and 2021 (+4.56σ).

Per the pre-registered G4 rule these are **flagged, not auto-dropped**; the
decision passes to 015b. Reading: realized volatility has a much fatter right
tail in 2020–2021 than in 2024 (2020 std is 2.17× the 2024 std), so a
train-window z-score standardization fitted on a low-vol year and applied to a
high-vol year will produce out-of-range standardized inputs. Per-fold
standardization on an expanding window mitigates this mechanically; it does not
eliminate it.

Everything else is inside 3σ. Notably `f_volratio_20` is the most stable feature
across all four years (mean within 0.04σ, std ratio 0.72–0.90) — expected, since
it is self-normalizing by construction.

## 7. Pre-mid-2020 liquidity check (G4 sub-question)

Claude's prior was that pre-mid-2020 data may be too thin to train on. Measured
rather than assumed, splitting 2020 into halves (2020-H2 as reference):

| feature | mean shift (H2 σ) | std ratio H1/H2 |
|---|---|---|
| f_ret_1 | −0.030 | 1.693 |
| f_roc_60 | −0.235 | 1.422 |
| f_rvol_20 | 0.656 | **2.414** |
| f_volratio_20 | −0.002 | 0.952 |
| l_fwdret_24 | −0.156 | 1.550 |

K1 bar: 2020-H1 = 0.540976058932 (2,350/4,344), 2020-H2 = 0.616803278689
(2,709/4,392).

No mean shift exceeds 3σ, so H1-2020 is **not** distributionally disqualified.
What is real is dispersion: H1-2020 realized volatility is 2.4× H2's, driven by
the March 2020 crash (`f_rvol_20` max 0.0799 vs 0.0179; `l_fwdret_24` min
−0.4736). The honest reading is "H1-2020 is a legitimate but extreme-volatility
regime", not "H1-2020 is illiquid noise."

## 8. Engine-spec decisions (G5)

1. **min_train_size = 8,760** (one full year as the first-fold floor).
2. **Walk-forward mode = expanding window** — each fold trains on everything
   strictly before its test start. Fold count is governed by
   `floor((n_rows − min_train_size − embargo) / test_size)`, so it does not
   shrink as the training prefix grows.
3. **2019 inclusion = drop.** No 2019 descriptor, identity table, or acquisition
   exists in this slice; 2019 is out of scope. The pre-mid-2020 question resolved
   to "keep, with a volatility-regime caveat" (§7) rather than "drop".
4. **Threshold derivation = do not reuse the global 0.5349 bar as a cross-year
   accuracy target.** §4 shows the majority class inverts in 2022. 015b must
   compute the baseline per fold from its own training window (the existing
   `majority_class_train_window` baseline already does this) and pre-register a
   per-year outcome map instead of one global bar.

Fold-count arithmetic, re-derived and verified:

```
folds = floor((n_rows − min_train_size − embargo) / test_size)
      = floor((35,064 − 8,760 − 24) / 72)
      = floor(26,280 / 72)
      = 365
```

The plan's 35,064 assumed 2020+2021+2022+**2023**. The store actually holds
2020+2021+2022+**2024** = 8,784+8,760+8,760+8,784 = **35,088**, which yields
`floor(26,304/72) = 365` — the same fold count. Either way: **365 folds**,
3.1× the 117 folds available within 2024 alone. More folds, not fewer.

**Important caveat for 015b:** those 365 folds are only *available* if the 2020
and 2021 lanes are published. As of this slice they are not (§0), so the corpus
actually reachable through the verified store today is 2022 + 2024 = 17,544 1h
rows → `floor((17,544 − 8,760 − 24) / 72) = 121` folds. 015b must not assume 365
folds until the header contract question is resolved.

## 9. Blocker: headerless 2020–2021 archives

The 24 monthly archives for 2020-01 … 2021-12 contain a single CSV member whose
first line is already a data row. The boundary is exact and clean:

- headerless: 2020-01 … 2021-12 (24 months, contiguous)
- headered: 2022-01 … 2022-12 and 2024 (all months)

Verified independently of the pipeline: all 24 headerless members have exactly 12
comma-separated fields per row, correct first/last minute boundaries,
`close_time == open_time + 59,999`, zero duplicate or non-adjacent open times,
and zero violations of any hard OHLC/price/volume/taker invariant. The data is
structurally sound; only the header line is absent.

The governing spec (`docs/superpowers/specs/2026-08-24-…-data-slice-design.md` §3)
states the header contract as exact: *"reordered, missing, extra, duplicated, or
case-changed names are rejected."* Accepting a headerless member therefore
requires a **formal spec amendment**, not a code tweak — the same class of change
as slice 010A's quality-policy amendment. Deliberately not done here:

- Not silently relaxed. `parsing.py` is untouched.
- Not worked around by injecting a synthetic header into retained bytes: that
  would change the member hash and break the source-reconciliation chain.
- Not hidden. Both years report BLOCKED with the real diagnostic
  (`source_header_mismatch`, exit 3).

Options for the owner (015-extended-b or an amendment slice), stated without
choosing one:

1. **Positional-schema amendment.** Extend the spec to accept a headerless
   variant under an explicit, versioned source-format flag on the descriptor
   (e.g. `source.header: absent`), with the field order pinned by the same frozen
   12-name tuple. Keeps identity exact; requires spec + descriptor + parser +
   test changes and a new schema fingerprint decision.
2. **Restrict the corpus to 2022+2024** (121 folds) and run 015b now. Cheapest,
   loses the COVID and bull-peak regimes — i.e. loses most of the reason 2020 and
   2021 were requested.
3. **Acquire 2023 instead** (headered, so it publishes with no amendment), giving
   2022+2023+2024 = 26,304 1h rows → 243 folds and a bear/recovery/bull spread
   without the 2020–2021 amendment.

My read: option 3 is the cheapest path to a genuinely multi-regime test, and
option 1 is the correct long-term fix if pre-2022 history matters. Option 2 is
the weakest — it tests two adjacent-ish regimes and reintroduces exactly the
narrow-evidence problem this slice exists to solve.

## 10. Open questions for slice 015b

- Does 2020 (COVID) materially differ from 2022 (LUNA/FTX)? On these numbers:
  yes in dispersion, no in central tendency. 2020 `f_rvol_20` std is 1.57× 2022's
  and its `l_fwdret_24` min is −0.474 vs 2022's −0.191. The two bear/stress
  regimes are not interchangeable, and `f_rvol_20` is the feature most likely to
  need regime conditioning.
- Does the per-year K1 bar differ enough to require per-year thresholds?
  **Yes.** The base rate spans 0.4694 (2022) to 0.5793 (2020) — an 11-point
  swing that straddles 0.5. A single global bar is not defensible.
- Is the 2022 down-majority evidence that the signal inverts, or only that the
  *baseline* inverts? Unanswerable from data alone; that is exactly the 015b run.

## 11. Gate status

| Gate | Status | Note |
|---|---|---|
| G1 — identity-table expansion | **pass** | 3 approved identity tables + 3 key sets + loader acceptance; 10 new descriptor tests, 9 new period/rights tests; 845 → 864 offline tests, zero failures |
| G2 — acquisition | **pass** | 36/36 ZIPs, all HTTP 200, all local SHA-256 == official digest, all content-addressed; 36/36 checksum documents retained; no retries, no quarantine |
| G3 — normalization | **partial** | 2022: 1m/1h/1d published, row counts exact, 1h→1d reconciliation 0 mismatches, reruns `VERIFIED_NO_OP`, pointers byte-identical. 2020/2021: **BLOCKED** on `source_header_mismatch` |
| G4 — distribution report | **pass** | this document; 4 features + 2 labels × 4 years, per-year K1 bars, per-year zero-volume counts, >3σ screen with 2 flags recorded and not auto-dropped |
| G5 — engine-spec decisions | **pass** | §8: all four decisions documented with rationale and re-derived arithmetic |

## 12. What did not change

- 012's `KILL_CRITERIA_FAILED` verdict, exit code 4, and attempt manifest.
- B3.5's `STOP_PUBLISH_NEGATIVE` on 2024 alone.
- The 2024 and Q1/January lanes: descriptors, approvals, commits, and pointers
  are byte-identical.
- `configs/legal/*` — v3 already covers 2020–2022 acquisition and analysis.
- `parsing.py`, `quality.py`, `aggregation.py`, `features.py`, `folds.py`, and
  every model module.
- 2025 remains untouched.
