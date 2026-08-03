# Security Policy

## Reporting a vulnerability

Please report suspected security vulnerabilities privately to
**team@inquiryon.com**. Do not open a public GitHub issue for suspected
vulnerabilities.

Include:

- a description of the issue and its potential impact;
- steps to reproduce (a minimal fictional example is ideal);
- the `amp-core` version and Python version in use.

We will acknowledge receipt within 5 business days and aim to provide a
remediation timeline within 10 business days of confirming the issue.

## Supported versions

This package is `0.x` (experimental `v0` contract). Only the latest `0.x`
release receives security fixes; there is no long-term-support branch at
this stage.

## Scope

In scope: the deterministic policy evaluator (`evaluator.py`), the
constrained expression engine (`expr/engine.py` — this replaced Python's
`eval()` specifically to remove arbitrary code execution from formula
evaluation, so correctness here is safety-critical), schema validation
(`schema.py`, `contracts/schemas/v0.json`), and the `DecisionProvider`
protocol and its bundled implementations (`providers.py`).

Particularly high-value reports: any input that lets a formula escape the
expression engine's sandboxing, any policy shape that causes a hard
criterion to resolve to `allow` instead of `require_human`, or any
`DecisionProvider` behavior that overrides a non-overridable policy outcome.

Out of scope: `amp-community` (report there — same contact), and any
Enterprise/private integration built on top of this package.
