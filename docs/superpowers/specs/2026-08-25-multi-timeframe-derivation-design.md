# Quantara Multi-Timeframe Derivation — Design Specification (Data Slice 002)

**Status:** Proposed design; awaiting owner review and approval
**Date:** 2026-08-25
**Project:** Quantara
**Project root:** `D:\PROJECT\Quantara`
**Design scope:** Deterministic derivation of 1h and 1d klines from the verified canonical BTCUSDT perpetual 1-minute dataset for January 2024
**Governing predecessor:** `docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md` (§18 anticipates this subproject)

## 1. Purpose

Data Slice 001 established one immutable, verified, content-addressed canonical month of 1-minute klines (44,640 rows; canonical-content hash `9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f`). This slice proves the next dependency in the approved order (predecessor §19 item 1): higher-timeframe candles constructed **only** from complete canonical one-minute groups under versioned boundary rules, published through the same immutable protocol, with full lineage back to the exact parent commit.

The governing principle is unchanged:

> Preserve source evidence, make every transformation explicit, reject ambiguity, and never promote unverified data into a modeling path.

## 2. Approved decisions inherited

All predecessor §2 decisions remain in force: commercial-safe architecture, Binance USD-M BTCUSDT perpetual only, January 2024 UTC only, archive-first, descriptors as authoritative configuration, market-data artifacts excluded from Git, everything internal while commercial rights are pending counsel review. Binary floating-point remains forbidden in every transform, reconciliation, and read-back check.

## 3. New decisions

1. **Timeframes in scope:** exactly `1h` and `1d`. The 5m, 15m, and 4h timeframes remain planned but out of scope; adding them later must be configuration plus tests, not new engineering.
2. **Authority:** the derived bars' correctness authority is the verified parent canonical dataset plus the published aggregation rules. Official Binance higher-timeframe archives are independent cross-check **evidence**, never a replacement authority (predecessor §18).
3. **Strictness:** the golden-slice policy carries over unchanged — derived datasets publish only with quality state exactly `PASS`; any warning blocks (`WARN_BLOCKED`).
4. **Determinism:** derivation is a pure function of (parent committed bytes, derived descriptor). Same inputs produce the same canonical-content hash forever; operational timestamps never participate in identity.
5. **Lineage:** every derived artifact records the exact parent commit it was computed from, and derivation refuses to run against anything less than a fully verified parent graph.
6. **Legal mapping:** derivation transforms internally retained normalized data into another internal representation; it is governed by the existing `normalize_internal` operation state. No new rights-operation vocabulary is introduced. `analyze_internal`, `model_train_internal`, `commercial_production_eligible`, `customer_display`, and `raw_redistribution` remain untouched and blocking.
7. **Storage:** derived Parquet objects reuse the existing `normalized` object kind (they are normalized data; content addressing prevents any collision). Dataset directories follow the established path convention with the derived interval segment (`…/BTCUSDT/1h/year=2024/month=01/`).
8. **CLI:** one entrypoint; the descriptor's `schema` field selects the pipeline. No second command surface.

## 4. Explicit non-goals

This slice does not include: additional months or instruments (multi-month expansion is a separate future slice); 5m/15m/4h timeframes; features, labels, training tables, models, calibration, backtesting; live collection; databases or services; APIs or UI; any customer-facing output; redistribution of any artifact; modification of the parent dataset or its publication; gap repair or interpolation of any kind.

## 5. Derived dataset identity

Two version-controlled derived descriptors are added beside the base descriptor. Their validated semantics are JCS-canonicalized into the derived descriptor hash, exactly mirroring slice 001.

```yaml
schema: quantara.derived-dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1h_2024_01
provider: binance
market_type: usd_m_futures
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
provider_symbol: BTCUSDT
base_asset: BTC
quote_asset: USDT
settlement_asset: USDT
contract_type: perpetual
dataset_type: klines
interval: 1h
base_dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
base_descriptor: configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml
period: { start: "2024-01-01T00:00:00Z", end: "2024-02-01T00:00:00Z" }   # [start, end); must equal base period
transformation:
  name: multi_timeframe_aggregation
  version: "1"
schema_version: binance_usdm_kline_1h_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
```

A second descriptor differs only where required: `dataset_id …_1d_2024_01`, `interval: 1d`, `schema_version: binance_usdm_kline_1d_v1`.

Validation rules: unknown keys rejected; identity fields must equal the base descriptor's approved values; `interval` restricted to the slice whitelist `{1h, 1d}` (anything else is `unsupported_timeframe`, not a silent generalization); `period` must equal the base descriptor's period exactly; the timeframe must divide the period length with zero remainder (misaligned configurations are rejected before any compute); `schema_version` must equal `binance_usdm_kline_{interval}_v1`.

Expected derived row counts are derived by calendar math, never embedded: `(end − start) / timeframe` → 744 hourly bars, 31 daily bars.

## 6. Bucket boundary rules

- Buckets are UTC epoch-aligned: bar open `B` satisfies `B mod timeframe_ms = 0`. Because the Unix epoch and the parent period start (2024-01-01T00:00:00Z) are aligned, no partial edge buckets exist; the configuration validation in §5 makes misalignment structurally impossible.
- Buckets are half-open `[B, B + timeframe_ms)`. A minute belongs to the bucket containing its `open_time_utc`.
- Timeframe constants: `1h = 3,600,000 ms`; `1d = 86,400,000 ms`.

## 7. Aggregation formulas (authoritative)

For each bucket over its complete, ordered set of constituent canonical minutes:

