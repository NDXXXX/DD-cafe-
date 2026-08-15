import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.events import emit_event
from app.agents.image_edit import ImageEditModel
from app.agents.image_gen import ImageGenModel
from app.agents.memory import recent_history
from app.agents.model import QwenVLRecommendationModel, RecommendationModel
from app.agents.order_agent import ConstrainedOrderAgent
from app.agents.router import (
    AgentRoute,
    RouteDecision,
    is_card_generation_request,
    requires_restaurant_evidence,
    route_by_rules,
)
from app.agents.state import AgentState, ImageAttachment, RecommendationHandoff
from app.agents.verification import verify_order_execution, verify_recommendation
from app.agents.vision import VisionModel
from app.agents.web_search import WebSearchTool
from app.catalog.service import CatalogService
from app.rag.pipeline import RagPipeline
from app.rag.schemas import RetrievedDocument
from app.rag.service import KnowledgeIndex, KnowledgeService
from app.util.paths import safe_path

logger = logging.getLogger(__name__)


def _normalize_menu_text(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?]", "", text).lower()


def _card_caption(message: str) -> str:
    for sep in ("：", ":"):
        if sep in message:
            message = message.split(sep, 1)[1]
            break
    text = message.strip("，。.！!？? ")
    return text[:15] if text else "今日份的DD时光"


def _card_prompt(message: str) -> str:
    description = _card_caption(message)
    return (
        "一张温馨治愈的咖啡馆打卡照片：暖色系，柔和自然光，"
        f"桌面上一杯手作咖啡与甜点，氛围放松。风格参考用户描述：「{description}」"
    )


