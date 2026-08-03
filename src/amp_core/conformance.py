"""Shared provider-conformance fixtures (OSS-002/OSS-008).

The fixed hard-criterion policy and request builder every
``DecisionProvider`` conformance suite evaluates against — Community's own
test-double suite (``tests/test_provider_conformance.py``) and any private
Enterprise provider suite — import these instead of redefining an
equivalent policy, so the conformance *input* is defined once. The
per-provider fault injection and assertions still live in each suite,
since how a provider is made to crash/time out/return malformed output is
necessarily provider-specific (an in-process double vs. a real remote
call).
"""

from __future__ import annotations

from .evaluator import run_eval_policy
from .providers import DecisionRequest

#: A single hard criterion (`amount > 1000`) — the non-overridable floor
#: every conformance scenario is checked against.
HARD_POLICY = {'action_governance': {'criteria': [{
    'criterion_id': 'c-amount', 'tool': 'pay_invoice', 'action': '*',
    'hardness': 'hard', 'evaluator': {'type': 'compute', 'formula': 'amount > 1000'}}]}}


def make_request(params: dict, request_id: str = 'req-1', timeout: float = 5.0,
                 scope=None) -> DecisionRequest:
    """Build a conformance ``DecisionRequest`` against :data:`HARD_POLICY`.

    ``params['amount'] > 1000`` triggers the hard floor (policy_evaluation
    demands at least ``require_human``); any other amount leaves the floor
    at ``allow`` so a provider's own outcome passes through unmodified.
    ``scope`` is opaque and passed through unchanged — a remote/Enterprise
    provider suite may use it to carry private identity, per OSS-002.
    """
    evaluation = run_eval_policy(HARD_POLICY, 'pay_invoice', 'submit', params)
    return DecisionRequest(request_id=request_id, tool='pay_invoice', action='submit',
                           params=params, policy_evaluation=evaluation,
                           scope=scope, timeout_seconds=timeout)
