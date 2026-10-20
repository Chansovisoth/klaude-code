"""Outcome regressions for compound requests, with no external network/model."""
from copy import deepcopy

import pytest
from klaude_core import Agent, PermissionGate, Tool, TurnScope
from klaude_core.model_runtime import ModelInfo


def call(name, **arguments):
    return {'role': 'assistant', 'content': '', 'tool_calls': [
        {'function': {'name': name, 'arguments': arguments}},
    ]}


class Runtime:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.last_chat_metadata = {}

    def chat(self, model, messages, **kwargs):
        self.requests.append(deepcopy(messages))
        return next(self.replies)


def agent_for(replies, *, search=None, gate=None, selector=None):
    runtime = Runtime(replies)
    tools = [
        Tool('web_search', 'Search', {'type': 'object'}, search or (lambda **_: {
            'content': 'Candidate artist portfolio https://artist.example/work',
            'metadata': {'search_results': [{'url': 'https://artist.example/work',
                                             'result_id': 'search_result_001'}]},
        })),
        Tool('fetch_url', 'Read page', {'type': 'object'}, lambda **_: {
            'content': '[src_001] Artist portfolio: work created in 2024. ' * 8,
            'metadata': {'source_id': 'src_001', 'status': 'succeeded'},
        }),
    ]
    agent = Agent(runtime, 'test', tools, gate or PermissionGate(
        {t.name: 'allow' for t in tools}, lambda *_: 'n'), 'system', tool_selector=selector)
    return agent, runtime


@pytest.mark.parametrize('prompt', [
    'can you look up where this is from',
    'look them up',
    'Could you look that artist up please?',
    'look thme up',
])
def test_lookup_omission_gets_bounded_model_directed_repair(prompt):
    agent, runtime = agent_for([
        {'role': 'assistant', 'content': 'This is probably artist X. I can search if you want.'},
        call('web_search', query='artist X official portfolio'),
        call('fetch_url', url='https://artist.example/work'),
        {'role': 'assistant', 'content': 'A portfolio lead is https://artist.example/work.'},
    ], selector=lambda *_: [])
    events = list(agent.run(prompt))
    assert any(e.kind == 'tool_result' and e.payload['tool'] == 'web_search' for e in events)
    assert len(runtime.requests) == 4
    assert not any(e.kind == 'error' for e in events)
    assert [e.payload['content'] for e in events if e.kind == 'text'] == [
        'A portfolio lead is https://artist.example/work.'
    ]


def test_direct_source_read_can_satisfy_lookup_without_redundant_search():
    agent, runtime = agent_for([
        call('fetch_url', url='https://artist.example/work'),
        {'role': 'assistant', 'content': 'The supplied portfolio credits the artist.'},
    ])
    events = list(agent.run('look them up'))
    assert len(runtime.requests) == 2
    assert not any(e.kind in {'retry', 'error'} for e in events)


def test_failed_lookup_cannot_be_reported_as_verified_success():
    def denied(**_):
        raise AssertionError('Permission denied; function must never run')
    agent, _ = agent_for([
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'I verified the artist is X.'},
    ], search=denied, gate=PermissionGate({'web_search': 'deny', 'fetch_url': 'deny'},
                                        lambda *_: 'n'))
    events = list(agent.run('look them up'))
    assert any(e.kind == 'error' for e in events)
    assert not any('I verified' in e.payload.get('content', '') for e in events)


@pytest.mark.parametrize('prompt', [
    'Hello', 'Reply with exactly OK', 'Describe only the image colors.',
    'Do not search the web. Describe this image.',
    'Look them up without using any tools.',
    'Look up the key in this dictionary; explain the Python code.',
    'Explain the phrase "look them up".',
    "Translate 'look them up' into French.",
    'Print exactly `look them up`.',
    'Explain this example: ```look them up```',
    'Do not look them up online; look up the key in this dictionary.',
    'Print exactly "look them up".',
    "Reply with exactly 'search the web'.",
])
def test_direct_and_restricted_requests_do_not_get_forced_research(prompt):
    agent, runtime = agent_for([{'role': 'assistant', 'content': 'OK'}],
                                selector=lambda *_: [])
    events = list(agent.run(prompt))
    assert len(runtime.requests) <= 1
    assert not any(e.kind in {'tool_start', 'retry', 'error'} for e in events)


