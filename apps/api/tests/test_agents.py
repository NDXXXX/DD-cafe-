from collections.abc import Iterable

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.graph import AgentRuntime
from app.agents.model import DemoRecommendationModel
from app.agents.order_agent import ConstrainedOrderAgent
from app.agents.router import AgentRoute, route_intent
from app.db.base import Base
from app.db.session import Database
from app.orders.service import OrderService
from app.rag.schemas import RetrievedDocument
from app.seed import seed_menu_if_empty


class FakeKnowledgeIndex:
    def upsert(self, document_id: str, title: str, content: str, source_type: str) -> None:
        pass

    def delete(self, document_id: str) -> None:
        pass

    def rebuild(self, documents: Iterable[tuple[str, str, str, str]]) -> None:
        pass

    def search(self, query: str, limit: int = 5) -> list[RetrievedDocument]:
        if "纸巾" not in query:
            return []
        return [
            RetrievedDocument(
                chunk_id="tissues:0",
                document_id="tissues",
                title="纸巾位置",
                source_type="guide",
                evidence="纸巾在桌下收纳篮里",
                retrieval_score=1.0,
                rerank_score=1.2,
            )
        ]


@pytest.fixture
def runtime() -> tuple[AgentRuntime, Database]:
    database = Database("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        seed_menu_if_empty(session)
    agent = AgentRuntime(
        session_factory=database.session_factory,
        rag_index=FakeKnowledgeIndex(),
        checkpointer=InMemorySaver(),
        recommendation_model=DemoRecommendationModel(),
    )
    yield agent, database
    database.close()


def test_router_separates_recommendation_and_order_writes() -> None:
    assert route_intent("不知道喝什么，推荐一下") == AgentRoute.RECOMMEND
    assert route_intent("纸巾在哪里") == AgentRoute.RECOMMEND
    assert route_intent("来一杯拿铁") == AgentRoute.ORDER
    assert route_intent("推荐一杯不甜的并帮我加入购物车") == AgentRoute.RECOMMEND_THEN_ORDER
    assert route_intent("帮我加点东西") == AgentRoute.CLARIFY


@pytest.mark.asyncio
async def test_agent_events_include_route_reason_and_request_id(runtime) -> None:
    agent, _ = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-event-contract",
            table_number="A12",
            request_id="request-event-contract-001",
            message="纸巾在哪里？",
        )
    ]

    routed = next(event for event in events if event.get("stage") == "routing")
    verified = next(event for event in events if event["type"] == "verification")
    assert routed["route"] == AgentRoute.RECOMMEND
    assert routed["confidence"] > 0
    assert routed["reason"]
    assert verified["passed"] is True
    assert all(event["request_id"] == "request-event-contract-001" for event in events)


@pytest.mark.asyncio
async def test_recommendation_handoff_is_explicit_before_cart_write(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-recommend-and-order",
            table_number="A12",
            request_id="request-recommend-and-order-001",
            message="推荐一杯不甜的并帮我加入购物车",
        )
    ]

    handoff = next(event for event in events if event["type"] == "handoff")
    assert handoff["from_agent"] == "recommendation"
    assert handoff["to_agent"] == "ordering"
    assert handoff["menu_item_id"]
    assert handoff["user_authorized_write"] is True
    assert any(event["type"] == "cart" for event in events)
    with database.session_factory() as session:
        assert OrderService(session).get_cart(
            "guest-recommend-and-order", "A12"
        ).total_quantity == 1


@pytest.mark.asyncio
async def test_order_agent_adds_validated_item_and_emits_cart(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-1",
            table_number="A12",
            request_id="request-add-001",
            message="来一杯桂花燕麦拿铁",
        )
    ]

    cart_event = next(event for event in events if event["type"] == "cart")
    assert cart_event["cart"]["total_cents"] == 3600
    assert cart_event["cart"]["items"][0]["temperature"] == "热"
    with database.session_factory() as session:
        cart = OrderService(session).get_cart("guest-1", "A12")
        assert cart.total_quantity == 1


@pytest.mark.asyncio
async def test_ambiguous_latte_clarifies_without_cart_write(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-ambiguous-latte",
            table_number="A12",
            request_id="request-ambiguous-latte-001",
            message="来一杯拿铁",
        )
    ]

    response = "".join(event["text"] for event in events if event["type"] == "token")
    assert not any(event["type"] == "cart" for event in events)
    assert "有好几款" in response
    assert "DD 拿铁" in response
    assert "桂花燕麦拿铁" in response
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-ambiguous-latte") is None


