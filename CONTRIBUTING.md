# Contributing to amp-core

Thanks for your interest in contributing.

## Developer Certificate of Origin (DCO)

Every commit must be signed off, certifying you wrote the change or
otherwise have the right to submit it under this project's license
(Apache-2.0):

```
git commit -s -m "your message"
```

This adds a `Signed-off-by: Your Name <you@example.com>` trailer. PRs with
unsigned commits will be asked to amend before merge.

## Development setup

```
pip install -e ".[dev]"
pytest
```

## Before opening a PR

- `pytest` passes locally.
- Behavior changes to the evaluator or expression engine come with
  characterization/parity coverage, not just new-feature tests.
- No secrets, production URLs, or non-fictional identifiers appear
  anywhere in the diff, including tests and fixtures.
- New public API surface is documented in docstrings and, for behavior
  changes, reflected in `CHANGELOG.md`.

## Scope

`amp-core` is a small, deterministic governance kernel: policy schema and
validation, policy evaluation, a constrained expression engine, and the
`DecisionProvider` contract. It is intentionally **not** a copy of any
SaaS product built on top of it.

PRs that add multi-tenancy, SaaS authentication/billing, progressive
autonomy or RLHF, model training, analytics, or any other Enterprise-only
concept will not be accepted here — those integrate behind the
`DecisionProvider` boundary in a private, separate implementation, not
inside this package. If you're building one of those, `DecisionProvider`
is the intended extension point; open an issue first if the existing
contract doesn't support your use case.

## Reporting bugs vs. security issues

Functional bugs: open a GitHub issue. Security vulnerabilities: see
`SECURITY.md` — do not open a public issue.
