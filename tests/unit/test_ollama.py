from __future__ import annotations

import json

import httpx
import pytest
from klaude_core.ollama import Ollama


def test_chat_assembles_streamed_transport_for_tool_compatible_response():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","content":"hello "},"done":false}\n'
                '{"message":{"role":"assistant","content":"world",'
                '"tool_calls":[{"function":{"name":"read_file","arguments":{}}}]},'
                '"done":true,"done_reason":"stop","prompt_eval_count":12,'
                '"eval_count":2}\n'
            ),
        )

    ollama = Ollama("http://ollama.test")
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    message = ollama.chat(
        "small-model",
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
    )

    assert observed["stream"] is True
    assert message["content"] == "hello world"
    assert message["tool_calls"][0]["function"]["name"] == "read_file"
    assert ollama.last_chat_metadata["prompt_eval_count"] == 12
    assert ollama.last_chat_metadata["eval_count"] == 2


def test_tool_chat_reports_reasoning_only_output_limit():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","thinking":"plan"},"done":false}\n'
                '{"message":{"role":"assistant","thinking":"more"},'
                '"done":true,"done_reason":"length","eval_count":4096}\n'
            ),
        )

    ollama = Ollama("http://ollama.test")
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )

    message = ollama.chat(
        "qwen3.5:4b", [{"role": "user", "content": "repair this file"}],
        tools=[{"type": "function", "function": {"name": "read_file"}}],
        think=False,
    )

    assert message["content"] == ""
    assert ollama.last_chat_metadata["done_reason"] == "length"
    assert ollama.last_chat_metadata["thinking_characters"] == 8


def test_cancel_active_closes_request_client():
    class FakeClient:
        closed = False

        def close(self):
            self.closed = True

    ollama = Ollama("http://ollama.test")
    active = FakeClient()
    ollama._track_request(active)

    assert ollama.cancel_active() is True
    assert active.closed is True


def test_cancel_active_is_best_effort_and_idempotent_when_closers_fail():
    class RaisingClient:
        close_calls = 0

        def close(self):
            self.close_calls += 1
            raise OSError("client already closed")

    class RaisingResponse:
        extensions = {}
        close_calls = 0

        def close(self):
            self.close_calls += 1
            raise OSError("response already closed")

    ollama = Ollama("http://ollama.test")
    client = RaisingClient()
    response = RaisingResponse()
    ollama._track_request(client, response)

    assert ollama.cancel_active() is True
    assert ollama.cancel_active() is False
    assert response.close_calls == 1
    assert client.close_calls == 1


def test_cancel_active_wakes_a_blocked_socket_reader():
    import socket
    import threading
    from types import SimpleNamespace

    probe_reader, probe_writer = socket.socketpair()
    try:
        try:
            probe_reader.shutdown(socket.SHUT_RDWR)
        except PermissionError:
            pytest.skip("test sandbox blocks socket shutdown")
    finally:
        probe_reader.close()
        probe_writer.close()

    reader, writer = socket.socketpair()
    finished = threading.Event()

    def receive():
        try:
            reader.recv(1)
        finally:
            finished.set()

    worker = threading.Thread(target=receive, daemon=True)
    worker.start()
    ollama = Ollama("http://ollama.test")
    response = SimpleNamespace(
        extensions={"network_stream": SimpleNamespace(get_extra_info=lambda _key: reader)},
        close=lambda: None,
    )
    ollama._track_request(SimpleNamespace(close=lambda: None), response)
    try:
        ollama.cancel_active()
        assert finished.wait(1), "Cancellation must wake recv without waiting for server data"
    finally:
        writer.close()
        worker.join(timeout=1)
        reader.close()
        ollama._client.close()