def test_literal_payload_does_not_reinstate_explicitly_named_retrieval_tools():
    agent, runtime = agent_for([{'role': 'assistant', 'content': 'search the web'}])
    events = list(agent.run('Print exactly "search the web".'))
    assert runtime.requests == []
    assert [e.payload['content'] for e in events if e.kind == 'text'] == ['search the web']
    assert agent.last_turn_capabilities['callable_tools'] == []
    assert not any(e.kind in {'tool_start', 'retry', 'error'} for e in events)


def test_literal_payload_keeps_direct_context_and_general_runtime_options():
    agent, runtime = agent_for([{'role': 'assistant', 'content': 'Update Klaude Python code'}])
    agent.ollama_options = {'num_ctx': 4096}
    agent.ollama_code_options = {'num_ctx': 32768}
    events = list(agent.run('Print exactly "Update Klaude Python code".'))
    assert agent._last_request_options['num_ctx'] == 4096
    assert runtime.requests == []
    assert [e.payload['content'] for e in events if e.kind == 'text'] == [
        'Update Klaude Python code']
    assert agent.last_turn_capabilities['callable_tools'] == []
    assert not any(e.kind in {'tool_start', 'retry', 'error'} for e in events)


def test_false_lookup_claim_is_not_streamed_before_completion_check():
    class Streaming(Runtime):
        def chat_stream(self, model, messages, **kwargs):
            response = self.chat(model, messages, **kwargs)
            if response.get('content'):
                yield {'role': 'assistant', 'content': response['content']}
            if response.get('tool_calls'):
                yield response

    agent, _ = agent_for([])
    runtime = Streaming([
        {'role': 'assistant', 'content': 'I verified a source without searching.'},
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'Only a candidate source was found.'},
    ])
    agent.ollama = runtime
    agent.model_info = ModelInfo('openai_compatible', 'test', 'Test')
    events = list(agent.run('look them up'))
    assert not any('I verified' in e.payload.get('content', '') for e in events)
    assert [e.payload['content'] for e in events if e.kind == 'text'] == [
        'Only a candidate source was found.'
    ]


def test_repeated_omission_stops_after_one_correction_without_false_success():
    agent, runtime = agent_for([
        {'role': 'assistant', 'content': 'I found the source.'},
        {'role': 'assistant', 'content': 'I checked the source.'},
    ])
    events = list(agent.run('look them up'))
    assert len(runtime.requests) == 2
    assert sum(e.kind == 'retry' for e in events) == 1
    assert any(e.kind == 'error' for e in events)
    assert agent.last_task_progress['status'] == 'pending'
    assert not any('I found' in e.payload.get('content', '') or
                   'I checked' in e.payload.get('content', '') for e in events)


def test_no_results_and_failed_calls_are_not_completion_evidence():
    agent, _ = agent_for([
        call('web_search', query='unknown'),
        {'role': 'assistant', 'content': 'I verified it.'},
    ], search=lambda **_: {'content': 'No results', 'metadata': {'search_results': []}})
    events = list(agent.run('look them up'))
    assert agent.last_task_progress['status'] == 'partial'
    assert agent.last_task_progress['outcomes'][0]['evidence'] == []
    assert any(e.kind == 'error' for e in events)
    assert not any('I verified' in e.payload.get('content', '') for e in events)


def test_followup_uses_prior_candidate_and_restore_does_not_replay_audit_as_evidence():
    agent, runtime = agent_for([
        call('web_search', query='Luma Quill official artist'),
        {'role': 'assistant', 'content': 'Only a portfolio lead was found.'},
    ])
    agent.restore_session([
        {'role': 'user', 'content': 'Who is the artist in this image?'},
        {'role': 'assistant', 'content': 'The credit might say Luma Quill; this is unverified.'},
        {'role': 'system', 'content': {'tool': 'web_search', 'executed': True}},
    ])
    events = list(agent.run('look them up', scope=TurnScope.PLAN))
    assert 'Luma Quill' in str(runtime.requests[0])
    assert 'unverified' in str(runtime.requests[0])
    assert any(e.kind == 'tool_result' for e in events)
    assert agent.last_task_progress['status'] == 'complete'


