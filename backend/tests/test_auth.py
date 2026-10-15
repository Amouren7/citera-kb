"""认证、授权与限流。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def random_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self) -> None:
        hashed = hash_password("secret123")
        assert "secret123" not in hashed
        assert hashed.startswith("scrypt$")

    def test_verify_roundtrip(self) -> None:
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed)
        assert not verify_password("secret124", hashed)

    def test_same_password_different_hashes(self) -> None:
        assert hash_password("secret123") != hash_password("secret123")

    def test_invalid_stored_value(self) -> None:
        assert not verify_password("secret123", "garbage")
        assert not verify_password("", "")

    def test_empty_password_rejected(self) -> None:
        try:
            hash_password("")
        except ValueError:
            return
        raise AssertionError("空密码应当抛错")


class TestJwt:
    def test_decode_roundtrip(self) -> None:
        token = create_access_token(42, "admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert payload["typ"] == "access"

    def test_expired_token_reports_code(self) -> None:
        from app.core.security import TokenError

        token = create_access_token(1, "user", expires_minutes=-1)
        try:
            decode_access_token(token)
        except TokenError as exc:
            assert exc.code == "token_expired"
            return
        raise AssertionError("过期 token 应当抛错")

    def test_tampered_token_reports_unauthorized(self) -> None:
        from app.core.security import TokenError

        token = create_access_token(1, "user") + "x"
        try:
            decode_access_token(token)
        except TokenError as exc:
            assert exc.code == "unauthorized"
            return
        raise AssertionError("篡改 token 应当抛错")


class TestRegister:
    def test_register_returns_token_and_user(self, client: TestClient) -> None:
        email = random_email()
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "abcd1234", "display_name": "新用户"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["user"]["email"] == email
        assert body["user"]["role"] == "user"
        assert body["token_type"] == "bearer"
        assert body["access_token"]

    def test_duplicate_email_conflict(self, client: TestClient) -> None:
        email = random_email()
        payload = {"email": email, "password": "abcd1234", "display_name": "甲"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        resp = client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "email_taken"

    def test_email_is_normalized(self, client: TestClient) -> None:
        email = random_email()
        client.post(
            "/api/v1/auth/register",
            json={"email": email.upper(), "password": "abcd1234", "display_name": "甲"},
        )
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "abcd1234"})
        assert resp.status_code == 200

    def test_weak_password_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": random_email(), "password": "12345678", "display_name": "甲"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "bad_request"

    def test_short_password_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": random_email(), "password": "ab12", "display_name": "甲"},
        )
        assert resp.status_code == 400

    def test_blank_display_name_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": random_email(), "password": "abcd1234", "display_name": "   "},
        )
        # 纯空白经 strip 后为空，由 schema 校验拒绝并统一映射为 400
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "bad_request"


class TestLogin:
    def test_demo_account_can_login(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/login", json={"email": "demo@citera.dev", "password": "demo1234"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["display_name"] == "演示用户"

    def test_wrong_password(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/login", json={"email": "demo@citera.dev", "password": "wrong1234"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"

    def test_unknown_email(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/auth/login", json={"email": random_email(), "password": "abcd1234"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "invalid_credentials"

    def test_inactive_user_cannot_login(self, client: TestClient, admin_headers: dict) -> None:
        email = random_email()
        created = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "abcd1234", "display_name": "待停用"},
        ).json()
        user_id = created["user"]["id"]
        assert (
            client.patch(
                f"/api/v1/admin/users/{user_id}", headers=admin_headers, json={"is_active": False}
            ).status_code
            == 200
        )
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "abcd1234"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"


class TestMe:
    def test_me_requires_token(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"

    def test_me_returns_profile(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get("/api/v1/auth/me", headers=demo_headers).json()
        assert body["user"]["email"] == "demo@citera.dev"

    def test_update_display_name(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.patch(
            "/api/v1/auth/me", headers=demo_headers, json={"display_name": "演示用户二"}
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["display_name"] == "演示用户二"
        # 还原，避免影响其他用例的展示断言
        client.patch("/api/v1/auth/me", headers=demo_headers, json={"display_name": "演示用户"})

    def test_invalid_token(self, client: TestClient) -> None:
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
        assert resp.status_code == 401

    def test_missing_bearer_prefix(self, client: TestClient, demo_token: str) -> None:
        resp = client.get("/api/v1/auth/me", headers={"Authorization": demo_token})
        assert resp.status_code == 401


class TestRateLimit:
    def test_limiter_blocks_after_threshold(self) -> None:
        limiter = rate_limit.SlidingWindowLimiter(limit=3, window_seconds=60)
        assert limiter.allow("k")
        assert limiter.allow("k")
        assert limiter.allow("k")
        assert not limiter.allow("k")
        assert limiter.remaining("k") == 0

    def test_limiter_is_per_key(self) -> None:
        limiter = rate_limit.SlidingWindowLimiter(limit=1, window_seconds=60)
        assert limiter.allow("a")
        assert limiter.allow("b")
        assert not limiter.allow("a")

    def test_reset_clears_state(self) -> None:
        limiter = rate_limit.SlidingWindowLimiter(limit=1, window_seconds=60)
        limiter.allow("a")
        limiter.reset()
        assert limiter.allow("a")

    def test_auth_rate_limit_enforced_when_enabled(
        self, client: TestClient, monkeypatch
    ) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "rate_limit_enabled", True)
        rate_limit.reset_all()
        codes = []
        for _ in range(rapid_attempts()):
            resp = client.post(
                "/api/v1/auth/login", json={"email": "demo@citera.dev", "password": "wrong1234"}
            )
            codes.append(resp.json()["error"]["code"])
        assert "rate_limited" in codes


def rapid_attempts() -> int:
    return 12
