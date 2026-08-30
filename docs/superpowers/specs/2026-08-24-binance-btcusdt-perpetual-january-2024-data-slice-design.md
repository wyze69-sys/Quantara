# Quantara First Historical Data Vertical Slice — Design Specification

**Status:** Approved design; implementation not started  
**Date:** 2026-08-24  
**Project:** Quantara  
**Project root:** `D:\PROJECT\Quantara`  
**Design scope:** Binance USD-M BTCUSDT perpetual, one-minute klines, January 2024

## 1. Purpose

This specification defines Quantara's first bounded implementation unit. Its purpose is to prove that one official crypto market-data archive can be acquired, verified, normalized, reconciled, and retained without silent alteration.

The slice establishes the minimum trustworthy foundation for later aggregation, replay, labels, models, execution simulation, and live collection. It does not claim that Quantara's broader data foundation, Phase 0, or scientific hypothesis is complete.

The governing principle is:

> Preserve source evidence, make every transformation explicit, reject ambiguity, and never promote unverified data into a modeling path.

## 2. Approved decisions

- Quantara is intended to become a commercial crypto-only product.
- The architecture must be commercial-safe from the beginning.
- The first market is Binance USD-M Futures.
- The first instrument is the BTCUSDT perpetual contract.
- The first dataset is one-minute klines.
- The first bounded period is January 2024 UTC.
- The approved approach is archive-first, not database-first and not historical-plus-live.
- One-minute klines are the canonical candle basis. Higher timeframes will be derived in a later, separately approved subproject.
- Version-controlled dataset descriptors are authoritative configuration for this slice.
- Downloaded and generated market-data artifacts are excluded from Git.
- PostgreSQL, TimescaleDB, Redis, Docker, MLflow, live streams, features, labels, models, APIs, and UI are outside this slice.
- Raw Binance data and normalized data remain internal while commercial-use rights are under review.

## 3. Fixed source contract

### 3.1 Dataset identity

- Provider: `binance`
- Market type: `usd_m_futures`
- Provider symbol: `BTCUSDT`
- Contract type: `perpetual`
- Base asset: `BTC`
- Quote asset: `USDT`
- Settlement asset: `USDT`
- Dataset type: `klines`
- Interval: `1m`
- Start, inclusive: `2024-01-01T00:00:00Z`
- End, exclusive: `2024-02-01T00:00:00Z`
- Stable Quantara instrument ID: `binance:usd_m_futures:BTCUSDT:perpetual`
- Schema version: `binance_usdm_kline_1m_v1`
- Timestamp-semantics version: `closed_interval_v1`

### 3.2 Official artifacts

Archive URL:

```text
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
```

Checksum URL:

```text
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
```

During design review on 2026-08-24, both endpoints were reachable. The checksum endpoint returned:

```text
21eeac04a76a7a35b10467e5e752fb2f8cff77cdeb57df6b50a23ce8d69bb190  BTCUSDT-1m-2024-01.zip
```

This value is design-review evidence, not a permanently embedded expected value. Implementation must retrieve the checksum artifact on each acquisition attempt and preserve it. A change in the published checksum triggers quarantine and review; it does not authorize silent replacement.

### 3.3 Verified source shape

The official January archive was inspected in memory during design review. Observed properties were:

- ZIP member: `BTCUSDT-1m-2024-01.csv`
- CSV columns: 12
- Header rows: 1
- Data rows: 44,640
- First open time: `2024-01-01T00:00:00Z`
- First close time: `2024-01-01T00:00:59.999Z`
- Last open time: `2024-01-31T23:59:00Z`
- Last close time: `2024-01-31T23:59:59.999Z`

The expected row count is derived from the approved half-open UTC interval at one-minute cadence. It must be calculated from calendar boundaries by implementation code rather than copied as a general rule.

The exact ordered CSV header contract is:

```text
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore
```

The file must decode as UTF-8 without a byte-order mark. Comma is the only delimiter. LF and CRLF record endings are accepted. Fields may use ordinary RFC 4180 quoting, but after CSV parsing the 12 header values must match the ordered values above exactly; whitespace is not trimmed and reordered, missing, extra, duplicated, or case-changed names are rejected.

