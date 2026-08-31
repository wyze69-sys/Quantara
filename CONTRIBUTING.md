# Contributing to Quantara

Quantara is a correctness-first research system. Contributions are welcome when they strengthen one bounded, reviewable capability without implying that planned software or scientific evidence already exists.

## Start with the current state

Before proposing a change:

1. Read the [README](README.md) and [roadmap](docs/superpowers/roadmap.md).
2. Read the governing specification under `docs/superpowers/specs/`.
3. Read the repository instructions in [`AGENTS.md`](AGENTS.md).
4. If the work belongs to an approved execution program, identify exactly one packet in `docs/superpowers/plans/`.
5. Use a design-proposal issue before widening scope, introducing a provider, changing a canonical or scientific contract, or adding an architectural boundary.

Do not add speculative packages, empty directories, placeholder APIs, or broad scaffolding for future work.

## Contribution and acceptance workflow

The repository-level sequence is:

> Define → Risk-review → Design → One bounded packet → Local verification → Independent audit → Correction if required → `ACCEPTED` → Next packet

For the current Protocol v1 program:

- Zcode implements exactly one assigned packet and stops after a local commit and evidence report.
- Hermes independently audits the diff, trust boundaries, tests, live behavior, hashes, quality state, and protocol compliance.
- When correction is required, Hermes defines the bounded correction and Zcode implements it; Hermes then re-audits. Hermes-direct implementation requires a separate independent audit before acceptance.
- Executor self-review and green tests do not grant acceptance.
- No later packet or stage starts until the preceding dependency is independently accepted.
- Governance, CI, or documentation changes must remain separate from an already accepted scientific packet.

A pull request should address one independently reviewable change. It must explain:

- the packet ID or bounded problem;
- the source-of-truth specification or approved design decision;
- the exact file allowlist and any deliberate deviations;
- temporal-ordering and leakage implications;
- provenance, serialization, and quality-state implications;
- provider/legal-use implications;
- exact tests and live/fresh-checkout verification performed;
- independent audit status and remaining risks;
- failure and rollback behavior.

If a change cannot be verified safely, mark it `INCOMPLETE` or `BLOCKED` rather than substituting plausible output.

## Data and research integrity

Contributions touching market data, labels, features, evaluation, or modeling must:

- preserve point-in-time availability;
- avoid random splitting for temporally ordered evaluation;
- identify event time, availability time, and decision time where applicable;
- use decimal-safe canonical representations for currency and volume contracts;
- preserve deterministic provenance and content identity;
- fail closed when quality or legal-use eligibility is not exactly satisfied;
- prevent canonical promotion unless quality state is exactly `PASS`;
- test boundary times, missing data, duplicates, ordering, and restart behavior;
- document every assumption that could alter scientific validity;
- preserve the Protocol v1 inventory and blind-seal rules unless an explicit protocol amendment is approved.

Do not commit provider archives, normalized datasets, credentials, tokens, model artifacts, or generated market outputs.

## Testing and evidence

Install from the committed lock file and run the offline suite:

```bash
uv sync --locked
uv run pytest -n 4
uv run ruff check src tests benchmarks
```

Networked integration acceptance stays explicit and serial:

```bash
uv run pytest -m integration
```

Pull requests must list exact commands and real results. Depending on scope, evidence may include:

- unit and property tests;
- deterministic reruns and hash comparison;
- temporal leakage checks;
- malformed and adversarial input tests;
- restart/idempotency tests;
- rendered documentation inspection;
- fresh-checkout and line-ending portability tests;
- live runtime or GitHub verification.

A green unit-test report does not replace integration or live-behavior verification when the change has a user-visible, scientific, or operational surface.

## Commit and pull-request standards

- Use focused commits with imperative, descriptive messages.
- Do not amend an accepted packet with unrelated documentation, governance, or CI work.
- Do not rewrite shared history or force-push protected/public work without explicit approval.
- Preserve unrelated tracked and untracked work after auditing its origin and scope.
- Keep generated diagnostics and temporary validation artifacts outside commits.
- Update documentation when a contract, risk, command, or operational behavior changes.
- Complete the pull-request checklist honestly; use `Not applicable` with a reason rather than silently skipping a control.

By submitting a contribution, you agree that it may be licensed under the repository's [Apache License 2.0](LICENSE), unless you conspicuously mark material as **Not a Contribution** as described by that license.

## Security and conduct

Report vulnerabilities through the private process in [SECURITY.md](SECURITY.md), not a public issue. Community participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
