from fastapi.testclient import TestClient

from app.main import app


def test_webhook_is_unavailable_without_bot_token() -> None:
    with TestClient(app) as client:
        response = client.post("/telegram/webhook", json={})
    assert response.status_code == 503
