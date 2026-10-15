"""FastAPI 依赖：当前用户、管理员校验、限流。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import ask_limiter, auth_limiter, upload_limiter
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def _token_credentials(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> HTTPAuthorizationCredentials:
    if credentials is None or not credentials.credentials:
        raise AppError("unauthorized", "请先登录")
    return credentials


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_token_credentials)],
    db: DbSession,
) -> User:
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise AppError(exc.code, exc.message) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AppError("unauthorized", "账号不存在或已被删除")
    if not user.is_active:
        raise AppError("forbidden", "账号已被停用")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise AppError("forbidden", "需要管理员权限")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_auth_rate_limit(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    if not auth_limiter.allow(client_ip(request)):
        raise AppError("rate_limited", "登录/注册过于频繁，请稍后再试")


def enforce_ask_rate_limit(user: CurrentUser) -> User:
    if settings.rate_limit_enabled and not ask_limiter.allow(f"u:{user.id}"):
        raise AppError("rate_limited", "提问过于频繁，请稍后再试")
    return user


def enforce_upload_rate_limit(user: CurrentUser) -> User:
    if settings.rate_limit_enabled and not upload_limiter.allow(f"u:{user.id}"):
        raise AppError("rate_limited", "上传过于频繁，请稍后再试")
    return user


# 组合依赖：既是"当前用户"，又带限流副作用。用 Annotated 形式声明，
# 避免与默认值 Depends(...) 同时出现（FastAPI 会直接断言失败）。
UploadUser = Annotated[User, Depends(enforce_upload_rate_limit)]
AskUser = Annotated[User, Depends(enforce_ask_rate_limit)]
