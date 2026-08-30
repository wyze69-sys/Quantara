# 2020–2021 Canonical Publication Result

**Status:** COMPLETE — independently verified on 2026-08-30.

## Scope

The owner authorized publication of the retained Binance USD-M BTCUSDT 2020 and 2021 full-year kline datasets. The existing immutable, content-bound zero-volume approval records were activated. No source row was deleted, changed, or imputed.

## Effective quality decisions

- **2020 1m:** raw `WARN_BLOCKED`; effective `WARN_APPROVED`; 2 zero-volume/no-trade candles; approval `binance-usdm-btcusdt-1m-2020-zero-volume-v1`.
- **2021 1m:** raw `WARN_BLOCKED`; effective `WARN_APPROVED`; 59 zero-volume/no-trade candles; approval `binance-usdm-btcusdt-1m-2021-zero-volume-v1`.
- **2020/2021 1h and 1d:** `PASS` after deterministic aggregation.

The warning remains visible in the published 1m manifests. Approval is an authenticated overlay, not a conversion of the raw result to `PASS`.

## Published identities

### 2020

- 1m canonical content: `429e7ad880aa15b9b11888c4a1b4ec386ad114cbd67bc1b935486d77c287bb38`
- 1h canonical content: `efa6987daa1b4abd520d472cd71da4e311e9e0b73c696b00364ce56e0c29e785`
- 1d canonical content: `bfcd800b45f1c5f642fb243520c0e31ca2e9ecfa90c27da24a9551a1e13c7882`

### 2021

- 1m canonical content: `c6f03f939777151a5d989b9f8476bbff57fd780b28c63bd3489e742207fcf310`
- 1h canonical content: `5f8269490d355ba0a60930bf498686aade2ff9faebd5237bb0ec6644e1c5c13a`
- 1d canonical content: `9aa400b70d145bd9a138cf1e88dfaf73c49fdaed920212d084b8820e0914b2ab`

## Independent verification

The verifier read canonical Parquet objects directly rather than trusting pipeline exit codes or reports.

- Every normalized object re-hashed to its content-addressed SHA-256.
- 2020 row counts: 527,040 × 1m; 8,784 × 1h; 366 × 1d.
- 2021 row counts: 525,600 × 1m; 8,760 × 1h; 365 × 1d.
- Exact UTC year boundaries passed for all six datasets.
- Every 1m timestamp adjacency was exactly 60,000 ms: no gaps or duplicates.
- Zero-volume and zero-trade counts independently reproduced: 2 for 2020 and 59 for 2021.
- 2020 1h→1d: 366 UTC days, exactly 24 hours each; 2,196 field comparisons, 0 mismatches.
- 2021 1h→1d: 365 UTC days, exactly 24 hours each; 2,190 field comparisons, 0 mismatches.
- Current-pointer manifest hashes authenticated.
- Base object graphs and both derived current graphs authenticated.
- Idempotent 1m reruns succeeded for both years against the retained policy-v2 evidence.

## Research boundary

This publication makes 2020–2021 legitimate canonical inputs for the separately specified target/protocol-design phase. It does not revive the terminated four-feature OHLCV direction model and does not authorize opening the sealed 2025 evaluation.
