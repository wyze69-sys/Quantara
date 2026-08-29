# Quantara Roadmap — From Research Foundation to Final Product

**Status:** Living document. Reflects repo state at 2026-08-29 (HEAD `1b19202`,
16 slice executions, 154 commits, 36 production modules, 836 collected tests /
14 integration deselected).
**Read this if you ask "how many slices are left?" — the answer is here, and it
depends on which product you mean.**

---

## 1. Two definitions of "final product"

The project has two honest targets, and they are very different sizes:

| Target | Definition | Status |
|---|---|---|
| **P1 — Research evidence base** | Offline, verified archive → canonical → research features/labels → walk-forward validation → trained models with calibrated probabilities and honest evaluation. The current bounded product per the README. | ~2 slices from done |
| **P2 — Live trading product** | Everything in P1 **plus** live data feeds, live signal generation, backtesting with costs, portfolio/risk, and order execution. The README explicitly defers this ("Live collection, forecasting models, backtesting, portfolio construction, and order execution require separate design and verification gates"). | 40+ slices from done |

This roadmap plans **P2** (the full program). P1 falls out of Phase A/B as a
side effect of the first few slices.

---

## 2. Where we are — completed and audited (001–012)

All 16 executions (counting sub-slices 003a-2, 010a, 010b) are committed,
audited, and accepted, except 012 which is implemented + real-run but awaiting
final gates and push.

| Slice | Delivered |
|---|---|
| 001 | Archive-to-canonical acquisition for Binance USD-M `BTCUSDT` 1m, Jan 2024. Immutable content-addressed store, rights gates, quality-gated publication. |
| 002 | Multi-timeframe derivation (1h, 1d) from canonical 1m; milestone-truthfulness hardening. |
| 003a | Rights record v2 — `analyze_internal` approved pending counsel; anti-laundering freeze tests. |
| 003a-2 | `pytest-xdist -n 4` adoption (suite 25m39s → 7m17s serial→parallel). |
| 003b | Research table: causal features `f_ret_1`, `f_roc_60`, `f_rvol_20`, `f_volratio_20`; labels `l_fwdret_24`, `l_fwddir_24`; lineage-bound, leakage-resistant. |
| 004 | Walk-forward validation folds: 117 folds, `{test_size:72, min_train:336, embargo:24}`. |
| 005 | Temporal expansion Q1 2024. |
| 006 | Dual-IC feature evaluation (information coefficient lane). |
| 007 | Performance baseline + streaming Python (canonical hash 21.2s → measured improvement). |
| 008 | Rust/PyO3 kernel: canonical content hash (measured hotspot, byte-identical differential). |
| 009 | Rust kernel: Q18 decimal rendering. |
| 010 | Full-year 2024 expansion: 8,784 research rows; +010a/010b reviewed zero-volume warning approvals. |
| 011 | First model lane: exact-decimal ridge walk-forward; 8,400 predictions; IC −0.141, directional accuracy 0.5148 vs majority baseline 0.5349 (lost to baseline). |
| 012 | Logistic probability head (IRLS, exact Decimal) with pre-registered kill criteria. Real run: **KILL_CRITERIA_FAILED** (exit 4, no publication) — IC 0.1786 ✓, log-loss 0.6955 ✓, accuracy 0.5151 ✗ (bar 0.5349), Brier 0.2511 ✗ (bar 0.25). Implemented; awaiting T6 final gates + push. |

**Honest headline of the research so far:** the four features carry real
signal (probability calibration is informative: IC 0.18, log-loss near the
no-information floor) but the direction calls do not yet beat "predict the
majority class." That is a legitimate, publishable research result — and it is
exactly why the remaining program below is large: finding *tradeable* edge is
open-ended research, not a fixed number of slices.

---

## 3. Immediately next (slices 013–014)

### 013 — Binance Vision derivatives backfill *(named, facts verified in 012 §3)*

- Acquire funding-rate archives (monthly ZIPs, **2020-01** → present, ~808 B/mo)
  and daily metrics (open interest, taker long/short ratios, **2020-09-01** →
  present, 2,188 files, ~30 MB total — light).
- New retained lanes under existing v3 rights; no rights change.
- **Size:** M (data-acquisition slice, ~30 MB, but 6 years × 2 data shapes = new
  descriptors, validation, quality, integration).

### 014 — Derivatives feature expansion

- Add funding-rate, open-interest, and long/short-ratio features to the
  research table (basis/positioning are the classic missing signal families).
- **Size:** M. **Dependency:** 013. Rights: `analyze_internal` — no change.