> **Amendment 2026-08-30 (headerless source variant).** The exact-header contract
> above remains the default and applies verbatim wherever a descriptor does not
> declare otherwise. A v2 descriptor may declare `source.csv_header: absent`,
> permitted only for the allow-listed 2020 and 2021 BTCUSDT 1m identities, in
> which case the member's first line is a data row and fields bind positionally to
> the same frozen 12-name tuple in the same order. Declared absence that turns out
> to be presence is rejected, as is the converse. Parser identity becomes
> `binance_kline_csv_v1_headerless` for that path and is unchanged everywhere else,
> so no published identity moves. See
> `docs/superpowers/specs/2026-08-30-headerless-source-variant-amendment-design.md`.


For this fixed source contract, `open_time` and `close_time` must be unsigned base-10 Unix epoch-millisecond integers. They are parsed directly as integers without floating-point conversion. Signs, decimal points, exponent notation, non-decimal digits, and microsecond or second units are rejected. The approved `[start, end)` membership test applies to `open_time_utc`. Each source `close_time` must equal `open_time + 59,999` milliseconds.

## 4. Scope

### 4.1 Included behavior

The slice contains five logical components:

1. **Source descriptor**
   - Declares the approved provider, market, instrument, dataset, interval, period, source paths, schema version, timestamp semantics, and legal status.
   - Constructs or validates only allow-listed Binance archive paths.

2. **Artifact acquirer**
   - Downloads the ZIP and checksum into staging.
   - Uses bounded retries only for eligible transient failures.
   - Calculates SHA-256 locally.
   - Verifies the official checksum before promotion.
   - Never silently overwrites an artifact with different content.

3. **Kline normalizer**
   - Safely reads the one expected CSV member.
   - Validates the source header and each row.
   - Maps source fields to the canonical schema.
   - Preserves decimal values exactly.
   - Performs no interpolation, imputation, resampling, or gap repair.

4. **Manifest writer**
   - Records source identity, hashes, schema and parser identities, temporal bounds, row counts, output artifacts, environment evidence, legal status, and quality results.
   - Produces immutable run evidence.

5. **Quality evaluator**
   - Runs explicit field, row, sequence, boundary, and reconciliation checks.
   - Reports every check and its evidence independently.
   - Never uses one aggregate score as the sole acceptance gate.

### 4.2 Explicit non-goals

This slice does not include:

- Other months, instruments, providers, or markets
- Binance spot data
- Five-minute, 15-minute, hourly, four-hour, or daily aggregation
- Trades, aggregate trades, mark prices, index prices, funding, open interest, liquidations, or books
- Live REST polling or WebSockets
- Databases or distributed infrastructure
- Features, labels, training tables, models, calibration, backtesting, or fill simulation
- API, UI, authentication, subscriptions, billing, or user-facing outputs
- Automatic repair of malformed, missing, duplicated, or out-of-order source data
- Redistribution of raw or normalized Binance market data

## 5. Configuration authority

The authoritative declaration is a version-controlled dataset descriptor, conceptually located at:

```text
configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml
```

The descriptor contains:

- Dataset and instrument identities
- Exact half-open UTC period
- Source and checksum URL templates or approved paths
- Expected ZIP-member pattern
- Schema and timestamp-semantics versions
- Quality-policy version
- Legal status and allowed-use flags

The descriptor must be validated before any network or filesystem action.

A future PostgreSQL registry may import these descriptors. It must not become a second independently editable authority. Immutable manifests are execution evidence and cannot be used as mutable configuration.

## 6. Canonical schema

### 6.1 Identity fields

Every canonical row contains:

- `provider`
- `market_type`
- `instrument_id`
- `provider_symbol`
- `base_asset`
- `quote_asset`
- `settlement_asset`
- `contract_type`
- `interval`
- `schema_version`

These values are stored as UTF-8 strings. Repetition is acceptable because Parquet dictionary encoding compresses low-cardinality identity fields and self-identifying rows are safer for downstream composition.

### 6.2 Temporal fields

- `open_time_utc`: Parquet `timestamp[ms, UTC]`, non-null
- `close_time_utc`: Parquet `timestamp[ms, UTC]`, non-null
- `nominal_available_time_utc`: Parquet `timestamp[ms, UTC]`, non-null

### 6.3 Market fields

- `open`: decimal128(38, 18), non-null
- `high`: decimal128(38, 18), non-null
- `low`: decimal128(38, 18), non-null
- `close`: decimal128(38, 18), non-null
- `base_asset_volume`: decimal128(38, 18), non-null
- `quote_asset_volume`: decimal128(38, 18), non-null
- `trade_count`: signed 64-bit integer, non-null and non-negative
- `taker_buy_base_volume`: decimal128(38, 18), non-null
- `taker_buy_quote_volume`: decimal128(38, 18), non-null
- `source_ignore`: UTF-8 string, non-null

