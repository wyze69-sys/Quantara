# Quantara Data Slice 001 — Implementation Plan

**Status:** Completed and independently verified
**Date:** 2026-08-24
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-24-binance-btcusdt-perpetual-january-2024-data-slice-design.md`
(commit `ca00220`, approved; its line 807 authorizes planning before code)

## 1. Goal

Implement Quantara's first historical-data vertical slice end to end with test-driven development: acquire the official Binance USD-M BTCUSDT 1-minute klines archive for January 2024, verify it against the published checksum, normalize it into an exact-decimal canonical Parquet dataset, reconcile every row, publish it through the content-addressed immutable protocol, and prove idempotency — without any silent alteration, binary-float contamination, or unreviewed promotion.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-24-data-slice-001-implementation.md
and execute it exactly. Do not modify scope. Follow TDD order. Report
COMPLETE / BLOCKED / INCOMPLETE with actual command output evidence.
```

## 3. Approved inputs

- Governing specification: commit `ca00220` (807 lines), approved by the owner; this plan derives every behavioral requirement from it and adds no provider, period, timeframe, service, feature, model, or product behavior.
- Public identity: `wyze69-sys`; all commits use `258711354+wyze69-sys@users.noreply.github.com` (verified configured locally).
- Legal posture (spec §17): a versioned provider-rights record must exist **before** acquisition executes. Internal operations `acquire_internal`, `retain_raw_internal`, `normalize_internal` require `ALLOWED` or explicit `OWNER_APPROVED_PENDING_COUNSEL`. This plan proposes `OWNER_APPROVED_PENDING_COUNSEL` for those three (owner risk acceptance, counsel review pending) and `UNKNOWN` for `analyze_internal`, `model_train_internal`, `commercial_production_eligible`, `customer_display`, `raw_redistribution` (not exercised or ineligible). **The owner must confirm these states during execution Step 1.2 before any network call.**
- Stack pins (proposed defaults; changeable only before execution starts, not after Task 1 commit):
  - Python `3.11.x` via uv (`requires-python = ">=3.11,<3.12"`); host has 3.11.9 and uv 0.11.15.
  - Runtime deps: `pyarrow` (pin exact resolved version ≥21), `PyYAML==6.0.2`, `httpx` (pin exact resolved ≥0.28).
  - Dev deps: `pytest`, `hypothesis`, `ruff` (line length 100).
  - CLI: stdlib `argparse`; entrypoint `python -m quantara`.
  - No pandas, polars, numpy, databases, Docker, or services. Binary floating-point is forbidden in acquisition, parsing, hashing inputs, reconciliation, and read-back checks (spec §6.5); hashing payloads admit only strings, integers, booleans, nulls, arrays, objects — never floats.

## 4. Observed starting state