def test_source_provenance_mcp_can_satisfy_lookup_without_builtin_search():
    agent, runtime = agent_for([
        call('mcp__research__read', query='artist X'),
        {'role': 'assistant', 'content': 'A source credits X.'},
    ], selector=lambda *_: ['mcp__research__read'])
    agent.tools['mcp__research__read'] = Tool(
        'mcp__research__read', 'Research', {'type': 'object'}, lambda **_: {
            'content': 'Portfolio credits X.', 'metadata': {'source_id': 'src_mcp_001'},
        })
    agent.gate.policies['mcp__research__read'] = 'allow'
    events = list(agent.run('look them up'))
    assert len(runtime.requests) == 2
    assert not any(e.kind in {'retry', 'error'} for e in events)
    assert agent.last_task_progress['status'] == 'complete'


def test_runtime_failure_retains_elapsed_budget_at_the_error_boundary(monkeypatch):
    from klaude_core.execution import TurnGovernor
    clock = [0.0]
    monkeypatch.setattr('klaude_core.agent.TurnGovernor',
                        lambda *a, **kw: TurnGovernor(*a, clock=lambda: clock[0], **kw))
    agent, runtime = agent_for([])
    def fail(*_a, **_kw):
        clock[0] = 269.0
        raise RuntimeError('Model connection interrupted')
    runtime.chat = fail
    events = list(agent.run('look them up'))
    assert any(e.kind == 'error' for e in events)
    assert agent.last_turn_budget['elapsed_seconds'] == 269.0
    assert agent.last_turn_capabilities['budget']['elapsed_seconds'] == 269.0


def test_origin_lookup_continues_from_search_lead_to_source_without_new_permission():
    agent, runtime = agent_for([
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'I found a lead. Would you like me to open it?'},
        call('fetch_url', url='https://artist.example/work'),
        {'role': 'assistant', 'content': 'The portfolio credits X; authenticity is unverified.'},
    ])
    events = list(agent.run('can you look up where this is from'))
    assert len(runtime.requests) == 4
    assert sum(e.kind == 'retry' for e in events) == 1
    assert 'Examine a candidate source' in str(runtime.requests[2])
    assert not any('Would you like me' in e.payload.get('content', '') for e in events)
    assert not any(e.kind == 'error' for e in events)
    assert agent.last_task_progress['status'] == 'complete'
    assert len(agent.last_task_progress['outcomes']) == 2


@pytest.mark.parametrize('unusable', [None, 'success', {'content': 'unavailable'}])
def test_search_without_structured_leads_cannot_establish_completion(unusable):
    agent, _ = agent_for([
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'I verified it.'},
    ], search=lambda **_: unusable)
    events = list(agent.run('look them up'))
    assert agent.last_task_progress['status'] == 'partial'
    assert any(e.kind == 'error' for e in events)
    assert not any('I verified' in e.payload.get('content', '') for e in events)


def test_tool_followup_retains_one_current_objective_note_without_history_growth():
    agent, runtime = agent_for([
        call('web_search', query='Luma Quill'),
        call('fetch_url', url='https://artist.example/work'),
        {'role': 'assistant', 'content': 'The portfolio dates the work to 2024.'},
    ])
    agent.restore_session([
        {'role': 'user', 'content': 'Read the credit. Do not search.'},
        {'role': 'assistant', 'content': 'Luma Quill.'},
    ])
    events = list(agent.run('look them up'))
    for messages in runtime.requests[1:]:
        assert messages[-1]['role'] == 'system'
        assert 'Continue the current user objective: "look them up"' in messages[-1]['content']
        assert sum('Continue the current user objective:' in str(m.get('content', ''))
                   for m in messages) == 1
    assert not any('Continue the current user objective:' in str(m.get('content', ''))
                   for m in agent.messages)
    assert not any(e.kind == 'error' for e in events)


def test_step_limit_cannot_bypass_source_examination_or_synthesize_false_completion():
    agent, runtime = agent_for([
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'I verified its original source.'},
    ])
    agent.max_steps = 1
    events = list(agent.run('can you look up where this is from'))
    assert len(runtime.requests) == 1
    assert agent.last_task_progress['status'] == 'partial'
    assert any(e.kind == 'error' for e in events)
    assert not any('I verified' in e.payload.get('content', '') for e in events)