`source_ignore` remains textual because Binance does not assign useful business semantics to the field. The first slice expects its observed value to be `0`; any other value is surfaced for review rather than interpreted.

### 6.4 Source-to-canonical mapping

- `open_time` -> `open_time_utc`
- `open` -> `open`
- `high` -> `high`
- `low` -> `low`
- `close` -> `close`
- `volume` -> `base_asset_volume`
- `close_time` -> `close_time_utc`
- `quote_volume` -> `quote_asset_volume`
- `count` -> `trade_count`
- `taker_buy_volume` -> `taker_buy_base_volume`
- `taker_buy_quote_volume` -> `taker_buy_quote_volume`
- `ignore` -> `source_ignore`

Identity fields come from the validated descriptor. `nominal_available_time_utc` is derived under the approved temporal contract.

### 6.5 Numeric policy

- Source numeric strings are parsed through exact decimal arithmetic.
- Binary floating-point is forbidden in acquisition, validation, normalization, reconciliation, and Parquet write/read-back checks.
- No source precision may be discarded.
- The fixed canonical decimal scale may add trailing zeros but must not change numeric value.
- Accepted numeric text matches `^(0|[1-9][0-9]*)(\.[0-9]+)?$`; signs, separators, whitespace, `NaN`, infinity, and scientific notation are rejected.
- Insignificant trailing fractional zeros may be removed only when determining representability. Any value with more than 18 fractional places after those trailing zeros are removed, more than 20 integer places after insignificant leading zeros are removed, or more than 38 total fixed-point digits is rejected.
- A value that would require rounding to fit decimal128(38, 18) causes `decimal_precision_or_scale_overflow`; rounding is never permitted.
- Research code may later create floating-point arrays under a separate, versioned feature contract.

### 6.6 Canonical field order

The logical and Parquet column order is fixed:

```text
provider
market_type
instrument_id
provider_symbol
base_asset
quote_asset
settlement_asset
contract_type
interval
schema_version
open_time_utc
close_time_utc
nominal_available_time_utc
open
high
low
close
base_asset_volume
quote_asset_volume
trade_count
taker_buy_base_volume
taker_buy_quote_volume
source_ignore
```

Changing field order, type, nullability, or meaning requires a new schema version and schema fingerprint.

## 7. Temporal semantics

For a one-minute candle opened at time `t`:

```text
open_time_utc              = t
close_time_utc             = t + 60 seconds - 1 millisecond
nominal_available_time_utc = t + 60 seconds
```

Interpretation:

- `open_time_utc` is the start of the represented interval.
- `close_time_utc` is Binance's final millisecond inside that interval.
- `nominal_available_time_utc` is the earliest interval boundary at which the completed historical candle may be considered.
- The archive does not reveal the original live message receipt time, exchange publication delay, network delay, processing delay, or order-submission latency.
- Historical `received_time` must remain unknown rather than fabricated.
- Archive retrieval time is operational provenance and belongs in the manifest, not in market event time.
- Future replay and execution contracts must add explicit processing and order latency after nominal availability.
- No downstream component may consume the completed candle and assume an automatic fill at its own close.

This is a bar-finalization contract, not an execution-price contract.

The integer source timestamps are converted to UTC directly from Unix epoch milliseconds. Local timezones, daylight-saving rules, locale parsing, and naive datetimes are forbidden. `open_time_utc` must be in the descriptor's `[start, end)` interval. `close_time_utc` may equal the final millisecond before `end` but may not reach or exceed `end`.

## 8. Row and sequence invariants

Every row must satisfy:

- `close_time_utc = open_time_utc + 59,999 milliseconds`
- `high >= open`
- `high >= close`
- `low <= open`
- `low <= close`
- `high >= low`
- All four prices are greater than zero
- All volume fields are greater than or equal to zero
- `trade_count >= 0`
- `taker_buy_base_volume <= base_asset_volume`
- `taker_buy_quote_volume <= quote_asset_volume`
- All required fields are non-null

Zero volume is not automatically invalid, but every occurrence is counted and surfaced.

The complete monthly dataset must satisfy:

