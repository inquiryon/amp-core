"""Deterministic policy evaluation extracted from the AMP monolith (OSS-003).

Behavior is characterized by ``tests/fixtures/eval_policy_cases.json`` and
must stay in parity with the legacy ``_run_eval_policy`` except where an
approved v0 change is documented. Approved v0 changes:

- Decision vocabulary: legacy ``hitl`` is spelled ``require_human`` in v0
  contracts (pure rename; parity harness maps between them).
- Formula execution uses the constrained AST interpreter in
  :mod:`inquiryon_amp_core.expr.engine` instead of Python ``eval()``. The observable
  formula language (pre-seeded param defaults, ``lockdown``/``get`` helpers,
  allow-listed builtins, ``true/false/null`` aliases) is preserved.
- Hard-criterion triggers still route to ``require_human`` — the roadmap's
  automatic-deny was explicitly deferred (product decision 2026-07-22).

Policies are plain dicts with the same shape the monolith uses; typed
wrappers live at the API layer, not here, to keep parity auditable.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional

from .expr.engine import DEFAULT_LIMITS, FormulaError, Limits, evaluate_formula

ALLOW = 'allow'
DENY = 'deny'
REQUIRE_HUMAN = 'require_human'

# Pre-seeded so wildcard criteria can reference common params without a
# name error (characterized legacy behavior).
PARAM_DEFAULTS = {
    'path': '', 'file_path': '', 'command': '', 'query': '',
    'recipient': '', 'subject': '', 'category': '', 'ticker': '',
    'amount': 0, 'workdir': '',
}

# Signature: evaluate(criterion, params) -> (condition_met: bool, reason: str).
# Used for 'llm' criteria and the LLM half of 'hybrid' criteria. The core
# ships none; adapters register implementations. Absent/failed evaluators
# resolve to the criterion fallback (hard criteria fail closed).
CriterionEvaluatorFn = Callable[[dict, dict], tuple]


def make_lockdown(params: Mapping) -> Callable[[str], bool]:
    """lockdown(folder_name) helper — parity with the legacy implementation."""
    def lockdown(folder_name):
        name = str(folder_name).strip('/')
        for v in [str(params.get('path', '')), str(params.get('file_path', '')),
                  str(params.get('workdir', ''))]:
            if not v:
                continue
            if (f'/{name}/' in v or v.startswith(f'{name}/') or
                    v.rstrip('/') == name or v.rstrip('/').endswith(f'/{name}')):
                return True
        for t in str(params.get('command', '')).split():
            # Only path-like tokens; bare words are intentionally not matched.
            if (f'/{name}/' in t or t.startswith(f'{name}/') or
                    t.rstrip('/').endswith(f'/{name}')):
                return True
        return False
    return lockdown


def build_formula_env(params: Mapping) -> dict:
    merged = {**PARAM_DEFAULTS, **dict(params or {})}
    merged['lockdown'] = make_lockdown(merged)
    merged['get'] = lambda name, default=None: merged.get(name, default)
    return merged


def eval_formula(formula: str, params: Mapping, fallback_result: bool = False,
                 limits: Limits = DEFAULT_LIMITS) -> bool:
    """Evaluate a compute formula; any failure yields ``fallback_result``."""
    if not formula:
        return bool(fallback_result)
    try:
        return evaluate_formula(str(formula), build_formula_env(params), limits)
    except FormulaError:
        return bool(fallback_result)


def coerce_bool_input(value) -> tuple:
    """Best-effort boolean coercion for criteria input values (parity)."""
    if isinstance(value, bool):
        return True, value
    if isinstance(value, (int, float)):
        return True, bool(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {'true', 't', 'yes', 'y', '1', 'on'}:
            return True, True
        if raw in {'false', 'f', 'no', 'n', '0', 'off', ''}:
            return True, False
    return False, False


def extract_input_key(criterion: dict) -> str:
    evaluator = criterion.get('evaluator', {}) if isinstance(criterion.get('evaluator'), dict) else {}
    key = str(evaluator.get('input_key') or evaluator.get('source') or '').strip()
    if key.startswith('input://'):
        key = key[len('input://'):]
    if key.startswith('criteria_inputs.'):
        key = key[len('criteria_inputs.'):]
    if not key:
        key = str(criterion.get('criterion_id') or '').strip()
    return key


def criterion_matches(criterion: dict, tool_name: str, action_name: str) -> bool:
    c_tool = criterion.get('tool') or '*'
    c_action = criterion.get('action') or '*'
    return (c_tool in ('*', tool_name)) and (c_action in ('*', action_name))


def condition_semantics(criterion: dict) -> str:
    """Return ``block_when`` (default) or ``allow_when``."""
    evaluator = criterion.get('evaluator', {}) if isinstance(criterion.get('evaluator'), dict) else {}
    token = str(
        criterion.get('condition_semantics')
        or criterion.get('decision_semantics')
        or criterion.get('trigger_mode')
        or evaluator.get('condition_semantics')
        or evaluator.get('decision_semantics')
        or evaluator.get('trigger_mode')
        or ''
    ).strip().lower()
    return token if token in {'block_when', 'allow_when'} else 'block_when'


def _run_llm_evaluator(criterion: dict, params: Mapping, prompt: str,
                       fallback: bool,
                       llm_evaluator: Optional[CriterionEvaluatorFn]) -> tuple:
    if llm_evaluator is None:
        return bool(fallback), 'llm_unavailable'
    try:
        condition_met, reason = llm_evaluator(
            {**criterion, 'evaluator': {**criterion.get('evaluator', {}), 'prompt': prompt}},
            dict(params))
        return bool(condition_met), str(reason or '')
    except Exception as exc:  # provider fault → criterion fallback
        return bool(fallback), f'llm_error: {exc}'


def _hybrid_command_missing(criterion: dict, params: Mapping) -> bool:
    """Conservatively skip the LLM half for command-oriented hybrids only when
    no command was supplied at all.

    This targets criteria written for shell-command inspection that were
    matched against non-shell exec actions such as ``web_search``. It does not
    change fail-closed behavior for provider faults or for criteria that depend
    on other inputs.
    """
    command = str(dict(params or {}).get('command') or '').strip()
    if command:
        return False
    evaluator = criterion.get('evaluator', {}) if isinstance(criterion.get('evaluator'), dict) else {}
    compute_eval = evaluator.get('compute', {}) or {}
    llm_eval = evaluator.get('llm', {}) or {}
    compute_formula = str(compute_eval.get('formula') or '').lower()
    llm_prompt = str(llm_eval.get('prompt') or '').lower()
    return 'command' in compute_formula or 'command' in llm_prompt


def evaluate_single_criterion(criterion: dict, params: Mapping,
                              criteria_inputs: Optional[Mapping] = None,
                              llm_evaluator: Optional[CriterionEvaluatorFn] = None,
                              limits: Limits = DEFAULT_LIMITS) -> dict:
    """Evaluate one criterion; returns the legacy diagnostic dict shape."""
    evaluator = criterion.get('evaluator', {}) if isinstance(criterion.get('evaluator'), dict) else {}
    eval_type = str(evaluator.get('type') or 'compute').lower()
    is_hard = criterion.get('hardness') != 'soft'
    # Hard criteria fail closed if inputs are missing/unresolvable.
    fallback = True if is_hard else evaluator.get('fallback_result', False)
    reason = ''

    if eval_type == 'llm':
        condition_met, reason = _run_llm_evaluator(
            criterion, params, evaluator.get('prompt', ''), fallback, llm_evaluator)
    elif eval_type == 'hybrid':
        compute_eval = evaluator.get('compute', {}) or {}
        llm_eval = evaluator.get('llm', {}) or {}
        outer_fallback = evaluator.get('fallback_result', False)
        c_fired = eval_formula(compute_eval.get('formula', ''), params,
                               compute_eval.get('fallback_result', outer_fallback), limits)
        if c_fired:
            condition_met, reason = True, 'compute_triggered'
        elif _hybrid_command_missing(criterion, params):
            condition_met, reason = False, 'hybrid_command_missing'
        else:
            condition_met, reason = _run_llm_evaluator(
                criterion, params, llm_eval.get('prompt', ''),
                llm_eval.get('fallback_result', outer_fallback), llm_evaluator)
            reason = reason or ('llm_triggered' if condition_met else 'hybrid_not_triggered')
    elif eval_type == 'input':
        inputs = criteria_inputs if isinstance(criteria_inputs, Mapping) else {}
        input_key = extract_input_key(criterion)
        raw_value = None
        if input_key and input_key in inputs:
            raw_value = inputs.get(input_key)
        elif criterion.get('criterion_id') in inputs:
            raw_value = inputs.get(criterion.get('criterion_id'))
        present, bool_val = coerce_bool_input(raw_value)
        condition_met = bool_val if present else bool(fallback)
        reason = 'input_true' if condition_met else ('input_false' if present else 'input_missing_fallback')
    else:  # compute (default)
        condition_met = eval_formula(evaluator.get('formula', ''), params, fallback, limits)
        reason = 'compute_true' if condition_met else 'compute_false_or_fallback'

    semantics = condition_semantics(criterion)
    triggered = bool(condition_met) if semantics == 'block_when' else (not bool(condition_met))
    return {
        'criterion': criterion,
        'criterion_id': str(criterion.get('criterion_id') or ''),
        'text': (str(criterion.get('text') or '').strip()
                 or str(criterion.get('description') or '').strip()),
        'hardness': 'hard' if is_hard else 'soft',
        'evaluator_type': eval_type,
        'status': 'met' if condition_met else 'not_met',
        'reason': reason,
        'condition_semantics': semantics,
        'condition_met': bool(condition_met),
        'triggered': bool(triggered),
        'trigger_reason': (
            f'criterion_{semantics}_true' if triggered and semantics == 'block_when'
            else (f'criterion_{semantics}_false' if triggered else 'criterion_not_triggered')
        ),
    }


def run_eval_policy(policy: dict, tool_name: str, action_name: str,
                    params: Mapping,
                    criteria_inputs: Optional[Mapping] = None,
                    llm_evaluator: Optional[CriterionEvaluatorFn] = None,
                    limits: Limits = DEFAULT_LIMITS) -> dict:
    """Evaluate an eval policy against a tool call.

    Returns ``{decision, reason, triggered_criteria, soft_triggered,
    criteria_results?}`` where ``decision`` is ``allow`` or ``require_human``
    (v0 spelling of legacy ``hitl``). Reason strings are parity-stable.
    """
    ag = policy.get('action_governance', {}) if isinstance(policy, dict) else {}
    if ag.get('force_human_approval', False):
        return {'decision': REQUIRE_HUMAN, 'reason': 'force_human_approval',
                'triggered_criteria': [], 'soft_triggered': []}

    criteria = ag.get('criteria', []) or []
    matching = [c for c in criteria if criterion_matches(c, tool_name, action_name)]
    results, triggered_hard, triggered_soft = [], [], []
    for criterion in matching:
        result = evaluate_single_criterion(
            criterion, params, criteria_inputs=criteria_inputs,
            llm_evaluator=llm_evaluator, limits=limits)
        results.append(result)
        if result['triggered']:
            (triggered_hard if result['hardness'] == 'hard' else triggered_soft).append(criterion)

    if not matching:
        if policy.get('allow_unknown_tools', False):
            return {'decision': ALLOW, 'reason': 'no_matching_criteria_allowed',
                    'triggered_criteria': [], 'soft_triggered': []}
        return {'decision': REQUIRE_HUMAN, 'reason': 'unknown_tool_not_allowed',
                'triggered_criteria': [], 'soft_triggered': []}

    if triggered_hard:
        return {'decision': REQUIRE_HUMAN, 'reason': 'hard_criterion_triggered',
                'triggered_criteria': triggered_hard,
                'soft_triggered': triggered_soft,
                'criteria_results': results}

    return {'decision': ALLOW, 'reason': 'no_hard_criteria_triggered',
            'triggered_criteria': [], 'soft_triggered': triggered_soft,
            'criteria_results': results}
