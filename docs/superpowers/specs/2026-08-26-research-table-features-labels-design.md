# Quantara Research Table — Features and Labels Design Specification (Data Slice 003b)

**Status:** Proposed design; awaiting owner review and approval
**Date:** 2026-08-26
**Project:** Quantara
**Project root:** `D:\PROJECT\Quantara`
**Design scope:** A deterministic, causally computed features-and-labels research table published through the immutable protocol, bound to a verified parent dataset commit
**Governing predecessors:** slice 001 design (canonical contract); slice 002 design §§3, 11, 16 (derivation, lineage binding, authenticated identity); rights record v2 amendment (2026-08-26)

## 1. Purpose

Slices 001–002 produced verified canonical klines and their higher-timeframe derivations. This slice adds the analytical layer the roadmap names next ("feature and label contracts with leakage-resistant temporal validation"): a versioned **research table** computed from one published dataset commit, containing clearly role-tagged feature columns (causal — may only use data at or before each row's bar close) and label columns (strictly forward — by definition use later data, and exist precisely so models never have to invent targets ad hoc).

The governing principle is unchanged:

> Preserve source evidence, make every transformation explicit, reject ambiguity, and never promote unverified data into a modeling path.

## 2. Approved decisions inherited

All predecessor decisions remain in force: exact `decimal.Decimal` arithmetic with binary floats forbidden everywhere; PASS-only publication; immutable content-addressed commits with atomic pointer promotion and read-back verification; attempt evidence for every terminal outcome including truthful current-invocation milestones (slice 002 closure); descriptors as the only configuration surface; `data/` never tracked.

## 3. New decisions

1. **One artifact, role-tagged columns.** Each research-table publication produces a single dataset whose Parquet schema carries feature and label columns distinguished by an authoritative role registry recorded in the manifest. Consumers cannot confuse roles without producing a different schema fingerprint.
2. **Feature set v1 (`btcusdt_core_v1`), exactly four causal features** computed per bar *t* from the parent's OHLCV series (all division/sqrt under explicit `decimal.Context(prec=50)`, stored quantized per §5):
   - `f_ret_1`: `close_t / close_{t-1} − 1`
   - `f_roc_60`: `close_t / close_{t-60} − 1`
   - `f_rvol_20`: sample standard deviation (ddof = 1) of the trailing 20 one-bar returns `f_ret_1` inputs — i.e. `sqrt( Σ (r_i − r̄)² / 19 )` over `r_{t-19..t}` — using correctly-rounded `Decimal.sqrt()`
   - `f_volratio_20`: `volume_t / mean(volume_{t-19..t})`
3. **Label set v1, exactly two strictly-forward labels** with horizon `H = 24` parent bars:
   - `l_fwdret_24`: `close_{t+H} / close_t − 1`
   - `l_fwddir_24`: exact sign of `l_fwdret_24` ∈ `{−1, 0, +1}` as nullable int8
4. **Storage quantization `Q18`.** Non-terminating quotients and square roots are quantized once, at storage time, to exactly 18 fractional digits with `ROUND_HALF_EVEN` inside the explicit context. No intermediate rounding exists anywhere else in the computation.
5. **Designed nullability.** Warm-up and trailing windows yield typed nulls with deterministic, calendar-derived counts (§6). The quality evaluator asserts those counts exactly — extra or missing nulls are failures, not warnings.
6. **Causality contract (the leakage rule).** Every feature value at row *t* is a pure function of parent rows with index `≤ t`; every label at row *t* depends only on indices `> t` and requires those bars to exist completely. This is enforced by a property test: mutating any bar after *t* must leave every feature value at rows `≤ t` bit-identical, and mutating any bar before *t* must leave labels at rows `≥ t` bit-identical.
7. **Parent eligibility is structural.** The descriptor must reference a base dataset whose committed row count satisfies every window plus the horizon; undersized bases (e.g. the 31-row daily table) are rejected before any compute with a stable diagnostic, never silently truncated.
8. **Legal gate.** The pipeline gates on `analyze_internal` against the v2 rights record referenced by the research descriptor. Publishing labels is analysis; it grants nothing toward `model_train_internal`, which remains `UNKNOWN` and blocking until its own amendment.
9. **Identity and lineage.** Content identity uses a new domain-separated hash `quantara-research-content-v1` over the research schema fingerprint and quantized row framing (never the kline framing). The commit address equals a domain-separated SHA-256 over JCS of `{content_hash, lineage}`, where lineage binds base `dataset_id`, the base pointer's exact commit address, base canonical-content hash, feature-set name/version/parameters, and horizon. Changed parameters ⇒ changed address ⇒ a new immutable commit; parents are never mutated.
10. **Truthful milestones carry over.** Attempt manifests reuse the corrected milestone semantics from slice 002 (`object_written` only on genuine creation; `commit_renamed` only on genuine rename; retained-equivalent fallback stays `False`). Exit codes 0/2/3/4 unchanged.

## 4. Explicit non-goals

No model training, evaluation, calibration, backtesting, or fill simulation; no train/test splitting (temporal-validation tooling is a later slice); no additional months, instruments, providers, or timeframes; no feature normalization beyond the causal windows above; no live collection; no databases, services, APIs, UI; no customer-facing output; no redistribution; no modification of parent datasets; no gap repair or interpolation; no second feature set.

## 5. Table schema (authoritative)

Seven physical columns, fixed order, stored Parquet with the established writer configuration:

| # | Column | Type | Nulls |
| --- | -------- | ------ | ------- |
| 1 | `open_time_ms` | int64 (epoch ms, UTC) | never |
| 2 | `f_ret_1` | decimal128(38,18) | row 0 |
| 3 | `f_roc_60` | decimal128(38,18) | first 60 rows |
| 4 | `f_rvol_20` | decimal128(38,18) | first 20 rows |
| 5 | `f_volratio_20` | decimal128(38,18) | first 19 rows |
| 6 | `l_fwdret_24` | decimal128(38,18) | last 24 rows |
| 7 | `l_fwddir_24` | int8 | last 24 rows |

Null counts are stated for a complete parent and are recomputed by the evaluator from the actual parent length; they are invariants of the definitions, never tunable tolerances.

## 6. Descriptor (`quantara.research-descriptor/v1`)

```yaml
schema: quantara.research-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1h_2024_01_research_core_v1
dataset_type: research_table
provider: binance
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
base_dataset_id: binance_usdm_btcusdt_klines_1h_2024_01
base_descriptor: configs/datasets/binance-usdm-btcusdt-1h-2024-01-derived.yaml
period: { start: "2024-01-01T00:00:00Z", end: "2024-02-01T00:00:00Z" }  # must equal base period
feature_set: { name: btcusdt_core_v1, version: "1" }
parameters: { roc_window: 60, vol_window: 20, volume_window: 20, label_horizon: 24 }
schema_version: quantara_research_featureset_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v2.yaml
```

Validation mirrors the derived-descriptor discipline: unknown keys rejected; identity fields equal the loaded base descriptor's approved values; `period` equal to the base period; whitelisted feature-set name and version; parameters restricted to the approved values (any other value is `unsupported_parameter`, never a silent generalization); `schema_version` fixed; minimum-parent-size precondition derived arithmetically as `max(windows needing closes) + label_horizon` and enforced against the base's expected row count.

## 7. Quality evaluation (`research_*` prefixed checks)

One finding per check; states follow policy v1; exactly `PASS` publishes: row count equals parent count; open times identical to the parent's, strictly ascending, unique; per-column designed-null budgets exact (no more, no fewer); all non-null decimals within `decimal128(38,18)` scale; `f_rvol_20` strictly positive where non-null (a zero-variance window means degenerate input and fails loudly rather than publishing zeros); `l_fwddir_24` consistent with `l_fwdret_24` sign including exact zero; reconciliation outcome from an independent recomputation of every cell.

## 8. Modules and reuse map

New: `research_descriptor.py` (loader), `features.py` (pure causal/forward engines operating on positional tuples from `read_canonical_rows`), `research_quality.py` (evaluator), `research_pipeline.py` (orchestration mirroring `derive_pipeline.py`). Extended additively: `hashing.py` (`research_schema_fingerprint`, `research_content_hash`), `cli.py` (third schema dispatch). Reused unmodified: publication primitives, manifests, rights loading, `render_decimal_18`, exit-code contract.

## 9. Foundational risks addressed

Target leakage through off-by-one window boundaries (closed-form null-budget checks plus the perturbation property test); silent float contamination via `math.sqrt`/float division (Decimal-only engines, schema-enforced types); identity drift between similar tables (domain separation plus lineage-bound addresses); accidental consumption of labels as features (role registry inside the fingerprinted schema); publishing against unverified or mutated parents (full graph authentication before compute); milestone dishonesty (inherited truthful semantics with regressions).

## 10. Completion statement

This document is the proposed design boundary for Quantara's research-table slice. It authorizes implementation planning, not immediate implementation. Implementation may begin only after the detailed plan is written, reviewed, and approved by the owner, preserving this scope without introducing additional feature sets, horizons, datasets, models, or product behavior.
