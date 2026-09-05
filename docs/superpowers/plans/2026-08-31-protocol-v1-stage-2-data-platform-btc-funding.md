# Quantara Protocol v1 — Stage 2: Canonical Data Platform and BTC Funding Reference Slice

**Status:** S01-B `ACCEPTED` and merged (PR #21, merge commit `a3e6e46`; executed directly by Hermes. One commit `ce45275` adding exactly the one tracked file the Stop B allowlist permits, `docs/superpowers/audits/protocol-v1/btc_settled_funding-inventory-and-quality.md` (254 lines), with zero other tracked files modified and all pre-existing untracked `temp/*.py` scripts preserved. Full frozen inventory verified: **60/60 periods** acquired through the frozen D07 `run_series_backfill` driver into an isolated temporary data root, 120 HTTP requests (archive plus adjacent `.CHECKSUM` per period) with zero requests outside the exact allowlist, provider checksum matching the retained ZIP 60/60, parser-input hash matching the published graph 60/60, commit graph verified 60/60. Aggregate source facts: **5481 settlement rows, 5481 distinct, 0 duplicates, 0 same-key conflicts**, source byte order strictly increasing in every period, observed `funding_interval_hours` `8` for every row, first settlement 2020-01-01T00:00:00Z and last 2024-12-31T16:00:00Z. Row count is independently consistent with the calendar — 1827 days across 2020-2024 times three settlements per day equals 5481, and every individual month equals its own day count times three, so no month is short. Cadence analysed as consecutive deltas across the whole 60-month series rather than against an assumed grid: 5480 deltas, **0 negative or zero**, **0 more than 60 s from 8 h**, 70 distinct delta values spanning -4 ms to +5 ms around 8 h in the ten most common. Millisecond jitter is preserved exactly and only reported as distance from each row's own interval grid: 2403 of 5481 rows (43.8%) carry offsets of 1-47 ms, per-period jitter counts 7-73; no timestamp was rounded, snapped, or filled. Provisional quality is **PASS on all 60 periods** with zero `warn` and zero `fail` findings, so no approval proposal was generated, no approver or decision time exists, nothing is `authorized: true`, and S01-C requires no designed-gap or duplicate approval for this source. Verification: full suite `-n 4` **2097 passed, 1 skipped** locally and identically in CI (11m24s) — unchanged from S01-A because Stop B adds no tests; focused 63 passed, ruff clean, `uv sync --locked` no drift; funding-rate values grep-verified absent from the committed document and every evidence JSON. No production `data/` root was written and no 2025 acquisition occurred. Caveat: no pre-run production-pointer snapshot was taken, so this asserts no production root was ever passed to the pipeline rather than a before/after pointer hash comparison, and it is not verified whether other sources are affected by F-S01B-1 since only this series was acquired.) Previously: S01-A

**Finding F-S01B-1 — dropped connections are not retry-eligible (OPEN, needs a D-series correction).** Robustness defect in shared acquisition; not a data-integrity problem and no incorrect data was produced or published. The first inventory run used `workers=4` and 3 of the first 4 periods failed with `DownloadFailed` carrying `"retry_evidence": []` — zero retry attempts — while the driver correctly halted the entire source (1 PUBLISHED, 3 FAILED, 56 `not_attempted`, exit 3) rather than hiding the failures in aggregate counts. Root cause: `_is_connection_reset` in `src/quantara/acquisition.py` decides retry eligibility by substring-matching the exception message (`isinstance(exc, httpx.TransportError) and 'reset' in str(exc).lower()`), so a server-dropped connection raising `httpx.RemoteProtocolError('Server disconnected without sending a response.')` — a `TransportError` whose message contains no 'reset' — falls straight through to `DownloadFailed` with no backoff and no second attempt. Reproduced offline with synthetic transports: the bare protocol error gets 1 transport call and 0 retries while the identical exception class with 'reset' in its message gets 3 calls, so the same class is retried once or three times depending purely on wording. Confirmed transient rather than a source problem by rerunning the identical inventory serially (`workers=1`), which published all 60 periods with exit 0; all recorded evidence comes from that serial run. Not fixed in S01-B because Stop B has no production-code allowance. The correction must classify retry eligibility by exception type rather than message text, with a synthetic test proving a `RemoteProtocolError` is retried `MAX_ATTEMPTS` times. Operational note until then: run multi-period backfills for this source with `workers=1`.

**Status:** S01-A `ACCEPTED` and merged (PR #20, merge commit `6708163`; executed directly by Hermes on owner authorization after three preflight BLOCKs, all three caused by packet defects rather than executor error: (1) a genuinely stale baseline after D08 governance moved main `0603e3b` to `6c729d3`, then (2) and (3) a hash-domain error where Hermes replaced the packet's 40-hex Git blob IDs with 64-hex SHA-256 content digests while leaving `git rev-parse BASE:path` as the prescribed verification command, so the pins could never compare equal; no file had drifted and no agent deleted code. Section 0 now names the hash domain explicitly and all 12 pins were reverified programmatically 12/12 at `6c729d3`. One commit `8e71f42` adding exactly the two files the Stop A allowlist permits (`tests/test_series_btc_funding.py` 27 offline contract tests with an autouse fixture that fails on any network use, and `tests/test_integration_series_btc_funding.py` 2 real-network tests marked `integration`), with **zero tracked files modified** and all five pre-existing untracked `temp/*.py` probes preserved. Real `data.binance.vision` acquisition verified for both frozen boundary periods: 2020-01 and 2024-12 each 93 source rows, 93 distinct, 0 duplicates, 0 conflicts, provider adjacent CHECKSUM authenticating the ZIP (matching the prior A1 probe `zip_sha256` for both), quality PASS, published with the commit graph verified, then rerun to `VERIFIED_NO_OP` with zero acquisitions; 4 HTTP requests total, each URL asserted against an exact two-entry allowlist before the socket opened. Recorded source facts: observed `funding_interval_hours` is `8` only in real data and is validated as a positive integer and preserved as observed, never forced to 8 (the offline suite proves `1`, `4`, `24`, `0004`, and int64-max survive while `0`, `-1`, `4.5`, `abc`, empty, and int64-overflow are BLOCKED with `counts_complete: false`); millisecond settlement jitter is preserved uncorrected and reported only as distance from each row's own interval grid — 14 off-grid rows in 2020-01 and 18 in 2024-12, offsets +1 to +7 ms. D08's scientific-notation support holds on real data and `1.25E-8`/`-2.5e-9` round-trip as exact `Decimal`. No funding-rate value appears in any committed file or evidence JSON; comparisons are boolean-only by construction. No production `data/` root was written — every data root was an isolated temporary directory — and 2025 appears only as a rejection assertion (exit 3, zero HTTP calls, no `datasets/`). Red-first was proven by mutation sensitivity rather than by deleting a module, which proves nothing about a contract: a disposable `temp/` probe monkeypatched `parse_scalar_rows` to round timestamps onto a clean 8h grid and to force every interval to `'8'`, each making the corresponding test fail (exit 1), with both passing again once the mutation was removed; in-suite negative controls cover corrupted provider CHECKSUM (exit 3, `ChecksumMismatch`, no parse attempt, no pointer, no `COMMITTED`) and non-strict eligibility. Full suite `-n 4` **2097 passed, 1 skipped** locally and identically in CI (11m24s); the honest delta is +27 collected offline tests measured as baseline collect 2071 selected at `6c729d3` versus 2098 with S01-A added, not a raw subtraction from D08's 2092 which had counted the earlier untracked test files; focused 63 passed, real integration 2 passed, fresh `git archive` checkout 27 passed, ruff clean, `uv sync --locked` no drift. Caveat: no pre-run production-pointer snapshot was taken, so this asserts no production root was ever passed to the pipeline rather than a before/after pointer hash comparison. Next: S01-B full 60-period inventory and provisional quality, a separate packet and commit.) Previously: D08

**Status:** D08 `ACCEPTED` and merged (PR #19, merge commit `831a56f`; Hermes independent audit PASS 2026-09-05 — original S01-A packet BLOCKED by executor because Binance renders small funding rates in scientific notation (e.g. `8.4E-7`, `-4.2E-7`) which the frozen `NUMERIC_PATTERN` rejected as malformed; fixed by adding `_expand_scientific()` to `parsing.py` that converts exact-decimal scientific notation to fixed-point *before* the existing policy checks, so all precision-budget and format guarantees stay intact — no floats used; two commits `3a1be63` + `e1902cc` on parent `0603e3b`, exactly three files modified (`src/quantara/parsing.py` production fix, `tests/test_parsing.py` new `test_scientific_notation_is_expanded_exactly` + removed unused `MalformedNumeric` import, `tests/test_series_scalar.py` replaced two parametrized values that assumed scientific notation was malformed); full suite `-n 4` **2092 passed, 1 skipped** = 2081 D07 baseline + 11 new parsing tests, fresh checkout 43 parsing tests pass, ruff clean, `uv sync --locked` no drift. Recorded: scientific notation is now accepted only when it represents an exact decimal (e.g. `8.4E-7` → `0.00000084`); the exponent branch runs before all existing guards, so `NaN`, `Infinity`, precision-budget overflow, and sign rules still apply unchanged. Note: D08 was implemented directly by Hermes on the executor's S01-A branch rather than as a separately authored packet with an independent audit, so it did not receive the usual D-series independent-falsification treatment; its behavior was subsequently exercised against real exchange archives by S01-A.) Previously: D07

**Status:** D07 `ACCEPTED` and merged (PR #18, merge commit `e095d39`; Hermes independent audit PASS 2026-09-04 — original packet BLOCKED by executor because its mandatory manifest-linkage rule demanded a `selected_period` the frozen pipeline cannot supply on a pre-selection terminal state, resolved by Correction 1 reclassifying rights denial as a series-level preflight (no period is attempted, no manifest fabricated) and replacing field matching with attempts-directory snapshot-difference; one commit `b37cb2a` on parent `f19e0c6`, exactly two added files and **zero existing files modified** (tracked count 322 to 324, CLI untouched); all 8 baseline pins matched at the parent; full suite `-n 4` **2081 passed, 1 skipped** = 2032 D06 baseline + 49 new, fresh checkout 49 passed, red-first reproduced (49 errors with the module stripped), 15/15 Hermes falsification probes pass — out-of-window and malformed range endpoints rejected with zero acquisition, all invalid worker counts rejected before execution, resume never contacts a source, blocked periods never publish, rights denial writes no manifest and creates no lane, repeated serial runs report identical stop points; ruff clean, `uv sync --locked` no drift. Recorded limit: with workers > 1, `stopped_at` is the first observed failure, so a batch holding both a BLOCKED and a FAILED period may report either; the attempted set, counts, not_attempted, and aggregate exit code remain deterministic. No real backfill was executed — first production run is a separate S-series invocation.) Previously: D06 `ACCEPTED` and merged (PR #17, merge commit `830dcbc`; Hermes independent audit PASS 2026-09-04 — original packet BLOCKED by executor on four real specification defects (no period selector, two nonexistent gate files, Kraken retained formats incompatible with a ZIP-only member read, ambiguous CLI pin semantics), Correction 1 BLOCKED on a contradictory Kraken integrity rule the executor reproduced with a synthetic probe (compressed vs decompressed member; windowed selection vs full member), resolved by Correction 2 separating the retained-bytes and parser-input hash domains; one commit `dc1614e` on parent `d154640`, exactly the three allowlisted files (new `series_pipeline.py`, new `test_series_pipeline.py`, additive `cli.py` dispatch arm + `--period`); all 12 baseline pins matched at the parent and all nine frozen modules byte-identical; full suite `-n 4` **2032 passed, 1 skipped** = 1996 D05 baseline + 36 new, fresh checkout 36 passed, red-first reproduced (36 errors with the module stripped), 12/12 Hermes falsification probes pass — manifest/object/pointer tampering all break verification, duplicate rows BLOCK instead of publishing, commit address equals the canonical row hash, legacy lanes byte-identical after a series run in the same data root; ruff clean, `uv sync --locked` no drift. PASS-only publication: WARN blocks for review, FAIL never publishes.) Previously: D05 `ACCEPTED` and merged (PR #16, merge commit `1dc1457`; Hermes independent audit PASS 2026-09-04 — original packet BLOCKED by executor on a real contract mismatch (parse results carried no duplicate_hashes/conflict_rows), corrected via Correction 1; one commit `7de5c15` on parent `182d193`, exactly the four allowlisted files, additive Part A + new quality layer; full suite `-n 4` **1996 passed, 1 skipped** = 1940 D04 baseline + 56 new quality tests, fresh checkout 390 passed, 18/18 Hermes falsification probes PASS, ruff clean; new identities: schema `quantara.series-quality/v1`, domain `quantara-series-quality-v1`; conflicts hard-fail with no approval path; unknown gaps stay `unclassified_pending_review`.  D04 `ACCEPTED` and merged (PR #15, merge commit `0f5152c`; Hermes independent audit PASS 2026-09-04 — one commit `5dc7a6a` on parent `9ed3e7a`, exactly the three allowlisted files, path→blob diff 317→318 paths with 0 removed/0 unrelated changed; executor COMPLETE confirmed: focused gate 203 passed, adjacent 576 passed/1 skipped/1 deselected, full suite `-n 4` **1940 passed, 1 skipped** = 1810 D03 baseline + 130 new kline tests, ruff clean, `uv sync --locked` clean, fresh checkout 363 passed; Hermes independently reproduced the full suite 1940/1 in 779s and the focused gate 203 from a clean `git archive` extraction, and reproduced the red claim by stripping the two D04 additive regions from a throwaway tree — 129 failed/1 passed, the single pass being `test_legacy_identities_unchanged`, which must pass before and after. New identities: kline rows `quantara.kline-series/v1` fingerprint `32048c41…` domain `quantara-kline-gap-manifest-content-v1`'s sibling `quantara-kline-series-content-v1`; gap manifest `quantara.kline-gap-manifest/v1` fingerprint `9625517b…` domain `quantara-kline-gap-manifest-content-v1`; domain census shows zero collisions, D03 scalar fingerprint `a2819e59…`, legacy kline-v1 `feab7d2b…`, and `quantara-canonical-content-v1` all unchanged. Design review: descriptor-driven header policy enforced both directions; 13-digit epoch-ms vs 10-digit epoch-s grammars with minute/hour grid alignment; Binance bar-span `close − open + 1 == 60000`; Kraken interval close derived `K + 3600000 − 1` and eligibility `close + 1 ms`; signed prices only for mark/index/premium; derived-family volumes asserted exactly zero with structural-zero semantics recorded; `source_count` nonnegative int64 evidence, `trade_count` null iff derived else equals source count; Kraken window hard-frozen to 1577836800000–1735689600000 matching the single `2020-2024` member; gap manifest enforces `present + gaps == expected` with strictly ascending grid-aligned in-window entries, `exclusion_reason` null because D04 evaluates no lookback (D05's authority); JCS+LF deterministic serialization with own hash domain; Parquet decimal128(38,18) typed read-back with exact-schema equality and fail-closed reconciliation; strictly increasing `(series_id, event_ts)`. Audit evidence notes (no correction): executor report SHA-256s for the two modified sources hash the CRLF worktree layer rather than committed blobs — blob layer verified separately by Hermes (`05d7b4ff…`/`a89cf806…`); red transcripts captured before `test_parquet_determinism_readback_and_reconciliation` widened from 1 to 3 params (127 vs 129 failing nodes), case-class coverage complete. Real Kraken 43,828/43,848/20 anchor deliberately NOT re-probed by the executor — synthetic only per packet; real-data acceptance is the acquisition/publication seam. Residual: `source_ordered: false` recorded but non-blocking (real member is ordered per D02); a disorder block is a D05 candidate. GitHub CI green 11m28s; merged main byte-identical to the audited commit, 318 paths, zero content differences; post-merge spot check 290 passed + ruff clean. **Next action: D05 only** (`src/quantara/series_quality.py` + `tests/test_series_quality.py`, quality/gap/duplicate policy, Zcode proposes findings but never authors approval records). D03 `ACCEPTED` and merged (PR #14, merge commit `69405b3`; Hermes independent audit PASS 2026-09-04 — two commits verified, `b812097` implementation plus `27e95b4` correction, each one commit on its pinned parent with only allowlisted files; path→blob tree diff confirms 0 unrelated files changed across both; focused gate 233 passed, adjacent regression 432 passed/1 skipped, full suite `-n 4` 1810 passed/1 skipped, ruff clean, `uv sync --locked` clean, fresh checkout of the commit object 317 files 233 passed; GitHub CI green 11m15s with 1810 passed/1 skipped; merged main verified byte-identical to the audited commit, 317 paths, zero content differences. 40 Hermes falsification probes: hostile ambient Decimal context — prec=1, traps on Inexact/Rounded/Subnormal — changes no content hash on nonzero, exact-zero, or OI paths; Protocol v1.1 eligibility exact at funding `F + 1 ms` and OI `O + 300000 ms`; forbidden ratio/taker families absent from schema, content arrays, and hash input; Q18 boundary rejects 19 fractional and 21 integer digits while `99999999999999999999.123456789012345678` round-trips byte-exact; Parquet writes byte-deterministic and a metadata-stripped schema is rejected on read; attempt evidence exclusive-create with no source value; kline-v1 identity unmoved at fingerprint `feab7d2b…`. Audit finding F1 — `csv.reader` unquoted RFC-4180 fields before the module's grammar ran, admitting a second physical encoding under parser identities `binance_settled_funding_csv/v1` and `binance_open_interest_csv/v1` — closed by `27e95b4`; red-first independently reproduced at exactly 28 failed/132 passed by removing only the two guard lines. Record terminators deliberately remain LF or CRLF compared as raw bytes; four real archive members verified value-blind as unquoted, LF-only, BOM-free across 77,059 bytes. Deferred finding: the legacy kline-v1 parser `src/quantara/parsing.py` accepts quoted fields and is left unchanged because its parser identity is froz... [truncated]
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
Use a dedicated feature branch in D:\PROJECT\Quantara (no worktree; git status --short empty before starting). Preserve unrelated work. Run every packet gate.
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

1. Work in `D:\PROJECT\Quantara` on a dedicated feature branch; `git status --short`
   must be empty before the packet starts. No per-packet worktree (successor master
   plan, post-C5 decision of record). Never work directly on `main`.
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
12. Extent metadata that necessarily spans beyond 2024-12-31 (archive first/last rows, remote
    sizes, member counts, CRC or hash anchors) may be read value-blind: cite the field name,
    count, or hash, but never display, log, or parse into memory a row or candle value dated
    2025 or later. Boundary rows of an explicitly bounded window ending on or before
    2024-12-31 (e.g. `audit_2020_2024.last_row`) are permitted. Added by IR-2026-09-03-1.

Any unexpected source drift
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

After D00 is accepted, execute **D01 only** and stop for Hermes audit. After D01 is
accepted (2026-09-03, PR #12), execute **D02 only** and stop for Hermes audit.

## Incident log

### IR-2026-09-03-1 — D01 start: Zcode displayed a 2025-dated archive-extent row

- **Reporter:** Zcode (executor), during D01 startup inspection of the A9 Kraken range probe.
- **Trigger:** `Get-Content temp/audit_a9_kraken/a9_kraken_range_probe_v1.json | Select-Object -First 95`
  displayed top-level `last_row` = a 2025-12-31 23:00 UTC row. Plan §6 stop rule fired; Zcode
  stopped before any implementation, created no files, and preserved a clean branch.
- **Exposure:** exactly one displayed value set: top-level `last_row[0] = 1767222000`
  (2025-12-31 23:00) plus sibling OHLCV columns in that row. The bounded
  `audit_2020_2024` window is clean (first `1577836800` = 2020-01-01 00:00 UTC; last
  `1735686000` = 2024-12-31 23:00 UTC; 43,828 rows of the 96,381-row archive). No other
  2025-range values exist anywhere in tracked `temp/` — verified by a repo-wide
  value-blind scan (`temp/scan_2025_exposure.py`, method recorded in this log) whose
  only hit is the same `$.last_row[0]`.
- **Provenance of the exposure:** the probe JSON was committed at `2f24ad6` (2026-08-31),
  which is the Stage 2 planning baseline itself. The 2025-dated extent metadata was present
  before D01 started and is *planned scope*: `range_requests` byte ranges and the member
  SHA-256 anchor are D02 acquisition inputs. Extent metadata is the *necessary* 2025-
  spanning surface D02 needs (archive extent must be known to fetch byte ranges).
- **Ruling: NON-BREACH.** The sealed-2025 rule governs labels, features, distributions, and
  scoring-relevant reads of 2025 *market data*. A single archive-extent row — the final row
  of a public archive, committed at baseline, whose sibling values are acquisition anchors —
  is not a market-data read for scoring purposes. Zcode's stop was correct and conservative;
  the prompt for D01 should have specified value-blind reading of extent fields, which is the
  process gap this IR fixes by adding §6 rule 12.
- **Resolution:** §6 rule 12 (value-blind extent-reading rule) added; status line updated;
  D01 resumes on the existing clean branch `codex/protocol-v1-d01-series-descriptors` at
  `95c2de6`, working tree clean, no code created yet. Amended D01 prompt issued by Hermes.
- **Method notes (scan):** digit-string handling was required (the ts is stored as a string
  `"1767222000"`), plus explicit ISO-date regex for string fields; dict-key-only heuristics
  miss list-position timestamps, so the scan walks all JSON scalars. The scanner is committed
  at `temp/scan_2025_exposure.py` for rerun.
- **Seal impact:** none. `sealed_2025` remains SEALED; forbidden operations (labels, feature
  distributions, model scores, conditional outcome inspection, protocol adaptation) were not
  performed; allowed pre-gate checks were used for boundary verification only.
- **Keys for the future:** when a probe artifact contains 2025 extent fields, prompts must
  instruct value-blind reading; when a worker reports a 2025 exposure, the first Hermes
  action is a value-blind scan for 2025-range values across `temp/` JSONs, then a ruling on
  extent-vs-market classification.

### IR template (for future incidents)

Reporter, trigger, exposure, provenance, ruling (breach / non-breach), resolution, method
notes, seal impact, keys for the future.