def test_chat_stream_yields_message_fragments_and_records_completion_metadata():
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","content":"hello ",'
                '"thinking":"plan"},"done":false}\n'
                '{"message":{"role":"assistant","content":"world"},'
                '"done":true,"done_reason":"stop","eval_count":2}\n'
            ),
        )

    ollama = Ollama("http://ollama.test")
    ollama._client.close()
    ollama._client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    fragments = list(
        ollama.chat_stream(
            "small-model",
            [{"role": "user", "content": "hi"}],
            options={"num_ctx": 4096},
            think=False,
        )
    )

    assert "".join(fragment["content"] for fragment in fragments) == "hello world"
    assert observed == {
        "model": "small-model",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "options": {"num_ctx": 4096},
        "think": False,
    }
    assert ollama.last_chat_metadata == {
        "done": True,
        "done_reason": "stop",
        "eval_count": 2,
        "thinking_characters": 4,
    }
    ollama._client.close()


@pytest.mark.parametrize("streamed", [False, True])
def test_cancel_active_before_response_headers_wakes_real_http_request(streamed):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    request_started = threading.Event()
    release_server = threading.Event()
    finished = threading.Event()
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            request_started.set()
            release_server.wait(5)
            self.close_connection = True

        def log_message(self, *_args):
            pass

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except (PermissionError, OSError):
        pytest.skip("test sandbox blocks loopback HTTP listener")
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    ollama = Ollama(f"http://127.0.0.1:{server.server_port}", timeout=30)

    def request():
        try:
            if streamed:
                list(ollama.chat_stream("slow-model", [{"role": "user", "content": "hi"}]))
            else:
                ollama.chat("slow-model", [{"role": "user", "content": "hi"}])
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=request, daemon=True)
    worker.start()
    try:
        assert request_started.wait(2)
        assert ollama._active_response is None
        assert ollama.cancel_active()
        assert finished.wait(1), "Cancellation must wake a request awaiting response headers"
        assert errors
        assert not ollama.cancel_active()
    finally:
        release_server.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        ollama.close()


def test_cancelled_request_cannot_reattach_or_clear_a_new_request():
    from klaude_core.ollama import OllamaError

    ollama = Ollama("http://ollama.test")
    old = httpx.Client()
    new = httpx.Client()
    response = httpx.Response(200)
    try:
        ollama._track_request(old)
        trace = ollama._request_trace(old)
        ollama.cancel_active()
        ollama._track_request(new)
        with pytest.raises(OllamaError, match="cancelled"):
            trace("http11.receive_response_headers.started", {})
        with pytest.raises(OllamaError, match="cancelled"):
            ollama._attach_response(old, response)
        ollama._finish_request(old)
        assert ollama._active_client is new
    finally:
        old.close()
        new.close()
        ollama.close()


def test_constrained_action_is_normalized_only_for_explicit_format_request():
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        content = json.dumps({'tool': 'read_file', 'arguments': {'path': 'README.md'}})
        if 'format' in payload:
            content = json.dumps({'actions': [json.loads(content)]})
        return httpx.Response(200, text=json.dumps({
            'message': {'role': 'assistant', 'content': content}, 'done': True,
            'done_reason': 'stop', 'prompt_eval_count': 20, 'eval_count': 8,
        }) + '\n')

    ollama = Ollama('http://ollama.test')
    ollama._chat_client_factory = lambda: httpx.Client(
        base_url=ollama.base_url, transport=httpx.MockTransport(handler))
    schemas = [{'type': 'function', 'function': {
        'name': 'read_file', 'description': 'Read a file', 'parameters': {
            'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path'],
        },
    }}]
    dialogue = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'Read README'}]
    ordinary = ollama.chat('small', dialogue, tools=schemas)
    assert 'tool_calls' not in ordinary
    recovered = ollama.chat_structured_action('small', dialogue, tools=schemas)
    assert recovered['tool_calls'][0]['function']['arguments'] == {'path': 'README.md'}
    assert 'format' not in requests[0]
    assert 'tools' not in requests[1]
    action_schema = requests[1]['format']['properties']['actions']['items']
    assert action_schema['properties']['tool']['enum'] == ['read_file', '__finish__']
    arguments = action_schema['properties']['arguments']
    assert set(arguments['properties']) == {'path', 'answer'}
    assert arguments['additionalProperties'] is False
    assert 'completed_step' not in arguments['properties']
    assert dialogue[0]['content'] == 'system'
    assert ollama.last_chat_metadata['prompt_eval_count'] == 20


