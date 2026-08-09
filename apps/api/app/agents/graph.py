import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.events import emit_event
from app.agents.memory import recent_history
from app.agents.model import RecommendationModel
from app.agents.order_agent import ConstrainedOrderAgent
from app.agents.router import AgentRoute, requires_restaurant_evidence, route_by_rules
from app.agents.state import AgentState, RecommendationHandoff
from app.agents.verification import verify_order_execution, verify_recommendation
from app.agents.web_search import WebSearchTool
from app.catalog.service import CatalogService
from app.rag.pipeline import RagPipeline
from app.rag.schemas import RetrievedDocument
from app.rag.service import KnowledgeIndex, KnowledgeService


class AgentRuntime:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        rag_index: KnowledgeIndex,
        checkpointer: BaseCheckpointSaver,
        recommendation_model: RecommendationModel,
        web_search: WebSearchTool | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.rag_index = rag_index
        self.recommendation_model = recommendation_model
        self.web_search = web_search
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
    ) -> AsyncIterator[dict[str, Any]]:
        inputs: AgentState = {
            "messages": [HumanMessage(content=message)],
            "session_id": session_id,
            "table_number": table_number,
            "request_id": request_id,
            "raw_user_message": message,
            "route": "",
            "route_confidence": 0.0,
            "route_reason": "",
            "response": "",
            "evidence": [],
            "handoff": None,
            "verification": {},
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
            web_results = await asyncio.to_thread(self.web_search.search, message, 3)
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
        suggested = self._pick_suggestion(message, menu)
        response_parts: list[str] = []
        if not evidence and requires_restaurant_evidence(message):
            fallback = "知识库里暂时没有这个信息。为了避免说错，请直接询问店员。"
            for index in range(0, len(fallback), 5):
                text = fallback[index : index + 5]
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
        serialized_evidence = [item.model_dump(mode="json") for item in evidence]
        emit_event(state, "evidence", items=serialized_evidence)
        verification = verify_recommendation(
            response,
            suggested,
            {item.id for item in menu},
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
        response = "请告诉我具体商品和数量，例如“来一杯拿铁”。明确后我才能修改购物车。"
        for index in range(0, len(response), 5):
            emit_event(state, "token", text=response[index : index + 5])
        return {"messages": [AIMessage(content=response)], "response": response}

    @staticmethod
    def _next_node(state: AgentState) -> AgentRoute:
        return AgentRoute(state["route"])

    @staticmethod
    def _pick_suggestion(message: str, menu) -> str:
        if not menu:
            return ""
        if any(word in message for word in ("清爽", "无奶", "不加奶")):
            for item in menu:
                if "清爽" in item.tags or "无奶" in item.tags:
                    return item.id
        if "甜点" in message or "吃" in message:
            for item in menu:
                if item.category == "甜点":
                    return item.id
        return menu[0].id
