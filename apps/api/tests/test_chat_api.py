import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_chat_sse_stream_emits_cart_tokens_and_done() -> None:
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            qdrant_url=":memory:",
            redis_checkpoints=False,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/stream",
            json={
                "session_id": "chat-guest",
                "table_number": "A12",
                "request_id": "chat-request-001",
                "message": "来一杯拿铁",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    current_type = ""
    for line in response.text.splitlines():
        if line.startswith("event: "):
            current_type = line.removeprefix("event: ")
        if line.startswith("data: "):
            events.append((current_type, json.loads(line.removeprefix("data: "))))

    assert any(event_type == "cart" for event_type, _ in events)
    assert any(event_type == "token" for event_type, _ in events)
    assert events[-1][0] == "done"