@pytest.mark.parametrize('action', [
    {'tool': 'run_shell', 'arguments': {}},
    {'tool': 'read_file', 'arguments': [], 'answer': 'done'},
    {'answer': ['not text']},
])
def test_constrained_action_rejects_unknown_or_ambiguous_envelopes(action):
    from klaude_core.ollama import OllamaError

    ollama = Ollama('http://ollama.test')
    ollama.chat = lambda *a, **kw: {'content': json.dumps({'actions': [action]})}
    with pytest.raises(OllamaError, match='invalid constrained action'):
        ollama.chat_structured_action('small', [{'role': 'system', 'content': 'system'}],
                                     tools=[{'function': {'name': 'read_file', 'parameters': {}}}])


def test_constrained_tool_recovery_excludes_cloud_and_root_schema_references():
    schemas = [{'function': {'name': 'read_file', 'parameters': {}}}]
    local = Ollama()
    assert local.supports_structured_tool_recovery('small', schemas)
    assert not local.supports_structured_tool_recovery('small:cloud', schemas)
    assert not Ollama('https://ollama.com').supports_structured_tool_recovery('small', schemas)
    assert not local.supports_structured_tool_recovery('small', [
        {'function': {'name': 'mcp__remote__read', 'parameters': {'$ref': '#/$defs/args'}}},
    ])


def test_discovery_format_enforces_observed_paths_without_an_object_union():
    from klaude_core.ollama import OllamaError

    requests = []
    reply = {'actions': [{'tool': 'list_dir', 'arguments': {'path': 'src'}}]}

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=json.dumps({
            'message': {'content': json.dumps(reply)}, 'done': True,
        }) + '\n')

    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler))
    schemas = [{'function': {'name': name, 'parameters': {
        'type': 'object', 'properties': {'path': {'type': 'string', 'enum': paths}},
        'required': ['path'],
    }}} for name, paths in [('list_dir', ['src']), ('read_file', ['README.md'])]]
    args = ('small', [{'role': 'system', 'content': 'system'}])
    result = client.chat_structured_action(*args, tools=schemas, allow_finish=False)
    assert result['tool_calls'][0]['function']['arguments'] == {'path': 'src'}
    schema = requests[-1]['format']['properties']['actions']['items']['properties']
    assert schema['tool']['enum'] == ['list_dir', 'read_file']
    assert schema['arguments']['properties']['path']['enum'] == ['src', 'README.md']
    assert schema['arguments']['required'] == ['path']
    assert 'oneOf' not in json.dumps(requests[-1]['format'])
    reply['actions'] = [{'tool': '__finish__', 'arguments': {'answer': 'Fake completion.'}}]
    with pytest.raises(OllamaError, match='invalid constrained action'):
        client.chat_structured_action(*args, tools=schemas, allow_finish=False)


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('body', [
    '{"message":{"content":"partial"},"done":false}\n',
    '{"error":"runner failed"}\n',
])
def test_incomplete_or_failed_stream_is_not_a_completed_model_answer(streaming, body):
    from klaude_core.ollama import OllamaError

    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=body)))
    with pytest.raises(OllamaError, match='stream'):
        if streaming:
            list(client.chat_stream('small', [{'role': 'user', 'content': 'hello'}]))
        else:
            client.chat('small', [{'role': 'user', 'content': 'hello'}])
    assert client._active_client is None


def test_unfinished_assembled_tool_call_has_a_typed_failure_and_returns_no_calls():
    from klaude_core.ollama import OllamaIncompleteResponse

    body = json.dumps({'message': {'tool_calls': [{'function': {
        'name': 'write_file', 'arguments': {'path': 'app.py', 'content': 'partial'},
    }}]}, 'done': False}) + '\n'
    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=body)))
    with pytest.raises(OllamaIncompleteResponse, match='partial calls discarded'):
        client.chat('small', [{'role': 'user', 'content': 'Implement the feature.'}])
    assert client.last_chat_metadata == {}
    assert client._active_client is None