def _save_generated_image(upload_dir: str, session_id: str, image_bytes: bytes) -> str:
    session_dir = safe_path(upload_dir, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = f"gen_{uuid.uuid4().hex}.png"
    (session_dir / filename).write_bytes(image_bytes)
    return filename


class AgentRuntime:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        rag_index: KnowledgeIndex,
        checkpointer: BaseCheckpointSaver,
        recommendation_model: RecommendationModel,
        web_search: WebSearchTool | None = None,
        vision_model: VisionModel | None = None,
        multimodal_reply_model: QwenVLRecommendationModel | None = None,
        image_gen_model: ImageGenModel | None = None,
        image_edit_model: ImageEditModel | None = None,
        upload_dir: str = "data/uploads",
    ) -> None:
        self.session_factory = session_factory
        self.rag_index = rag_index
        self.recommendation_model = recommendation_model
        self.web_search = web_search
        self.vision_model = vision_model
        self.multimodal_reply_model = multimodal_reply_model
        self.image_gen_model = image_gen_model
        self.image_edit_model = image_edit_model
        self.upload_dir = upload_dir
        self.graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer: BaseCheckpointSaver):
        builder = StateGraph(AgentState)
        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("recommendation", self._recommendation_node)
        builder.add_node("ordering", self._ordering_node)
        builder.add_node("clarify", self._clarify_node)
        builder.add_edge(START, "supervisor")
        builder.add_conditional_edges(
            "supervisor",
            self._next_node,
            {
                AgentRoute.RECOMMEND: "recommendation",
                AgentRoute.ORDER: "ordering",
                AgentRoute.RECOMMEND_THEN_ORDER: "recommendation",
                AgentRoute.CLARIFY: "clarify",
            },
        )
        builder.add_conditional_edges(
            "recommendation",
            lambda state: "ordering"
            if state["route"] == AgentRoute.RECOMMEND_THEN_ORDER.value
            else END,
            {"ordering": "ordering", END: END},
        )
        builder.add_edge("ordering", END)
        builder.add_edge("clarify", END)
        return builder.compile(checkpointer=checkpointer)

    async def stream(
        self,
        session_id: str,
        table_number: str,
        request_id: str,
        message: str,
        images: list[ImageAttachment] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        images = images or []
        raw_message = message
        image_analysis = ""

        if is_card_generation_request(message) and not images and self.image_gen_model is not None:
            yield {"type": "status", "request_id": request_id, "stage": "generating_card"}
            try:
                image_bytes = await self.image_gen_model.generate_image(
                    _card_prompt(message)
                )
                filename = _save_generated_image(
                    self.upload_dir, session_id, image_bytes
                )
                yield {
                    "type": "generated_card",
                    "request_id": request_id,
                    "image_url": f"/api/images/{session_id}/{filename}",
                    "caption": _card_caption(message),
                }
                yield {
                    "type": "token",
                    "request_id": request_id,
                    "text": "打卡照片已生成，点击卡片即可保存。",
                }
            except Exception:
                logger.exception("Image generation failed")
                yield {
                    "type": "error",
                    "request_id": request_id,
                    "message": "打卡照片生成失败，请稍后重试。",
                }
            yield {"type": "done", "request_id": request_id}
            return

        caption = ""
        if images and self.vision_model is not None:
            yield {
                "type": "status",
                "request_id": request_id,
                "stage": "analyzing_image",
            }
            try:
                result = await self.vision_model.analyze_images(
                    [img["local_path"] for img in images],
                    message,
                )
                image_analysis = result["description"]
                caption = result["caption"]
            except Exception:
                logger.exception("Image analysis failed")
                image_analysis = ""

        if images and self.image_edit_model is not None:
            yield {
                "type": "status",
                "request_id": request_id,
                "stage": "editing_image",
            }
            try:
                edited = await self.image_edit_model.generate_edit(
                    images[0]["local_path"]
                )
                filename = _save_generated_image(
                    self.upload_dir, session_id, edited
                )
                yield {
                    "type": "generated_card",
                    "request_id": request_id,
                    "image_url": f"/api/images/{session_id}/{filename}",
                    "caption": caption or "今日份的DD时光",
                }
            except Exception:
                logger.exception("Image editing failed")
                if caption:
                    yield {
                        "type": "checkin_card",
                        "request_id": request_id,
                        "caption": caption,
                        "description": image_analysis,
                    }
        elif caption:
            yield {
                "type": "checkin_card",
                "request_id": request_id,
                "caption": caption,
                "description": image_analysis,
            }

        if not raw_message.strip() and image_analysis:
            raw_message = image_analysis
        elif images and not raw_message.strip():
            raw_message = f"用户上传了{len(images)}张照片。请根据照片氛围给予温暖回应。"

        inputs: AgentState = {
            "messages": [HumanMessage(content=raw_message)],
            "session_id": session_id,
            "table_number": table_number,
            "request_id": request_id,
            "raw_user_message": raw_message,
            "route": "",
            "route_confidence": 0.0,
            "route_reason": "",
            "response": "",
            "evidence": [],
            "handoff": None,
            "verification": {},
            "images": images,
        }
        config = {"configurable": {"thread_id": session_id}}
        async for part in self.graph.astream(
            inputs,
            config=config,
            stream_mode="custom",
            version="v2",
        ):
            if part["type"] == "custom":
                yield part["data"]
        yield {"type": "done", "request_id": request_id}

    async def _supervisor_node(self, state: AgentState) -> dict[str, Any]:
        decision = route_by_rules(state["raw_user_message"])
        if decision is None and state["images"]:
            decision = RouteDecision(AgentRoute.RECOMMEND, 1.0, "带图消息按推荐处理")
        if decision is None:
            decision = await self.recommendation_model.classify_route(
                state["raw_user_message"]
            )
        emit_event(
            state,
            "status",
            stage="routing",
            route=decision.route.value,
            confidence=decision.confidence,
            reason=decision.reason,
        )
        return {
            "route": decision.route.value,
            "route_confidence": decision.confidence,
            "route_reason": decision.reason,
        }

    async def _recommendation_node(self, state: AgentState) -> dict[str, Any]:
        emit_event(state, "status", stage="retrieving")
        message = state["raw_user_message"]
        history = recent_history(state["messages"][:-1])
        with self.session_factory() as session:
            menu = CatalogService(session).list_available()
            rag_result = await RagPipeline(
                KnowledgeService(session, self.rag_index),
                self.recommendation_model,
            ).run(message, history, limit=3)
            evidence = rag_result.evidence
        emit_event(
            state,
            "rag_trace",
            rewritten_query=rag_result.rewritten_query,
            timings_ms=rag_result.timings_ms,
            degraded_steps=rag_result.degraded_steps,
            no_evidence=rag_result.no_evidence,
        )
        if self.web_search is not None and self.web_search.should_search(message):
            try:
                web_results = await asyncio.to_thread(self.web_search.search, message, 3)
            except Exception:
                logger.exception("Web search failed, skipping results")
                web_results = []
            evidence.extend(
                RetrievedDocument(
                    chunk_id=result.url,
                    document_id=result.url,
                    title=result.title,
                    source_type="web",
                    evidence=result.snippet,
                    retrieval_score=0.0,
                    rerank_score=0.0,
                )
                for result in web_results
            )
        response_parts: list[str] = []
        if not evidence and requires_restaurant_evidence(message):
            fallback = "知识库里暂时没有这个信息。为了避免说错，请直接询问店员。"
            for index in range(0, len(fallback), 5):
                text = fallback[index : index + 5]
                response_parts.append(text)
                emit_event(state, "token", text=text)
        elif state["images"] and self.multimodal_reply_model is not None:
            async for text in self.multimodal_reply_model.stream_reply(
                message,
                menu,
                evidence,
                history,
                images=state["images"],
            ):
                response_parts.append(text)
                emit_event(state, "token", text=text)
        else:
            async for text in self.recommendation_model.stream_reply(
                message,
                menu,
                evidence,
                history,
            ):
                response_parts.append(text)
                emit_event(state, "token", text=text)
        response = "".join(response_parts)
        suggested = self._pick_suggestion(response, menu)
        serialized_evidence = [item.model_dump(mode="json") for item in evidence]
        emit_event(state, "evidence", items=serialized_evidence)
        verification = verify_recommendation(
            response,
            suggested,
            menu,
        )
        emit_event(state, "verification", **verification.as_event())
        if not verification.passed:
            response = "当前没有可靠的推荐结果，请告诉我你的口味或直接查看菜单。"

        handoff: RecommendationHandoff | None = None
        if state["route"] == AgentRoute.RECOMMEND_THEN_ORDER.value and suggested:
            handoff = {
                "from_agent": "recommendation",
                "to_agent": "ordering",
                "menu_item_id": suggested,
                "user_authorized_write": True,
            }
            emit_event(state, "handoff", **handoff)
        return {
            "messages": [AIMessage(content=response)],
            "response": response,
            "evidence": serialized_evidence,
            "handoff": handoff,
            "verification": verification.as_event(),
        }

    async def _ordering_node(self, state: AgentState) -> dict[str, Any]:
        emit_event(state, "status", stage="validating_order")
        message = state["raw_user_message"]
        handoff = state.get("handoff")
        suggested_menu_item_id = None
        if handoff is not None and handoff["user_authorized_write"]:
            suggested_menu_item_id = handoff["menu_item_id"]
        with self.session_factory() as session:
            result = ConstrainedOrderAgent(session).execute(
                message=message,
                session_id=state["session_id"],
                table_number=state["table_number"],
                request_id=state["request_id"],
                suggested_menu_item_id=suggested_menu_item_id,
            )
        if result.cart is not None:
            emit_event(state, "cart", cart=result.cart.model_dump(mode="json"))
        if result.order is not None:
            emit_event(state, "order", order=result.order.model_dump(mode="json"))
        if result.cancellation is not None:
            emit_event(
                state,
                "cancellation",
                cancellation=result.cancellation.model_dump(mode="json"),
            )
        verification = verify_order_execution(result)
        emit_event(state, "verification", **verification.as_event())
        for index in range(0, len(result.response), 5):
            emit_event(state, "token", text=result.response[index : index + 5])
        return {
            "messages": [AIMessage(content=result.response)],
            "response": result.response,
            "verification": verification.as_event(),
        }

    async def _clarify_node(self, state: AgentState) -> dict[str, Any]:
        response = "请告诉我具体商品和数量，例如「来一杯拿铁」。明确后我才能修改购物车。"
        for index in range(0, len(response), 5):
            emit_event(state, "token", text=response[index : index + 5])
        return {"messages": [AIMessage(content=response)], "response": response}

    @staticmethod
    def _next_node(state: AgentState) -> AgentRoute:
        return AgentRoute(state["route"])

    @staticmethod
    def _pick_suggestion(response: str, menu) -> str:
        """Return the menu item the reply actually names, or "" if none.

        Handoff must reflect what the assistant recommended, so we parse the
        generated reply for the longest menu item name/alias that appears in
        it instead of guessing from the user's message.
        """
        if not menu:
            return ""
        compact = _normalize_menu_text(response)
        best_id = ""
        best_len = 0
        for item in menu:
            for name in sorted([item.name, *item.aliases], key=len, reverse=True):
                normalized = _normalize_menu_text(name)
                if normalized and normalized in compact and len(normalized) > best_len:
                    best_id = item.id
                    best_len = len(normalized)
                    break
        return best_id


