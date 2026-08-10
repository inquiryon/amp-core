# inquiryon-amp-core (experimental v0)

Public governance core for AMP: versioned policy schema, deterministic
policy evaluation, and transport-neutral decision-provider contracts.

**Status: experimental `v0`.** Contracts may change until validated by the
Community Edition, one Enterprise adapter, and existing integration behavior.

## Installation

**Not yet published to PyPI** — install from a local clone for now:

```bash
git clone https://github.com/inquiryon/amp-core.git
pip install -e ./amp-core
# or, for full JSON Schema validation (see "Quick start" below):
pip install -e "./amp-core[schema]"
```

Once published, this collapses to `pip install inquiryon-amp-core` (or
`inquiryon-amp-core[schema]`). The "Quick start" example below assumes this
step is already done.

## What's here

- `inquiryon_amp_core.evaluator` — deterministic policy evaluation (`run_eval_policy`):
  criterion matching, hard/soft aggregation, `block_when`/`allow_when`
  semantics, input-signal criteria, and fail-closed fallbacks.
- `inquiryon_amp_core.expr` — a constrained AST interpreter for compute formulas.
  Policy expressions never execute arbitrary Python; escapes and resource
  abuse are rejected, and hard criteria fail closed to human review.
- `inquiryon_amp_core.providers` — the `DecisionProvider` contract plus Community
  implementations. Safety invariants are enforced in the workflow: providers
  cannot override non-overridable policy outcomes, and provider failure,
  timeout, or invalid output falls back to `require_human`.
- `inquiryon_amp_core.stores` — `PolicyStore` adapters: in-memory and file-backed.
- `inquiryon_amp_core.interfaces` — extension points (audit sink, clock, ids,
  workitem store, identity, notification, agent callback).
- `inquiryon_amp_core/contracts/schemas/v0.json` — language-neutral JSON Schemas for
  `Policy`, `EvaluationRequest`, `CriterionResult`, `EvaluationDecision`,
  `HITLRequest`, `HITLDecision`, `AuditEvent`, error envelope, pagination.

## Quick start

```python
from inquiryon_amp_core import InMemoryPolicyStore, run_eval_policy

store = InMemoryPolicyStore()
store.put_policy('invoice-governance', {
    'action_governance': {'criteria': [
        {'criterion_id': 'c-high-amount', 'tool': 'pay_invoice',
         'hardness': 'hard',
         'evaluator': {'type': 'compute', 'formula': 'amount > 1000'}},
    ]},
})

result = run_eval_policy(store.get_policy('invoice-governance'),
                         'pay_invoice', 'submit', {'amount': 4000})
# {'decision': 'require_human', 'reason': 'hard_criterion_triggered', ...}
```

The core has **zero runtime dependencies**. LLM/hybrid criteria use a
pluggable `CriterionEvaluator`; without one they resolve to the criterion's
fallback (hard criteria fail closed). Install the `schema` extra for full
JSON Schema validation.

## Design rules

- No Flask, no database drivers, no SaaS identity, billing, analytics, or
  RLHF concepts — enforced by `tests/test_architecture_rules.py`.
- Deterministic: inject `Clock` and `IdGenerator` for reproducible tests.
- Behavior is pinned by characterization fixtures extracted from the
  original AMP implementation; intentional changes ship as documented,
  separately-fixtured decisions.

## License

Apache-2.0. Contributions require DCO sign-off (`git commit -s`).