- Branch `main` == `origin/main`, working tree clean, HEAD `7b40f3f`.
- Repository contains documentation and repository-presentation assets only; no Python package exists.
- `.gitignore` already excludes `/data/`, `.venv/`, caches (from `ca00220`).
- Design-review evidence embedded in the spec: official checksum observed `21eeac04a76a7a35b10467e5e752fb2f8cff77cdeb57df6b50a23ce8d69bb190  BTCUSDT-1m-2024-01.zip`; observed shape 12 columns, 1 header, 44,640 data rows, exact boundaries `2024-01-01T00:00:00Z` … `2024-01-31T23:59:59.999Z`. These are evidence, not embedded expectations: checksum is re-fetched every attempt.

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
pyproject.toml
uv.lock
configs/datasets/binance-usdm-btcusdt-1m-2024-01.yaml
configs/legal/binance-usdm-provider-rights.v1.yaml
src/quantara/__init__.py
src/quantara/__main__.py
src/quantara/errors.py            # stable error identifiers
src/quantara/jcs.py               # RFC 8785 canonicalization subset
src/quantara/descriptor.py        # descriptor + rights-record loading/validation
src/quantara/hashing.py           # hash contract v1 (descriptor/schema/quality/content)
src/quantara/acquisition.py       # downloads, checksum, staging, retries, reuse/quarantine
src/quantara/archive.py           # ZIP central-directory safety + streaming member access
src/quantara/parsing.py           # header contract, timestamps, numeric policy, row mapping
src/quantara/canonical.py         # canonical rows, row + sequence invariants
src/quantara/quality.py           # quality evaluator, states, findings
src/quantara/publication.py       # object store, commit dirs, atomic rename, current.json
src/quantara/manifests.py         # dataset manifest, attempt manifest
src/quantara/pipeline.py          # 22-step orchestration + idempotent rerun
src/quantara/cli.py
tests/conftest.py
tests/fixtures/**                 # committed synthetic + golden fixtures (tiny)
tests/test_*.py                   # mirrors module layout
README.md                         # modified: append one short internal-use section only
```

### 5.2 Forbidden changes

- No edits to: governing spec, presentation spec/plan, README sections other than the single appended section, LICENSE/CODE_OF_CONDUCT/SECURITY/CONTRIBUTING/CITATION.cff, `.github/**`, docs/assets, `.gitignore` (already sufficient).
- No new providers, markets, instruments, intervals, months, timeframes, features, labels, models, APIs, UI, databases, CI workflows, or remote repository-setting mutations.
- No network access in the default test run; the real-archive integration test is separately marked and explicitly invoked.
- No force-push; no rewriting existing history.

## 6. Completion states

- **COMPLETE:** all acceptance items in spec §16 pass, including official-checksum verification, full reconciliation, quality state exactly `PASS`, rights record permitting every performed operation, and a demonstrated `VERIFIED_NO_OP` rerun.
- **BLOCKED:** owner declines the proposed legal states, source unreachable after bounded retries, checksum drift triggers review, or environment prerequisites fail.
- **INCOMPLETE:** implementation exists but any correctness, reconciliation, security, idempotency, or documentation requirement remains unsatisfied.

**Known acceptance risk (surfaced now, not hidden):** spec §14.2 makes *any* warning — including zero-volume candles and nonzero `source_ignore` — produce `WARN_BLOCKED`, and §16 admits only `PASS` for this golden slice. If the real January 2024 archive contains a single zero-volume minute, the slice lands **INCOMPLETE/BLOCKED-by-policy**, resolvable only by a formal spec amendment. Execution therefore runs the real-archive structural scan early (Step 9.2 probe) so this is discovered before deep polish work.

## 7. Task 0 — Preflight

1. `git status --short --branch` → clean `main`, HEAD `7b40f3f`; stop on drift.
2. Verify tools: `uv --version`, `python --version`, `git config user.email` → noreply address.
3. Create transaction dir `%TEMP%\quantara-slice-001\`; all scratch evidence lives there, outside Git.

## 8. Task 1 — Scaffold (commit 1)

1. Write `pyproject.toml`: project `quantara`, `requires-python = ">=3.11,<3.12"`, deps as pinned above, `[project.scripts] quantara = "quantara.cli:main"`, ruff + pytest config (markers `integration`; default addopts `-m "not integration"`), ruff line length 100.
2. Package skeleton with module docstrings defining each component boundary (spec §4.1 five components).
3. `uv lock && uv sync`; record resolved versions into the transaction dir.
4. `uv run pytest` (collects zero tests, exits cleanly) and `uv run ruff check .`.
5. Commit `chore: scaffold quantara package`.

## 9. Task 2 — Errors, JCS, descriptor, rights record (TDD)

Tests first, red → green:

- `errors.py`: stable machine-readable error ids matching spec §14.1 hard failures (e.g. `checksum_mismatch`, `decimal_precision_or_scale_overflow`, `unsafe_zip_member`) and warning ids (§14.2).
- `jcs.py`: RFC 8785 serialization for strings/ints/bools/null/arrays/objects (UTF-8, shortest escaping, key sorting by UTF-16 code units); hard-reject floats. Fixed vectors taken independently from the RFC 8785 test set; production serializer never validates itself.
- `descriptor.py`: strict loader for the YAML descriptor below — unknown keys rejected, identities must equal spec §3.1 exactly, half-open UTC period parse, expected row count derived by calendar math (31 d × 1440 = 44,640), instrument id string equality `binance:usd_m_futures:BTCUSDT:perpetual`, URL construction restricted to template interpolation of validated symbol/interval/month segments (regex `[A-Z0-9]+`, `1m`, `\d{4}-\d{2}`) so path manipulation through fields is impossible; rejection tests for tampered hosts, traversal segments, bad periods/intervals.
- Rights-record loader: eight operations × {state, source_terms, review_date, reviewer, rationale}; gate function `permits(op)` honoring spec §13.4 semantics (`UNKNOWN`/`PROHIBITED` block; pending-counsel permits only the named internal op).
- Descriptor semantic hash stability: two YAML files differing only in formatting/key order hash identically (JCS over validated semantics).
- Commit `feat(descriptor): validated descriptors and rights records`.

Descriptor content (authoritative copy of spec §3):

```yaml
schema: quantara.dataset-descriptor/v1
dataset_id: binance_usdm_btcusdt_klines_1m_2024_01
provider: binance
market_type: usd_m_futures
instrument_id: binance:usd_m_futures:BTCUSDT:perpetual
provider_symbol: BTCUSDT
base_asset: BTC
quote_asset: USDT
settlement_asset: USDT
contract_type: perpetual
dataset_type: klines
interval: 1m
period: { start: "2024-01-01T00:00:00Z", end: "2024-02-01T00:00:00Z" }  # [start, end)
source:
  archive_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
  checksum_url: https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip.CHECKSUM
  allowed_hosts: [data.binance.vision]
  member_pattern: "^BTCUSDT-1m-2024-01\\.csv$"
schema_version: binance_usdm_kline_1m_v1
timestamp_semantics: closed_interval_v1
quality_policy_version: "1"
legal_record: configs/legal/binance-usdm-provider-rights.v1.yaml
```

## 10. Task 3 — Hash contract v1 (TDD)

Per spec §12.1, with fixed expected byte sequences and SHA-256 values generated by an independent script (not the production path):

- `zip_hash`, `checksum_artifact_hash`, `member_hash` over exact bytes.
- `descriptor_hash`: SHA-256 over JCS of validated descriptor semantics.
- `schema_fingerprint`: SHA-256 over JCS of ordered logical schema + nullability rules (the 23 canonical columns, their types/scales).
- `quality_identity`: JCS over ordered check ids, policy version, outcomes, counts, evidence; operational timestamps excluded.
- `canonical_content_hash`: SHA-256(`"quantara-canonical-content-v1" \0` + schema_fingerprint + `\n` + one JCS array per row, ascending, each + `\n`). Timestamps = signed epoch-ms ints; decimals = strings with exactly 18 fractional digits, no exponent; strings printable-ASCII-restricted.
- Regression proofs: logical change ⇒ identity change; Parquet-writer variation ⇒ content identity unchanged.
- Commit `feat(hashing): canonical hashing contract v1`.

## 11. Task 4 — Acquisition (TDD, offline via local fake server fixtures)

Spec §§4.1-2, 14.3, 14.4:

- Unique staging paths under `data/staging/<attempt_id>/…`; stream download with running SHA-256; size cap enforced during transfer.
- Checksum document strict grammar: `^[0-9a-f]{64}  BTCUSDT-1m-2024-01\.zip\r?\n?$` — wrong filename, short/long/non-hex, missing → `invalid_checksum_document`.
- Local-vs-official mismatch → `checksum_mismatch`; matching pre-existing staged/raw artifact reused byte-for-byte; same-name/different-hash conflict quarantined, never overwritten.
- Retries (max 3, backoff 1/2/4 s + jitter) only for connect/read timeout, connection reset, HTTP 429, 502/503/504; deterministic failures never retried.
- Redirects followed manually hop-by-hop; every hop host must be in `allowed_hosts`, else hard fail.
- Quarantine writes reason + hashes + timestamps under `data/quarantine/`.
- Commit `feat(acquisition): verified artifact acquisition`.

## 12. Task 5 — Archive security (TDD)

Spec §§11, 15.3 with synthetic fixtures:

- Central-directory inspection first: exactly one member matching `member_pattern`; absolute/drive-letter/`..` segment names rejected; unexpected extra members rejected; corrupt central directory rejected.
- Bounds: declared uncompressed size ≤ 256 MiB and compression ratio ≤ 100× else `unsafe_zip_member` (constants recorded as policy with rationale; actual file ≈ tens of MB compressed, ~3–4 MB).
- Member streamed via `ZipFile.open` (no extraction to disk); CRC failure mid-stream surfaces as corrupt-zip hard failure.
- Commit `feat(archive): hardened zip inspection and streaming`.

## 13. Task 6 — Parsing and numeric policy (TDD)

Spec §§3.3, 6.4–6.6, 15.4:

- UTF-8 decode, BOM rejected; comma-only; RFC 4180 quoting; LF/CRLF tolerated.
- Header must equal the exact ordered 12-name contract; missing/extra/reordered/duplicated/case-changed names rejected.
- `open_time`/`close_time`: unsigned base-10 epoch-ms integers only (sign, decimal point, exponent, seconds/microseconds rejected); `close_time == open_time + 59_999 ms`; open ∈ [start, end).
- Numerics: regex `^(0|[1-9][0-9]*)(\.[0-9]+)?$`; parsed as `decimal.Decimal` (never float); representability in decimal128(38,18) checked exactly per §6.5 digit budgets; overflow → `decimal_precision_or_scale_overflow`, rounding never.
- `count`: signed int64, non-negative; `ignore` kept verbatim as `source_ignore` (nonzero surfaced, not interpreted).
- Golden value `42571.90` survives to canonical representation exactly (string-level assertion later at read-back).
- Commit `feat(parsing): exact kline parsing and numeric policy`.

## 14. Task 7 — Canonical rows, invariants, quality evaluator (TDD)

Spec §§6–8, 13.3, 14.2:

- Canonical 23-column row assembly; identity fields from validated descriptor; `nominal_available_time_utc = open + 60_000 ms`.
- Row invariants: OHLC bounds, prices > 0, volumes ≥ 0, `taker_buy_* ≤` counterparts, all non-null.
- Sequence invariants over the complete month: derived expected count; unique strictly ascending open times; exactly 60,000 ms adjacency; exact first/last boundary equality; no out-of-period row.
- Quality evaluator emits one finding per check with evidence counts; states per §13.3; any warning ⇒ `WARN_BLOCKED`; aggregate scores never gate alone.
- Source ordering: complete+unique-but-unordered sorts only while recording `source_order_invalid` warning (⇒ WARN_BLOCKED).
- Every invariant has an explicit failing regression fixture; hypothesis generates additional cases (fixed seeds).
- Commit `feat(canonical): row and sequence invariants with quality evaluation`.

## 15. Task 8 — Parquet write/read-back + reconciliation (TDD)

- Fixed writer configuration constant: `pyarrow.parquet` zstd compression, pinned writer version/config recorded in manifest; column order = §6.6 exactly; `timestamp[ms, UTC]`; `decimal128(38,18)`; int64 count; dictionary-encoded identity columns acceptable (logical rows unchanged).
- Read back using the approved explicit schema; reconcile every source row against every Parquet row via exact decimal-string and integer/timestamp comparisons — binary floats never constructed.
- Truncated/garbage Parquet detected by read-back failure → hard fail (feeds §15.8 tests later).
- Commit `feat(parquet): exact write, read-back, and reconciliation`.

## 16. Task 9 — Publication protocol (TDD)

Spec §9 layout and §10 steps 18–22:

- Content-addressed objects under `data/objects/{raw,checksum,normalized}/sha256/<hex>` written once; collision with different bytes = hard fail.
- Commit dir assembled at `datasets/…/commits/.staging-<attempt_id>/` containing manifest, quality report, object refs, content identity, `COMMITTED` marker; flush/close files, best-effort metadata sync; single `os.rename` into `commits/<canonical_content_hash>/` (target must not exist).
- `current.json` written to temp sibling then atomically replaced only after the committed dir verifies.
- Discovery verification reopens through `current.json` and validates the whole referenced graph (manifest hashes → objects → parquet) before reporting success; readers never discover partial graphs; crash points leave only safe orphans, reported and deferred to explicit cleanup.
- Idempotent path: existing valid commit whose source hash, descriptor hash, schema fingerprint, parser version, content hash, quality identity, and object refs all verify ⇒ `VERIFIED_NO_OP` attempt manifest, pointer untouched.
- Changed official checksum vs retained raw ⇒ separate quarantined evidence set + blocking review event.
- Commit `feat(publication): content-addressed immutable publication`.

## 17. Task 10 — Manifests, attempts, pipeline, CLI

- Dataset manifest per §13.1 field list + `publication_protocol_version: v1`, env evidence (python/pyarrow versions, uv.lock hash, git rev-parse, platform).
- Attempt manifest per §13.2: unique id `YYYYMMDDTHHMMSSZ-<uuid4>`, retrieval/start/end timestamps, per-artifact disposition, retry/status evidence sans secrets, terminal result enum, diagnostic ids.
- `pipeline.py` implements the 22-step flow in order with early exit codes: `0` PUBLISHED/VERIFIED_NO_OP; `2` BLOCKED (legal gate or WARN_BLOCKED); `3` FAILED validation; `4` QUARANTINED event.
- CLI: `python -m quantara --descriptor <yaml> --data-root <dir> [--dry-run]`; `--dry-run` performs descriptor/rights/existing-commit verification without network or mutation.
- Commit `feat(cli): end-to-end pipeline orchestration`.

## 18. Task 11 — Golden offline transformation (committed fixture)

Small committed CSV (≤ ~20 rows) covering: ordinary row, zero volume, high precision (`42571.90`-style), first/last boundary timestamps, large trade count. Expected canonical rows, canonical-content hash, and manifest evidence computed by an independent script, reviewed, then frozen in the fixture. Test proves pipeline output equals them offline. Commit `test(golden): offline transformation fixture`.

## 19. Task 12 — Corruption and recovery suite

Simulate §15.8 scenarios (truncated ZIP/Parquet, byte corruption altering checksum, same-name/different-hash, failure injected between publication stages, invalid pointer/manifest refs, stale staging). Assert: hard stop with useful diagnostics, no partial graph discoverable, safe orphan reporting. Commit `test(recovery): corruption and recovery scenarios`.

## 20. Task 13 — Real-artifact integration (marked `integration`, networked)

Explicit invocation `uv run pytest -m integration`. Sequence:

1. **Structural probe first** (cheap, before polish investment): download + checksum-verify the official archive, stream-parse, report zero-volume count, nonzero `source_ignore` count, ordering state, row count/boundaries against §16 gates. If any warning exists → stop, report INCOMPLETE with the amendment question surfaced to the owner (known-risk clause §6 of this plan).
2. Full end-to-end run: PUBLISHED, quality `PASS`, manifest references verified.
3. Rerun: `VERIFIED_NO_OP`, commit dir and `current.json` byte-identical (hashes compared), exactly one new attempt manifest.
4. Cross-run stability: identical canonical-content hash; identical Parquet byte hash within this pinned environment.
5. `git status` proves `/data/` fully ignored; no temp artifacts inside the repo.
Commit (if green) `test(integration): real january-2024 archive acceptance`.

## 21. Task 14 — Documentation and final gates

1. Append one README section `## Data foundation status` (~8 lines): slice 001 implemented; artifacts internal-use only while commercial rights are pending review; nothing customer-facing; pointer to descriptor + rights record. Re-run markdownlint-cli2 0.23.2 with the presentation-pass config over README (expect 0 issues) so the earlier quality bar stays intact.
2. Full local gates: `uv lock --check`, `uv run ruff check .`, `uv run pytest -m "not integration"`, then integration suite again fresh.
3. Push `main` normally (no force); verify remote head and that `/data/` is absent remotely.

## 22. Failure handling

- Any red gate: fix forward; never weaken an assertion to pass.
- Owner rejects legal-state proposal at Step 9 of execution → BLOCKED before any network action.
- Checksum drift vs spec evidence → QUARANTINED + BLOCKED for review; never silent replacement.
- Post-push defect: new fix commit; revert via `git revert` only; never reset/force-push.

## 23. Final evidence report

Record actual commands and outputs for: tool versions and resolved dependency pins; red-test evidence per task; full suite and integration results; official/local checksum agreement; row count, boundaries, continuity proof; canonical-content hash across two runs; VERIFIED_NO_OP evidence; quality state; rights-record states used; `git status` cleanliness re `/data/`; commit SHAs pushed; and terminal status COMPLETE / BLOCKED / INCOMPLETE with residual limitations. Passing unit tests alone is insufficient (spec §16).
