# Quantara Protocol v1 — Stage 3: Remaining Twelve Source Series

**Status:** READY FOR ZCODE EXECUTION — not implemented
**Date:** 2026-08-31
**Project root:** `D:\PROJECT\Quantara`
**Planning baseline:** `main` at `2f24ad6f30850e8a90dfaca661b1ed8b1d9f1b57`
**Dependency:** Stage 2 accepted, including the fully published BTC funding reference slice.
**Implementation worker:** Zcode, exactly one packet per invocation
**Acceptance auditor:** Hermes

## Execution prompt contract

Never execute this entire stage automatically. The user supplies one packet id. Zcode must execute
that packet only, commit locally, avoid push/merge, report evidence, and stop. Hermes audits before
the next packet.

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-31-protocol-v1-stage-3-remaining-series.md and execute <PACKET_ID> only.
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

## Stage 3 source packets

### S02 — BTC open interest

- Series: `binance_usdm_btcusdt_open_interest`.
- Source: `data/futures/um/daily/metrics/BTCUSDT/`.
- Period: 2020-09-01 through 2024-12-31; exactly 1,583 calendar files expected before source checks.
- Prehistory remains null.
- Enumerate duplicate behavior across every day; never generalize sampled duplicate pairs.
- Exact duplicates deduplicate with evidence; conflicting rows block.
- An OI feature is eligible after its five-minute snapshot interval, not at guessed bar-open time.
### S03 — BTC mark-price klines

- Series: `binance_usdm_btcusdt_mark_1m`.
- Source: `data/futures/um/monthly/markPriceKlines/BTCUSDT/1m/`.
- Period: 60 months.
- Headerless row 0 is data in early files; schema transition is registry controlled.
- Every gap remains null. Constructed mark/index basis is diagnostic only.
### S04 — BTC index-price klines

Same as S03 using `indexPriceKlines/BTCUSDT/1m/`. No model feature stage.
### S05 — BTC native premium-index klines

Same as S03 using `premiumIndexKlines/BTCUSDT/1m/`. This is M1’s primary futures-dislocation
source. Never rename it basis and never reconstruct it from mark/index.
### S06 — Binance BTCUSDT spot klines

- Source: `data/spot/monthly/klines/BTCUSDT/1m/`.
- Period: 60 months, all headerless in the audited range.
- Freeze the A8 expectation: 15 discontinuities and 2,325 missing minutes. Any mismatch blocks
  until source drift is explained; do not edit expectations to pass.
- Use the Binance spot rights record, not the USD-M rights record.
### S07 — ETHUSDT perpetual traded klines

- Source: `data/futures/um/monthly/klines/ETHUSDT/1m/`.
- Period: 60 months.
- Candidate cross-market input only; no model acceptance implied.
### S08 — ETHUSDT settled funding

Same scalar contract as S01, source symbol ETHUSDT, 60 months.
### S09 — ETHUSDT open interest

Same scalar contract as S02, but start exactly 2021-12-01. Expect 1,127 daily filenames through
2024-12-31. Do not create rows, zeros, or missingness indicators before that date. M3 excludes this
series; M3b uses the identical common sample only.
### S10 — ETHUSDT mark-price klines

Source `markPriceKlines/ETHUSDT/1m/`, 60 months, gaps explicit, diagnostic only.
### S11 — ETHUSDT index-price klines

Source `indexPriceKlines/ETHUSDT/1m/`, 60 months, gaps explicit, diagnostic only.
### S12 — ETHUSDT native premium-index klines

Source `premiumIndexKlines/ETHUSDT/1m/`, 60 months. Native premium is distinct from constructed
mark/index basis.
### S13 — Kraken XBT/USD hourly OHLCVT

- Frozen member: `master_q4/XBTUSD_60.csv`.
- Remote object size: 7,885,068,519 bytes.
- Member CRC32: `c351083a`.
- Member SHA-256: `b45e7ce94911d4c1d13bf5c2e270c9219b81631292f7c40bab27e81f7f3f8297`.
- Frozen 2020–2024 expectation: 43,828 rows, 43,828 timestamps, zero duplicates, 20 missing hours.
- Preserve interval-start timestamp. Missing no-trade candles remain null without trade-level proof.
- No raw redistribution; use Kraken rights record.

## 9. Hourly research-data packets

These packets may start only after S01–S13 are accepted and published.
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

**COMPLETE:** S02–S13 are each accepted through A/B/C; every frozen source is checksum/member verified, canonical, quality-approved where defensible, immutably published, graph-verified, and reproducible; no 2025 access occurred.

**BLOCKED:** Any scientific ambiguity, rights failure, integrity mismatch, unexplained source drift,
quality finding without Hermes approval, protocol-hash mismatch, forbidden 2025 access, or need to
expand scope.

**INCOMPLETE:** Code or documents exist but any required test, live run, audit, commit, or acceptance
remains unfinished. A green unit test alone is never COMPLETE.

## First action

Execute **S02-A only** and stop for Hermes audit.