@pytest.mark.asyncio
async def test_explicit_iced_americano_is_preserved_exactly(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-iced-americano",
            table_number="A12",
            request_id="request-iced-americano-001",
            message="你好我要一杯冰美式",
        )
    ]

    cart_event = next(event for event in events if event["type"] == "cart")
    line = cart_event["cart"]["items"][0]
    response = "".join(event["text"] for event in events if event["type"] == "token")
    assert line["name"] == "美式"
    assert line["temperature"] == "冰"
    assert "冰美式" in response
    assert "热" not in response
    with database.session_factory() as session:
        cart = OrderService(session).get_cart("guest-iced-americano", "A12")
        assert [(item.name, item.temperature) for item in cart.items] == [("美式", "冰")]


def test_explicit_product_overrides_recommendation_handoff(runtime) -> None:
    _, database = runtime

    with database.session_factory() as session:
        result = ConstrainedOrderAgent(session).execute(
            message="我要一杯冰美式",
            session_id="guest-explicit-over-handoff",
            table_number="A12",
            request_id="request-explicit-over-handoff-001",
            suggested_menu_item_id="dd-latte",
        )

        assert result.cart is not None
        assert [
            (item.menu_item_id, item.name, item.temperature, item.quantity)
            for item in result.cart.items
        ] == [("sea-salt-americano", "美式", "冰", 1)]


@pytest.mark.asyncio
async def test_retried_chat_request_does_not_add_the_same_item_twice(runtime) -> None:
    agent, database = runtime

    for _ in range(2):
        events = [
            event
            async for event in agent.stream(
                session_id="guest-retried-add",
                table_number="A12",
                request_id="request-retried-add-001",
                message="来一杯冰美式",
            )
        ]
        cart_event = next(event for event in events if event["type"] == "cart")
        assert cart_event["cart"]["total_quantity"] == 1

    with database.session_factory() as session:
        cart = OrderService(session).get_cart("guest-retried-add", "A12")
        assert [(item.name, item.temperature, item.quantity) for item in cart.items] == [
            ("美式", "冰", 1)
        ]


@pytest.mark.asyncio
async def test_unsupported_temperature_does_not_mutate_cart(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-invalid-temperature",
            table_number="A12",
            request_id="request-invalid-temperature-001",
            message="来一杯热抹茶云顶",
        )
    ]

    response = "".join(event["text"] for event in events if event["type"] == "token")
    assert not any(event["type"] == "cart" for event in events)
    assert "不支持" in response
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-invalid-temperature") is None


@pytest.mark.asyncio
async def test_multiple_products_fail_closed_without_cart_write(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-multiple-products",
            table_number="A12",
            request_id="request-multiple-products-001",
            message="来一杯拿铁和一杯冰美式",
        )
    ]

    response = "".join(event["text"] for event in events if event["type"] == "token")
    assert not any(event["type"] == "cart" for event in events)
    assert "一次只确认一个商品" in response
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-multiple-products") is None


@pytest.mark.asyncio
async def test_recommendation_agent_is_read_only_and_answers_restaurant_question(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-2",
            table_number="B03",
            request_id="request-question-001",
            message="纸巾在哪里？",
        )
    ]

    text = "".join(event["text"] for event in events if event["type"] == "token")
    assert "桌下收纳篮" in text
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-2") is None


@pytest.mark.asyncio
async def test_restaurant_question_without_evidence_fails_closed(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-no-evidence",
            table_number="B03",
            request_id="request-no-evidence-001",
            message="停车场在哪里？",
        )
    ]

    text = "".join(event["text"] for event in events if event["type"] == "token")
    assert "知识库里暂时没有" in text
    assert "询问店员" in text
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-no-evidence") is None


@pytest.mark.asyncio
async def test_ambiguous_order_request_does_not_mutate_cart(runtime) -> None:
    agent, database = runtime

    events = [
        event
        async for event in agent.stream(
            session_id="guest-3",
            table_number="C08",
            request_id="request-ambiguous-001",
            message="帮我加点东西",
        )
    ]

    text = "".join(event["text"] for event in events if event["type"] == "token")
    assert "具体商品" in text
    with database.session_factory() as session:
        assert OrderService(session)._find_cart("guest-3") is None


@pytest.mark.asyncio
async def test_multi_item_remove_clears_all_matching_lines(runtime) -> None:
    agent, database = runtime

    with database.session_factory() as session:
        service = OrderService(session)
        service.add_item(
            "guest-remove-multi",
            "A12",
            "sea-salt-americano",
            quantity=1,
            temperature="冰",
            idempotency_key="rm-add-americano",
        )
        service.add_item(
            "guest-remove-multi",
            "A12",
            "basque-cheesecake",
            quantity=1,
            temperature="常温",
            idempotency_key="rm-add-cake",
        )

    events = [
        event
        async for event in agent.stream(
            session_id="guest-remove-multi",
            table_number="A12",
            request_id="rm-request-001",
            message="删掉美式和巴斯克",
        )
    ]

    cart_event = next(event for event in events if event["type"] == "cart")
    assert cart_event["cart"]["items"] == []
    with database.session_factory() as session:
        assert (
            OrderService(session).get_cart("guest-remove-multi", "A12").total_quantity == 0
        )
