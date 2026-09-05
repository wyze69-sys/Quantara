# D10 — BTC open-interest exact-duplicate disposition

**Status:** CORRECTION IMPLEMENTED; acceptance pending verification
**Finding:** F-S02A-1
**Series:** `btc_open_interest_5m`
**Date:** 2026-09-05

## Decision

For this series only, a repeated row is an informational `pass` finding when the source
bytes are exactly identical. It remains counted and hashed in the quality report, but it
does not block publication after deterministic deduplication.

This closes F-S02A-1. It does not approve missing snapshots, off-grid timestamps,
source-order failures, or same-key rows with different bytes. Those remain warning or hard
failure states under the existing policy.

## Why this is safe

The S02-A real-source audit established all of the following before this correction:

- On a fully doubled day, 576 source rows reduce to exactly 288 distinct timestamps.
- Each removed row is byte-for-byte identical to its retained row. There is no differing
  value, timestamp text, symbol text, or incidental metrics text to choose between.
- All 288 retained timestamps sit on the native 5-minute grid.
- The parser records one SHA-256 duplicate hash per removed source row.
- Any same-key row with even one different byte still raises
  `OpenInterestDuplicateConflict` before canonical publication. Numeric equivalence does
  not weaken this rule: a textual `1.50` is different from `1.5`.
- The 288 retained economic rows equal the corresponding clean-source rows after raw-source
  provenance is normalized. Canonical identity still binds the exact source bytes, so the
  doubled provider object and a hypothetical clean object deliberately have different
  canonical content hashes.

Therefore, the duplicate carries provenance information but no additional market
information. Keeping it as a warning would require an approval record for every affected
daily object while approving the same deterministic, lossless operation each time. The
narrow policy disposition is simpler and stronger: preserve the source ZIP, duplicate
count, duplicate hashes, parser evidence, quality finding, and authenticated graph, while
letting the exact deduplicated canonical object reach quality state `PASS`.

## Scope lock

The code checks the exact registered series id `btc_open_interest_5m`. It does not change
duplicate handling for BTC funding, ETH open interest, spot candles, Kraken candles, or any
other present or future series. A dedicated negative test proves that
`eth_open_interest_5m` still reports an exact duplicate as `WARN`.

The correction does not infer that all early days are complete. `oi_daily_boundary` remains
a warning when fewer than 288 native slots survive deduplication. For example,
2021-05-21 remains blocked because only 284 slots are present, and 2021-10-01 remains
blocked because only 287 are present. No gap is filled, interpolated, zeroed, or approved.

## Red-first proof

Before implementation, the new public-behaviour test failed on the old policy:

```text
FAILED test_oi_exact_duplicates_are_audited_but_do_not_block
AssertionError: assert 'warn' == 'pass'
1 failed, 43 deselected, exit 1
```

The implementation then changed only the quality disposition for the exact reviewed series.
No parser, canonical serializer, descriptor, downloader, publication primitive, or data
object was changed.

## Acceptance criteria

D10 is accepted only if fresh verification establishes all of these:

1. A complete doubled BTC OI day publishes with quality state exactly `PASS`.
2. The authenticated quality-report object still records 288 duplicate rows and 288
   duplicate hashes as a `duplicate_exact_bytes` finding.
3. The real first frozen day, 2020-09-01, publishes and reruns to `VERIFIED_NO_OP` with zero
   additional HTTP requests.
4. The real transition day, 2021-05-21, remains `BLOCKED` on its four missing native
   slots even though its eight exact duplicate rows are informational; the real short day,
   2021-10-01, also remains `BLOCKED` on `oi_daily_boundary`, and neither writes a pointer.
5. Same-key different-byte rows remain a hard conflict.
6. ETH OI and every non-target series retain the old warning policy.
7. Frozen descriptors and canonical serialization remain byte-identical.
8. Ruff, focused tests, the four explicit integration tests, a fresh isolated checkout, and
   the full suite all pass.

Until all eight are evidenced, the status is not ACCEPTED.
