import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MenuItemModel, OrderItemModel, OrderModel
from app.orders.errors import OrderConflict, OrderValidationError
from app.orders.service import OrderService


def add_menu(session: Session) -> None:
    session.add_all(
        [
            MenuItemModel(
                id="latte",
                name="拿铁",
                description="浓缩咖啡与牛奶",
                category="咖啡",
                price_cents=3200,
                temperatures=["热", "冰"],
                tags=["奶咖"],
                aliases=["拿铁"],
                image_key="latte",
                available=True,
            ),
            MenuItemModel(
                id="americano",
                name="美式咖啡",
                description="清爽黑咖啡",
                category="咖啡",
                price_cents=2600,
                temperatures=["热", "冰"],
                tags=["无奶"],
                aliases=["美式"],
                image_key="americano",
                available=True,
            ),
        ]
    )
    session.commit()


def test_cart_uses_catalog_price_and_validates_temperature(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)

    cart = service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=1,
        temperature="热",
        idempotency_key="add-latte-001",
    )

    assert cart.total_cents == 3200
    assert cart.items[0].unit_price_cents == 3200
    with pytest.raises(OrderValidationError, match="温度"):
        service.add_item(
            "guest-1",
            "A12",
            "latte",
            quantity=1,
            temperature="常温",
            idempotency_key="add-latte-invalid-001",
        )


def test_add_item_refreshes_a_previously_loaded_empty_cart(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    empty_cart = service.get_cart("guest-1", "A12")

    updated_cart = service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=1,
        temperature="热",
        idempotency_key="add-latte-after-load-001",
    )

    assert empty_cart.items == []
    assert updated_cart.total_quantity == 1
    assert updated_cart.total_cents == 3200


def test_session_cannot_silently_change_table(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=1,
        temperature="热",
        idempotency_key="add-table-a12-001",
    )

    with pytest.raises(OrderConflict, match="桌号"):
        service.add_item(
            "guest-1",
            "B03",
            "americano",
            quantity=1,
            temperature="冰",
            idempotency_key="add-table-b03-001",
        )


def test_cart_mutations_are_durable_and_idempotent(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)

    first = service.add_item(
        "guest-1",
        "A12",
        "americano",
        quantity=1,
        temperature="冰",
        idempotency_key="add-americano-001",
    )
    repeated = service.add_item(
        "guest-1",
        "A12",
        "americano",
        quantity=1,
        temperature="冰",
        idempotency_key="add-americano-001",
    )
    assert first == repeated
    assert repeated.total_quantity == 1

    line_id = repeated.items[0].id
    changed = service.change_item(
        "guest-1",
        line_id,
        quantity=2,
        temperature="冰",
        idempotency_key="change-americano-001",
    )
    changed_again = service.change_item(
        "guest-1",
        line_id,
        quantity=2,
        temperature="冰",
        idempotency_key="change-americano-001",
    )
    assert changed == changed_again
    assert changed_again.total_quantity == 2

    removed = service.remove_item(
        "guest-1", line_id, idempotency_key="remove-americano-001"
    )
    removed_again = service.remove_item(
        "guest-1", line_id, idempotency_key="remove-americano-001"
    )
    assert removed == removed_again
    assert removed_again.items == []


def test_reused_idempotency_key_with_different_command_is_rejected(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    service.add_item(
        "guest-1",
        "A12",
        "americano",
        quantity=1,
        temperature="冰",
        idempotency_key="same-key-001",
    )

    with pytest.raises(OrderConflict, match="幂等键"):
        service.add_item(
            "guest-1",
            "A12",
            "latte",
            quantity=1,
            temperature="热",
            idempotency_key="same-key-001",
        )


def test_submit_is_idempotent_and_snapshots_price(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=2,
        temperature="冰",
        idempotency_key="add-before-submit-001",
    )

    first = service.submit("guest-1", "submit-001")
    second = service.submit("guest-1", "submit-001")

    assert first.id == second.id
    assert first.total_cents == 6400
    assert len(session.scalars(select(OrderModel)).all()) == 1
    order_item = session.scalar(select(OrderItemModel))
    assert order_item is not None
    assert order_item.name == "拿铁"
    assert order_item.unit_price_cents == 3200


def test_later_addition_creates_addendum_without_mutating_original(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=1,
        temperature="热",
        idempotency_key="add-original-001",
    )
    original = service.submit("guest-1", "submit-original")

    service.add_item(
        "guest-1",
        "A12",
        "americano",
        quantity=1,
        temperature="冰",
        idempotency_key="add-addendum-001",
    )
    addendum = service.submit("guest-1", "submit-addendum", parent_order_id=original.id)

    original_again = service.get_order(original.id, "guest-1")
    assert original_again.total_cents == 3200
    assert [item.menu_item_id for item in original_again.items] == ["latte"]
    assert addendum.parent_order_id == original.id
    assert [item.menu_item_id for item in addendum.items] == ["americano"]


def test_cancellation_creates_pending_request(session: Session) -> None:
    add_menu(session)
    service = OrderService(session)
    service.add_item(
        "guest-1",
        "A12",
        "latte",
        quantity=1,
        temperature="热",
        idempotency_key="add-before-cancel-001",
    )
    order = service.submit("guest-1", "submit-001")

    request = service.request_cancellation(order.id, "guest-1", "顾客点错了")
    order_after = service.get_order(order.id, "guest-1")

    assert request.status == "pending"
    assert order_after.status == "submitted"
    with pytest.raises(OrderValidationError):
        service.request_cancellation(order.id, "guest-2", "不是我的订单")
