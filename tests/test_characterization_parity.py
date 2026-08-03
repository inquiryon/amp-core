"""Parity: amp-core must reproduce the Phase 0 characterization fixtures.

The fixtures capture legacy monolith behavior (decision spelled ``hitl``);
v0 spells it ``require_human`` — an approved rename, mapped here.
"""

import json
import os

import pytest

from inquiryon_amp_core import run_eval_policy

FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures', 'eval_policy_cases.json')

with open(os.path.abspath(FIXTURES), encoding='utf-8') as f:
    SUITE = json.load(f)

LEGACY_TO_V0 = {'hitl': 'require_human', 'allow': 'allow', 'deny': 'deny'}


def crit_ids(criteria):
    return sorted(str(c.get('criterion_id') or '') for c in criteria)


@pytest.mark.parametrize('case', SUITE['cases'], ids=[c['id'] for c in SUITE['cases']])
def test_parity(case):
    result = run_eval_policy(
        case['policy'], case['tool'], case['action'],
        case.get('params') or {},
        criteria_inputs=case.get('criteria_inputs'))
    assert result['decision'] == LEGACY_TO_V0[case['expect']['decision']]
    assert result['reason'] == case['expect']['reason']
    assert crit_ids(result['triggered_criteria']) == sorted(case['expect']['hard_ids'])
    assert crit_ids(result['soft_triggered']) == sorted(case['expect']['soft_ids'])
