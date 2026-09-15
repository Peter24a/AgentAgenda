from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from app.services import llm_service


async def collect(handler):
    factory = httpx.AsyncClient
    with patch.object(llm_service.httpx, 'AsyncClient', side_effect=lambda **kw: factory(transport=httpx.MockTransport(handler), **kw)):
        return [chunk async for chunk in llm_service.stream_chat_completion([{'role': 'user', 'content': 'Hola'}])]


@pytest.mark.asyncio
async def test_authenticated_sse_with_usage(monkeypatch):
    monkeypatch.setattr(llm_service.settings, 'llm_api_key', SecretStr('test-app-key'))
    def handler(request):
        assert request.headers['Authorization'] == 'Bearer test-app-key'
        return httpx.Response(200, text='data:{"choices":[{"delta":{"content":"Hola"}}]}\n\ndata: {"choices":[],"usage":{"total_tokens":2}}\n\ndata: [DONE]\n\n')
    assert await collect(handler) == ['Hola']


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 429, 500, 503])
async def test_http_errors_raise(status):
    with pytest.raises(llm_service.LLMError):
        await collect(lambda request: httpx.Response(status))


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    'data: [DONE]\n\n',
    'data: {"error":{"message":"private upstream detail"}}\n\n',
    'data: broken-json\n\n',
])
async def test_broken_streams_raise(body):
    with pytest.raises(llm_service.LLMError):
        await collect(lambda request: httpx.Response(200, text=body))


@pytest.mark.asyncio
async def test_connection_error_is_safe():
    def handler(request):
        raise httpx.ConnectError('sensitive details', request=request)
    with pytest.raises(llm_service.LLMError, match='servicio local'):
        await collect(handler)
