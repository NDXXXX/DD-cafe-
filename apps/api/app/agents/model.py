import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from openai import AsyncOpenAI, OpenAIError

from app.agents.memory import AGENT_RULES
from app.agents.router import AgentRoute, RouteDecision
from app.agents.state import ImageAttachment
from app.agents.vision import encode_image_data_url
from app.catalog.schemas import MenuItemView
from app.rag.schemas import RetrievedDocument


def _system_prompt(
    menu: Sequence[MenuItemView],
    evidence: Sequence[RetrievedDocument],
) -> str:
    menu_context = "\n".join(
        f"- {item.name}，{item.price_cents / 100:.0f}元，{item.description}，标签：{'、'.join(item.tags)}"
        for item in menu
    )
    evidence_context = "\n".join(
        f"- {item.title}：{item.evidence}" for item in evidence
    ) or "无相关餐厅知识"
    rules_context = "\n".join(f"- {rule}" for rule in AGENT_RULES)
    return (
        "你是DD咖啡馆的推荐助手。语气温暖、简洁，先理解偏好再推荐。"
        "只能依据提供的菜单与餐厅知识回答，不得编造价格、库存或店内设施。"
        "你没有修改购物车或订单的权限。涉及严重过敏时必须提醒顾客向店员确认。\n\n"
        f"运行规则：\n{rules_context}\n\n"
        f"菜单：\n{menu_context}\n\n餐厅知识：\n{evidence_context}"
    )


class RecommendationModel(Protocol):
    async def classify_route(self, message: str) -> RouteDecision: ...

    async def rewrite_query(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
    ) -> str: ...

    async def stream_reply(
        self,
        message: str,
        menu: Sequence[MenuItemView],
        evidence: Sequence[RetrievedDocument],
        history: Sequence[tuple[str, str]],
        images: list[ImageAttachment] | None = None,
    ) -> AsyncIterator[str]: ...


class DemoRecommendationModel:
    async def classify_route(self, message: str) -> RouteDecision:
        del message
        return RouteDecision(
            route=AgentRoute.RECOMMEND,
            confidence=0.7,
            reason="演示模型将未识别对话作为只读问答处理",
        )

    async def rewrite_query(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
    ) -> str:
        del history
        return query

    async def stream_reply(
        self,
        message: str,
        menu: Sequence[MenuItemView],
        evidence: Sequence[RetrievedDocument],
        history: Sequence[tuple[str, str]],
        images: list[ImageAttachment] | None = None,
    ) -> AsyncIterator[str]:
        del history, images
        if evidence:
            reply = f"{evidence[0].evidence} 如果现场情况有变化，也可以直接问店员。"
        else:
            names = "、".join(item.name for item in menu[:2])
            reply = f"如果你还没想好，我会先推荐 {names}。告诉我你偏好清爽、奶香还是低甜，我可以继续缩小选择。"
        for index in range(0, len(reply), 5):
            yield reply[index : index + 5]


class DeepSeekRecommendationModel:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def classify_route(self, message: str) -> RouteDecision:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是DD咖啡馆的路由器。只输出JSON，包含route、confidence、reason。"
                            "route只能是recommend、order、recommend_then_order、clarify。"
                            "明确修改购物车或订单选order；推荐或餐厅问答选recommend；"
                            "同时推荐并要求加入购物车选recommend_then_order；"
                            "想写入但商品不明确选clarify。"
                        ),
                    },
                    {"role": "user", "content": message},
                ],
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            route = AgentRoute(str(payload.get("route", "")))
            confidence = max(0.0, min(float(payload.get("confidence", 0.0)), 1.0))
            reason = str(payload.get("reason", "")).strip()
            if confidence < 0.65 or not reason:
                return RouteDecision(
                    route=AgentRoute.CLARIFY,
                    confidence=confidence,
                    reason=reason or "模型路由缺少可验证理由",
                )
            return RouteDecision(route=route, confidence=confidence, reason=reason)
        except (OpenAIError, AttributeError, ValueError, TypeError):
            return RouteDecision(
                route=AgentRoute.CLARIFY,
                confidence=0.0,
                reason="模型路由结果无法验证",
            )

    async def rewrite_query(
        self,
        query: str,
        history: Sequence[tuple[str, str]],
    ) -> str:
        history_context = "\n".join(
            f"{role}: {content}" for role, content in history[-4:]
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "根据最近对话把用户问题改写为一句可独立检索的中文问题。"
                        "不得增加对话中没有的商品、条件或事实，只输出改写后的问题。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"最近对话：\n{history_context}\n\n当前问题：{query}",
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()

    async def stream_reply(
        self,
        message: str,
        menu: Sequence[MenuItemView],
        evidence: Sequence[RetrievedDocument],
        history: Sequence[tuple[str, str]],
        images: list[ImageAttachment] | None = None,
    ) -> AsyncIterator[str]:
        del images
        messages = [{"role": "system", "content": _system_prompt(menu, evidence)}]
        messages.extend(
            {"role": role, "content": content}
            for role, content in history[-6:]
            if role in {"user", "assistant"}
        )
        messages.append({"role": "user", "content": message})
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text


class QwenVLRecommendationModel:
    """Multimodal reply model: same cafe persona, but sees image content blocks."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def stream_reply(
        self,
        message: str,
        menu: Sequence[MenuItemView],
        evidence: Sequence[RetrievedDocument],
        history: Sequence[tuple[str, str]],
        images: list[ImageAttachment] | None = None,
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": _system_prompt(menu, evidence)}]
        messages.extend(
            {"role": role, "content": content}
            for role, content in history[-6:]
            if role in {"user", "assistant"}
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": message}]
        for image in images or []:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_image_data_url(image["local_path"]),
                        "detail": "auto",
                    },
                }
            )
        messages.append({"role": "user", "content": content})
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                yield text
