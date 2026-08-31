# Pull request

## Packet and bounded scope

- Packet ID or bounded change:
- Governing plan/specification:
- Branch/base:
- Allowed files:

<!-- Explain the one independently reviewable problem solved by this pull request. -->

## Implementation status

- Executor:
- Local implementation status: `COMPLETE` / `BLOCKED` / `INCOMPLETE`
- Independent auditor:
- Audit verdict: `ACCEPTED` / `CORRECTION REQUIRED` / `BLOCKED` / `PENDING`

A `COMPLETE` executor report is not the same as independent acceptance.

## Verification evidence

<!-- List exact commands and real results. Include live and fresh-checkout evidence when applicable. -->

- Tests executed:
- Result and counts:
- Fresh-checkout/line-ending verification:
- Live/runtime verification:
- Hashes or immutable identities:
- Additional evidence:

## Correctness and risk review

- [ ] The change is bounded to one packet or one independently reviewable concern.
- [ ] The diff matches the declared file allowlist; deviations are explained.
- [ ] Unrelated tracked and untracked work was preserved.
- [ ] Capability claims distinguish implemented and verified, specified but not implemented, and planned states.
- [ ] Temporal ordering and leakage risk were assessed, or are not applicable with an explanation.
- [ ] Data provenance, deterministic serialization, and quality-state effects were assessed, or are not applicable.
- [ ] Provider terms and legal-use gates were assessed, or are not applicable.
- [ ] Failure, restart, idempotency, and rollback behavior were tested or documented as not applicable.
- [ ] Mutable files are not being presented as independent trust anchors for one another.
- [ ] The Protocol v1 inventory/model ladder was not widened without an approved amendment.
- [ ] The 2025 blind seal was not accessed or weakened.
- [ ] No credentials, provider data, generated market artifacts, reviewer briefs, or unintended personal information are included.
- [ ] Documentation and security guidance were updated where behavior changed.
- [ ] Independent audit is accepted, or this pull request is explicitly marked as awaiting audit.

## Reviewer notes

<!-- Identify residual risks, deferred work, reproducibility instructions, and anything reviewers should independently inspect. -->
