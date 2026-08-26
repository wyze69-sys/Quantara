# Quantara Data Slice 003a — Rights Record v2 Implementation Plan

**Status:** Proposed plan; awaiting owner review and approval
**Date:** 2026-08-26
**Project root:** `D:\PROJECT\Quantara`
**Governing design:** `docs/superpowers/specs/2026-08-26-rights-record-v2-analytical-use-design.md`
(the features/labels lane is blocked on `analyze_internal`; this slice unblocks it honestly)

## 1. Goal

Implement the versioned governance amendment end to end with test-driven development: add `configs/legal/binance-usdm-provider-rights.v2.yaml` exactly as design §5, reclassify `analyze_internal` into the owner-approvable internal class in `src/quantara/descriptor.py`, prove with a full permit-matrix regression that v1 behavior is byte-for-byte unchanged while v2 grants exactly one new permission, freeze the anti-laundering guarantee for training/commercial/display/redistribution, leave every descriptor and pipeline untouched, update the README's rights note, and push — without any in-place rights edit, identity drift, or scope creep.

## 2. Required execution prompt

```text
Read D:\PROJECT\Quantara\docs\superpowers\plans\2026-08-26-data-slice-003a-rights-record-v2.md
and execute it exactly. Do not modify scope. Follow TDD order. Report
COMPLETE / BLOCKED / INCOMPLETE with actual command output evidence.
```

## 3. Approved inputs

- Governing design: this slice's design specification (proposed above); behavioral requirements derive from it, slice 001 design §17, and slice 002 design §3.6/§13. The owner approves both documents by launching execution.
- Public identity: `wyze69-sys`; all commits use `258711354+wyze69-sys@users.noreply.github.com`.
- Legal posture: this amendment itself is the owner risk-acceptance decision; it changes no pipeline gating yet. `model_train_internal`, `commercial_production_eligible`, `customer_display`, `raw_redistribution` remain `UNKNOWN` and blocking.
- Stack pins: unchanged (Python 3.11 via uv; PyYAML 6.0.2; pytest, hypothesis, ruff line length 100). No new dependencies.
- No networked work is required; the integration-marked suite is not part of acceptance.

## 4. Observed starting state

- Branch `main` == `origin/main`, working tree clean, HEAD `40ae2b08f2e1198f4b1476fbd2000a3ab0aeeaeb` (slice 002 milestone correction, independently verified).
- 332 offline tests green; ruff clean; lockfile verified at starting HEAD.
- Frozen anchors (captured 2026-08-26 at HEAD `40ae2b0`):
  - `sha256(configs/legal/binance-usdm-provider-rights.v1.yaml)` = `547fc79c060aba09197e7d22efe6cfd8a94a2f2515f8b8150c7a3cf767e03697`
  - `descriptor.APPROVED_INTERNAL_OPERATIONS == ("acquire_internal", "retain_raw_internal", "normalize_internal")`
  - `tests/test_rights_and_periods.py` pins the v1 permit matrix (lines ~92–99) and the tuple contents (line ~129).
- Reuse unmodified: `load_rights_record`, `RightsRecord.permits`, `RIGHTS_*` grammar constants (`src/quantara/descriptor.py`).

## 5. Scope and file boundaries

### 5.1 Exact file allowlist (new unless marked)

```text
configs/legal/binance-usdm-provider-rights.v2.yaml   # v2 record, content fixed by design §5
src/quantara/descriptor.py                           # modified: APPROVED_INTERNAL_OPERATIONS gains "analyze_internal" — nothing else
tests/test_rights_and_periods.py                     # modified: tuple assertion updated + new v2/v1 matrix tests
README.md                                            # modified: short rights-amendment note appended to "Data foundation status" section only
```

### 5.2 Forbidden changes

- No edits to: the v1 record (re-verify its SHA-256 unchanged at the end); any dataset descriptor (`configs/datasets/**`); `pipeline.py`, `derive_pipeline.py`, `cli.py`, `manifests.py`, `publication.py`, or any other module; existing specs/plans; `.github/**`; `.gitignore`.
- No semantic weakening of existing tests; the tuple-content assertion change is the codified amendment, not a relaxation — the new value must assert all four operations explicitly.
- No new operations, states, schema versions, providers, periods, timeframes, features, labels code, models, APIs, UI, databases, CI workflows, or remote repository-setting mutations.
- No network access; no force-push; no history rewrite; `/data/` never enters Git.

## 6. Completion states

