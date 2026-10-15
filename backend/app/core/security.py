"""密码哈希与 JWT。

密码哈希刻意使用标准库 ``hashlib.scrypt``：
- 零外部依赖，不引入 passlib（Python 3.14 已移除 ``crypt``，passlib 1.7.4 会崩）
- scrypt 是内存硬化 KDF，本身是推荐的密码哈希算法
- 存储格式自带算法与参数，便于未来平滑升级：``scrypt$n$r$p$salt_b64$hash_b64``
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16

SCHEME = "scrypt"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("密码不能为空")
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "$".join(
        [SCHEME, str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P), _b64e(salt), _b64e(digest)]
    )


def verify_password(password: str, stored: str) -> bool:
    if not password or not stored:
        return False
    try:
        scheme, n_s, r_s, p_s, salt_b64, hash_b64 = stored.split("$")
        if scheme != SCHEME:
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64d(salt_b64),
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(_b64d(hash_b64)),
        )
        return hmac.compare_digest(digest, _b64d(hash_b64))
    except Exception:
        return False


def create_access_token(user_id: int, role: str, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


class TokenError(Exception):
    """token 无效或过期。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token_expired", "登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("unauthorized", "登录凭证无效") from exc
    if payload.get("typ") != "access":
        raise TokenError("unauthorized", "登录凭证类型不正确")
    if not payload.get("sub"):
        raise TokenError("unauthorized", "登录凭证缺少主体")
    return payload


def generate_password(length: int = 16) -> str:
    return secrets.token_urlsafe(length)
