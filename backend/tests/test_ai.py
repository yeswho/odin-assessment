import json

import httpx
import pytest
from pydantic import ValidationError

from app.ai.providers import AnthropicProvider, MockProvider, ProviderError, build_provider
from app.core.config import Settings
from tests.conftest import VALID_ANALYSIS


def settings():
    return Settings(ai_mode="anthropic", anthropic_api_key="test-only-key")


async def test_anthropic_request_and_tool_output(payload):
    async def handler(request):
        data = json.loads(request.content)
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert data["tool_choice"]["name"] == "submit_analysis"
        assert data["tools"][0]["input_schema"]["properties"]["recommendedAction"]
        return httpx.Response(
            200,
            json={
                "stop_reason": "tool_use",
                "content": [
                    {"type": "tool_use", "name": "submit_analysis", "input": VALID_ANALYSIS}
                ],
            },
        )

    provider = AnthropicProvider(settings(), httpx.MockTransport(handler))
    assert await provider.analyse(payload, 1) == VALID_ANALYSIS


@pytest.mark.parametrize(
    "status,body",
    [
        (429, {}),
        (500, {}),
        (200, {"stop_reason": "max_tokens", "content": []}),
        (200, {"stop_reason": "tool_use", "content": []}),
    ],
)
async def test_anthropic_errors_are_not_silent_mock_fallbacks(payload, status, body):
    provider = AnthropicProvider(
        settings(), httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )
    with pytest.raises(ProviderError):
        await provider.analyse(payload, 1)


async def test_anthropic_limits_response_bytes(payload):
    provider = AnthropicProvider(
        settings(), httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 65537))
    )
    with pytest.raises(ProviderError, match="size limit"):
        await provider.analyse(payload, 1)


def test_provider_selection():
    assert isinstance(
        build_provider(Settings(ai_mode="auto", anthropic_api_key=None)), MockProvider
    )
    assert isinstance(build_provider(settings()), AnthropicProvider)
    with pytest.raises(ValidationError):
        Settings(ai_mode="anthropic", anthropic_api_key=None)