- Expected row count calculated from `[start, end)` and the one-minute interval
- Exact first and last approved boundaries
- Unique open times
- Strictly ascending canonical open times
- Exactly 60,000 milliseconds between adjacent open times
- No missing minute
- No duplicate minute
- No out-of-period row

The normalizer may sort complete, unique source rows into canonical order only while recording that source order was invalid. Under the first golden-slice policy, that condition prevents acceptance until reviewed. Missing values are never interpolated.

## 9. Artifact layout and publication model

The configurable data root initially defaults to:

```text
D:\PROJECT\Quantara\data
```

Conceptual layout:

```text
data/
├── staging/
├── objects/
│   ├── raw/sha256/
│   ├── checksum/sha256/
│   └── normalized/sha256/
├── datasets/
│   └── binance/usdm/klines/BTCUSDT/1m/year=2024/month=01/
│       ├── commits/<canonical-content-hash>/
│       └── current.json
├── attempts/
└── quarantine/
```

Rules:

- The data root is excluded from Git.
- Staging and published paths are on the same filesystem volume.
- Raw ZIP, checksum, and Parquet objects are immutable and addressed by SHA-256.
- A complete dataset commit directory contains the manifest, quality report, object references, content identity, and a `COMMITTED` marker.
- Files are flushed and closed before publication; file and directory metadata are synchronized where the host filesystem/runtime supports it.
- A complete staged commit directory is atomically renamed into `commits/<canonical-content-hash>`.
- `current.json` is written to a temporary sibling and atomically replaced only after the immutable commit exists.
- Readers discover data only through a valid `current.json` pointer to a complete committed directory. Unreferenced objects and incomplete directories are never canonical.
- A crash before pointer replacement may leave safe orphaned objects or commits; it cannot expose a partial dataset. Orphans are reported and handled by a later explicit cleanup operation.
- Pointer collision, existing different content at a commit path, or a pointer to missing/invalid evidence is a hard failure.
- The canonical month is stored as one Parquet object for this bounded slice.
- Parquet uses Zstandard compression and a fixed, versioned writer configuration.
- The data root can later move to dedicated or object storage without changing dataset identity, but the publication protocol must receive a separate design for stores without atomic filesystem rename semantics.

## 10. Processing flow

1. Load the approved descriptor.
2. Validate every descriptor field and the legal-use state.
3. Construct or validate the exact allow-listed Binance URLs.
4. Download ZIP and checksum into unique staging paths.
5. Parse the checksum document strictly and verify its filename.
6. Calculate the ZIP SHA-256 locally.
7. Reject any checksum mismatch.
8. Inspect the ZIP's central directory safely.
9. Require exactly one approved CSV member.
10. Stream the CSV without arbitrary filesystem extraction.
11. Validate the exact source header.
12. Parse rows through exact decimal and timestamp logic.
13. Record source ordering and all quality evidence.
14. Sort only if needed for canonical ordering; never hide the source-order finding.
15. Write staged canonical Parquet.
16. Read the Parquet back using the approved schema.
17. Reconcile every normalized source row with every Parquet row.
18. Calculate raw, checksum-artifact, member, descriptor, schema, canonical-content, and Parquet hashes.
19. Write staged immutable objects, dataset manifest, quality report, commit marker, and attempt manifest.
20. Flush and close staged content, then publish the immutable commit directory atomically.
21. Atomically replace `current.json` only after the committed directory is independently valid.
22. Re-open discovery through `current.json` and verify the complete published graph before reporting success.

## 11. Archive and transport safety

Before streaming a ZIP member:

- Exactly one expected CSV member must exist.
- Absolute paths are forbidden.
- Drive-prefixed paths are forbidden.
- Parent traversal segments are forbidden.
- Unexpected members are rejected.
- Uncompressed member size and compression ratio are checked against bounded safety limits.
- Corrupt archives are rejected.
- Redirects must end on an allow-listed HTTPS host.
- URL parameters and path segments cannot be supplied through unchecked free text.

The published SHA-256 proves consistency with Binance's checksum artifact. It does not replace HTTPS validation, allow-listing, provenance recording, or commercial-rights review.

## 12. Hashing, idempotency, and republished data

### 12.1 Hash contract

All hashes use SHA-256 and are labeled with `hash_contract_v1`.

