# Quantara Headerless Source Variant — Formal Amendment to Slice 001 §3.3

**Status:** Approved by the owner on 2026-08-30; implemented under
`docs/superpowers/plans/2026-08-30-headerless-source-variant-implementation-handoff.md`
**Date:** 2026-08-30
**Project:** Quantara
**Project root:** `D:\PROJECT\Quantara`
**Design scope:** Versioned amendment to the fixed source contract, admitting the
headerless monthly Binance Vision archive variant under an explicit, allow-listed
descriptor declaration. No change to any numeric, temporal, canonical, or hashing
policy.
**Governing predecessors:** slice 001 design §3.3 (fixed source contract, exact
header), §12 (hashing and idempotency), §13 (manifests and quality evidence);
slice 010A (quality policy v2 amendment, the precedent for this class of change);
rights record v3
**Amends:** `docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md` §3.3
**Blocker of record:** `docs/research/per-year-feature-distribution-2020-2022.md` §9
(option 1 of the three stated options is the one adopted here)

## 1. Purpose

The 24 official monthly archives covering 2020-01 … 2021-12 contain a single CSV
member whose first line is already a data row. Slice 001 §3.3 states the header
contract as exact — *"reordered, missing, extra, duplicated, or case-changed
names are rejected"* — so `parsing.parse_rows` rejects all 24 members with
`source_header_mismatch`, and both years report `BLOCKED`. Two market regimes
(the March 2020 COVID crash and the 2021 bull peak) are therefore unreachable
even though their bytes are retained, checksum-verified, and structurally sound.

This amendment admits the headerless variant the same way slice 010A admitted
reviewed quality warnings: as an **explicit, versioned, narrowly allow-listed
declaration**, never as a relaxation of the default. Absent an explicit
declaration, the exact-header contract remains in force unchanged.

## 2. Verified source shape (headerless variant)

Established by reading the retained bytes directly (all 60 monthly archives for
2020–2024 are present under `data/objects/raw/sha256/`, each matching its
retained checksum document; 302 MB total; no re-download was required):

- Headerless: 2020-01 … 2021-12 — 24 contiguous months.
- Headered: 2022-01 … 2024-12 — 36 months, first line exactly the 12-name tuple.
- The boundary is exact at 2021-12 → 2022-01. There is no mixed month.
- All 60 members: single CSV member per ZIP, LF record endings, 12
  comma-separated fields per row, no byte-order mark.

Parsed through the **unmodified** numeric, timestamp, and membership policy (the
header line supplied externally purely to exercise the existing code path), the
24 headerless months yield:

- 2020: 527,040 rows across 12 months, each month exactly `days × 1440`
  (2020-02 = 41,760, leap-aware), zero non-60,000 ms adjacencies.
- 2021: 525,600 rows across 12 months, zero non-60,000 ms adjacencies.
- Both years: first open time exactly `YYYY-01-01T00:00:00Z`, last open time
  exactly `YYYY-12-31T23:59:00Z`, `close_time == open_time + 59,999` on every
  row, zero duplicate open times, zero period-membership violations, and zero
  violations of any hard OHLC, price, volume, taker, or trade-count invariant.
- Raw quality state for both years: `WARN_BLOCKED`, from exactly one warning
  check — `zero_volume_candle`, 2 occurrences in 2020 and 59 in 2021. No other
  warning fires; `source_order_invalid` and `nonzero_source_ignore` both pass.

The missing header line is therefore the sole obstruction. Nothing else about
these archives departs from the frozen contract.

## 3. New decisions

1. **Explicit declaration, never inference.** A v2 descriptor's `source` block
   may carry exactly one new optional key, `csv_header`, whose only permitted
   value is the string `absent`. Omitting the key means the header is present and
   the exact 12-name contract applies verbatim. The parser never sniffs, guesses,
   or falls back: a descriptor that omits `csv_header` still rejects a headerless
   member with `source_header_mismatch`, unchanged.

2. **Symmetric strictness.** Under `csv_header: absent`, a member whose first
   line *does* equal the 12-name header tuple is rejected with
   `source_header_mismatch`. Declared absence that turns out to be presence is
   provider drift and must fail loudly, exactly as the converse does today.

3. **Frozen field order, no positional freedom.** The headerless path binds
   fields positionally to the same frozen 12-name tuple in
   `parsing.HEADER`, in the same order. No alternate ordering, width, or
   alias set is introduced. Every row is subject to the identical field-count
   check, timestamp policy, `close_time == open_time + 59,999` rule, half-open
   `[start, end)` membership test, `count` int64 policy, and
   decimal128(38,18) representability budget. No interpolation, imputation,
   coercion, or rounding is added.

4. **Narrow allow-list, year is not a free parameter.** `csv_header: absent` is
   accepted only for the two pre-registered dataset identities
   `binance_usdm_btcusdt_klines_1m_2020` and
   `binance_usdm_btcusdt_klines_1m_2021`, matching the observed provider
   boundary. Any other dataset declaring it is rejected at descriptor load.
   Extending the allow-list requires its own amendment, exactly as each rights
   reclassification does.

5. **Parser identity records the variant; existing identity is not perturbed.**
   The variant changes parse policy, so it must appear in identity evidence.
   `PARSER_VERSION` is *not* bumped globally. Instead parser identity is resolved
   per descriptor:
   - header present → `binance_kline_csv_v1`, byte-identical to today;
   - `csv_header: absent` → `binance_kline_csv_v1_headerless`.

   Every already-published dataset (2022, 2023, 2024 across 1m/1h/1d, and all
   research, training, validation, and evaluation descendants) resolves to the
   unchanged string, so no published `descriptor_sha256`,
   `canonical_content_hash`, `schema_fingerprint`, `parser_version`,
   `quality_identity`, or commit address moves. Reruns of settled datasets must
   still return `VERIFIED_NO_OP`.

