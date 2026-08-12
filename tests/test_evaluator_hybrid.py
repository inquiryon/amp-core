from inquiryon_amp_core.evaluator import evaluate_single_criterion


def _command_hybrid():
    return {
        'criterion_id': 'c_command_guard',
        'description': 'command-oriented hybrid criterion',
        'tool': 'exec',
        'action': '*',
        'hardness': 'hard',
        'evaluator': {
            'type': 'hybrid',
            'compute': {
                'formula': "any(pat in command for pat in ['rm -rf'])",
                'fallback_result': False,
            },
            'llm': {
                'prompt': "The agent is about to run '{{action.params.command}}'. Is it destructive?",
                'fallback_result': False,
            },
            'fallback_result': False,
        },
    }


def test_command_hybrid_skips_llm_when_command_missing():
    calls = []

    def fake_llm(_criterion, _params):
        calls.append(True)
        return True, 'llm_triggered'

    result = evaluate_single_criterion(
        _command_hybrid(),
        {'query': 'Social Security fraud news August 2026'},
        llm_evaluator=fake_llm,
    )

    assert calls == []
    assert result['triggered'] is False
    assert result['reason'] == 'hybrid_command_missing'


def test_command_hybrid_still_calls_llm_when_command_present():
    calls = []

    def fake_llm(_criterion, _params):
        calls.append(True)
        return False, 'llm_not_triggered'

    result = evaluate_single_criterion(
        _command_hybrid(),
        {'command': 'git status'},
        llm_evaluator=fake_llm,
    )

    assert calls == [True]
    assert result['triggered'] is False
    assert result['reason'] == 'llm_not_triggered'
