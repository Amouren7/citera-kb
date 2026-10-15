"""管理端：统计、用户、设置、重灌种子、权限。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class TestPermissions:
    def test_non_admin_forbidden(self, client: TestClient, demo_headers: dict) -> None:
        for path in (
            "/api/v1/admin/stats",
            "/api/v1/admin/users",
            "/api/v1/admin/settings",
        ):
            resp = client.get(path, headers=demo_headers)
            assert resp.status_code == 403, path
            assert resp.json()["error"]["code"] == "forbidden"

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/admin/stats").status_code == 401

    def test_admin_can_read(self, client: TestClient, admin_headers: dict) -> None:
        assert client.get("/api/v1/admin/stats", headers=admin_headers).status_code == 200


class TestStats:
    def test_stats_shape_and_values(self, client: TestClient, admin_headers: dict) -> None:
        body = client.get("/api/v1/admin/stats", headers=admin_headers).json()
        assert set(body) == {
            "users",
            "documents",
            "chunks",
            "conversations",
            "messages",
            "eval_runs",
            "recent_7d",
        }
        assert body["users"] >= 2
        assert body["documents"] >= 6
        assert body["chunks"] >= 20
        assert set(body["recent_7d"]) == {"documents", "messages"}


class TestUsers:
    def test_list_pagination(self, client: TestClient, admin_headers: dict) -> None:
        body = client.get(
            "/api/v1/admin/users", headers=admin_headers, params={"page_size": 1}
        ).json()
        assert len(body["items"]) == 1
        assert body["total"] >= 2

    def test_toggle_active(self, client: TestClient, admin_headers: dict) -> None:
        email = f"toggle-{uuid.uuid4().hex[:8]}@example.com"
        created = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "abcd1234", "display_name": "待切换"},
        ).json()
        user_id = created["user"]["id"]
        resp = client.patch(
            f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": False}
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_promote_to_admin(self, client: TestClient, admin_headers: dict) -> None:
        email = f"promote-{uuid.uuid4().hex[:8]}@example.com"
        created = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "abcd1234", "display_name": "晋升"},
        ).json()
        user_id = created["user"]["id"]
        resp = client.patch(
            f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"role": "admin"}
        )
        assert resp.json()["role"] == "admin"
        # 新管理员应当能访问管理接口
        token = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "abcd1234"}
        ).json()["access_token"]
        assert (
            client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {token}"}).status_code
            == 200
        )
        # 清理：降回普通用户
        client.patch(f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"role": "user"})

    def test_cannot_demote_self(self, client: TestClient, admin_headers: dict) -> None:
        me = client.get("/api/v1/auth/me", headers=admin_headers).json()["user"]
        resp = client.patch(
            f"/api/v1/admin/users/{me['id']}", headers=admin_headers, json={"role": "user"}
        )
        assert resp.status_code == 400

    def test_cannot_deactivate_self(self, client: TestClient, admin_headers: dict) -> None:
        me = client.get("/api/v1/auth/me", headers=admin_headers).json()["user"]
        resp = client.patch(
            f"/api/v1/admin/users/{me['id']}", headers=admin_headers, json={"is_active": False}
        )
        assert resp.status_code == 400

    def test_missing_user(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.patch(
            "/api/v1/admin/users/999999", headers=admin_headers, json={"is_active": False}
        )
        assert resp.status_code == 404


class TestSettings:
    def test_defaults_present(self, client: TestClient, admin_headers: dict) -> None:
        body = client.get("/api/v1/admin/settings", headers=admin_headers).json()
        assert body["settings"]["retrieval_mode"] == "hybrid"
        assert body["settings"]["top_k"] == 5
        assert body["settings"]["registration_open"] is True

    def test_update_and_persist(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"top_k": 8, "retrieval_mode": "vector"}},
        )
        assert resp.status_code == 200
        body = client.get("/api/v1/admin/settings", headers=admin_headers).json()
        assert body["settings"]["top_k"] == 8
        assert body["settings"]["retrieval_mode"] == "vector"
        # 还原
        client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"top_k": 5, "retrieval_mode": "hybrid"}},
        )

    def test_unknown_key_rejected(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"jwt_secret": "hack"}},
        )
        assert resp.status_code == 400

    def test_invalid_mode_rejected(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"retrieval_mode": "magic"}},
        )
        assert resp.status_code == 400

    def test_invalid_chunk_params_rejected(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"chunk_size": 100, "chunk_overlap": 200}},
        )
        assert resp.status_code == 400

    def test_non_integer_rejected(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/v1/admin/settings",
            headers=admin_headers,
            json={"settings": {"top_k": "many"}},
        )
        assert resp.status_code == 400


class TestReseed:
    def test_reseed_is_idempotent(self, client: TestClient, admin_headers: dict) -> None:
        first = client.post("/api/v1/admin/reseed", headers=admin_headers)
        assert first.status_code == 200
        assert first.json()["ok"] is True
        second = client.post("/api/v1/admin/reseed", headers=admin_headers)
        assert second.status_code == 200
        # 第二次不应再新建文档或重建向量
        assert second.json()["documents_created"] == 0
        assert second.json()["documents_rebuilt"] == 0
        assert second.json()["eval_items"] >= 20

    def test_reseed_requires_admin(self, client: TestClient, demo_headers: dict) -> None:
        assert client.post("/api/v1/admin/reseed", headers=demo_headers).status_code == 403