6. **No schema, hash-contract, or canonical-column change.**
   `SCHEMA_VERSION`, `HASH_CONTRACT_VERSION`, `CONTENT_HASH_DOMAIN`,
   `CANONICAL_COLUMNS`, the 23-column canonical row, the decimal contract, and
   `schema_fingerprint` are untouched. The header line was never canonical
   content; only the descriptor's declared parse policy changes.

7. **Truthful header evidence in the manifest.** `pipeline` currently derives the
   manifest's `source_header` field by splitting the member's first line. Under
   the headerless variant that line is a data row, so emitting it would publish
   false evidence. Under `csv_header: absent` the manifest records
   `source_header: null`. Under the default path the field is unchanged.

8. **No synthetic-header workaround.** Retained bytes are never mutated, and no
   header line is injected before hashing. The member SHA-256 recorded in the
   manifest remains the digest of the exact retained bytes, preserving the
   source-reconciliation chain.

9. **Quality outcome is a separate, owner-reviewed decision.** This amendment
   makes the two years *parseable*; it does not approve their warnings. Both
   land on raw `WARN_BLOCKED`. Publication requires the pre-registered policy-2
   combination already reserved in `descriptor.py`
   (`configs/quality/approvals/binance-usdm-btcusdt-1m-2020-zero-volume.v1.yaml`
   and the 2021 equivalent), each bound to that year's exact canonical content
   hash, schema fingerprint, 12 source digests, raw quality identity digest, and
   observed finding count (2 and 59 respectively). Those records are owner
   decisions and are authored only after a first blocked run reports the real
   digests.

10. **Descriptor digests for the two unpublished years may move.** Adding
    `csv_header: absent` to the 2020 and 2021 configs changes their canonical
    semantics, hence their frozen round-trip digests in `tests/test_descriptor.py`
    (`EXTENDED_YEAR_CANONICAL_DIGESTS[2020]`, `[2021]`). This is admissible
    precisely because neither year has ever been published — no commit exists
    under `data/datasets/.../1m/year=2020` or `year=2021`. The 2022 and 2023
    entries in that same table must not move, and a test asserts so.

## 4. Explicit non-goals

This amendment does not include: any change to numeric, temporal, canonical,
hashing, or quality-check policy; header sniffing, auto-detection, or fallback;
alternate column orders, widths, or aliases; any new provider, instrument,
market, interval, or year beyond 2020 and 2021; a global `PARSER_VERSION` bump;
any modification to a published dataset, descriptor, manifest, or commit; the
zero-volume approval decisions themselves; and any research, feature, model, or
evaluation work over the newly unblocked years.

## 5. Descriptor grammar delta

The v2 `source` block, today required to contain exactly `allowed_hosts`, becomes:

```yaml
source:
  allowed_hosts:
    - data.binance.vision
  csv_header: absent      # optional; only permitted value; only 2020/2021
```

Validation rules, all hard rejections at load:

- Any key other than `allowed_hosts` and `csv_header` — rejected, as today.
- `csv_header` present with any value other than the exact string `absent`
  (including `present`, `"none"`, `null`, booleans, or a list) — rejected. The
  header-present case is expressed by omission, so there is exactly one
  representation of each state and no redundant encoding to drift.
- `csv_header: absent` on any dataset identity outside the two allow-listed ones
  — rejected.
- The key is not accepted in v1 descriptors at all.

Canonical semantics include `source.csv_header` only when it is declared, so
every existing descriptor's JCS bytes are unchanged.

## 6. Test strategy

Additive; no existing assertion is weakened.

1. **Headerless parse, positive.** A headerless fixture under a descriptor
   declaring `csv_header: absent` parses to the expected rows with values
   identical, field for field, to the same fixture parsed with a header under a
   default descriptor.
2. **Default path unchanged, negative.** The same headerless fixture under a
   descriptor omitting `csv_header` still raises `source_header_mismatch`.
3. **Symmetric strictness, negative.** A headered fixture under
   `csv_header: absent` raises `source_header_mismatch`.
4. **Row-level policy still applies.** Under the headerless variant, a malformed
   timestamp, an out-of-period open time, a wrong field count, a signed or
   over-scale decimal, and a bad `count` each raise their existing error.
5. **Descriptor acceptance.** 2020 and 2021 accept `csv_header: absent`; 2022,
   2023, 2024, 2024-01, 2024-q1 reject it; unknown values reject; v1 rejects.
6. **Identity non-perturbation.** Parser identity resolves to
   `binance_kline_csv_v1` for every descriptor that omits the key, and the frozen
   2022/2023 canonical-semantics digests are asserted unchanged in the same test
   that updates the 2020/2021 values.
7. **Manifest evidence.** `source_header` is `null` under the headerless variant
   and the exact 12-name list otherwise.

## 7. Acceptance gate

- Every existing test passes unmodified, except the two 2020/2021 frozen
  descriptor digests, whose change is required by decision 10 and is asserted
  alongside unchanged 2022/2023 digests.
- `ruff check src tests` clean.
- 2020 and 2021 1m publish from retained bytes with row counts 527,040 and
  525,600, exact UTC boundaries, and canonical content hashes verified by
  independent re-hashing of the stored normalized object rather than by trusting
  the pipeline's own report.
- A rerun of any 2022, 2023, or 2024 lane returns `VERIFIED_NO_OP` with an
  unchanged commit address.

## 8. Design completion statement

This document is the proposed amendment boundary for admitting the headerless
monthly archive variant. It authorizes implementation of exactly the descriptor
key, parser path, parser-identity resolution, manifest evidence rule, and tests
described above. It authorizes no quality approval, no research use of the
unblocked years, and no further relaxation of the source contract.