- `open_time_utc` = `B`
- `close_time_utc` = `B + timeframe_ms − 1`
- `nominal_available_time_utc` = `B + timeframe_ms` (bar-finalization contract inherited from predecessor §7; availability, not execution price)
- `open` = `open` of the earliest constituent; `close` = `close` of the latest constituent
- `high` = maximum of constituent highs; `low` = minimum of constituent lows
- `base_asset_volume`, `quote_asset_volume`, `taker_buy_base_volume`, `taker_buy_quote_volume` = exact `decimal.Decimal` sums of the constituents
- `trade_count` = exact integer sum
- identity fields come from the **derived** descriptor (`interval`, `schema_version` updated accordingly)
- `source_ignore`: every constituent must equal `"0"`; otherwise the group is rejected outright (`nonzero_source_ignore_in_group`) because no faithful aggregate representation exists. The verified parent guarantees this never fires; it is defense in depth.

All arithmetic is exact-decimal or integer. Addition cannot exceed the 18-fractional-digit scale of the addends, and `decimal128(38,18)` representability is re-checked per row exactly as in slice 001; overflow remains a hard error, rounding never occurs.

## 8. Completeness and incomplete-group behavior

A bucket is constructible iff its constituents number exactly `timeframe_minutes` and their open times are unique, strictly ascending, contiguous at 60,000 ms, and fully cover `[B, B + timeframe_ms)`. Any missing or duplicate minute is a hard failure (`incomplete_group`, `duplicate_open_time`). No interpolation, imputation, or repair exists. Input to the aggregator must be strictly ascending; unordered input is rejected rather than silently sorted, because the parent's ordering is already a settled, verified property.

## 9. Schema and content identity

- The logical schema is the fixed 23-column canonical order from predecessor §6.6, unchanged; only the stored `interval` and `schema_version` string values differ per timeframe.
- `schema_fingerprint` becomes parameterized by schema version; the existing no-argument call must remain byte-identical to the slice 001 value (regression-frozen).
- The canonical-content hash domain `quantara-canonical-content-v1`, row framing, and exactly-18-fractional-digit decimal rendering carry over unchanged. Distinct fingerprints make cross-timeframe hash collisions structurally meaningless.
- Parquet writing, read-back, and field-by-field exact reconciliation reuse the slice 001 machinery and fixed writer configuration.

## 10. Quality evaluation

A dedicated derived-dataset evaluator emits one finding per check, prefixed `derived_`: expected bucket count, exact first/last boundaries, unique open times, strictly ascending order, adjacency exactly `timeframe_ms`, OHLC bounds, strictly positive prices, non-negative volumes and counts, taker-buy bounds versus counterparts, close-time relation, zero-volume-bucket warning (defensive; cannot fire while the parent holds `PASS`), and reconciliation outcome. States and gating follow predecessor §13.3 with policy version `"1"`: exactly `PASS` publishes; any warning blocks; aggregate scores never gate alone.

## 11. Lineage, manifests, and idempotency

Dataset manifests gain a lineage block recording: parent `dataset_id`, parent canonical-content hash (the commit directory identity), parent Parquet SHA-256 and size, parent descriptor hash and schema fingerprint, and the transformation `{name, version, timeframe_ms}`. Attempt manifests, terminal-result enums, and exit-code mapping (0 PUBLISHED/VERIFIED_NO_OP, 2 BLOCKED, 3 FAILED, 4 QUARANTINED) carry over unchanged.

Idempotency: the derived identity evidence extends the slice 001 key set with the lineage block, so a rerun verifies the existing commit — including its parent binding — and writes `VERIFIED_NO_OP` without touching the commit or pointer. If the parent ever legitimately changed, the derived identity changes and a new commit publishes alongside the old one; the old derived commit is never mutated.

Derivation preconditions, enforced in order: derived descriptor validates; rights record permits `normalize_internal`; the parent resolves through `current.json` and its full graph verifies (manifest references → objects exist → hashes match, including the frozen Parquet SHA-256). A missing or unverifiable parent is `BLOCKED`, never a bypass.

## 12. Cross-check against official Binance archives

As independent evidence, the acceptance suite downloads the official `BTCUSDT-1h-2024-01` and `BTCUSDT-1d-2024-01` monthly klines archives with their `.CHECKSUM` documents (verified under the same strict grammar discipline as slice 001) inside separately marked networked tests:

- `open`, `high`, `low`, `close`, and `count` must match **exactly**: they are endpoint/extreme selections of the same underlying trades, so provider-side rendering cannot introduce drift.
- Volume-family fields tolerate `|Δ| ≤ 1e-8` per bar (provider-side per-candle rendering may differ in the last published digit); every delta is recorded as evidence, and any delta beyond tolerance fails acceptance and triggers engine investigation before the slice can be accepted.
- Cross-check results never participate in publication identity, and official archives are never persisted into the canonical store.

## 13. Commercial-safety boundary

Derived artifacts inherit the parent's restrictions completely: private internal evaluation only; no customer display, no commercial production, no redistribution of raw, normalized, or derived data. The performed operation maps to `normalize_internal` (`OWNER_APPROVED_PENDING_COUNSEL`, owner risk acceptance pending counsel review — recorded risk acceptance, not legal verification). Nothing in this slice alters the rights record or infers permission from public accessibility.

## 14. Foundational risks addressed

Silent divergence between derived and parent data; aggregation from incomplete or duplicate groups; hidden binary-float contamination during summation; undocumented timeframe semantics; lineage loss (orphaned derived artifacts nobody can trace); accidental parent mutation; treating Binance's own aggregates as an authority that overrides deterministic recomputation; scope creep into features, labels, or additional months/timeframes before the derivation layer is proven.

## 15. Completion statement

This document is the proposed design boundary for Quantara's multi-timeframe derivation slice. It authorizes implementation planning, not immediate implementation. Implementation may begin only after the detailed plan is written, reviewed, and approved by the owner, preserving this scope without introducing additional providers, periods, timeframes, features, models, or product behavior.
