"""Transport errors retain safe category/phase without publishing server text."""
import httpx
import pytest
from klaude_core.compatible_runtime import CompatibleModelError, CompatibleRuntime


@pytest.mark.parametrize(('failure', 'code'), [
    (httpx.ConnectTimeout, 'connect_timeout'), (httpx.ReadTimeout, 'read_timeout'),
    (httpx.WriteTimeout, 'write_timeout'), (httpx.PoolTimeout, 'pool_timeout'),
    (httpx.ConnectError, 'connect_error'), (httpx.ReadError, 'read_error'),
    (httpx.WriteError, 'write_error'), (httpx.RemoteProtocolError, 'remote_protocol_error'),
    (httpx.ProxyError, 'proxy_error'),
])
def test_before_headers_error_preserves_category_without_private_detail(failure, code):
    runtime = CompatibleRuntime('https://model.example/v1', 'private-test-secret')
    def handler(request):
        raise failure('private-test-secret https://user:password@private-host', request=request)
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(CompatibleModelError) as caught:
            runtime.chat('test', [{'role': 'user', 'content': 'hello'}])
        error = caught.value
        assert error.error_type == code
        assert error.output_started is False
        assert error.phase == 'awaiting_headers'
        assert runtime.last_chat_metadata['error_type'] == code
        assert runtime.last_chat_metadata['request_elapsed_seconds'] >= 0
        assert 'private-test-secret' not in str(error)
        assert 'password' not in str(error)
        assert 'private-host' not in str(error)
    finally:
        runtime.close()


def test_stream_failure_keeps_actual_model_and_marks_partial_output():
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"model":"actual/model","choices":[{"delta":{"content":"prefix"}}]}\n\n'
            raise httpx.ReadTimeout('private-stream-detail')
    runtime = CompatibleRuntime('https://model.example/v1')
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url, transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=Stream())))
    try:
        stream = runtime.chat_stream('router/model', [{'role': 'user', 'content': 'hello'}])
        assert next(stream)['content'] == 'prefix'
        with pytest.raises(CompatibleModelError) as caught:
            list(stream)
        assert caught.value.error_type == 'read_timeout'
        assert caught.value.phase == 'streaming'
        assert caught.value.output_started is True
        assert runtime.last_chat_metadata['routed_model'] == 'actual/model'
        assert 'private-stream-detail' not in str(caught.value)
    finally:
        runtime.close()


def test_cancelled_transport_error_is_not_presented_as_retryable_failure():
    runtime = CompatibleRuntime('https://model.example/v1')
    def handler(request):
        runtime.cancel_active()
        raise httpx.ReadError('private cancellation detail', request=request)
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match='cancelled') as caught:
            runtime.chat('test', [{'role': 'user', 'content': 'hello'}])
        assert caught.value.error_type == 'cancelled'
        assert runtime.last_chat_metadata['error_type'] == 'cancelled'
    finally:
        runtime.close()
