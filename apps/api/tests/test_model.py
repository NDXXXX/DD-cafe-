import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from openai import OpenAIError

from app.agents.model import DeepSeekRecommendationModel
from app.agents.router import AgentRoute


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def make_model() -> DeepSeekRecommendationModel:
    with patch("app.agents.model.AsyncOpenAI"):
        return DeepSeekRecommendationModel(
            api_key="test-key", base_url="http://test", model="test-model"
        )


@pytest.mark.asyncio
async def test_classify_route_parses_valid_json() -> None:
    model = make_model()
    model.client.chat.completions.create = AsyncMock(
        return_value=_completion(
            json.dumps({"route": "order", "confidence": 0.9, "reason": "明确购物车操作"})
        )
    )

    decision = await model.classify_route("来一杯拿铁")

    assert decision.route == AgentRoute.ORDER
    assert decision.confidence == 0.9
    assert decision.reason == "明确购物车操作"


@pytest.mark.asyncio
async def test_classify_route_degrades_on_low_confidence_or_missing_reason() -> None:
    model = make_model()

    model.client.chat.completions.create = AsyncMock(
        return_value=_completion(
            json.dumps({"route": "recommend", "confidence": 0.3, "reason": "理由"})
        )
    )
    decision = await model.classify_route("随便聊聊")
    assert decision.route == AgentRoute.CLARIFY
    assert decision.confidence == 0.3

    model.client.chat.completions.create = AsyncMock(
        return_value=_completion(
            json.dumps({"route": "recommend", "confidence": 0.9, "reason": ""})
        )
    )
    decision = await model.classify_route("随便聊聊")
    assert decision.route == AgentRoute.CLARIFY


@pytest.mark.asyncio
async def test_classify_route_degrades_on_invalid_json_or_api_error() -> None:
    model = make_model()
    model.client.chat.completions.create = AsyncMock(
        return_value=_completion("not json")
    )
    decision = await model.classify_route("来一杯拿铁")
    assert decision.route == AgentRoute.CLARIFY
    assert decision.confidence == 0.0

    model.client.chat.completions.create = AsyncMock(side_effect=OpenAIError("boom"))
    decision = await model.classify_route("来一杯拿铁")
    assert decision.route == AgentRoute.CLARIFY
    assert decision.confidence == 0.0


@pytest.mark.asyncio
async def test_stream_reply_yields_streamed_tokens() -> None:
    model = make_model()

    async def fake_stream():
        for text in ("你好", "，", "想喝什么"):
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

    model.client.chat.completions.create = AsyncMock(return_value=fake_stream())

    chunks = [
        chunk
        async for chunk in model.stream_reply(
            message="hi", menu=[], evidence=[], history=[]
        )
    ]

    assert "".join(chunks) == "你好，想喝什么"
