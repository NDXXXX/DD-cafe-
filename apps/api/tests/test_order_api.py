from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def create_client() -> TestClient:
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            qdrant_url=":memory:",
            redis_checkpoints=False,
        )
    )
    return TestClient(app)


def test_menu_and_order_flow_rejects_client_price() -> None:
    with create_client() as client:
        menu_response = client.get("/api/menu")
        assert menu_response.status_code == 200
        assert len(menu_response.json()) == 6

        rejected = client.post(
            "/api/cart/demo-session/items",
            headers={"Idempotency-Key": "reject-client-price-001"},
            json={
                "table_number": "A12",
                "menu_item_id": "dd-latte",
                "quantity": 1,
                "temperature": "热",
                "price_cents": 1,
            },
        )
        assert rejected.status_code == 422

        missing_idempotency_key = client.post(
            "/api/cart/demo-session/items",
            json={
                "table_number": "A12",
                "menu_item_id": "dd-latte",
                "quantity": 1,
                "temperature": "热",
            },
        )
        assert missing_idempotency_key.status_code == 422

        cart_response = client.post(
            "/api/cart/demo-session/items",
            headers={"Idempotency-Key": "add-demo-latte-001"},
            json={
                "table_number": "A12",
                "menu_item_id": "dd-latte",
                "quantity": 1,
                "temperature": "热",
            },
        )
        assert cart_response.status_code == 200
        assert cart_response.json()["total_cents"] == 3200

        repeated = client.post(
            "/api/cart/demo-session/items",
            headers={"Idempotency-Key": "add-demo-latte-001"},
            json={
                "table_number": "A12",
                "menu_item_id": "dd-latte",
                "quantity": 1,
                "temperature": "热",
            },
        )
        assert repeated.status_code == 200
        assert repeated.json()["total_quantity"] == 1

        order_response = client.post(
            "/api/orders",
            json={"session_id": "demo-session", "idempotency_key": "submit-demo-001"},
        )
        assert order_response.status_code == 201
        assert order_response.json()["total_cents"] == 3200
