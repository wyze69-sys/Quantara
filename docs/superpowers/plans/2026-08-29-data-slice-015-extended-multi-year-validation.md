# Slice 015-extended — Multi-Year OHLCV Acquisition (2020-2022) + Per-Year Feature Distribution

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-29
**Starting HEAD:** `2918708` (main, clean, synced with origin)
**Executor:** Owner-chosen (Codex default per memory).
**Provenance:** this slice implements the data half of the multi-year validation plan
agreed on 2026-08-29. B3.5 STOP_PUBLISH_NEGATIVE was the trigger; the post-B3.5 review
(GPT + Claude) converged on "freeze the 012 model, test on 4 years (2020+2021+2022+2023)
before deciding whether to continue, halt, or pivot." This plan covers the data side
only: acquisition, descriptor changes, and the per-year feature distribution report.
The model-run half is slice 015b (separate plan to be drafted after this slice lands).

## 0. Owner authorization (read first)

This slice **acquires and normalizes 3 additional years of OHLCV data** (2020, 2021, 2022)
into the existing data store, then produces a per-year feature distribution report
that the engine spec (slice 015b) will use to decide min_train_size and 2019 inclusion.

**No model is trained, no frozen slice is changed, no rights record is amended.** The
existing v3 provider-rights record already covers "data.binance.vision public archives"
generically (no year range specified), so 2020-2022 acquisition is in scope under the
existing authorized operations (`acquire_internal`, `retain_raw_internal`,
`normalize_internal`, `analyze_internal`, `model_train_internal`). Private research
evidence only; no customer display, no redistribution, no commercial production use,
no live trading.

## 1. Goal

Add 3 years of canonical OHLCV (1m klines, BTCUSDT USD-M perpetual) to the data store:
- 2020 (full year, ~525,600 1m bars; 8,784 1h bars after aggregation; includes the
  March 2020 COVID crash — the highest-vol event in BTC perp history)
- 2021 (full year, ~525,600 1m bars; 8,760 1h bars; bull peak in April then chop)
- 2022 (full year, ~525,600 1m bars; 8,760 1h bars; full bear year, LUNA/FTX)

For each year, run the existing per-timeframe aggregation pipeline (1m → 1h, 1d) to
produce the same canonical 1h store the 012 model trained on. Then compute the
**per-year feature distribution report** (the actual new engineering work) covering
the 4 features and 2 forward labels the 012 model used. This report is the basis for
the engine-spec decisions in slice 015b (min_train_size, 2019 inclusion, expanding-window
walk-forward).

The slice produces:
- 3 new approved identity tables in `descriptor.py` (one per year: 2020, 2021, 2022)
- 3 new 1m descriptor YAMLs (one per year)
- 3 new 1h derived descriptor YAMLs (one per year)
- 3 new 1d derived descriptor YAMLs (one per year)
- 3 new quality approval YAMLs (one per year, after acquisition reveals zero-volume counts)
- 36 monthly ZIPs acquired and content-addressed under `data/objects/raw/sha256/`
- Per-year 1h/1d canonical content under `data/datasets/binance/usdm/...`
- Per-year feature distribution report at `docs/research/per-year-feature-distribution-2020-2022.md`
- Engine-spec decisions documented (min_train_size=8760 proposed, expanding-window proposed,
  2019 train-only-or-drop, 2020-2022 zero-volume counts)

## 2. Why 3 years (not just 2023)

The original 015 plan covers derivatives backfill (different question). This 015-extended
plan covers OHLCV year expansion. The post-B3.5 review explicitly named 2022 as the
stress test year ("does the signal survive a bear?"), 2020 as the COVID crash year
("does the signal survive the highest-vol event in BTC perp history?"), and 2021 as
the bull-peak-and-chop year ("does the signal work in mixed regimes?"). Acquiring
only 2023 would test 3 out of 4 ~similar regimes and miss the discriminating years.