### 014.5 — README refresh *(small, overdue)*

- README still reads "FOUNDATION-STAGE — SPECIFIED, NOT IMPLEMENTED" from the
  001 era, which is now false. Update to reflect the implemented pipeline.
- **Size:** S. Could fold into any nearby docs commit.

---

## 4. The full program (P2) — ordered phases

Each entry: **name** — what it delivers — why — gate/size.

### Phase A — Data depth (make the evidence base wide enough to trust)

The 2024-only, single-asset, four-feature base is a proof of concept, not a
research corpus. A model trained on one year of one asset cannot demonstrate
generalization.

| # | Slice | Delivers | Why | Gate/Size |
| --- | --- | --- | --- | --- |
| A1 | 013 | Vision derivatives backfill | funding/OI/positioning data 2020–2026 | v3 rights ✓ / M |
| A2 | 014 | Derivatives features | funding, OI, long/short features on research table | analyze ✓ / M |
| A3 | 015 | 2023 backfill | second training year (walk-forward cross-year) | v3 ✓ / M |
| A4 | 016 | 2025 acquisition + holdout | honest out-of-sample year never touched by training | v3 ✓ / M |
| A5 | 017 | Multi-instrument (ETHUSDT first) | generalization across assets; same pipeline, new descriptors | v3 ✓ / M |
| A6 | 018 | 2022 backfill (if A3/A5 show promise) | deeper history for regimes (bear/COVID era) | v3 ✓ / M |
| A7 | — | Higher-timeframe research tables (4h/1d) | strategy-relevant horizons, lower noise | v3 ✓ / S–M |

### Phase B — Modeling edge (turn signal into decisions)

Open-ended by nature. The slices below are the *named* candidates; each is one
bounded TDD slice, but the loop "feature idea → train → evaluate → kill/promote"
repeats as long as the kill criteria keep failing or improving.