- ZIP hash: exact downloaded ZIP bytes.
- Checksum-artifact hash: exact downloaded checksum-file bytes.
- Member hash: exact uncompressed CSV member bytes, including header and line endings.
- Descriptor hash: the validated semantic descriptor serialized as UTF-8 RFC 8785 JSON Canonicalization Scheme (JCS), not the original YAML formatting.
- Schema fingerprint: the complete ordered logical schema and nullability rules serialized as UTF-8 JCS.
- Quality identity: ordered raw quality check IDs, outcomes, severities, counts, and evidence serialized as UTF-8 JCS (the policy-independent raw finding identity); operational timestamps and reviewer display names are excluded. Under policy v2, an effective-decision binding additionally authenticates the policy version, raw-identity SHA-256, effective state, approval record ID, and approval record SHA-256.
- Canonical-content hash: SHA-256 over the ASCII domain prefix `quantara-canonical-content-v1` followed by one NUL byte, then the lowercase ASCII schema fingerprint, a newline, and one UTF-8 JCS JSON array per canonical row in ascending `open_time_utc` order, each terminated by `\n`.

Canonical row arrays use the exact field order in the schema definition. Timestamps are signed epoch-millisecond JSON integers. Decimal values are JSON strings rendered with exactly 18 fractional digits and no exponent. String values are exact validated strings; identity/configuration strings are restricted to printable ASCII in this slice. Nulls cannot occur because every canonical field is non-null. These rules supply unambiguous row framing and prevent Parquet serialization details from changing logical content identity.

Hash-test fixtures must include fixed expected byte sequences and SHA-256 values generated independently from the production hashing path.

### 12.2 Content identity versus attempt evidence

A deterministic content commit and a run attempt are different records:

- The content commit is addressed by canonical-content hash and references deterministic content and quality identities.
- Every invocation, including a verified no-op, writes a unique immutable attempt manifest under `attempts/`.
- Attempt IDs use an unambiguous UTC basic timestamp plus a UUIDv4 suffix. Uniqueness does not depend on clock ordering.
- Attempt manifests record operational timestamps, acquisition/reuse decisions, retry evidence, and the referenced existing or newly published content commit.
- Attempt timestamps never participate in content equality.

### 12.3 Idempotency and provider republication

- If the raw ZIP exists and matches the currently retrieved official checksum, it is reused.
- If the discovered content commit's source hash, descriptor hash, schema fingerprint, parser version, canonical-content hash, quality identity, and object references verify (including committed approval record semantics and effective decision identity under policy v2), execution writes a no-op attempt manifest and leaves the commit and pointer unchanged.
- A same-name artifact with a different hash is never overwritten.
- A changed official checksum creates a separate quarantined evidence set and a blocking review event.
- Partial staged files may be discarded under the explicit recovery policy, but they never become canonical.
- Failed artifacts and uncommitted objects cannot be discovered through `current.json`.

Parquet byte hashes are recorded but are not assumed stable across different library versions or writer configurations. Within the same pinned implementation environment and writer configuration, the Parquet byte hash is expected to be stable. The serialization-independent canonical-content hash is the cross-environment logical identity.

## 13. Manifests, quality evidence, and review transitions

### 13.1 Deterministic content manifest

Each committed dataset manifest records:

- Descriptor semantic content and descriptor hash
- Dataset and instrument identities
- Source and checksum URLs
- Official checksum text hash and parsed SHA-256
- Local ZIP SHA-256 and size
- ZIP member name, uncompressed size, and member hash
- Exact source-header identity
- Parser version
- Schema version and schema fingerprint
- Timestamp-semantics version
- Quality-policy version, deterministic raw quality identity, and under policy v2, effective quality state (`WARN_APPROVED`), raw quality state (`WARN_BLOCKED`), approval record ID, and approval record SHA-256, with canonical `quality-approval.json` preserved in the commit directory
- Source and canonical row counts
- Source and canonical temporal boundaries
- Source ordering state
- Canonical-content hash
- Parquet SHA-256 and size
- Immutable object references
- Legal-use record ID and allowed-use states
- Publication-protocol version

### 13.2 Attempt manifest

Each invocation records separately:

- Unique attempt ID
- Retrieval, processing-start, and processing-end timestamps
- Whether each artifact was downloaded, reused, quarantined, or published
- HTTP status/retry evidence without secrets
- Code revision
- Runtime and dependency-lock identity
- Platform identity where relevant
- Referenced content commit, if any
- Terminal attempt result: `PUBLISHED`, `VERIFIED_NO_OP`, `QUARANTINED`, `FAILED`, or `BLOCKED`
- Diagnostic error identifiers and safe evidence