**GPT's specific framing** (verbatim from the 2026-08-29 review): "2022 is the stress
test. Your current Q1-2024 result came from a relatively bullish environment. Testing
2022 answers a much harder question." That question is unanswerable without 2020-2022
data in the store.

## 3. Verified facts (oracle check 2026-08-29)

- `data/datasets/binance/usdm/klines/BTCUSDT/1h/year=2024/` exists and is the only year
  currently in the store. Per `ls`: only `year=2024` directory present at every TF.
- The 2024 full-year 1m descriptor at `configs/datasets/binance-usdm-btcusdt-1m-2024.yaml`
  uses `dataset_id: binance_usdm_btcusdt_klines_1m_2024` and references 12 months
  `"2024-01"` through `"2024-12"`.
- The V2 year-identity check in `src/quantara/descriptor.py:351` is hardcoded:
  `elif document.get("dataset_id") == "binance_usdm_btcusdt_klines_1m_2024":`
  with the corresponding `V2_YEAR_APPROVED_IDENTITIES` and `V2_YEAR_DESCRIPTOR_KEYS`
  at lines 72-103. **Three new identity tables are required.**
- The `Acquirer` class at `src/quantara/acquisition.py:141` downloads a single
  monthly ZIP, verifies SHA-256 against the official Binance Vision `.CHECKSUM` file,
  and content-addresses the result under `data/objects/raw/sha256/`. **No
  descriptor changes are required to call it 36 times** — each call takes its own
  descriptor.
- The legal record at `configs/legal/binance-usdm-provider-rights.v3.yaml` covers
  "data.binance.vision public archives" generically with no year range. All 5
  internal operations (`acquire_internal`, `retain_raw_internal`, `normalize_internal`,
  `analyze_internal`, `model_train_internal`) are `OWNER_APPROVED_PENDING_COUNSEL`.
  No legal-record amendment required for 2020-2022.
- The aggregation pipeline (1m → 1h, 1d) is the existing derive pipeline; running it
  on 3 new years is the same call as for 2024, just with different months.

## 4. Pre-registered gates (no result can move these)

This slice is data work, not modeling. The gates are about data integrity, not signal:

### G1 — Identity-table expansion gate

For each of 2020, 2021, 2022:
- A new `V2_YEAR_APPROVED_IDENTITIES_<YYYY>` constant exists in `descriptor.py`
  (or, owner-approved alternative, a generalized per-year identity table)
- A new `V2_YEAR_DESCRIPTOR_KEYS_<YYYY>` constant exists with the same key set
  as `V2_YEAR_DESCRIPTOR_KEYS` (line 97)
- The V2 year-identity check at `descriptor.py:351` accepts the new dataset_ids
- All existing `test_descriptor.py` and `test_rights_and_periods.py` tests still pass
- One new round-trip test per year loads a 2020/2021/2022 1m descriptor and
  asserts `canonical_semantics()` matches the expected frozen bytes

**Pass criterion:** all 36 above conditions hold. **Fail criterion:** any one
fails → block and fix.

### G2 — Acquisition gate

For each of 36 monthly ZIPs (12 months × 3 years):
- HTTP 200 on `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip`
- HTTP 200 on the matching `.CHECKSUM` file
- Local SHA-256 (computed during streaming) equals the official digest parsed
  from the checksum document
- ZIP retained at `data/objects/raw/sha256/<official_digest>` (content-addressed)
- Checksum document retained at `data/objects/checksum/sha256/<local_sha256>`
- Acquisition evidence (`AcquisitionEvidence`) records: `zip_sha256`, `zip_size`,
  `reused_zip`, `reused_checksum`, `http_statuses`, `redirect_hops`,
  `retry_evidence`. None of these may be empty/missing for a fresh acquisition.

**Pass criterion:** all 36 ZIPs pass, with the SHA-256 chain linking the downloaded
file to the official digest. **Fail criterion:** any SHA-256 mismatch or
non-200 → quarantine (existing path) and block the slice.

### G3 — Normalization gate (1m → 1h, 1d)