def test_workspace_plan_request_is_constrained_public_data_without_callable_tools():
    changes = [{'goal': 'Implement current source', 'files': ['app.py'],
                'request_refs': ['r1']}]
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, text=json.dumps({
            'message': {'content': json.dumps({'changes': changes})}, 'done': True,
        }) + '\n')

    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler))
    result = client.chat_workspace_plan('small', [{'role': 'system', 'content': 'system'}],
                                        request_refs=['r1', 'r2'])
    assert result['workspace_plan'][0] == {**changes[0], 'kind': 'implement'}
    assert [step['kind'] for step in result['workspace_plan']] == [
        'implement', 'validate', 'review']
    assert 'tools' not in requests[0]
    assert requests[0]['format']['properties']['changes']['maxItems'] == 4
    assert 'kind' not in requests[0]['format']['properties']['changes']['items']['properties']


def test_constrained_batch_read_bodies_keep_their_paths_without_changing_history():
    from copy import deepcopy

    messages = [{'role': 'system', 'content': 'system'},
                {'role': 'assistant', 'content': '', 'tool_calls': [
                    {'id': key, 'function': {'name': 'read_file', 'arguments': {'path': path}}}
                    for key, path in [('entry', 'pkg/__main__.py'), ('cli', 'pkg/cli.py'),
                                      ('failed', 'missing.py')]
                ]},
                *[{'role': 'tool', 'tool_call_id': key, 'tool_name': 'read_file', 'content': body}
                  for key, body in [('entry', 'from .cli import main\nmain()\n'),
                                    ('cli', 'def main(): return 2\n'),
                                    ('failed', 'tool error: FileNotFoundError')]]]
    original = deepcopy(messages)
    requests = []
    client = Ollama()

    def chat(model, outgoing, **kwargs):
        requests.append(outgoing)
        return {'content': json.dumps({'actions': [
            {'tool': '__finish__', 'arguments': {'answer': 'Observed results.'}},
        ]})}

    client.chat = chat
    client.chat_structured_action('small', messages, tools=[{'function': {
        'name': 'read_file', 'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string'}}, 'required': ['path']},
    }}])
    for outgoing, path, body in zip(requests[0][2:],
                                   ['pkg/__main__.py', 'pkg/cli.py', 'missing.py'],
                                   [m['content'] for m in messages[2:]], strict=True):
        assert outgoing['content'].startswith('read_file result for requested arguments ')
        assert json.dumps({'path': path}) in outgoing['content']
        assert outgoing['content'].endswith(body)
    assert messages == original


@pytest.mark.parametrize(('arguments', 'expected'), [
    ({'path': 'app.py'}, {'path': 'app.py', 'limit': 100}),
    ({'path': 'app.py', 'offset': 151}, {'path': 'app.py', 'offset': 151, 'limit': 100}),
    ({'path': 'app.py', 'offset': 151, 'limit': 5},
     {'path': 'app.py', 'offset': 151, 'limit': 5}),
])
def test_local_read_default_is_paged_and_explicit_ranges_stay_unchanged(
    tmp_path, arguments, expected,
):
    from copy import deepcopy

    from klaude_tools import Workspace, build_tools

    workspace = Workspace(tmp_path)
    (tmp_path / 'app.py').write_text('\n'.join(f'VALUE_{i}={i}' for i in range(1, 251)))
    tool = next(t for t in build_tools(workspace) if t.name == 'read_file')
    original_schema, original_arguments = deepcopy(tool.schema()), deepcopy(arguments)
    requests = []
    client = Ollama()

    def chat(model, messages, **kwargs):
        requests.append(messages)
        assert kwargs['response_format']['properties']['actions']['items']['properties'][
            'arguments']['properties']['limit']['default'] == 100
        return {'content': json.dumps({'actions': [
            {'tool': 'read_file', 'arguments': arguments},
        ]})}

    client.chat = chat
    response = client.chat_structured_action('small', [{'role': 'system', 'content': 'system'}],
                                            tools=[tool.schema()], allow_finish=False)
    actual = response['tool_calls'][0]['function']['arguments']
    assert actual == expected and arguments == original_arguments
    assert tool.schema() == original_schema
    page = tool.fn(**actual)
    start = expected.get('offset', 1)
    end = min(start + expected['limit'] - 1, 250)
    assert page.startswith(f'app.py: lines {start}-{end} of 250\n')
    assert page.endswith(f'{end}: VALUE_{end}={end}')
    assert 'VALUE_250=250' in tool.fn(path='app.py')  # Native unpaged compatibility.