Attempt manifests are immutable and do not alter content identity.

### 13.3 Quality states

Dataset quality uses explicit states:

- `PASS`: every required check passes; publication is eligible subject to legal gates.
- `WARN_BLOCKED`: no hard invariant failed, but one or more warnings require review; publication is blocked.
- `WARN_APPROVED`: every warning is covered by an immutable approval record under the same quality-policy version.
- `FAIL`: at least one hard quality rule failed; publication is forbidden.

The first golden slice (policy v1) is accepted only with `PASS`. `WARN_APPROVED` may preserve reviewed evidence but does not satisfy this slice's completion gate under policy v1. Under formal amendment Slice 010A (policy v2), `WARN_APPROVED` is an authenticated effective state permitted only when every observed warning matches an immutable, content-bound approval record.

A warning approval record includes the dataset/content identity, canonical content hash, schema fingerprint, ordered source SHA-256 digests, finding IDs, finding counts, canonical finding JCS SHA-256 hashes, approver identity, UTC decision time, rationale, scope, quality-policy version ("2"), quality-identity SHA-256, and canonical self-hash `record_sha256`. Changing data, findings, or policy invalidates the approval. Review never mutates the original quality report or raw quality identity.

### 13.4 Legal-use states

The provider-rights record separately controls:

- `acquire_internal`
- `retain_raw_internal`
- `normalize_internal`
- `analyze_internal`
- `model_train_internal`
- `commercial_production_eligible`
- `customer_display`
- `raw_redistribution`

Each operation is `ALLOWED`, `OWNER_APPROVED_PENDING_COUNSEL`, `PROHIBITED`, or `UNKNOWN`, with source terms, review date, reviewer, and rationale. Acquisition, retention, and normalization proceed only when their corresponding internal states are `ALLOWED` or `OWNER_APPROVED_PENDING_COUNSEL`. `PROHIBITED` or `UNKNOWN` blocks that operation. Owner-approved pending-counsel status is an explicit risk decision and cannot be inferred by code or by public URL accessibility.

Customer-facing or commercial-production behavior requires the relevant state to be `ALLOWED`; pending-counsel status is insufficient. This slice may reach internal `COMPLETE` while commercial production remains ineligible, but only when all operations performed by the slice have an explicit permitted internal state.

## 14. Error handling

### 14.1 Hard failures

No canonical promotion occurs for:

- Invalid descriptor
- Non-allow-listed source
- Failed download after bounded retries
- Missing, malformed, or filename-mismatched checksum
- Checksum mismatch
- Unsafe, corrupt, or structurally unexpected ZIP
- Source-header mismatch
- Malformed numeric or timestamp field
- Decimal precision or scale overflow
- Wrong row count or monthly boundaries
- Missing or duplicate timestamp
- Broken OHLC invariant
- Impossible negative value
- Failed Parquet write or read-back
- Source-to-Parquet reconciliation mismatch
- Manifest inconsistency
- Failure to complete atomic promotion

### 14.2 Warnings

Potential warnings include:

- Source rows are complete and unique but not ordered
- Zero-volume candles
- Nonzero `source_ignore`
- Non-critical transport metadata differences

For the first golden slice (policy v1), any warning produces `WARN_BLOCKED` and prevents acceptance. A review record may preserve an approval decision as `WARN_APPROVED`, but this slice still requires `PASS` under policy v1. Under policy v2 (Slice 010A amendment), narrowly defined reviewed warnings may produce effective `WARN_APPROVED` through immutable, authenticated approval records without mutating raw evidence or relaxing hard invariants.

### 14.3 Retries

Retries are allowed only for eligible transient acquisition failures:

- Connection timeout or reset
- HTTP 429
- Eligible HTTP 5xx responses

Retries are bounded, observable, and use backoff. Checksum, parsing, schema, and quality failures are deterministic and are not hidden behind retries.

### 14.4 Quarantine

Diagnostic artifacts may be retained in quarantine with reason, hashes, and timestamps. Quarantined artifacts are ineligible for normalization promotion, feature construction, model training, serving, or customer use.

## 15. Test strategy

Implementation follows test-driven development.

### 15.1 Descriptor and contract tests

Tests prove:

- Only the approved provider, market, instrument, interval, and bounded period are accepted.
- Invalid periods and intervals are rejected.
- Non-allow-listed hosts and malformed source paths are rejected.
- Path manipulation through symbol, interval, or period is rejected.
- Expected row count is calculated from the half-open UTC interval.
- The stable instrument identity is produced exactly.

