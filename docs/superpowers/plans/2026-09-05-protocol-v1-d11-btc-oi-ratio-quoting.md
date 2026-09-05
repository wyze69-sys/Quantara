# D11 — BTC open-interest incidental-ratio quote variant

**Status:** ACCEPTED
**Finding:** F-S02B-1
**Series:** `btc_open_interest_5m`
**Date:** 2026-09-05

## Problem

The full S02-B inventory found provider archives that encode empty cells in the four
incidental ratio columns as quoted empty strings. The first observed day is 2021-12-30.
Each affected row keeps the frozen eight-column order:

1. `create_time`
2. `symbol`
3. `sum_open_interest`
4. `sum_open_interest_value`
5. `count_toptrader_long_short_ratio`
6. `sum_toptrader_long_short_ratio`
7. `count_long_short_ratio`
8. `sum_taker_long_short_vol_ratio`

On 2021-12-30, 113 of 288 rows quote exactly columns 5–8, with eight quote bytes per
quoted row. The frozen parser rejected any quote byte before inspecting the CSV grammar,
so it failed before reading any row.

No open-interest or ratio values are included in this document or committed evidence.

## Narrow disposition

D11 allows whole-field quotes only for empty source-null cells in columns 5–8 of the OI
parser. Those columns remain documented nullable diagnostics and are discarded, exactly as
before.

The parser still rejects:

- quotes in the timestamp, symbol, OI, or OI-value fields;
- quoted embedded delimiters;
- partial, escaped, or malformed quotes;
- quoted headers;
- all quoting in funding-rate archives;
- wrong column counts and wrong ordered headers.

Raw source bytes and parser-input hashes remain unchanged and authenticated. The change
does not rewrite provider payloads or alter canonical OI values.

## Acceptance evidence

Required before acceptance:

1. A red/green test proves the legacy global quote rejection fails the new contract.
2. Synthetic tests accept the exact four-ratio quote shape and reject five wider shapes.
3. Funding tests prove the old quote prohibition remains intact.
4. A real 2021-12-30 archive publishes with 288 rows, PASS quality, matched provider
   checksum, and authenticated parser-input identity.
5. The full S02-B inventory reruns from a fresh disposable root against D11.
6. Ruff and the full test suite pass.
7. An independent reviewer returns `ACCEPTED`.

## Scope

Allowed production changes: `src/quantara/series_parsing.py`,
`src/quantara/series_descriptor.py`, and the BTC OI descriptor YAML. The descriptor
change assigns BTC OI the explicit `binance_open_interest_csv/v2_quoted_empty_ratios`
parser identity; ETH OI and every other scalar series remain on their frozen v1
identities. Tests and this correction record are additive. The canonical serializer,
quality policy, acquisition, publication primitives, and production data are
prohibited from modification.
