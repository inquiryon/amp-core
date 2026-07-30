"""Decision-provider contract and Community implementations (OSS-002/003).

The shared governance workflow calls a general, transport-neutral
``DecisionProvider`` — never progressive autonomy or any Enterprise concept.
Safety invariants are enforced *here*, in public workflow code, so no
provider can bypass them:

- A provider cannot override a non-overridable policy outcome (a triggered
  hard criterion, force_human_approval, or unknown-tool routing) merely by
  returning ``allow``. It may only make the outcome stricter.
- Provider timeout, failure, invalid output, or unknown outcome falls back
  to ``require_human`` unless a stricter policy outcome already applies.
- Provider diagnostics are optional, opaque, namespaced, and size-limited;
  they never enter the decision logic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from .evaluator import ALLOW, DENY, REQUIRE_HUMAN

VALID_OUTCOMES = {ALLOW, DENY, REQUIRE_HUMAN}
_STRICTNESS = {ALLOW: 0, REQUIRE_HUMAN: 1, DENY: 2}
MAX_DIAGNOSTICS_BYTES = 4096


@dataclass(frozen=True)
class DecisionRequest:
    """Transport-neutral input to a decision provider."""
    request_id: str
    tool: str
    action: str
    params: dict
    policy_evaluation: dict  # output of run_eval_policy (decision, reason, ...)
    scope: Optional[str] = None  # opaque execution scope; no SaaS org semantics
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class DecisionResult:
    outcome: str  # allow | deny | require_human
    reason_code: str
    provider_name: str = 'unknown'
    provider_version: str = '0'
    confidence: Optional[float] = None  # optional score; no proprietary semantics
    diagnostics: dict = field(default_factory=dict)  # namespaced, size-limited


class DecisionProvider(Protocol):
    name: str
    version: str

    def decide(self, request: DecisionRequest) -> DecisionResult: ...


class StaticPolicyProvider:
    """Community default: mirrors the deterministic policy evaluation."""
    name = 'community-static'
    version = '0'

    def decide(self, request: DecisionRequest) -> DecisionResult:
        decision = request.policy_evaluation.get('decision', REQUIRE_HUMAN)
        reason = request.policy_evaluation.get('reason', 'unknown')
        if decision not in VALID_OUTCOMES:
            decision = REQUIRE_HUMAN
        return DecisionResult(outcome=decision, reason_code=reason,
                              provider_name=self.name, provider_version=self.version)


class HumanReviewProvider:
    """Community fallback: route everything to human review."""
    name = 'community-human-review'
    version = '0'

    def decide(self, request: DecisionRequest) -> DecisionResult:
        return DecisionResult(outcome=REQUIRE_HUMAN, reason_code='human_review_default',
                              provider_name=self.name, provider_version=self.version)


def _policy_floor(policy_evaluation: dict) -> str:
    """The minimum (non-overridable) strictness implied by policy evaluation."""
    decision = policy_evaluation.get('decision')
    if decision in (REQUIRE_HUMAN, DENY):
        return decision
    return ALLOW


def _truncate_diagnostics(diags) -> dict:
    if not isinstance(diags, dict):
        return {}
    try:
        if len(json.dumps(diags, default=str)) <= MAX_DIAGNOSTICS_BYTES:
            return diags
    except Exception:
        return {}
    return {'_truncated': True}


def decide_with_safety(provider: DecisionProvider,
                       request: DecisionRequest) -> DecisionResult:
    """Run a provider under the public safety invariants.

    This is the only sanctioned path from a provider result to a workflow
    decision. It never raises.
    """
    floor = _policy_floor(request.policy_evaluation)
    started = time.monotonic()
    try:
        result = provider.decide(request)
        elapsed = time.monotonic() - started
        if elapsed > request.timeout_seconds:
            result = None
            fault = 'provider_timeout'
        elif not isinstance(result, DecisionResult) or result.outcome not in VALID_OUTCOMES:
            result = None
            fault = 'provider_invalid_output'
        else:
            fault = None
    except Exception:
        result = None
        fault = 'provider_error'

    if result is None:
        # Fail safe: human review, unless policy already demands stricter.
        outcome = DENY if floor == DENY else REQUIRE_HUMAN
        return DecisionResult(outcome=outcome, reason_code=fault,
                              provider_name=getattr(provider, 'name', 'unknown'),
                              provider_version=getattr(provider, 'version', '0'))

    outcome = result.outcome
    # Non-overridable policy outcomes: provider may tighten, never loosen.
    if _STRICTNESS[outcome] < _STRICTNESS[floor]:
        return DecisionResult(
            outcome=floor, reason_code='policy_outcome_not_overridable',
            provider_name=result.provider_name, provider_version=result.provider_version,
            confidence=result.confidence,
            diagnostics=_truncate_diagnostics(result.diagnostics))
    return DecisionResult(
        outcome=outcome, reason_code=result.reason_code,
        provider_name=result.provider_name, provider_version=result.provider_version,
        confidence=result.confidence,
        diagnostics=_truncate_diagnostics(result.diagnostics))
