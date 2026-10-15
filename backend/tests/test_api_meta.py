"""健康检查、元信息、统一错误格式。"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealth:
    def test_health_ok(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["version"] == "0.1.0"
        assert body["llm_provider"] in {"echo", "openai"}

    def test_health_needs_no_auth(self, client: TestClient) -> None:
        assert client.get("/api/health").status_code == 200

    def test_meta_shape(self, client: TestClient) -> None:
        resp = client.get("/api/v1/meta")
        assert resp.status_code == 200
        body = resp.json()
        assert body["app_name"]
        assert set(body["limits"]) == {"max_upload_mb", "max_documents", "max_conversations"}
        assert isinstance(body["registration_open"], bool)

    def test_openapi_docs_available(self, client: TestClient) -> None:
        assert client.get("/api/openapi.json").status_code == 200
        assert client.get("/api/docs").status_code == 200

    def test_request_id_header_present(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.headers.get("X-Request-ID")
        assert float(resp.headers["X-Process-Time-Ms"]) >= 0


class TestErrorFormat:
    def test_unknown_route_uses_error_envelope(self, client: TestClient) -> None:
        body = client.get("/api/v1/definitely-not-here").json()
        assert set(body) == {"error"}
        assert set(body["error"]) == {"code", "message", "details", "request_id"}
        assert body["error"]["code"] == "not_found"

    def test_request_id_matches_header(self, client: TestClient) -> None:
        resp = client.get("/api/v1/definitely-not-here")
        assert resp.json()["error"]["request_id"] == resp.headers["X-Request-ID"]

    def test_validation_error_uses_bad_request(self, client: TestClient) -> None:
        resp = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "bad_request"
        assert isinstance(body["error"]["details"], list)
        assert body["error"]["details"][0]["field"]

    def test_method_not_allowed(self, client: TestClient) -> None:
        resp = client.delete("/api/health")
        assert resp.status_code == 405
        assert resp.json()["error"]["code"] == "method_not_allowed"