For each of 36 monthly ZIPs:
- 1m canonical content derived, content-addressed, manifest published
- 1h aggregated content derived from 1m, content-addressed, manifest published
- 1d aggregated content derived from 1m, content-addressed, manifest published
- Per-month expected row count: 1m = days_in_month × 1440 (e.g., 2020-02 = 29 × 1440
  = 41,760; 2020-01 = 31 × 1440 = 44,640); 1h = days_in_month × 24; 1d = days_in_month.
- Per-year total: 2020 = 527,040 (leap year); 2021 = 525,600; 2022 = 525,600
  (1m rows). 1h: 2020 = 8,784; 2021 = 8,760; 2022 = 8,760. 1d: 2020 = 366;
  2021 = 365; 2022 = 365.

**Pass criterion:** row counts match calendar math for all 36 months × 3 TFs.
**Fail criterion:** any row count off → block, investigate, do not paper over.

### G4 — Per-year feature distribution report gate

For each of 2020, 2021, 2022 (1h TF):
- Per-year count of 1h bars (~8,760 ± a few for non-leap; 8,784 for 2020 leap)
- Per-year summary stats (mean, std, p01, p99, min, max) for each of:
  - `f_ret_1` (1-bar return)
  - `f_roc_60` (60-bar rate of change)
  - `f_rvol_20` (20-bar realized volatility)
  - `f_volratio_20` (20-bar volume ratio)
  - `l_fwdret_24` (24-bar forward return)
  - `l_fwddir_24` (24-bar forward direction, binary)
- Per-year base rate of `l_fwddir_24` (the K1 bar value, can differ year-to-year)
- Visual: histogram or density plot per feature per year, overlaid across 4 years
  (including 2024 as the baseline)
- Per-year zero-volume candle count (1m TF; the same invariant 012 already
  produced for 2024 with 89 zero-volume candles)

**Pass criterion:** report committed at
`docs/research/per-year-feature-distribution-2020-2022.md`, all 4 features ×
3 years summarized, per-year K1 bar values computed. **Fail criterion:** any
feature's per-year distribution shifts by >3σ vs 2024 (Claude's liquidity-claim
verification) → flag in the report, do not auto-drop the year, hand the decision
to slice 015b.

### G5 — Engine-spec decisions gate

Documented in the same report:
- **min_train_size proposal:** 8,760 (one full year as first-fold floor). Rationale:
  with 35,000+ rows across 4 years, this gives ~364 expanding-window folds
  (not fewer; fold count is governed by test_size and embargo, NOT by
  min_train_size — verified by math in §6 of this plan).
