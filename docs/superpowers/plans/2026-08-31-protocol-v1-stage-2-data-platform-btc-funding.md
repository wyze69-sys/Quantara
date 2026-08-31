# Quantara Protocol v1 — Stage 2: Canonical Data Platform and BTC Funding Reference Slice

**Status:** READY FOR ZCODE EXECUTION — not implemented
**Date:** 2026-08-31
**Project root:** `D:\PROJECT\Quantara`
**Planning baseline:** `main` at `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`
**Dependency:** Stage 1 P00–P02 accepted and the Protocol v1 semantic hash frozen.
**Implementation worker:** Zcode, exactly one packet per invocation
**Acceptance auditor:** Hermes

## Execution prompt contract

Never execute this entire stage automatically. The user supplies one packet id. Zcode must execute
that packet only, commit locally, avoid push/merge, report evidence, and stop. Hermes audits before
the next packet.

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-31-protocol-v1-stage-2-data-platform-btc-funding.md and execute <PACKET_ID> only.
Use a dedicated branch/worktree. Preserve unrelated work. Run every packet gate.
Commit only the packet allowlist. Do not push, merge, or auto-advance.
Return COMPLETE / BLOCKED / INCOMPLETE with raw commands, outputs, changed files, hashes, and risks.
STOP after the report.
```

## 2. Goal

Freeze a scientifically defensible Protocol v1, then turn the frozen 2020–2024 raw inventory into
immutable, exact, point-in-time canonical datasets and a locked hourly research table. Only after
those artifacts pass independent audit may Quantara run the pre-registered 2022–2024 experiment.
The plan must remain capable of reporting an honest null result.
## 3. State and inventory boundary

### 3.1 Already canonical

1. Binance USD-M BTCUSDT perpetual traded-price OHLCV, 2020–2024, at 1m/1h/1d.

This lane is immutable input. Packets in this plan may read it but may not alter its published
identities, pointers, descriptors, parser identity, manifests, quality evidence, or canonical bytes.

### 3.2 Frozen remaining inventory — exactly 13 source series

BTC:

1. Settled funding.
2. Open interest snapshots.
3. Mark-price 1m klines.
4. Index-price 1m klines.
5. Native premium-index 1m klines.
6. Binance spot 1m klines.
7. Kraken XBT/USD spot 1h OHLCVT.

ETH:

8. Perpetual traded-price 1m klines.
9. Settled funding.
10. Open interest snapshots, beginning 2021-12-01 only.
11. Mark-price 1m klines.
12. Index-price 1m klines.
13. Native premium-index 1m klines.

### 3.3 Frozen exclusions

Do not add liquidations, options, long/short ratios, taker ratios, altcoins, order books, macro,
on-chain, sentiment, news, or technical-indicator searches. Incidental columns in the Binance
metrics archive may be retained in the immutable raw object but are not canonical Protocol-v1
series and must not enter any feature table.

The older
`docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md` is superseded for
Protocol v1. In particular, its top-trader and taker-ratio scope, guessed completeness rules, and
combined metrics feature direction are not authorized here.
## 5. Architecture boundary

Do not generalize the existing BTCUSDT kline-v1 classes in place. They contain published hard-coded
identities and must remain byte-compatible. Introduce additive Protocol-v1 modules:

```text
src/quantara/protocol.py
src/quantara/series_descriptor.py
src/quantara/series_acquisition.py
src/quantara/series_parsing.py
src/quantara/series_canonical.py
src/quantara/series_quality.py
src/quantara/series_pipeline.py
src/quantara/series_backfill.py
src/quantara/protocol_hourly.py
src/quantara/protocol_features.py
src/quantara/protocol_labels.py
src/quantara/protocol_models.py
src/quantara/protocol_evaluation.py
src/quantara/protocol_run.py
```

Two additive canonical schema families are allowed:

1. `quantara.kline-series/v1`: exact-decimal OHLCV/OHLCVT with explicit temporal envelope and
   designed gap mask. It allows honest missing intervals but never null payload values in present
   rows.
2. `quantara.scalar-series/v1`: exact-decimal scalar observations for settled funding and OI with
   explicit settlement/snapshot semantics.

Use a new hash-domain separator and schema fingerprint for each family. Do not modify
`hash_contract_v1` or any existing canonical hash.
## 6. Global executor rules

For every packet:

1. Work on a dedicated branch/worktree, never directly on shared dirty `main`.
2. Record starting HEAD and `git status --porcelain=v1 -uall`.
3. Preserve all pre-existing untracked `temp/*.md`; do not stage, delete, rename, or rewrite them.
4. Read packet dependencies and stop if an earlier packet lacks Hermes `ACCEPTED` status.
5. Write failing tests first and include the observed red output.
6. Implement only the packet allowlist.
7. Run focused tests, then the packet integration command if named.
8. Run `git diff --check` and inspect `git diff --stat` plus the complete diff.
9. Stage explicit paths only; `git add .` and `git add -A` are forbidden.
10. Commit locally with the packet commit message; do not push, merge, rebase, reset, clean, stash,
    or start another packet.
11. Report exact commands, outputs, files, hashes, row/gap/duplicate counts, and status.

Any unexpected source drift, rights ambiguity, conflicting duplicate, checksum failure, unapproved
quality warning, 2025 access, or need to expand scope is `BLOCKED`, not permission to improvise.

The existing default suite has a long runtime. Use focused tests during a packet and
`.venv/Scripts/python.exe -m pytest -n 4` only at phase gates. Ruff formatting has known pre-existing failures; run
ruff only on changed Python files and never reformat unrelated files.

## Stage 2 platform packets

### D00 — Rights records for the frozen providers and markets

**Depends on:** P02 accepted.

**Create:**

- `configs/legal/binance-spot-provider-rights.v1.yaml`
- `configs/legal/kraken-spot-provider-rights.v1.yaml`
- `tests/test_protocol_rights.py`

**Modify:** none of the existing rights records.

Use the audited internal-only posture: acquisition, raw retention, normalization, analysis, and
internal model development are `OWNER_APPROVED_PENDING_COUNSEL`; commercial production, customer
display, and raw redistribution remain `UNKNOWN`. Bind source terms and audit references. Tests
prove every frozen series resolves to exactly one rights record and forbidden operations fail.

**Commit:** `docs(rights): govern Protocol v1 spot sources`
**Stop:** Hermes audits the rights semantics before any networked packet.
### D01 — Closed series descriptor contract

**Depends on:** D00 accepted.

**Create:**

- `src/quantara/series_descriptor.py`
- `tests/test_series_descriptor.py`
- `configs/series/binance-usdm-btcusdt-funding-settled-2020-2024.yaml`
- `configs/series/binance-usdm-btcusdt-open-interest-2020-09-2024.yaml`
- `configs/series/binance-usdm-btcusdt-mark-1m-2020-2024.yaml`
- `configs/series/binance-usdm-btcusdt-index-1m-2020-2024.yaml`
- `configs/series/binance-usdm-btcusdt-premium-1m-2020-2024.yaml`
- `configs/series/binance-spot-btcusdt-1m-2020-2024.yaml`
- `configs/series/kraken-spot-xbtusd-1h-2020-2024.yaml`
- `configs/series/binance-usdm-ethusdt-traded-1m-2020-2024.yaml`
- `configs/series/binance-usdm-ethusdt-funding-settled-2020-2024.yaml`
- `configs/series/binance-usdm-ethusdt-open-interest-2021-12-2024.yaml`
- `configs/series/binance-usdm-ethusdt-mark-1m-2020-2024.yaml`
- `configs/series/binance-usdm-ethusdt-index-1m-2020-2024.yaml`
- `configs/series/binance-usdm-ethusdt-premium-1m-2020-2024.yaml`

Implement schema `quantara.series-descriptor/v1` with an exact registry of the 13 remaining series.
No free-form provider, symbol, path, parser, interval, start, or end values. URL templates are
constructed from frozen registry entries. Permit only 2020–2024, except BTC OI begins 2020-09-01
and ETH OI begins 2021-12-01. Reject 2019, 2025, traversal, unapproved hosts, wrong rights records,
and model-feature fields in data descriptors.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_descriptor.py tests/test_descriptor.py`
**Commit:** `feat(series): add closed Protocol v1 descriptors`
### D02 — Checksum-aware acquisition and inventory

**Depends on:** D01 accepted.

**Create:** `src/quantara/series_acquisition.py`, `tests/test_series_acquisition.py`.

Reuse existing `Acquirer` and archive safety primitives where compatible. Support:

- Binance ZIP plus adjacent `.CHECKSUM` as mandatory.
- Kraken range retrieval of the frozen `master_q4/XBTUSD_60.csv` member, anchored to remote size,
  central-directory CRC, and member SHA-256 from A9.
- Bounded retries, allowed-host checks on every redirect, content-length caps, unique staging,
  immutable raw objects, and attempt evidence.

No source may silently fall back to an API or another venue. A missing checksum on Binance blocks.
Kraken must explicitly record that its computed member hash is not an operator signature.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_acquisition.py tests/test_acquisition.py tests/test_archive.py`
**Commit:** `feat(series): acquire frozen archives with integrity evidence`
### D03 — Scalar parsing and exact canonical schema

**Depends on:** D02 accepted.

**Create:** `src/quantara/series_parsing.py`, `src/quantara/series_canonical.py`,
`tests/test_series_scalar.py`.

Implement scalar rows for funding and OI using `Decimal`, never float. Funding canonical payload is
`last_funding_rate`; preserve `funding_interval_hours` as source evidence. OI canonical payload is
`sum_open_interest`; preserve `sum_open_interest_value` as diagnostic provenance but do not expose
it as a model feature. Long/short and taker-ratio columns are ignored after structural validation
and cannot appear in canonical output.

Freeze Arrow schema, column order, nullability, Q18 rendering, content-hash domain, writer config,
exact read-back, and reconciliation. Include all temporal-envelope and source-evidence fields.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_scalar.py tests/test_parsing.py tests/test_hashing.py`
**Commit:** `feat(series): canonical scalar funding and OI rows`
### D04 — Gapped kline/OHLCVT canonical schema

**Depends on:** D03 accepted.

**Modify:** `src/quantara/series_canonical.py`, `src/quantara/series_parsing.py`.
**Create:** `tests/test_series_kline.py`.

Support Binance 1m kline shapes and Kraken hourly OHLCVT without changing old kline-v1. Header
presence is descriptor-registry controlled. Present rows are exact and non-null. Missing expected
intervals are represented in a separate deterministic gap manifest, not fabricated Parquet rows.
Freeze OHLC, volume, trade-count invariants and Kraken’s interval-start semantics.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_kline.py tests/test_canonical.py tests/test_parsing.py`
**Commit:** `feat(series): canonical gapped kline and OHLCVT rows`
### D05 — Duplicate, gap, and quality policy

**Depends on:** D04 accepted.

**Create:** `src/quantara/series_quality.py`, `tests/test_series_quality.py`.

Implement family-specific quality checks, complete expected-grid gap enumeration, exact-duplicate
byte comparison, conflict blocking, boundary checks, scalar cadence checks, kline invariants, and
deterministic quality identity. A gap may be an approved designed null; a conflict may never be
approved. Quality approval records must bind series id, source hashes, exact finding ids/counts,
reviewer, and self-hash.

Zcode may generate a proposed finding report but may not author an approval record in this
packet.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_quality.py tests/test_quality.py tests/test_quality_approval.py`
**Commit:** `feat(series): quality gates for gaps and exact duplicates`
### D06 — Generic immutable series publication pipeline

**Depends on:** D05 accepted.

**Create:** `src/quantara/series_pipeline.py`, `tests/test_series_pipeline.py`.
**Modify:** `src/quantara/cli.py` additively for `quantara.series-descriptor/v1`.

Implement descriptor/rights gate, acquisition, archive inspection, parse, dedup evidence, canonical
write/read-back/reconciliation, gap manifest, quality evaluation, PASS-only publication, immutable
objects/commits/current pointer, discovery verification, idempotent `VERIFIED_NO_OP`, and attempt
manifests. Preserve established exit codes. Existing lanes and current pointers must not move.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_pipeline.py tests/test_pipeline.py tests/test_cli.py`
**Commit:** `feat(series): publish immutable Protocol v1 series`
### D07 — Resumable 2020–2024 backfill driver

**Depends on:** D06 accepted.

**Create:** `src/quantara/series_backfill.py`, `tests/test_series_backfill.py`.

Accept one frozen `series_id` and explicit period range from its closed descriptor. Default serial
execution; bounded optional concurrency may not exceed four and must preserve deterministic result
ordering. Resume only from verified current pointers. Emit per-period and aggregate terminal counts.
Never accept 2025.

**Focused gate:** `.venv/Scripts/python.exe -m pytest -q tests/test_series_backfill.py`
**Phase gate:** `.venv/Scripts/python.exe -m pytest -n 4`
**Commit:** `feat(series): add resumable frozen-range backfill`

## 8. Uniform source-packet protocol

Each source packet S01–S13 has three stops:

1. **A — source-contract verification and real boundary artifacts:** tests first; run one earliest and
   one latest audited artifact through a temporary data root; no production pointer. Shared
   infrastructure is already frozen by D00–D07, so a required production-code change blocks A.
2. **B — full inventory and provisional quality:** fetch every frozen file, verify every checksum,
   enumerate all timestamps/gaps/duplicates, and emit a proposed quality report. Do not publish a
   warning-bearing dataset.
3. **C — audited approval and publication:** only after Hermes independently verifies B. If a
   designed-gap/duplicate approval is required, Hermes supplies or approves its exact record.
   Zcode then publishes, verifies the commit graph, reruns to `VERIFIED_NO_OP`, and reports hashes.

A, B, and C are separate commits and separate Zcode invocations. Any failed period stops the
source; do not continue and hide it in aggregate counts.

Source-packet file allowlist:

- `<slug>` is one of `btc_funding`, `btc_oi`, `btc_mark`, `btc_index`, `btc_premium`, `btc_spot`,
  `eth_perp`, `eth_funding`, `eth_oi`, `eth_mark`, `eth_index`, `eth_premium`, or `kraken_spot`.
- A may create only `tests/test_series_<slug>.py` and
  `tests/test_integration_series_<slug>.py`; it may write disposable runtime evidence under
  `temp/protocol_v1_audits/<series_id>/`. If shared production code or a descriptor must change,
  return `BLOCKED`; Hermes will issue a separate D-series correction packet.
- B creates or updates only
  `docs/superpowers/audits/protocol-v1/<series_id>-inventory-and-quality.md` plus disposable runtime
  evidence. It may not create an approval or move a production pointer.
- C consumes an exact Hermes-approved quality record, performs publication, and updates only the
  permanent audit report plus source-specific regression expectations. Publication artifacts live
  under the configured data root and are not staged into Git unless an already-tracked repository
  policy explicitly requires it. A Git commit is still required for the permanent audit evidence.
- No source packet may modify `protocol.py`, the frozen protocol YAML/spec, model code, another
  source descriptor/test, or any old BTC kline-v1 file.

Common focused tests:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_series_<slug>.py tests/test_series_pipeline.py
.venv/Scripts/python.exe -m pytest -q -m integration tests/test_integration_series_<slug>.py
```

## 8. Uniform source-packet protocol

Each source packet S01–S13 has three stops:

1. **A — source-contract verification and real boundary artifacts:** tests first; run one earliest and
   one latest audited artifact through a temporary data root; no production pointer. Shared
   infrastructure is already frozen by D00–D07, so a required production-code change blocks A.
2. **B — full inventory and provisional quality:** fetch every frozen file, verify every checksum,
   enumerate all timestamps/gaps/duplicates, and emit a proposed quality report. Do not publish a
   warning-bearing dataset.
3. **C — audited approval and publication:** only after Hermes independently verifies B. If a
   designed-gap/duplicate approval is required, Hermes supplies or approves its exact record.
   Zcode then publishes, verifies the commit graph, reruns to `VERIFIED_NO_OP`, and reports hashes.

A, B, and C are separate commits and separate Zcode invocations. Any failed period stops the
source; do not continue and hide it in aggregate counts.

Source-packet file allowlist:

- `<slug>` is one of `btc_funding`, `btc_oi`, `btc_mark`, `btc_index`, `btc_premium`, `btc_spot`,
  `eth_perp`, `eth_funding`, `eth_oi`, `eth_mark`, `eth_index`, `eth_premium`, or `kraken_spot`.
- A may create only `tests/test_series_<slug>.py` and
  `tests/test_integration_series_<slug>.py`; it may write disposable runtime evidence under
  `temp/protocol_v1_audits/<series_id>/`. If shared production code or a descriptor must change,
  return `BLOCKED`; Hermes will issue a separate D-series correction packet.
- B creates or updates only
  `docs/superpowers/audits/protocol-v1/<series_id>-inventory-and-quality.md` plus disposable runtime
  evidence. It may not create an approval or move a production pointer.
- C consumes an exact Hermes-approved quality record, performs publication, and updates only the
  permanent audit report plus source-specific regression expectations. Publication artifacts live
  under the configured data root and are not staged into Git unless an already-tracked repository
  policy explicitly requires it. A Git commit is still required for the permanent audit evidence.
- No source packet may modify `protocol.py`, the frozen protocol YAML/spec, model code, another
  source descriptor/test, or any old BTC kline-v1 file.

Common focused tests:

```text
.venv/Scripts/python.exe -m pytest -q tests/test_series_<slug>.py tests/test_series_pipeline.py
.venv/Scripts/python.exe -m pytest -q -m integration tests/test_integration_series_<slug>.py
```

## Stage 2 reference-source packet

### S01 — BTC settled funding

- Series: `binance_usdm_btcusdt_funding_settled`.
- Source: `data/futures/um/monthly/fundingRate/BTCUSDT/`.
- Period: 2020-01 through 2024-12.
- Parse all 60 months; do not rely on the earlier 15-month sample.
- Preserve timestamp jitter; do not round `calc_time` to an 8h boundary.
- Validate the observed interval field; do not hardcode a universal cap.
- Feature eligibility uses strict settlement time; archive publication is separate.

Commits: `feat(funding): ... adapter`, `data(funding): ... inventory`,
`data(funding): publish BTC settled funding 2020-2024`.
## 11. Phase-gate audit requirements

Hermes performs these after P02, D07, each source C packet, H07, E02, E03, and E04:

1. Inspect complete diff and commit content.
2. Verify file allowlist and no ownership contamination.
3. Rerun focused and full tests independently.
4. Run real acquisition/publication in a separate temporary data root.
5. Verify source hashes, row counts, gaps, duplicates, exact Decimal paths, and manifests.
6. Verify all current pointers and authenticated graph closure.
7. Verify old BTC kline/research/training identities did not move.
8. Search for forbidden 2025 reads, forward/nearest joins, fills, floats, feature columns, and source
   fallbacks.
9. Confirm `HEAD` remains unpushed until acceptance.
10. Return `ACCEPTED`, `CORRECTION_REQUIRED`, or `BLOCKED` with evidence.

## Stage completion gate

**COMPLETE:** D00–D07 and S01-A/B/C are accepted; BTC funding is fully checksum-verified, canonical, immutably published, graph-verified, and a verified no-op rerun; shared abstractions pass all legacy tests.

**BLOCKED:** Any scientific ambiguity, rights failure, integrity mismatch, unexplained source drift,
quality finding without Hermes approval, protocol-hash mismatch, forbidden 2025 access, or need to
expand scope.

**INCOMPLETE:** Code or documents exist but any required test, live run, audit, commit, or acceptance
remains unfinished. A green unit test alone is never COMPLETE.

## First action

Execute **D00 only** and stop for Hermes audit.