| # | Slice | Delivers | Why | Gate/Size |
| --- | --- | --- | --- | --- |
| B1 | 019 | Multi-horizon labels (12h/48h) | horizon robustness; 24h-only labels are a single point | analyze ✓ / M |
| B2 | 020 | Formal feature selection (IC-ranked, dual-IC from 006) | cut noise features before spending modeling budget | analyze ✓ / S |
| B3 | 021 | Ensemble: ridge + logistic blend | probability blending, not new model class | model_train (approved pending counsel) ✓ / S |
| B4 | 022 | Threshold optimization (p̂ → direction map ≠ 0.5) | accuracy bar is beaten at the *decision* layer, not the fit layer | model_train ✓ / S |
| B5 | 023 | Regime conditioning (vol/trend gating) | edge may exist only in regimes; 012's IC 0.18 hints at this | analyze + model_train / M |
| B6 | 024 | Drift monitoring + retraining cadence | live-feasible models must know when they decay | model_train / M |
| B7 | 025 | Non-linear family *only if* the Decimal contract survives | gradient-boosted exact-decimal trees (design question — the exact-Decimal, no-float contract is the project's identity; a tree port is a major design amendment, not a code change) | ⛔ design gate / L |

### Phase C — Decision-grade evaluation (make results trustworthy enough to act on)

012 proved the evaluation lane works. The next step is making it *decision-grade*:
a number you'd put money behind.

| # | Slice | Delivers | Why | Gate/Size |
| --- | --- | --- | --- | --- |
| C1 | 026 | Cost-aware metrics (fees, slippage, funding carry) | a 51.5% accuracy model is profitable or not *after* costs; raw accuracy hides this | analyze ✓ / M |
| C2 | 027 | Statistical significance suite (bootstrap CIs, multiple-testing correction) | 117 folds ≠ 117 independent samples; honest n | analyze ✓ / M |
| C3 | 028 | Strategy backtest engine (signal → position → P&L, walk-forward, costs) | the bridge between "model metrics" and "would this make money" | analyze + model_train / L |
| C4 | 029 | Benchmark suite (buy-and-hold, momentum, carry) | every strategy must be compared to not-trading | analyze ✓ / S |

### Phase D — Live product (the P2 payoff — fully gated)

⛔ **Every slice in this phase is blocked until the owner makes the live-trading
decision.** Today the rights record blocks `model_train_internal` pending
counsel, and the README + artifact disclaimers say "no live trading, no
performance claim, no commercial use." Choosing P2 means consciously amending
that posture (rights v4 + counsel review), not drifting into it.

| # | Slice | Delivers | Why | Gate/Size |
| --- | --- | --- | --- | --- |
| D1 | 030 | Live data feed (WebSocket ingestion) | new architecture: streaming ingestion vs today's fetch-once-exit | ⛔ live decision / L |
| D2 | 031 | Live signal service | periodic model inference on fresh bars | ⛔ live decision / M |
| D3 | 032 | Paper trading + backtest-live reconciliation | prove the live path matches backtests before real money | ⛔ live decision / M |
| D4 | 033 | Order execution (broker integration) | actual orders, API keys, latency, failure handling | ⛔ live decision + counsel / L |
| D5 | 034 | Risk management (position sizing, limits, circuit breakers) | the layer that keeps a bad model from being a catastrophe | ⛔ live decision / L |
| D6 | 035 | Monitoring + alerting | unattended processes must fail loudly | ⛔ live decision / M |
| D7 | 036 | Portfolio allocation (multi-strategy/asset) | diversification is the only free lunch | ⛔ live decision / M |
| D8 | 037 | API/UI layer *if* customer-facing | commercial posture — a separate rights decision | ⛔ commercial decision / L |

### Phase E — Governance and hardening (spans everything)

| # | Slice | Delivers | Why | Gate/Size |
| --- | --- | --- | --- | --- |
| E1 | 038 | Rights v4 (live/commercial posture) + counsel review | P2 is impossible without it; two-part amendment (record + `APPROVED_INTERNAL_OPERATIONS` reclassification + tests) | ⛔ owner + counsel / S–M |
| E2 | 039 | Deployment/ops (process management, restart, secrets) | live systems need a home | ⛔ live decision / M |
| E3 | 040 | Packaging/docs for external users | only if commercial; else private-research posture stays | ⛔ commercial decision / M |

---

## 5. The slice count, made honest

- **Named remaining:** 013 (plus 012's final gates).
- **P1 research-complete:** ~2 slices (012 wrap + 013), with 014 as the natural
  third.
- **P2 full program:** 24 named future slices (013–040) ≈ **40+ total
  executions** counting the 16 done — and the model-research loop (B) is
  genuinely open-ended, so the real number is "at least 24, likely more."

**Timeline feel** (this machine, current slice cadence of ~1–3 slices/day with
full audit discipline):

- Phase A: ~1.5–2 weeks
- Phase B: ~2–4 weeks (research loop dominates)
- Phase C: ~1–2 weeks
- Phase D: ~1–2 months *if* the live decision is made
- Phase E: interleaved

---

## 6. Decision gates (owner choices that change the roadmap)

1. ⛔ **Live vs offline** — the single biggest fork. Offline research can reach
   P1 and stop; P2 requires counsel + rights v4 + real infrastructure.
2. ⛔ **Multi-asset vs single-asset** — A5+ only if generalization matters to
   you.
3. ⛔ **Commercial vs private** — D8/E3 and the whole "customer-facing" posture
   hang on this.
4. ⛔ **Model class boundary** — B7 (non-linear models) forces a design
   amendment to the exact-Decimal contract; not a default yes.

---

## 7. Definition of done per phase

- **Phase A done:** research base covers ≥2 years, ≥2 assets, derivatives
  features, and one held-out year never seen by training.
- **Phase B done:** at least one model beats all causal baselines (accuracy,
  IC, log-loss, Brier) *and* clears cost-aware evaluation in Phase C — or the
  program is honestly concluded "no tradeable edge found" with the evidence
  published either way.
- **Phase C done:** any strategy claim is expressed as walk-forward P&L after
  costs with significance bounds and benchmark comparison.
- **Phase D done (if chosen):** a monitored, risk-limited, paper-validated
  execution path with documented reconciliation.
- **Phase E done:** governance matches reality; nothing runs on a posture the
  records don't authorize.

---

## 8. Honest caveats

- **No fixed slice count guarantees a profitable model.** The kill criteria
  exist precisely so the project can publish an honest negative result (012 is
  the first such). The roadmap's job is to make every attempt cheap and every
  verdict trustworthy, not to promise edge.
- **The integrity discipline is the product.** Exact Decimal, immutable
  evidence, rights gates, and full audits are what make Quantara's claims
  defensible — and they make each slice more expensive than in a normal
  project. That is the price of the "correctness-first" identity in the README.
- **012's result is the roadmap's reason to exist.** IC 0.18 with
  below-baseline accuracy says: signal exists, decision layer doesn't exploit
  it yet. Threshold/regime/cost work (B4, B5, C1) is the most promising
  immediate direction — and none of it requires the live decision.
