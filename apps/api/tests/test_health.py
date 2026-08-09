from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health() -> None:
    app = create_app(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            qdrant_url=":memory:",
            redis_checkpoints=False,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