@pytest.mark.parametrize(('files', 'reference'), [
    (['app.py'], 'made_up'), (['app.py'], 1), (['app.py', 'tests/test_app.py'], 'r1'),
])
def test_workspace_plan_rejects_invalid_links_or_collapsed_file_changes(files, reference):
    from klaude_core.ollama import OllamaError

    client = Ollama()
    client.chat = lambda *a, **kw: {'content': json.dumps({'changes': [
        {'goal': 'Change code', 'files': files, 'request_refs': [reference]},
    ]})}
    with pytest.raises(OllamaError, match='invalid workspace plan'):
        client.chat_workspace_plan('small', [{'role': 'system', 'content': 'system'}],
                                   request_refs=['r1'])


def test_constrained_batch_rejects_unknown_action_before_returning_any_calls():
    from klaude_core.ollama import OllamaError

    client = Ollama()
    client.chat = lambda *a, **kw: {'content': json.dumps({'actions': [
        {'tool': 'read_file', 'arguments': {'path': 'app.py'}},
        {'tool': 'invented_tool', 'arguments': {}},
    ]})}
    with pytest.raises(OllamaError, match='invalid constrained action'):
        client.chat_structured_action('small', [{'role': 'system', 'content': 'system'}],
                                     tools=[{'function': {'name': 'read_file', 'parameters': {}}}])


@pytest.mark.parametrize('writable,action_count', [(False, 2), (True, 1), (True, 2)])
def test_constrained_execution_enforces_one_action_without_losing_discovery_batches(
    writable, action_count,
):
    from klaude_core.ollama import OllamaError

    requests = []
    name = 'write_file' if writable else 'read_file'
    arguments = {'path': 'app.py', **({'content': 'VALUE = 1\n'} if writable else {})}

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        content = json.dumps({'actions': [
            {'tool': name, 'arguments': arguments} for _ in range(action_count)
        ]})
        return httpx.Response(200, text=json.dumps({
            'message': {'content': content}, 'done': True,
        }) + '\n')

    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler))
    schemas = [{'type': 'function', 'function': {'name': name, 'parameters': {
        'type': 'object', 'properties': {'path': {'type': 'string'},
                                       'content': {'type': 'string'}},
        'required': ['path'], 'additionalProperties': False,
    }}}]
    try:
        if writable and action_count > 1:
            with pytest.raises(OllamaError, match='invalid constrained action'):
                client.chat_structured_action('small', [{'role': 'system', 'content': ''}],
                                              tools=schemas)
        else:
            result = client.chat_structured_action(
                'small', [{'role': 'system', 'content': ''}], tools=schemas)
            assert len(result['tool_calls']) == action_count
        assert requests[0]['format']['properties']['actions']['maxItems'] == (
            1 if writable else 4)
    finally:
        client.close()


