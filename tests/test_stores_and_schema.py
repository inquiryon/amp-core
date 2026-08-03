"""Stores, schema validation, and the documented in-memory/file example
(OSS-003 acceptance: a policy evaluates using only in-memory or file-backed
components)."""

import pytest

from inquiryon_amp_core import FilePolicyStore, InMemoryPolicyStore, run_eval_policy
from inquiryon_amp_core.schema import validate

POLICY = {
    'policy_id': 'invoice-governance',
    'schema_version': 'v0',
    'allow_unknown_tools': False,
    'action_governance': {
        'force_human_approval': False,
        'criteria': [
            {'criterion_id': 'c-high-amount', 'tool': 'pay_invoice', 'action': '*',
             'hardness': 'hard',
             'evaluator': {'type': 'compute', 'formula': 'amount > 1000'}},
        ],
    },
}


def test_policy_validates_against_v0_schema():
    assert validate(POLICY, 'Policy') == []


def test_invalid_policy_reports_errors():
    assert validate({'nonsense': True}, 'Policy') != []


def test_end_to_end_with_in_memory_store():
    store = InMemoryPolicyStore()
    store.put_policy('invoice-governance', POLICY)
    policy = store.get_policy('invoice-governance')
    result = run_eval_policy(policy, 'pay_invoice', 'submit', {'amount': 4000})
    assert result['decision'] == 'require_human'


def test_end_to_end_with_file_store(tmp_path):
    store = FilePolicyStore(str(tmp_path))
    store.put_policy('invoice-governance', POLICY)
    assert store.list_policies() == ['invoice-governance']
    policy = store.get_policy('invoice-governance')
    result = run_eval_policy(policy, 'pay_invoice', 'submit', {'amount': 40})
    assert result['decision'] == 'allow'


def test_file_store_rejects_traversal_ids(tmp_path):
    store = FilePolicyStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.get_policy('../../etc/passwd')
    with pytest.raises(ValueError):
        store.put_policy('a/b', POLICY)