- **COMPLETE:** all tasks done; offline suite fully green including new regressions; v1 SHA-256 anchor re-proven unchanged; README lint-clean; pushed once with remote synchronization proven.
- **BLOCKED:** repository drift from expected HEAD; environment prerequisites fail; owner declines this plan before execution.
- **INCOMPLETE:** implementation exists but any record-content, permit-matrix, anti-laundering, documentation, or cleanliness requirement remains unsatisfied.

**Known risks (surfaced now):** none functional — this slice executes no pipeline. The governance risk (counsel may later overturn owner acceptance) is accepted by design §7 and resolved by a future v3 supersession, not by silent edits.

## 7. Task 0 — Preflight

1. `git status --short --branch` → clean `main`, HEAD `40ae2b0`, synchronized with `origin/main` after a normal fetch; stop on drift.
2. Verify `uv --version`, Python 3.11.x, `git config user.email` → noreply address.
3. Confirm `sha256sum configs/legal/binance-usdm-provider-rights.v1.yaml` equals the frozen anchor.
4. Create transaction dir `%TEMP%\quantara-slice-003a\`; scratch lives there only.

## 8. Task 1 — v2 record + loader validation (TDD)

Tests first, red → green:

- New test loading `configs/legal/binance-usdm-provider-rights.v2.yaml` through `load_rights_record`: asserts `record_id == "binance-usdm-provider-rights.v2"`, schema-valid eight-operation coverage, top-level review date `2026-08-26`, and `permits("analyze_internal") is True`. Runs red today (file absent / gate closed).
- Add `configs/legal/binance-usdm-provider-rights.v2.yaml` byte-exactly per design §5.
- Commit `feat(governance): add provider-rights record v2 for internal analytical use`.

## 9. Task 2 — Permit-matrix regression + reclassification (TDD)

Tests first, red → green:

- Matrix test over both records: under v1 `permits("analyze_internal") is False`; under v2 it is `True`; acquire/retain/normalize identical (`True`) under both; model-train/commercial/customer/redistribution `False` under both.
- Anti-laundering freeze: build an in-memory variant of the v1 record with `model_train_internal.state = "OWNER_APPROVED_PENDING_COUNSEL"` and assert `permits("model_train_internal") is False` — pending-counsel status must never suffice outside the internal-approved class.
- Then the single code change: `APPROVED_INTERNAL_OPERATIONS = ("acquire_internal", "retain_raw_internal", "normalize_internal", "analyze_internal")` in `src/quantara/descriptor.py`.
- Update the tuple-content assertion deliberately to the four-operation value.
- Full offline suite green; no other existing test modified.
- Commit `feat(governance): classify analytical computation as owner-approvable internal use`.

## 10. Task 3 — Documentation, gates, push

1. Append to README's `## Data foundation status` section (~4 lines): a v2 rights record now exists authorizing internal analytical computation pending counsel review; v1 remains the binding record for published datasets; training, commercial, display, and redistribution stay ineligible.
2. `markdownlint-cli2@0.23.2` over `README.md` with temporary out-of-repo config `{"MD013": false}` → 0 issues; remove the temp config afterward.
3. Full local gates fresh: `uv lock --check`, `uv run ruff check .`, `uv run pytest -m "not integration"`, `git diff --check`.
4. Cleanliness proofs: v1 SHA-256 still equals the frozen anchor; `git ls-files data` empty; `git status --ignored --short data` shows `!! data/`; changed-file set equals the allowlist exactly.
5. Stage exactly the four allowlisted files (never `git add .`); inspect `git diff --cached`; commit `docs(governance): document rights record v2 amendment`; push `main` normally once; verify `HEAD == origin/main == ls-remote` and `/data/` absent remotely.

## 11. Failure handling

- Any red gate: fix forward; never weaken an assertion or policy to pass.
- v1 hash mismatch or descriptor drift discovered mid-task: stop and report `BLOCKED` — that indicates out-of-scope mutation requiring owner review.
- Post-push defect: new fix commit; revert via `git revert` only.

## 12. Final evidence report

Record actual commands and outputs for: preflight state; red→green evidence per task; final permit matrix (v1 vs v2); anti-laundering freeze result; v1 SHA-256 equality proof; lock/ruff/offline-suite results; markdownlint output; changed-file list vs allowlist; commit SHAs; push synchronization; terminal status COMPLETE / BLOCKED / INCOMPLETE with residual limitations. Passing unit tests alone is insufficient.
