# Contributing to Quantara

Quantara is currently in a foundation and specification phase. Contributions are welcome when they strengthen a bounded, reviewable capability without implying that planned software already exists.

## Start with the current state

Before proposing a change:

1. Read the [README](README.md).
2. Read the specification related to your change under `docs/superpowers/specs/`.
3. Confirm whether the capability is delivered documentation, specified but not implemented, or planned.
4. Use a design-proposal issue before widening scope, introducing a provider, changing a canonical contract, or adding a new architectural boundary.

Do not add speculative packages, empty directories, placeholder APIs, or broad scaffolding for future work.

## Contribution workflow

The required sequence is:

> Define → Risk-review → Design → Test → Bounded implementation → Verification → Stabilization

A pull request should address one independently reviewable change. It must explain:

- the problem and bounded scope;
- the source-of-truth specification or approved design decision;
- temporal-ordering and leakage implications;
- provenance, serialization, and quality-state implications;
- provider/legal-use implications;
- tests and live verification performed;
- failure and rollback behavior.

If a change cannot be verified safely, mark it incomplete rather than substituting plausible output.

## Data and research integrity

Contributions that touch market data, labels, features, evaluation, or modeling must:

- preserve point-in-time availability;
- avoid random splitting for temporally ordered evaluation;
- identify event time, availability time, and decision time where applicable;
- use decimal-safe canonical representations for currency and volume contracts;
- preserve deterministic provenance and content identity;
- fail closed when quality or legal-use eligibility is not exactly satisfied;
- prevent canonical promotion unless quality state is exactly `PASS`;
- test boundary times, missing data, duplicates, ordering, and restart behavior;
- document every assumption that could alter scientific validity.

Do not commit provider archives, normalized datasets, credentials, tokens, model artifacts, or generated market outputs.

## Testing and evidence

No universal setup command exists yet because executable project scaffolding has not been approved. Each implementation plan must define its own environment and verification commands before code is added.

The offline suite runs in parallel by default during development:

```powershell
uv run pytest -n 4          # offline tests only; integration stays excluded
uv run pytest -m integration # networked acceptance; always serial, never with -n
```

Pull requests must list the exact commands executed and their real results. Depending on scope, evidence may include:

- unit and property tests;
- deterministic reruns and hash comparison;
- temporal leakage checks;
- malformed and adversarial input tests;
- restart/idempotency tests;
- rendered documentation inspection;
- live runtime or GitHub verification.

A green unit-test report does not replace integration or live-behavior verification when the change has a user-visible or operational surface.

## Commit and pull-request standards

- Use focused commits with imperative, descriptive messages.
- Do not rewrite shared history or force-push protected/public work without explicit approval.
- Keep generated diagnostics and temporary validation artifacts outside the repository.
- Update documentation when a contract, risk, command, or operational behavior changes.
- Complete the pull-request checklist honestly; use `Not applicable` with a reason rather than silently skipping a control.

By submitting a contribution, you agree that it may be licensed under the repository's [Apache License 2.0](LICENSE), unless you conspicuously mark material as **Not a Contribution** as described by that license.

## Security and conduct

Report vulnerabilities through the private process in [SECURITY.md](SECURITY.md), not a public issue. Community participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
