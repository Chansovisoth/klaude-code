from importlib import resources

from klaude_core.agent import _parse_text_tool_calls
from klaude_core.request_context import select_request_prompt


def test_workspace_policy_selection_preserves_safety_guidance_and_skill_catalog():
    prompt = (resources.files('klaude_core') / 'prompts/system.md').read_text()
    prompt = prompt.replace('{CONFIGURATION}', '''<klaude_configuration>
<configuration_detail>
- Appearance: red
- Web providers: off
</configuration_detail>
- Installed Skills: 1
  - coding: conventions
<repository_instructions>Retain the public API.</repository_instructions>
</klaude_configuration>''')
    result = select_request_prompt(
        prompt, {'read_file', 'edit_file', 'read_skill', 'run_shell'}, workspace_execution=True,
    )
    assert 'Pre-existing dirty changes belong to the user' in result
    assert 'Tool approval is handled by the host' in result
    assert 'Retain the public API' in result
    assert 'coding: conventions' in result
    assert 'When a Skill' in result
    assert 'After editing, run' in result
    assert 'Appearance: red' not in result
    assert 'Runtime context:' not in result
    assert 'Command-reference source:' not in result
    assert 'complete code, provide one' not in result
    assert 'When the user explicitly asks to learn' not in result
    assert 'search/read/reflect' not in result
    assert len(result) < len(prompt) * .6


def test_relevant_policy_modules_return_after_routing_changes():
    prompt = (resources.files('klaude_core') / 'prompts/system.md').read_text()
    result = select_request_prompt(prompt, {
        'learn_source', 'web_search', 'list_commands', 'delegate_task', 'mcp__docs__read',
    })
    assert 'canonical command registry' in result
    assert 'call `learn_source`' in result
    assert 'search/read/reflect' in result
    assert 'child retains only' in result
    assert 'untrusted data' in result
    assert 'Runtime context:' in result
    assert '<tool_policy' not in result
    # Selection is request-local; the source prompt stays intact.
    assert '<tool_policy' in prompt


def test_invalid_json_call_envelope_is_non_executable_but_detected():
    bad = ('```json\n{"name":"edit_file","arguments":{"path":"fake.py",'
           '"content":"broken\nquote"}}\n```')
    calls = _parse_text_tool_calls(bad, {'edit_file'}, recover_json=True)
    assert calls[0]['parse_status'] == 'malformed'
    assert calls[0]['function']['arguments'] == {}
    assert not _parse_text_tool_calls(bad, {'edit_file'}, recover_json=False)
    assert not _parse_text_tool_calls('Example: ' + bad, {'edit_file'}, recover_json=True)


def test_lost_native_call_at_output_limit_requests_smaller_fresh_call():
    from klaude_core import Agent, PermissionGate, Tool

    class Runtime:
        def __init__(self):
            self.requests = []
            self.last_chat_metadata = {}

        def chat(self, model, messages, **kwargs):
            self.requests.append(messages.copy())
            if len(self.requests) == 1:
                self.last_chat_metadata = {'done_reason': 'length'}
                return {'role': 'assistant', 'content': ''}
            self.last_chat_metadata = {'done_reason': 'stop'}
            if len(self.requests) == 2:
                return {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {
                    'name': 'write_file', 'arguments': {'path': 'app.py', 'content': 'x=1'},
                }}]}
            return {'role': 'assistant', 'content': 'Edited app.py.'}

    runtime = Runtime()
    writes = []
    tool = Tool('write_file', 'Write file', {'type': 'object'},
                lambda **args: writes.append(args) or 'wrote')
    agent = Agent(runtime, 'fake', [tool], PermissionGate({'write_file': 'allow'},
                  lambda *_: 'n'), 'system')
    events = list(agent.run('Implement the Python code in this project.'))
    assert len(writes) == 1
    assert 'No edit from that response executed' in runtime.requests[1][-1]['content']
    assert 'Continue exactly' not in runtime.requests[1][-1]['content']
    assert not any(e.kind == 'error' for e in events)


def test_repeated_lost_native_calls_fail_with_no_execution():
    from klaude_core import Agent, PermissionGate, Tool

    class Runtime:
        last_chat_metadata = {'done_reason': 'length'}

        def chat(self, *args, **kwargs):
            return {'role': 'assistant', 'content': 'Preparing changes.'}

    writes = []
    agent = Agent(Runtime(), 'fake', [Tool('write_file', 'Write', {'type': 'object'},
                  lambda **kw: writes.append(kw))],
                  PermissionGate({'write_file': 'allow'}, lambda *_: 'n'), 'system')
    events = list(agent.run('Implement Python code in this project.'))
    assert not writes
    assert sum(e.kind == 'retry' for e in events) == 1
    assert any(e.kind == 'error' and 'repeatedly exhausted' in e.payload['message'] for e in events)
