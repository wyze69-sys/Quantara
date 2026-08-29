# Data Slice 013 — Binance Vision Derivatives Backfill (Funding + Metrics)

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-29
**Starting HEAD:** `d328f3b22e9d731b78ce3c5a5ba3c8269ff1f95a` (main, clean, synced with origin)
**Executor:** Owner-chosen (Codex default per memory; OpenCode/Antigravity/Cline acceptable). Hermes wrote this plan from a verified live archive probe on 2026-08-29.

**Provenance:** implements the only named deferred slice from the 012 plan
(§3) and Phase A1 of `docs/superpowers/roadmap.md`. The derivatives data
(funding rate, open interest, top-trader long/short ratios) is the classical
missing signal family for perpetual-futures research — slice 014 will fold
these into the research table, but the data must exist as its own retained
lane first.

## 0. Owner authorization (read first)

The v3 rights record (`configs/legal/binance-usdm-provider-rights.v3.yaml`)
already approves `acquire_internal`, `retain_raw_internal`,
`normalize_internal`, and `analyze_internal` over `data.binance.vision` public
archives. **No rights-record amendment is required or permitted in this slice.**
All artifacts stay private internal research evidence; no customer display, no
redistribution, no commercial production use, no live trading — the same
posture as 001–012. This slice trains nothing; it is acquisition +
normalization only.

## 1. Goal

Acquire and normalize two new data families from `data.binance.vision` into
the existing content-addressed store, retaining them as new lanes alongside
the klines/research/validation/evaluation/training chain:

- **Funding rate** — perpetual-futures funding payments (every 8h, all
  contracts on the symbol). `archive_url` pattern
  `data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-YYYY-MM.zip`,
  archived **2020-01 → present**.
- **Metrics** — open interest, top-trader long/short position ratios, taker
  long/short volume ratios, 5-minute granularity. `archive_url` pattern
  `data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip`,
  archived **2020-09-01 → present**.

Both are small (funding ~825 B/mo × ~80 months ≈ 66 KB; metrics ~12 KB/day ×
~2,188 days ≈ 26 MB — combined < 30 MB total). The slice publishes them
under the existing immutable, content-addressed, quality-gated, attempt-
evidence discipline used by every prior slice.

## 2. Verified archive facts (live probe 2026-08-29)

These were fetched with `curl -sI` against the real archive before this plan
was frozen; the plan's references and frozen anchors are the values the
archive actually returned today.

- **Funding — 2020-01 first file:**
  `GET https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip`
  → `200 OK`, `Content-Length: 825`, `Last-Modified: 2023-05-09`.
  CSV columns: `calc_time,funding_interval_hours,last_funding_rate` (94
  rows in 2020-01 = 3 payments/day × 31 days + 1 boundary row, matches
  the 8-hour funding interval).
- **Funding — recent month sanity check:**
  `BTCUSDT-fundingRate-2026-07.zip` → `200 OK`, `Content-Length: 914`.
- **Metrics — 2020-09-01 first file:**
  `GET https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip`
  → `200 OK`, `Content-Length: 12191`.
  CSV columns:
  `create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio`
  (577 rows = 5-minute samples × 288/day, 5-min granularity — note the
  correction from 012 §3 which said "daily"; the *file* is daily but
  *rows* are 5-min intraday samples).
- **Metrics — recent day sanity check:**
  `BTCUSDT-metrics-2026-08-28.zip` → `200 OK`, `Content-Length: 11604`.

`allowed_hosts: ["data.binance.vision"]` for both; `member_pattern`
anchored to the exact filename so the zip-bomb guard rejects any
unexpected extra member. **No checksum file is published for either
family** — the kline CHECKSUM pattern doesn't exist here; integrity is
re-verified by content hash after staging, same as the kline path.

## 3. Scope and non-goals

In scope: two new dataset descriptors (one per family); two new pipeline
modules (or a parameterized `funding_pipeline` / `metrics_pipeline` pair);
per-month funding run (80 months) and per-day metrics run (2,188 days) as
new retained lanes; unit tests; one real-data integration test per family;
plan-doc commit; one final push.