- **walk-forward mode:** expanding window (each fold trains on "everything
  strictly before the test start"). Rationale: standard quant-finance approach;
  fold count grows with corpus size, preserving statistical power.
- **2019 inclusion:** train-only or drop, decided after per-year distribution
  check (G4). Pre-registered default: drop pre-mid-2020 entirely; 2019 partial
  is not in scope for any year except possibly 2020 itself.

**Pass criterion:** all 3 decisions documented with rationale. **Fail criterion:**
silent default → block the slice.

## 5. Engine spec — fold count math (re-derived, not invented)

The post-B3.5 review caught me confusing fold-count formulas. Re-deriving cleanly:

For a walk-forward with `min_train_size`, `test_size`, `embargo`:
```
folds = floor((n_rows - min_train_size - embargo) / test_size)
```

This is the **fixed-window** count. The **expanding-window** count is the same
formula but the per-fold training prefix grows: fold 1 sees `min_train_size` rows,
fold 2 sees `min_train_size + test_size` rows, etc. Each subsequent fold's training
prefix is strictly larger. The number of *folds* is the same as fixed-window; what
differs is per-fold training data.

**Verified numbers for the planned setup:**
- n_rows = 35,064 (sum of 2020 1h bars + 2021 + 2022 + 2023, all full years)
- min_train_size = 8,760 (1 year floor)
- test_size = 72 (3 days, same as 012)
- embargo = 24 (1 day, same as 012)
- folds = floor((35,064 − 8,760 − 24) / 72) = floor(26,280 / 72) = **365 folds**

This is 3.1× the current 117-fold count within 2024 alone. **More folds, not fewer.**
The fold count is governed by `n_rows - min_train_size - embargo` divided by
`test_size`, NOT by `min_train_size` alone. Option D (expanding-window with
`min_train_size` as a first-fold floor) is what gives MORE folds, not fewer.

**Audit: do not re-invent this number.** The fold count of ~365 is derivable from
the formula and inputs. If the implementation produces a different number, that's
a bug to investigate, not a number to negotiate.

## 6. What this slice explicitly does NOT do

- **Does NOT train any model.** Pure data work + report.
- **Does NOT add derivatives features (slice 014).** Per the post-B3.5 review, both
  GPT and Claude independently recommended NOT adding features before multi-year
  validation of the cheap 4-feature model.
- **Does NOT touch the 012 model configuration.** `λ=1`, 4 features, logistic IRLS,
  same walk-forward parameters (test_size=72, embargo=24). The model freeze is a
  015b concern, not 015-extended.
- **Does NOT touch 2025 data.** 2025 remains the untouched OOS canary. It is not
  in scope for any slice in this plan chain.
- **Does NOT add a regime classifier or regime filter.** If 2022 inverts in 015b,
  the regime-filter slice comes after, designed with a no-future-info constraint.
- **Does NOT change the rights record.** v3 already covers this.
- **Does NOT change the B3.5 plan or its verdict.** B3.5 STOP_PUBLISH_NEGATIVE on
  2024 stands as the documented result; 015-extended + 015b is the multi-year
  re-evaluation, not a reversal.

## 7. Files changed (allowlist)

- `src/quantara/descriptor.py` — add 3 new approved-identity tables (2020, 2021, 2022)
  and corresponding descriptor-keys sets. Update the V2 year-identity check at line 351
  to accept the new dataset_ids. ~50 lines of additions, no deletions.
- `configs/datasets/binance-usdm-btcusdt-1m-2020.yaml` — new file, mirror of 2024.
- `configs/datasets/binance-usdm-btcusdt-1m-2021.yaml` — new file, mirror of 2024.
- `configs/datasets/binance-usdm-btcusdt-1m-2022.yaml` — new file, mirror of 2024.
- `configs/datasets/binance-usdm-btcusdt-1h-2020-derived.yaml` — new file.
- `configs/datasets/binance-usdm-btcusdt-1h-2021-derived.yaml` — new file.
- `configs/datasets/binance-usdm-btcusdt-1h-2022-derived.yaml` — new file.
- `configs/datasets/binance-usdm-btcusdt-1d-2020-derived.yaml` — new file.
- `configs/datasets/binance-usdm-btcusdt-1d-2021-derived.yaml` — new file.
- `configs/datasets/binance-usdm-btcusdt-1d-2022-derived.yaml` — new file.
- `configs/quality/approvals/binance-usdm-btcusdt-1m-2020-zero-volume.v1.yaml` — new file (after acquisition).
- `configs/quality/approvals/binance-usdm-btcusdt-1m-2021-zero-volume.v1.yaml` — new file.
- `configs/quality/approvals/binance-usdm-btcusdt-1m-2022-zero-volume.v1.yaml` — new file.
- `tests/conftest.py` — extend with 3 year-specific helpers (mirror 4f23b0a).
- `tests/test_descriptor.py` — add 3 round-trip tests (one per year).
- `tests/test_rights_and_periods.py` — add 3 period-coverage tests.
- `docs/research/per-year-feature-distribution-2020-2022.md` — new report.

**Files NOT changed:**
- `data/` (gitignored, contains only the new content-addressed artifacts; not tracked)
- `configs/legal/*` (v3 already covers 2020-2022)
- `src/quantara/{acquisition,derive_pipeline,pipeline}.py` (the existing code handles the
  new descriptors without modification)
- Any model file in `src/quantara/training_*.py` (frozen until 015b)
- `docs/superpowers/roadmap.md` (no roadmap edit needed; 015-extended is a clarification
  of the existing 015 plan, not a new roadmap entry)

## 8. T-criteria (executor T-checks)

The executor runs these after the descriptor changes and after acquisition; the plan
closes only when all pass.

- **T0 — unit tests pass:** `uv run pytest -m "not integration" -q` → expected ~845+ pass
  (current baseline), zero new failures.
- **T1 — descriptor changes verified:** `uv run pytest tests/test_descriptor.py tests/test_rights_and_periods.py -q` →
  all pass, including the 3 new round-trip tests.
- **T2 — acquisition verification:** all 36 monthly ZIPs acquired, all SHA-256s match
  the official Binance Vision checksums, all artifacts content-addressed under
  `data/objects/raw/sha256/`. Per-month: download attempt count, retry count, HTTP
  status code, final SHA-256.
- **T3 — normalization verification:** all 36 months × 3 TFs (1m, 1h, 1d) have canonical
  content with row counts matching calendar math. Cross-check 1h from 1m aggregation
  vs 1d from 1m aggregation — sum of 24 1h bars per day = 1 daily bar.
- **T4 — per-year feature distribution report committed:** report exists, has
  per-year stats for all 4 features + 2 labels, has per-year K1 bar values, has
  per-year zero-volume counts, has the 4 decisions (min_train_size, walk-forward mode,
  2019 inclusion, threshold derivation) all documented.
- **T5 — frozen manifest unchanged:** the existing 012 attempt manifest at
  `data/attempts/training/20260829T064246Z-...json` is untouched, the existing 7
  live pointers in the publication store are restored byte-for-byte.
- **T6 — repo hygiene:** `git ls-files data` returns 0 (data/ untracked);
  `uv run ruff check .` all checks pass; `git diff --check` clean; no file > 100 KB.

## 9. Per-slice output for the per-year feature distribution report

The report at `docs/research/per-year-feature-distribution-2020-2022.md` should have
this structure (one section per year + a cross-year section):

```
# Per-Year Feature Distribution (2020-2022) — Multi-Year Validation Setup

## 0. Provenance
- Date: 2026-08-29
- Slice: 015-extended
- Source: data/objects/raw/sha256/<official_digest> for each monthly ZIP
- Pipeline: derive_pipeline.py (1m → 1h, 1d) using the same 012-feature
  definitions

## 1. Row count sanity
| Year | 1m rows | 1h rows | 1d rows | Calendar check |
| 2020 | ?       | ?       | ?       | 527,040 / 8,784 / 366 (leap) |
| 2021 | ?       | ?       | ?       | 525,600 / 8,760 / 365 |
| 2022 | ?       | ?       | ?       | 525,600 / 8,760 / 365 |

## 2. Per-year feature distribution (1h TF, 4 features + 2 labels)
For each of {f_ret_1, f_roc_60, f_rvol_20, f_volratio_20, l_fwdret_24, l_fwddir_24}:
| Year | mean | std | p01 | p99 | min | max |
| 2020 | ?    | ?   | ?   | ?   | ?   | ?   |
| 2021 | ?    | ?   | ?   | ?   | ?   | ?   |
| 2022 | ?    | ?   | ?   | ?   | ?   | ?   |
| 2024 | (baseline from existing 012 work) |

## 3. Per-year K1 bar (base rate of l_fwddir_24)
| Year | Up fraction (K1 bar) |
| 2020 | ?                    |
| 2021 | ?                    |
| 2022 | ?                    |
| 2024 | 0.5349 (existing)    |

## 4. Per-year zero-volume candles (1m TF)
| Year | Count | Calendar comment |
| 2020 | ?     | (e.g., Mar 2020 crash) |
| 2021 | ?     |                     |
| 2022 | ?     |                     |

## 5. Cross-year visual (if generated as image: link; if text: per-feature ASCII)
For each feature: a 1-line note on whether the per-year distributions are
visually similar (candidates for direct concatenation) or visibly different
(candidates for separate handling).

## 6. Engine-spec decisions (G5)
- min_train_size: 8760 (one full year, expanding-window floor)
- walk-forward mode: expanding window
- 2019 inclusion: drop pre-mid-2020; 2019 partial not in scope
- threshold derivation: scaling_factor=1.0 against B3.5's 0.266 SD

## 7. Open questions for slice 015b
- Does 2020 (COVID crash) materially differ from 2022 (LUNA/FTX) in any
  feature's distribution? If yes, those features may need regime conditioning.
- Does the per-year K1 bar differ enough to require a per-year threshold
  (i.e., not just one global 0.5349)?
```

## 10. Risks and unknowns

- **Pre-2020 liquidity claim (Claude's prior).** Per the G4 gate, we do not pre-judge
  this; we compute per-year distributions and report the actual shifts. If 2020-01
  through 2020-06 are visibly different from 2020-07 onward (the per-feature p01/p99
  or std shift by >3σ), we document and recommend dropping pre-mid-2020 from training.
- **Per-month zero-volume counts.** 2020-03 (COVID crash) likely has more zero-volume
  candles than typical months; 2022-11 (FTX collapse) may also be elevated. The
  quality approval is per-year, not per-month, so a single 2020 approval with elevated
  count is acceptable; the report should note which months contribute most.
- **Acquisition time.** 36 ZIPs, average 5-10 MB each, single-shot downloads from
  Binance Vision (public archive, no rate limit announced). Estimate: 30-60 min for
  all 36 if no retries. If retries happen, double that. This is a one-time cost;
  the 8760 content-addressed artifacts are then retained.
- **Network reliability.** If any 2020-2022 ZIP is unreachable, the slice blocks on
  G2 (acquisition gate) until either (a) the file becomes reachable, or (b) the owner
  approves using the existing `Acquirer` retry path with extended backoff. Default:
  do not paper over acquisition failures.

## 11. Time budget

| Sub-task | Estimate | Notes |
|---|---|---|
| Descriptor changes + tests | 0.5 day | Mirror 2024 pattern, 3 years, ~50 lines + 6 tests |
| 9 new config YAMLs (1m/1h/1d × 3 years) | 0.25 day | Mechanical, copy-paste-and-edit |
| 36 monthly ZIP acquisition | 0.5-1 day | Single-shot downloads, 1-2 retries possible |
| 36 × 3 TF normalization (1m/1h/1d) | 0.5 day | Existing derive pipeline |
| 3 quality approval YAMLs (after acquisition) | 0.25 day | Mechanical, mirror 2024 |
| Per-year feature distribution report | 1 day | New engineering, per-feature stats + cross-year visual |
| Per-year decisions documentation | 0.25 day | G5 output |
| T6 final gate re-run | 0.5 day | ruff, full suite, integration |
| **Total** | **3.5-4 days** | |

This is slightly longer than the initial 3-4 day estimate because the descriptor
changes are non-trivial. The data acquisition itself is the same speed as 2024 was;
the new work is the descriptor generalization and the per-year distribution report.

## 12. Post-slice state

When 015-extended closes:
- HEAD advances to a new commit on `main`, with the descriptor, configs, tests,
  and report committed. `data/` is unchanged in the repo (gitignored).
- The next slice (015b) can be drafted immediately using the per-year distribution
  report as its basis. 015b is the model-run half: 012 frozen, expanding-window
  walk-forward on the 4-year corpus (~365 folds), per-year outcome mapping
  pre-registered.
- B3.5b (cross-year decision gate) is the slice after 015b.

## 13. What does NOT change

- The 012 KILL verdict and exit code 4 stand. The publication pointer is unchanged.
- B3.5's STOP_PUBLISH_NEGATIVE on 2024 alone stands as documented result.
- The 013 plan (derivatives backfill) is unaffected. It remains a separate slice
  and is explicitly NOT triggered by 015-extended.
- 2025 data remains untouched. No code path references 2025.
