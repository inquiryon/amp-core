"""inquiryon-amp-core — AMP governance core (experimental v0).

Public, dependency-free policy evaluation and decision-provider contracts.
Contracts are experimental v0: they may change until validated by Community,
one Enterprise adapter, and existing frontend/callback behavior (OSS-002).
"""

from .evaluator import (
    ALLOW,
    DENY,
    REQUIRE_HUMAN,
    eval_formula,
    evaluate_single_criterion,
    run_eval_policy,
)
from .expr.engine import (
    FormulaError,
    FormulaNameError,
    FormulaResourceError,
    FormulaRuntimeError,
    FormulaSyntaxError,
    Limits,
)
from .interfaces import (
    AuditEvent,
    AuditEventSink,
    Clock,
    IdGenerator,
    InMemoryAuditSink,
    SystemClock,
    UuidGenerator,
)
from .providers import (
    DecisionProvider,
    DecisionRequest,
    DecisionResult,
    HumanReviewProvider,
    StaticPolicyProvider,
    decide_with_safety,
)
from .stores import FilePolicyStore, InMemoryPolicyStore, PolicyStore

__version__ = '0.0.1'

# `conformance` is intentionally not imported here (it is test-support, not
# runtime code) — import it explicitly as `inquiryon_amp_core.conformance`
# in a provider conformance suite.