Forbidden (STOP and report BLOCKED if tempted): any change to frozen slices
001–012 behavior or retained artifacts; any edit to any rights YAML; new
dependencies; any binary-float arithmetic in transforms/aggregation/
hashing; any change to `data/` layout, content-addressing, or the
existing klines/research/validation/evaluation/training lanes; `git add .`;
force-push; training on the new data; touching research-table features
or models (slice 014's job); any change to the kline `acquisition.py`
parser beyond what's strictly needed for the new CSV shapes; any claim
that derivatives data implies model performance.

Non-goals (deferred to named later slices):

- Slice 014: derivatives feature expansion (funding → research table).
- Slice 015+: multi-year/multi-asset backfill of the kline path.
- The 5-min metrics granularity is not propagated to 1h/1d in this slice —
  it is acquired + retained as its own 5-min lane; the higher-timeframe
  derivation (if any) is a later slice.

## 4. Frozen anchors (re-verify at T0)

Verify each at T0 against the live store; the slice must restore them
byte-exactly at exit (the integration test owns the snapshot/restore
discipline for all eight pointers, including the new funding/metrics
lanes).

Resting pointers from the existing 012 chain (must be unchanged at
slice exit — same seven values as 012 §2):

```text
klines/BTCUSDT/1m       9d7eee742d0a75612d0b37affcc0e4e40feee67c6f5e1d21f317a8821c9b448f
klines/BTCUSDT/1h       702dab9f66b9d7181458916324ce906020d6415709b4189b395b1378b6b9e271
klines/BTCUSDT/1d       2d09178f767dc563306359db8a31d96d7d00c90890ffd78635ffd94db35a02bf
research/BTCUSDT/1h     cb9079eab9e1f7237d736f5f5021270fd0c8dc176a5ee37d5fdd38ac9977c548
validation/BTCUSDT/1h   166651165729ec3cda1cc48967e45eace09dc6a9b078a3e619efc9af15b3a410
evaluation/BTCUSDT/1h   d2354cd10fd9b1640e42ba90c2d677c329103859c3f9673e6bcbec76210d4675
training/BTCUSDT/1h     0284c655c7c195820f7cb739ea5574bc69334986ca5a108537be585f2cfbc20f
```

The two new lanes (funding, metrics) start empty — no `current.json` yet.
First publish creates it; no-op rerun is the default thereafter.

## 5. Design

### 5.1 Dataset descriptors (one per family)

Additive to the existing descriptor schema. Two new YAMLs under
`configs/datasets/`:

- `binance-usdm-btcusdt-funding-2020-01.yaml` (and per-month siblings, or
  one descriptor parameterized by month — see §5.2) — `schema:
  quantara.dataset-descriptor/v1`, `dataset_type: funding`,
  `instrument_id: binance:usd_m_futures:BTCUSDT:perpetual`,
  `interval: 8h` (funding cadence), `period: 2020-01-01T00:00:00Z →
  2020-02-01T00:00:00Z` for the first month, `legal_record:
  configs/legal/binance-usdm-provider-rights.v3.yaml`,
  `source.archive_url: data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip`,
  `source.member_pattern: "^BTCUSDT-fundingRate-2020-01\\.csv$"`.
- `binance-usdm-btcusdt-metrics-2020-09-01.yaml` (and per-day siblings, or
  one parameterized) — same shape, `dataset_type: metrics`, `interval:
  5m`, `period: 2020-09-01T00:00:00Z → 2020-09-02T00:00:00Z`,
  `source.archive_url: data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-09-01.zip`.

**Decision needed at planning time:** the kline path acquired one ZIP per
month (e.g. `BTCUSDT-1m-2024-01.zip`); the 80-month funding backfill would
mean 80 descriptor files, which is mechanically fine but verbose. The
**recommended approach** (to confirm with the executor's first TDD task) is
to extend the existing pipeline to take a parameterized descriptor with a
`period: {month: "YYYY-MM"}` and a `repeat_until: "YYYY-MM"` block, so one
descriptor drives 80 month-runs via the existing loop. The kline path is
left unchanged (regression test: no kline descriptor now supports
`repeat_until`). The metrics path uses the same pattern with
`period.day` and `repeat_until_day`.

### 5.2 Acquisition (extends `acquisition.py` minimally)

- New `acquire_funding_archive(month: str) -> ArchiveFetchResult` and
  `acquire_metrics_archive(day: str) -> ArchiveFetchResult` thin wrappers
  that reuse the existing `fetch_zip` + `verify_member_pattern` +
  `verify_no_extra_members` (the zip-bomb guard).
- The acquisition module gains a small `parse_funding_csv` and
  `parse_metrics_csv` function — each returns a typed record list
  (Decimal for monetary fields, int for timestamps, str for symbol).
  Funding: `FundingRow(calc_time_ms: int, funding_interval_hours: int,
  last_funding_rate: Decimal)`. Metrics: `MetricsRow(create_time:
  datetime, symbol: str, sum_open_interest: Decimal,
  sum_open_interest_value: Decimal,
  count_toptrader_long_short_ratio: Decimal,
  sum_toptrader_long_short_ratio: Decimal,
  count_long_short_ratio: Decimal,
  sum_taker_long_short_vol_ratio: Decimal)`.
- The kline parser is **not** touched; new code lives in
  `src/quantara/funding_acquisition.py` and
  `src/quantara/metrics_acquisition.py` (or a single
  `derivatives_acquisition.py` if the executor prefers one module —
  either is acceptable; the allowlist below commits to one file).

### 5.3 Canonical normalization (new modules)

- `src/quantara/funding_canonical.py` — Q18-quantized Decimal values,
  ms-since-epoch `calc_time` (matches the source; conversion to a
  `datetime` happens only at read-back), `funding_interval_hours` as
  small int, `last_funding_rate` as Q18 string.
- `src/quantara/metrics_canonical.py` — Q18 for the seven numeric
  columns, `create_time` as ms-since-epoch int (or as ISO 8601 string
  for stable hashing — choose one and pin it in the descriptor;
  ISO 8601 with `Z` suffix and `microsecond=0` is the safer default
  because it survives timezone interpretation drift in tests).
- Both modules use the same `DECIMAL_CONTEXT(prec=50,
  ROUND_HALF_EVEN, Emin/Emax=±999999, traps
  InvalidOperation/DivisionByZero/Overflow)` and the same
  `canonical_content_hash` discipline as 001.
- New `schema_fingerprint` for the two new `schema_version` strings
  (e.g. `binance_usdm_funding_8h_v1`, `binance_usdm_metrics_5m_v1`).
  Pin them in the descriptor; the canonical module rejects mismatches.

### 5.4 Quality (new modules)

- `src/quantara/funding_quality.py`:
  - Row count equals `expected_count` for the month (3/day × days-in-
    month ± 1, anchored on `funding_interval_hours = 8`).
  - `calc_time` strictly increasing and within the month period
    `[start, end)`.
  - `last_funding_rate` is a finite Decimal; reject NaN/inf silently
    encoded as strings.
  - `funding_interval_hours` is one of `{8}` (today) or whatever the
    archive actually shows for that month (the value is in the CSV;
    do not hardcode 8 globally; assert it appears consistently
    within a month).
- `src/quantara/metrics_quality.py`:
  - Row count for a day: 288 ± small slack (5-min samples × 288/day,
    but allow ±2 for archive boundary noise).
  - `create_time` strictly increasing.
  - `symbol == "BTCUSDT"` (the archive is per-symbol already, but
    verify; the file we probed shows `BTCUSDT`).
  - All seven numeric fields are finite Decimal.

### 5.5 Pipeline (new modules)

- `src/quantara/funding_pipeline.py` — runs acquisition →
  normalization → quality → publication for a single month.
- `src/quantara/metrics_pipeline.py` — same for a single day.
- Both follow the exact pattern of 001's `pipeline.py`: rights gate →
  staging → integrity → content hash → write → read-back → quality
  check → `write_current` → attempt manifest. Exit codes
  0/2/3/4 with the established meanings.
- Idempotency: rerun is `VERIFIED_NO_OP` with byte-identical pointer.
- Per-month/per-day runs are dispatched by a thin driver
  `src/quantara/derivatives_backfill.py` that loops over
  `2020-01 → 2026-08` (funding) and `2020-09-01 → 2026-08-28`
  (metrics). The driver writes one attempt manifest per (family,
  period) and is itself a thin shell — the per-period real work is
  delegated to the per-period pipeline.
- The driver runs **serially** by default (network calls + per-period
  quality gate, not suitable for the xdist harness). Configurable
  concurrency stays at 1 in this slice; an option for parallelism is
  a later slice (no over-engineering here).

### 5.6 Pointer layout (new lanes under `data/`)

- `data/datasets/binance/usdm/funding/BTCUSDT/year=YYYY/month=MM/current.json`
  — one pointer per month (matches the kline path's year=month=01
  grouping but the funding lane uses the actual month directory
  layout, not just `01`).
- `data/datasets/binance/usdm/metrics/BTCUSDT/year=YYYY/month=MM/day=DD/current.json`
  — one pointer per day.
- Staging, objects, and CAS layout under
  `data/objects/`, `data/staging/` follow the existing pattern
  unchanged. The per-month/per-day directory naming is the only
  layout change, and it lives under the lane dirs only.

### 5.7 Leakage guarantees (encode as tests)

- Acquisition only talks to `data.binance.vision` (host allowlist).
- No member outside `member_pattern` is extracted (zip-bomb guard
  regression).
- `last_funding_rate` and the seven metrics numerics never round-
  trip through `float`; the parser raises on float inputs (mirror
  011's `_validate_numeric`).
- Quality gate's `expected_count` is computed from the period
  parameters in the descriptor, not from a hardcoded constant.
- Pointer write only happens on quality PASS; the integration
  test's `finally` restores both new pointers and the seven
  resting pointers byte-exactly.

## 6. Task sequence (strict TDD)

- **T0 — Plan and baseline.** Write this document verbatim to
  `docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md`;
  commit `docs: plan data slice 013 Vision derivatives backfill`. Verify
  starting state: HEAD `d328f3b…`, clean tree, the seven resting
  pointers (§4) match the live store, offline suite green
  (`uv run pytest -m "not integration" -q`).
- **T1 — Funding acquisition + canonical + quality.** Red: hand-
  computed 2020-01 fixture (expected rows, expected
  `last_funding_rate` Q18 strings, expected `calc_time` ms-since-
  epoch values from the live probe); parser rejects floats; quality
  rejects NaN strings, non-monotonic time, wrong interval, wrong
  count. Green: `src/quantara/funding_acquisition.py` (or part of
  the single derivatives module), `src/quantara/funding_canonical.py`,
  `src/quantara/funding_quality.py`, plus unit tests
  `tests/test_funding_acquisition.py`, `tests/test_funding_canonical.py`,
  `tests/test_funding_quality.py`. Commit
  `feat(funding): acquire, canonical, quality for funding-rate lane`.
- **T2 — Funding pipeline.** Red: full path against a synthetic
  descriptor (parquet bytes + manifest + pointer write +
  no-op rerun + bad-quality → exit 3 + race-safe object write).
  Green: `src/quantara/funding_pipeline.py`,
  `tests/test_funding_pipeline.py`. Commit
  `feat(funding): funding-rate publication pipeline`.
- **T3 — Funding real-data integration.**
  `tests/test_integration_funding.py` — drives the real 2020-01
  acquisition, snapshots the seven resting pointers + both new
  lane pointers (the funding lane starts empty, so the new
  pointer is *created* by this test and must be restored in
  `finally` to "no file" or to a per-test fresh sibling if the
  test runner reuses the store). Asserts: exit 0, `PUBLISHED`,
  `pointer_replaced=True` for the new lane, `object_written=True`
  (new bytes), `commit_renamed=True`, attempt manifest with
  `referenced_commit` matching the published commit, then a
  no-op rerun exits 0 with `VERIFIED_NO_OP` and all eight
  pointers byte-identical. Commit
  `test(integration): real Vision funding acquisition for 2020-01`.
- **T4 — Metrics acquisition + canonical + quality.** Mirror T1
  for the metrics shape (8 columns, 5-min granularity, 288 rows
  per day, ISO 8601 timestamps, `symbol == "BTCUSDT"`). Same
  module split decision. Commit
  `feat(metrics): acquire, canonical, quality for metrics lane`.
- **T5 — Metrics pipeline.** Mirror T2. Commit
  `feat(metrics): metrics publication pipeline`.
- **T6 — Metrics real-data integration.** Mirror T3 for
  2020-09-01. Commit
  `test(integration): real Vision metrics acquisition for 2020-09-01`.
- **T7 — Backfill driver.** Red: a `dry_run` driver that
  iterates `2020-01 → 2026-08` (funding, 80 months) and
  `2020-09-01 → 2026-08-28` (metrics, ~2,188 days) and reports
  what it would publish without writing. Green: actual driver
  that runs each (family, period) through the per-period
  pipeline. The driver writes a single top-level
  `attempt_manifest.json` per (family, period) and is itself
  resumable: on re-entry, periods already at `VERIFIED_NO_OP`
  are skipped. Commit
  `feat(backfill): derivatives backfill driver with resume`.
- **T8 — Full backfill integration.** Real driver run end-to-end
  for the 2020-01 funding month and 2020-09-01 metrics day
  (one period per family, to keep the test runtime bounded
  — the production run is the human-driven CLI). The full
  80-month + 2,188-day production run is **not** part of the
  CI test suite; it is a one-shot CLI invocation the executor
  performs after T8 gates are green. Commit
  `test(integration): derivatives backfill driver real-data probe`.
- **T9 — Final gates and push.** `uv lock --check`;
  `uv run ruff check .`; `uv run pytest -m "not integration" -q`;
  `uv run pytest -m integration -q` (both year-chain training
  drives take minutes each; keep the machine quiet; the new
  integration tests for funding/metrics are fast — one
  acquisition each);
  `git diff --check`; changed-file set equals §7 allowlist;
  single push; verify `HEAD == origin/main`, clean tree,
  `data/` untracked. Report COMPLETE/BLOCKED/INCOMPLETE
  with raw outputs, the per-lane pointer bytes, and the
  produced attempt-manifest terminal_results.

## 7. Strict file allowlist

Create:

- `src/quantara/funding_acquisition.py` (or part of
  `derivatives_acquisition.py` — choose one and commit to it),
- `src/quantara/funding_canonical.py`,
- `src/quantara/funding_quality.py`,
- `src/quantara/funding_pipeline.py`,
- `src/quantara/metrics_acquisition.py` (or part of the same derivatives
  module),
- `src/quantara/metrics_canonical.py`,
- `src/quantara/metrics_quality.py`,
- `src/quantara/metrics_pipeline.py`,
- `src/quantara/derivatives_backfill.py`,
- `configs/datasets/binance-usdm-btcusdt-funding-2020-01.yaml`,
- `configs/datasets/binance-usdm-btcusdt-metrics-2020-09-01.yaml`,
- `tests/test_funding_acquisition.py`,
- `tests/test_funding_canonical.py`,
- `tests/test_funding_quality.py`,
- `tests/test_funding_pipeline.py`,
- `tests/test_integration_funding.py`,
- `tests/test_metrics_acquisition.py`,
- `tests/test_metrics_canonical.py`,
- `tests/test_metrics_quality.py`,
- `tests/test_metrics_pipeline.py`,
- `tests/test_integration_metrics.py`,
- `tests/test_derivatives_backfill.py`,
- `tests/test_integration_derivatives_backfill.py`,
- `docs/superpowers/plans/2026-08-29-data-slice-013-vision-derivatives-backfill.md`.

Modify:

- `src/quantara/descriptor.py` (add `binance_usdm_funding_8h_v1` and
  `binance_usdm_metrics_5m_v1` to the schema fingerprint set, if
  schema_fingerprint is centrally registered there; if it's per-
  module, no change),
- `tests/conftest.py` (additive only — new fixture helpers for the
  two descriptors and the empty-lane pointer snapshot),
- `README.md` (one-line note in the "Current bounded scope" section
  that funding and metrics lanes now exist; do **not** remove the
  "FOUNDATION-STAGE" header — that change belongs to 014.5).

Nothing else — no CLI change, no rights change, no `uv.lock` change
(no new dependencies: `httpx`, `pyarrow`, `pyyaml` already cover
network, parquet, and config). Any other changed file = BLOCKED.

## 8. Stop conditions

Report BLOCKED with evidence if: any §2 verified archive fact has
drifted by the time T0 runs (re-probe with `curl -sI` and update
the plan in a separate commit before T1); the seven resting
pointers do not match the live store at T0; the offline suite
is not green at T0; any quality-policy test fails; a real-data
acquisition produces a different `Content-Length` or row count
than §2 (a single daily/monthly archive can drift; if it does,
the executor records the new value in the final report and
proceeds; only a *systematic* drift across multiple periods
blocks); the integration test cannot restore the eight pointers
byte-exactly (or "no file" for the two new lanes at the start
of T3/T6); any §3 scope boundary would need violating.

## 9. Final report requirements

Status (`COMPLETE`/`BLOCKED`/`INCOMPLETE`); starting/ending HEAD;
changed-file list vs §7; per-task red→green evidence; the eight
restored pointer bytes (or "no file" for the two new lanes at
slice exit, which is the expected steady state for a re-run
slice — the integration tests are the durable evidence, not
the production backfill's published commits); the per-period
attempt-manifest counts (`PUBLISHED` vs `VERIFIED_NO_OP` per
month for funding, per day for metrics); the two new
`dataset_id` values and their content hashes; raw gate outputs;
push confirmation.

The 80-month funding + 2,188-day metrics production backfill is
**not** part of this slice's test suite. It is a one-shot CLI
invocation the executor runs after T8 gates are green and
records in the final report as
`BACKFILL_FUNDING_MONTHS=80 BACKFILL_METRICS_DAYS=2188` with
the per-period terminal_result counts. If the production run
encounters any `BLOCKED` or `FAILED` period, report the per-
period diagnosis and the resumable position — do not re-run
the whole backfill.