### 15.2 Checksum and acquisition tests

Tests cover:

- Valid checksum text
- Whitespace and line-ending variants
- Wrong filename
- Missing, short, long, or non-hexadecimal hash
- Local mismatch
- Interrupted transport
- Eligible retry and ineligible no-retry behavior
- Atomic staging and promotion
- Matching-artifact reuse
- Conflicting-artifact quarantine

Routine tests use controlled local responses and do not depend on Binance availability.

### 15.3 Archive-security tests

Synthetic fixtures prove rejection of:

- Absolute paths
- Drive-prefixed paths
- Parent traversal
- Multiple or unexpected members
- Missing CSV
- Wrong CSV name
- Excessive uncompressed size or compression ratio
- Corrupt ZIP data
- Malformed member content

### 15.4 Parsing and schema tests

Fixtures cover:

- Exact approved 12-column header
- Missing, extra, duplicated, or reordered columns
- Exact decimal preservation
- Explicit scientific-notation policy
- Empty or whitespace-only fields
- Invalid timestamps
- Invalid integer trade counts
- Negative prices or volumes
- Nonzero `source_ignore`
- UTF-8 and line endings
- One-row and parser chunk boundaries

A value such as `42571.90` must remain numerically exact through Parquet read-back without binary-float comparison.

### 15.5 Invariant and property tests

Each row and sequence invariant has an explicit failing regression example. Property-based tests may generate additional valid and invalid cases but do not replace reviewed examples.

### 15.6 Golden offline transformation

A small committed fixture contains representative rows for:

- Ordinary data
- Zero volume
- High decimal precision
- Boundary timestamps
- Large trade count

Expected canonical rows, canonical-content hash, and manifest-relevant evidence are reviewed and fixed. This validates behavior without network access.

### 15.7 Real-artifact integration

A separately marked integration test executes the approved official January archive end to end. It verifies:

- Official and local SHA-256 agreement
- Exactly 44,640 data rows
- Exact first and last UTC boundaries
- No missing or duplicate minute
- Every row and sequence invariant
- Approved Parquet schema fingerprint
- Full source-to-Parquet value reconciliation
- Stable canonical-content hash across equivalent runs
- Stable Parquet hash within the same pinned writer environment
- Verified no-op behavior on rerun
- No temporary canonical artifacts

It does not pass merely because output files exist.

### 15.8 Corruption and recovery

Tests simulate:

- Truncated staged ZIP
- Checksum-altering byte corruption
- Truncated Parquet output
- Same-name/different-hash artifact
- Failure before object publication
- Failure after object publication but before commit-directory rename
- Failure after commit-directory rename but before `current.json` replacement
- Invalid `current.json` reference
- Invalid manifest or object reference
- Stale staging content

The pipeline must recover safely or stop with useful diagnostic evidence. Readers must never discover a partial artifact graph.

### 15.9 Hash, no-op, quality-state, and legal-gate tests

Tests must prove:

- Fixed hash-contract fixtures match independently calculated SHA-256 values.
- YAML formatting and key-order differences that produce the same validated descriptor semantics produce the same descriptor hash.
- Any logical row, schema, field-order, timestamp, or decimal change changes the relevant identity.
- Parquet writer changes cannot alter canonical-content identity when logical rows are identical.
- Every invocation writes exactly one immutable attempt manifest.
- A verified rerun writes `VERIFIED_NO_OP` while leaving content commit and `current.json` unchanged.
- `PASS` permits publication when legal gates permit it.
- `WARN_BLOCKED`, `WARN_APPROVED`, and `FAIL` do not satisfy this golden-slice (policy v1) acceptance gate; policy v2 permits `WARN_APPROVED` solely through exact immutable approval authentication.
- `UNKNOWN` or `PROHIBITED` internal legal state blocks its corresponding operation.
- `OWNER_APPROVED_PENDING_COUNSEL` can permit only the explicitly named internal operation and never makes customer or commercial-production states eligible.

## 16. Acceptance gate

The slice is `COMPLETE` only when:

