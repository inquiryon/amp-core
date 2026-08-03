"""Security tests for the constrained formula engine (OSS-003 task 3).

Policy expressions must never execute arbitrary Python. Every escape or
resource-abuse attempt must raise FormulaError — and, in criterion context,
a hard criterion must fail closed (require_human), never crash or allow.
"""

import pytest

from inquiryon_amp_core import run_eval_policy
from inquiryon_amp_core.expr.engine import (
    FormulaError,
    FormulaNameError,
    FormulaResourceError,
    FormulaSyntaxError,
    evaluate_formula,
)

ESCAPE_ATTEMPTS = [
    "__import__('os').system('true')",
    "().__class__.__bases__[0].__subclasses__()",
    "''.__class__.__mro__",
    "getattr(str, 'maketrans')",
    "open('/etc/passwd')",
    "exec('print(1)')",
    "eval('1+1')",
    "(lambda: 1)()",
    "[x for x in ().__class__.__mro__]",
    "compile('1', '<s>', 'eval')",
    "globals()",
    "locals()",
    "type(1)",
    "str.__init__",
    "amount.__class__",
    "recipient.format('x')",
    "recipient.join(['a'])",
    "f'{amount}'",
    "(a := 5)",
    "min(*[1,2])",
    "len(**{'obj': 'x'})",
]

RESOURCE_ATTEMPTS = [
    '9' * 3000 + ' > 0',                    # oversized formula
    '2 ** 9999',                            # pow bomb
    "'a' * 100000",                         # string repetition bomb
    '1' + ' + 1' * 600 + ' > 0',            # node-count bomb
]


@pytest.mark.parametrize('formula', ESCAPE_ATTEMPTS)
def test_escape_attempts_raise(formula):
    with pytest.raises(FormulaError):
        evaluate_formula(formula, {'amount': 5, 'recipient': 'a@example.com'})


@pytest.mark.parametrize('formula', RESOURCE_ATTEMPTS)
def test_resource_attempts_raise(formula):
    with pytest.raises((FormulaResourceError, FormulaSyntaxError)):
        evaluate_formula(formula, {})


def test_comprehension_iteration_budget():
    # Within a single comprehension the per-source cap applies.
    with pytest.raises(FormulaError):
        evaluate_formula("any(x > 0 for x in 'a' * 999999)", {})


def test_missing_name_raises_name_error():
    with pytest.raises(FormulaNameError):
        evaluate_formula('undefined_variable == 1', {})


@pytest.mark.parametrize('formula', ESCAPE_ATTEMPTS + RESOURCE_ATTEMPTS)
def test_hard_criterion_with_malicious_formula_fails_closed(formula):
    policy = {'action_governance': {'criteria': [{
        'criterion_id': 'c-mal', 'tool': '*', 'action': '*', 'hardness': 'hard',
        'evaluator': {'type': 'compute', 'formula': formula}}]}}
    result = run_eval_policy(policy, 'any_tool', 'any_action', {'amount': 1})
    assert result['decision'] == 'require_human'
    assert result['reason'] == 'hard_criterion_triggered'


def test_legitimate_formulas_still_work():
    env = {'amount': 250, 'recipient': 'alice@example.com',
           'query': 'SELECT password FROM users', 'command': 'ls /data/payroll/x'}
    assert evaluate_formula('amount > 100', env) is True
    assert evaluate_formula("recipient.endswith('@example.com')", env) is True
    assert evaluate_formula("any(kw in query.lower() for kw in ['password', 'secret'])", env) is True
    assert evaluate_formula("len(str(amount)) >= 3 and amount < 1000", env) is True
    assert evaluate_formula("get('missing_field', 0) == 0", {
        **env, 'get': lambda n, d=None: {'amount': 250}.get(n, d)}) is True
    assert evaluate_formula('true', env) is True
    assert evaluate_formula('amount > 100 if recipient else false', env) is True
