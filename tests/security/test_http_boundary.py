"""HTTP trust boundary checks using an actual ASGI application."""
import pytest
from fastapi.testclient import TestClient

from agentsync.integrations.http import create_app


def test_http_bearer_is_required_and_health_has_no_private_state(tmp_path):
    app = create_app(data_dir=tmp_path / "db", api_token="test-http-token")
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 15000)) as client:
        assert set(client.get("/health").json()) == {"status", "version"}
        payload = {"name": "HTTP", "root_path": str(tmp_path)}
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            response = client.post("/v1/create_project", json=payload, headers=headers)
            assert response.status_code == 401
            assert response.json()["ok"] is False
        response = client.post("/v1/create_project", json=payload,
                               headers={"Authorization": "Bearer test-http-token"})
        assert response.status_code == 200 and response.json()["ok"] is True


@pytest.mark.parametrize("remote,base_url", [
    ("192.0.2.10", "http://127.0.0.1"),
    ("127.0.0.1", "http://attacker.example"),
])
def test_remote_clients_and_foreign_host_headers_are_rejected(tmp_path, remote, base_url):
    app = create_app(data_dir=tmp_path / "db", api_token="test-http-token")
    with TestClient(app, base_url=base_url, client=(remote, 15000)) as client:
        response = client.get("/health")
        assert response.status_code in {400, 403}


def test_no_cors_grant_and_malformed_requests_do_not_execute(tmp_path):
    app = create_app(data_dir=tmp_path / "db", api_token="test-http-token")
    headers = {"Authorization": "Bearer test-http-token", "Origin": "https://attacker.example"}
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 15000)) as client:
        for body in ("not-json", "[]", "null"):
            response = client.post("/v1/create_project", content=body, headers=headers)
            assert response.status_code == 400
            assert response.json()["ok"] is False
            assert "access-control-allow-origin" not in response.headers
        response = client.post("/v1/__getattribute__", json={}, headers=headers)
        assert response.status_code >= 400
        assert response.json()["ok"] is False


def test_http_missing_token_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTSYNC_HTTP_TOKEN", raising=False)
    with pytest.raises(ValueError):
        create_app(data_dir=tmp_path / "db")