- The approved descriptor exists and validates.
- Unit, property, security, corruption, and integration tests pass.
- The official archive passes checksum verification.
- The canonical Parquet dataset is readable.
- Every source row reconciles with its canonical Parquet representation.
- Structural checks prove expected count, exact boundaries, continuity, uniqueness, and invariants.
- Manifest references exact verified artifacts and identities.
- Quality state is exactly `PASS` for the golden slice (policy v1); under policy v2, effective `WARN_APPROVED` is acceptable only with complete immutable approval authentication while raw state remains visible.
- The provider-rights record explicitly permits every internal operation performed by the slice under the state rules in Section 13.4.
- An equivalent rerun demonstrates idempotency and writes a `VERIFIED_NO_OP` attempt manifest without altering the content commit or pointer.
- Raw and normalized market data are excluded from Git.
- Documentation restricts artifacts to internal use while commercial rights remain pending review.
- Actual commands and observed results are recorded in the completion report.

Status meanings:

- `COMPLETE`: every acceptance requirement passes.
- `BLOCKED`: source access, legal restrictions, or environment prerequisites prevent completion.
- `INCOMPLETE`: implementation exists but any correctness, reconciliation, security, or idempotency requirement remains unsatisfied.

Passing unit tests alone is insufficient.

## 17. Commercial-safety boundary

Quantara is intended to be commercial, but source accessibility is not treated as redistribution permission.

For this slice:

- A versioned provider-rights record must exist before implementation performs acquisition, raw retention, or normalization.
- `acquire_internal`, `retain_raw_internal`, and `normalize_internal` must each be `ALLOWED` or explicitly `OWNER_APPROVED_PENDING_COUNSEL`; `UNKNOWN` and `PROHIBITED` block the corresponding action.
- Raw and normalized artifacts are restricted to private internal evaluation.
- `commercial_production_eligible`, `customer_display`, and `raw_redistribution` remain ineligible unless separately verified as `ALLOWED`.
- No raw, normalized, delayed, or current market data is exposed to customers by this slice.
- No commercial-use claim is inferred from a public URL.
- Before customer-facing use, the provider-rights matrix must resolve internal storage, model training, derived outputs, customer display, raw redistribution, retention, attribution, and termination obligations.

The internal slice may be completed under an explicit owner-approved pending-counsel decision, but that decision is recorded as risk acceptance rather than legal verification. It never makes the dataset commercially production-eligible.

## 18. Multi-timeframe dependency

One-minute candles are the canonical base, not the only planned timeframe.

The next separately approved subproject may derive:

- 5m
- 15m
- 1h
- 4h
- 1d

Higher-timeframe candles are constructed only from complete canonical one-minute groups under versioned boundary rules. Missing constituent minutes prevent ordinary promotion of the aggregate. Official Binance higher-timeframe archives may be used as independent cross-check evidence, not as a silent replacement authority.

The later aggregation design must specify:

- UTC bucket boundaries
- Half-open intervals
- OHLCV aggregation formulas
- Trade-count and taker-volume aggregation
- Closed-candle availability
- Incomplete-group behavior
- Batch/replay parity
- Cross-check tolerances and discrepancy reporting

## 19. Dependency order after this slice

If this slice is accepted, the preferred order is:

1. Canonical multi-timeframe aggregation and minimal replay
2. Minimal point-in-time feature and label contract
3. Purged temporal validation and simple baseline experiment
4. Versioned execution and cost simulator
5. Candidate-action research
6. Calibration and reliability
7. One bounded live recorder
8. Historical/live feature parity and paper trading
9. Additional crypto instruments and specialist datasets, each through separate maturity gates
10. Product API and UI only after live evidence supports them

This order intentionally moves replay and execution contracts earlier than the broad handoff's original sequence.

## 20. Foundational risks addressed

This design explicitly prevents:

- Silent archive corruption
- Unsafe archive extraction
- Hidden source schema drift
- Binary-float mutation of source decimals
- Missing-minute interpolation
- Duplicate or out-of-order data being silently accepted
- Confusing candle close time with model availability
- Treating archive retrieval time as historical event availability
- Filling at the same candle close after consuming that candle
- Mutable duplicate sources of configuration truth
- Database or service complexity before proving one data path
- Existing artifacts being overwritten after provider republication
- Structurally valid but numerically altered normalized data
- Public source accessibility being interpreted as commercial permission

## 21. Design completion statement

This document is the approved design boundary for Quantara's first historical-data vertical slice. It authorizes implementation planning, not immediate implementation.

Implementation may begin only after a separate detailed plan is written, reviewed, and approved. That plan must preserve this scope and must not silently introduce additional providers, periods, timeframes, services, features, models, or product behavior.
