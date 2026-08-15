from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(admin_api_key: str | None = None) -> TestClient:
    settings = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        qdrant_url=":memory:",
        redis_checkpoints=False,
        admin_api_key=admin_api_key,
    )
    return TestClient(create_app(settings))


def _add_item_headers(idempotency_key: str, token: str | None = None) -> dict[str, str]:
    headers = {"Idempotency-Key": idempotency_key}
    if token is not None:
        headers["X-Session-Token"] = token
    return headers


def _add_item_body() -> dict[str, object]:
    return {
        "table_number": "A12",
        "menu_item_id": "dd-latte",
        "quantity": 1,
        "temperature": "热",
    }


def test_cart_write_requires_session_token() -> None:
    with make_client() as client:
        response = client.post(
            "/api/cart/guest-1/items",
            headers=_add_item_headers("auth-test-001"),
            json=_add_item_body(),
        )
        assert response.status_code == 401


def test_cart_write_rejects_wrong_session_token() -> None:
    with make_client() as client:
        client.post("/api/sessions", json={"session_id": "guest-1"})
        response = client.post(
            "/api/cart/guest-1/items",
            headers=_add_item_headers("auth-test-002", token="wrong-token"),
            json=_add_item_body(),
        )
        assert response.status_code == 403


def test_knowledge_write_fail_closed_when_admin_key_unset() -> None:
    with make_client() as client:
        response = client.post(
            "/api/knowledge",
            json={"title": "x", "content": "y", "source_type": "guide"},
        )
        assert response.status_code == 403


def test_knowledge_write_requires_admin_key() -> None:
    with make_client(admin_api_key="secret") as client:
        response = client.post(
            "/api/knowledge",
            json={"title": "x", "content": "y", "source_type": "guide"},
        )
        assert response.status_code == 403


def test_knowledge_write_with_admin_key_passes_auth() -> None:
    with make_client(admin_api_key="secret") as client:
        response = client.delete(
            "/api/knowledge/nonexistent",
            headers={"X-Admin-Key": "secret"},
        )
        assert response.status_code == 404