@pytest.mark.parametrize('bound_arguments', [False, True])
def test_supported_local_recovery_limits_choices_to_missing_outcome_without_finish(bound_arguments):
    agent, _ = agent_for([])
    class Constrained(Runtime):
        def supports_structured_tool_recovery(self, model, tools):
            return True

        def chat_structured_action(self, model, messages, *, tools, allow_finish, **kwargs):
            self.requests.append(deepcopy(messages))
            assert allow_finish is False
            assert {schema['function']['name'] for schema in tools} == {'fetch_url'}
            assert kwargs.get('bind_arguments', False) is bound_arguments
            return call('fetch_url', url='https://artist.example/work')
    runtime = Constrained([
        call('web_search', query='artist X'),
        {'role': 'assistant', 'content': 'I cannot read pages. Please paste the page.'},
        {'role': 'assistant', 'content': 'The source dates the work to 2024.'},
    ])
    runtime.supports_bound_action_arguments = bound_arguments
    agent.ollama = runtime
    events = list(agent.run('can you look up where this is from'))
    assert len(runtime.requests) == 4
    assert sum(e.kind == 'tool_result' for e in events) == 2
    assert not any(e.kind == 'error' for e in events)
    assert agent.last_task_progress['status'] == 'complete'


def test_explicit_page_read_is_an_outcome_before_budget_synthesis():
    agent, runtime = agent_for([call('web_search', query='artist portfolio')])
    agent.max_steps = 1
    events = list(agent.run('Look up this work and read the relevant portfolio page.'))
    assert len(runtime.requests) == 1
    assert agent.last_task_progress['status'] == 'partial'
    assert any(o['key'] == 'source_examination' and o['status'] == 'pending'
               for o in agent.last_task_progress['outcomes'])
    assert any(e.kind == 'error' for e in events)


def test_research_with_clock_keeps_compact_context_and_both_callable_tools():
    from importlib import resources

    agent, runtime = agent_for([
        call('current_time'),
        call('web_search', query='event start time'),
        {'role': 'assistant', 'content': 'The event starts after the current local time.'},
    ], selector=lambda *_: ['web_search', 'fetch_url', 'current_time'])
    agent.messages[0]['content'] = (
        resources.files('klaude_core') / 'prompts/system.md'
    ).read_text()
    agent.tools['current_time'] = Tool(
        'current_time', 'Local clock', {'type': 'object'}, lambda: '2026-10-16T12:00:00+07:00',
    )
    agent.gate.policies['current_time'] = 'allow'
    events = list(agent.run('Look up the event start time and compare it with the local time.'))
    assert {e.payload['tool'] for e in events if e.kind == 'tool_result'} == {
        'current_time', 'web_search',
    }
    for messages in runtime.requests:
        assert 'Research policy:' in messages[0]['content']
        assert 'complete code, provide one' not in messages[0]['content']
    assert not any(e.kind == 'error' for e in events)


@pytest.mark.parametrize(('prompt', 'expected'), [
    ('Reply exactly OK. Do not use tools.', 'OK'),
    ('Please output exactly "  alpha. beta!  ".', '  alpha. beta!  '),
    ('Repeat `read secret.md and search the web`.', 'read secret.md and search the web'),
    ('Reply with exactly “안녕”.', '안녕'),
    ('Return exactly 42', '42'),
    ('Print exactly "".', ''),
])
def test_exact_literal_is_user_text_with_no_provider_or_tool_request(prompt, expected):
    agent, runtime = agent_for([])
    runtime.last_chat_metadata = {'prompt_eval_count': 99, 'eval_count': 33}
    agent.last_request_usage = (99, 33)
    events = list(agent.run(prompt))
    assert [e.payload['content'] for e in events if e.kind == 'text'] == [expected]
    assert events[-1].kind == 'done'
    assert runtime.requests == [] and runtime.last_chat_metadata == {}
    assert agent.last_request_usage is None
    assert agent.last_turn_capabilities['callable_tools'] == []
    assert agent.last_turn_budget['model_steps_used'] == 0
    assert agent.last_turn_budget['tool_calls_used'] == 0
    assert agent.messages[-1] == {'role': 'assistant', 'content': expected}
