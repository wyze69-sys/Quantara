# Quantara Repository Instructions

These instructions apply to the entire repository. A more specific `AGENTS.md` may narrow them for a subtree but may not weaken the scientific-integrity or evidence requirements here.

## Roles and execution boundary

- **Zcode is the bounded implementation worker.** Give it exactly one packet ID from an approved plan per invocation.
- **Hermes owns specification, independent audit, verification, and acceptance.** Executor self-review is evidence, not acceptance.
- Zcode must commit locally and stop after the assigned packet. It must not push, merge, or begin another packet.
- A packet may advance only after Hermes independently returns `ACCEPTED`. A green executor report is not sufficient.
- Pushes, pull requests, merges, stage transitions, and scientific scope changes require owner authorization. An explicit instruction to finish the work includes normal commit, push, and remote verification; it never authorizes bypassing scientific gates or merging without review.

## Required packet loop

1. Read the governing specification and the single assigned packet.
2. Confirm dependencies, branch/worktree, file allowlist, prohibited files, and acceptance commands.
3. Audit pre-existing tracked and untracked work before editing; preserve unrelated work and attribution.
4. Implement only the packet, tests first where the plan requires it.
5. Run every packet gate and report raw commands, outputs, changed files, hashes, and residual risks.
6. Commit only the packet allowlist locally and stop.
7. Hermes independently inspects the diff and trust boundaries, reruns the gates, performs required live/fresh-checkout verification, and returns `ACCEPTED`, `CORRECTION REQUIRED`, or `BLOCKED`.
8. If correction is required, Hermes writes bounded correction requirements, Zcode implements and commits them locally, and Hermes re-audits. Do not auto-advance. If the owner explicitly routes implementation to Hermes-direct instead, a separate independent reviewer must audit it before acceptance.

The routing index for the current program is `docs/superpowers/plans/2026-08-31-protocol-v1-freeze-and-canonicalization-master-plan.md`.

## Scientific and data-integrity invariants

- The frozen Protocol v1 specification and its machine-readable contract are authoritative for the current experiment.
- Preserve point-in-time eligibility. Never use nearest, forward, unfinished-bar, stale-value, or future-revision joins where the protocol forbids them.
- Missing is null, never zero. Do not interpolate prohibited gaps or invent availability.
- Preserve exact decimal-safe canonical representations, deterministic provenance, authenticated manifests, and content identity.
- Canonical publication requires quality state exactly `PASS`; warnings are not self-approving.
- Treat provider/legal-use gates as fail-closed controls.
- Do not add datasets, features, model stages, thresholds, or tuning outside the frozen inventory and model ladder.
- Native premium is the preregistered futures-dislocation feature. Constructed mark/index basis is diagnostic only.
- ETH open interest begins 2021-12-01, is never zero-filled, and enters only its identical-common-sample ablation.
- The former four-feature OHLCV 24-hour-direction modeling line is terminated. Do not reopen it.
- The 2025 evaluation window remains blind-sealed until all locked 2022–2024 gates pass and the protocol authorizes its single evaluation.

## Evidence and trust boundaries

- Never claim completion from plausible output, mocked behavior, or an executor summary. Run the real verification command and inspect its exit status.
- For runtime-facing changes, run live end-to-end verification in addition to unit tests.
- For checkout-sensitive contracts, verify in a fresh checkout using Windows-compatible line endings.
- Committed YAML checks out with LF according to `.gitattributes` because legacy descriptors have raw-byte identity pins. Protocol v1 text references are additionally hash-normalized as specified below.
- Hash Protocol v1 text references only according to the frozen basis: decode as UTF-8, normalize CRLF and CR to LF, then compute SHA-256.
- Do not treat two mutually editable files that mirror each other as independent evidence. Stable trust anchors must be outside the mutable pair.
- If verification is incomplete, report `INCOMPLETE` or `BLOCKED`; never substitute fabricated artifacts or results.

## Git and repository hygiene

- Use focused commits and preserve accepted commits; do not amend an accepted packet merely to attach unrelated governance or CI work.
- Never force-push or rewrite shared history without explicit authorization.
- Keep reviewer briefs, diagnostics, provider archives, generated datasets, credentials, model artifacts, and temporary outputs out of commits.
- Store committed plans and working documents under `docs/superpowers/`; keep temporary material under ignored scratch locations.
- Before push, inspect staged names and diff, run the relevant gates, and recheck branch/HEAD because another worker may have changed the repository.
- After push, verify the remote branch and GitHub checks separately. A successful push does not imply passing CI.

## Standard verification lanes

```bash
uv sync --locked
uv run pytest -n 4
uv run ruff check src tests benchmarks
```

Networked integration acceptance is explicit and serial:

```bash
uv run pytest -m integration
```

A packet may define stricter or more targeted commands. Run those in addition to, not instead of, the evidence required by its scope.
