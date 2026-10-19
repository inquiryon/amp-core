# inquiryon-amp-core

Public governance core for AMP (Autonomous Multi-agent Platform): versioned policy schema, deterministic
policy evaluation, and transport-neutral decision-provider contracts.

## Get Started

Most users shouldn't install amp-core directly — start with
**[amp-community](https://github.com/inquiryon/amp-community)**, which
pulls amp-core in as a dependency and adds the HITL review workflow,
audit trail, REST API, and operator UI on top of it. Its README covers
installation and a full working walkthrough.

### Installing amp-core directly

Install this package on its own only if you're building a governance
service without amp-community — for example, embedding just the policy
evaluator in another system, or implementing a custom `DecisionProvider`
for a different application boundary.

```bash
# Optional but recommended — keeps this off your system/global Python.
python3 -m venv .venv && source .venv/bin/activate

pip install inquiryon-amp-core
# or, for full JSON Schema validation (see "Python API Example" below):
pip install "inquiryon-amp-core[schema]"
```

To work from source instead: `git clone https://github.com/inquiryon/amp-core.git`
then `pip install -e ./amp-core`.

## How it works

### AMP Core Components

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

### Python API Example

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

### Design rules

- No Flask, no database drivers, no SaaS identity, billing, analytics, or
  RLHF concepts — enforced by `tests/test_architecture_rules.py`.
- Deterministic: inject `Clock` and `IdGenerator` for reproducible tests.
- Behavior is pinned by characterization fixtures extracted from the
  original AMP implementation; intentional changes ship as documented,
  separately-fixtured decisions.

## License

Apache-2.0. Contributions require DCO sign-off (`git commit -s`).