@pytest.mark.parametrize('completed_step', [False, True])
def test_execution_discriminator_binds_arguments_and_preserves_completion(completed_step):
    requests = []
    tools = [
        {'function': {'name': 'edit_file', 'parameters': {
            'type': 'object', 'properties': {
                key: {'type': 'string'} for key in ('path', 'old_str', 'new_str')
            }, 'required': ['path', 'old_str', 'new_str'], 'additionalProperties': False,
        }}},
        {'function': {'name': 'run_shell', 'parameters': {
            'type': 'object', 'properties': {'command': {'type': 'string'}},
            'required': ['command'], 'additionalProperties': False,
        }}},
    ]
    original = json.dumps(tools)
    client = Ollama('http://ollama.test')

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, text=json.dumps({
            'message': {'content': json.dumps({'actions': [{
                'tool': 'edit_file', 'arguments': {
                    'path': 'app.py', 'old_str': 'VALUE=2', 'new_str': 'VALUE=1',
                },
            }]})}, 'done': True,
        }) + '\n')

    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler))
    try:
        prior = {'role': 'assistant', 'content': '', 'completed_step': completed_step,
                 'tool_calls': [{'id': 'prior', 'function': {
                     'name': 'edit_file', 'arguments': {
                         'path': 'app.py', 'old_str': 'VALUE=0', 'new_str': 'VALUE=2',
                     },
                 }}]}
        messages = [{'role': 'system', 'content': ''}, prior,
                    {'role': 'tool', 'tool_call_id': 'prior', 'content': 'edited'}]
        result = client.chat_structured_action('small', messages, tools=tools)
        converted = json.loads(requests[0]['messages'][1]['content'])
        assert converted['completed_step'] is completed_step
        assert messages[1] is prior and prior['completed_step'] is completed_step
        assert result['tool_calls'][0]['function']['name'] == 'edit_file'
        variants = requests[0]['format']['properties']['actions']['items']['oneOf']
        by_name = {v['properties']['tool']['enum'][0]: v for v in variants}
        for tool in tools:
            function = tool['function']
            assert by_name[function['name']]['properties']['arguments'] == function['parameters']
        assert set(by_name['__finish__']['properties']['arguments']['properties']) == {'answer'}
        assert '"tools":' not in requests[0]['messages'][0]['content']
        assert json.dumps(tools) == original
    finally:
        client.close()


@pytest.mark.parametrize('permission', ['allow', 'ask'])
@pytest.mark.parametrize('failure', ['printed', 'parser'])
def test_constrained_recovery_through_runtime_wrapper_still_uses_permission_gate(
    permission, failure,
):
    from klaude_core import Agent, PermissionGate, Tool
    from klaude_core.model_runtime import OllamaRuntime

    requests = []
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if 'format' not in payload:
            if failure == 'parser':
                return httpx.Response(500, text='ollama tool call parsing failed: unexpected EOF')
            content = '{"name":"read_file","arguments":{"path":"invented.py"}}'
        elif len(requests) == 2:
            content = json.dumps({'tool': 'read_file', 'arguments': {'path': 'README.md'}})
        else:
            content = json.dumps({'tool': '__finish__', 'arguments': {
                'answer': 'Observed result or permission boundary reported.',
            }})
        if 'format' in payload:
            content = json.dumps({'actions': [json.loads(content)]})
        return httpx.Response(200, text=json.dumps({
            'message': {'role': 'assistant', 'content': content},
            'done': True, 'done_reason': 'stop',
        }) + '\n')

    client = Ollama('http://ollama.test')
    client._chat_client_factory = lambda: httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler))
    tool = Tool('read_file', 'Read', {'type': 'object', 'properties': {
        'path': {'type': 'string'}}, 'required': ['path']},
        lambda path: calls.append(path) or 'actual README')
    agent = Agent(OllamaRuntime(client), 'small', [tool],
                  PermissionGate({'read_file': permission}, lambda *_: 'n'), 'system')
    events = list(agent.run('Read README.md'))
    assert calls == (['README.md'] if permission == 'allow' else [])
    assert len(requests) == 3
    assert 'format' not in requests[0]
    assert 'format' in requests[1]
    assert 'invented.py' not in str(agent.messages)
    assert not any(e.kind == 'error' for e in events)
