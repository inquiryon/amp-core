"""Decision-provider conformance (OSS-002): timeout, invalid output, safe
fallback, and non-overridable policy outcomes.

The fixed policy and request builder live in ``amp_core.conformance`` so a
private Enterprise provider suite (OSS-008) can evaluate against the same
fixture instead of redefining an equivalent one."""

import time

from amp_core import (
    DecisionResult,
    HumanReviewProvider,
    StaticPolicyProvider,
    decide_with_safety,
)
from amp_core.conformance import HARD_POLICY, make_request

assert HARD_POLICY  # re-exported for suites that want the raw policy too


class AlwaysAllowProvider:
    name, version = 'test-always-allow', '0'

    def decide(self, request):
        return DecisionResult(outcome='allow', reason_code='model_confident',
                              provider_name=self.name)


class CrashingProvider:
    name, version = 'test-crash', '0'

    def decide(self, request):
        raise RuntimeError('provider exploded')


class InvalidOutputProvider:
    name, version = 'test-invalid', '0'

    def decide(self, request):
        return DecisionResult(outcome='auto_approve_everything', reason_code='x')


class SlowProvider:
    name, version = 'test-slow', '0'

    def decide(self, request):
        time.sleep(0.05)
        return DecisionResult(outcome='allow', reason_code='slow_allow')


class OversizedDiagnosticsProvider:
    name, version = 'test-big-diag', '0'

    def decide(self, request):
        return DecisionResult(outcome='require_human', reason_code='big',
                              diagnostics={'test-big-diag': 'x' * 10000})


def test_provider_cannot_override_hard_trigger():
    result = decide_with_safety(AlwaysAllowProvider(), make_request({'amount': 5000}))
    assert result.outcome == 'require_human'
    assert result.reason_code == 'policy_outcome_not_overridable'


def test_provider_allow_passes_when_policy_allows():
    result = decide_with_safety(AlwaysAllowProvider(), make_request({'amount': 10}))
    assert result.outcome == 'allow'
    assert result.reason_code == 'model_confident'


def test_provider_may_tighten_policy_allow():
    class Tighten(HumanReviewProvider):
        pass
    result = decide_with_safety(Tighten(), make_request({'amount': 10}))
    assert result.outcome == 'require_human'


def test_provider_crash_fails_safe():
    result = decide_with_safety(CrashingProvider(), make_request({'amount': 10}))
    assert result.outcome == 'require_human'
    assert result.reason_code == 'provider_error'


def test_provider_invalid_output_fails_safe():
    result = decide_with_safety(InvalidOutputProvider(), make_request({'amount': 10}))
    assert result.outcome == 'require_human'
    assert result.reason_code == 'provider_invalid_output'


def test_provider_timeout_fails_safe():
    result = decide_with_safety(SlowProvider(), make_request({'amount': 10}, timeout=0.01))
    assert result.outcome == 'require_human'
    assert result.reason_code == 'provider_timeout'


def test_diagnostics_size_limited():
    result = decide_with_safety(OversizedDiagnosticsProvider(), make_request({'amount': 10}))
    assert result.diagnostics == {'_truncated': True}


def test_community_static_provider_mirrors_policy():
    provider = StaticPolicyProvider()
    blocked = decide_with_safety(provider, make_request({'amount': 5000}))
    assert blocked.outcome == 'require_human'
    assert blocked.reason_code == 'hard_criterion_triggered'
    allowed = decide_with_safety(provider, make_request({'amount': 10}))
    assert allowed.outcome == 'allow'
    assert allowed.reason_code == 'no_hard_criteria_triggered'
