"""认证接口（契约 §4.2 认证段）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, DbSession, enforce_auth_rate_limit
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import AppSetting, User
from app.schemas import LoginIn, RegisterIn, TokenPair, UpdateMeIn, UserEnvelope, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _registration_open(db: DbSession) -> bool:
    row = db.get(AppSetting, "registration_open")
    if row is None:
        return True
    value = row.value
    if isinstance(value, dict):
        return bool(value.get("value", True))
    return bool(value)


def _issue(user: User) -> TokenPair:
    return TokenPair(
        user=UserOut.model_validate(user),
        access_token=create_access_token(user.id, user.role),
        token_type="bearer",
    )


@router.post("/register", response_model=TokenPair, status_code=201)
def register(
    payload: RegisterIn,
    db: DbSession,
    _: None = Depends(enforce_auth_rate_limit),
) -> TokenPair:
    if not _registration_open(db):
        raise AppError("forbidden", "当前未开放注册")

    email = payload.email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise AppError("email_taken", "该邮箱已被注册")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(user)


@router.post("/login", response_model=TokenPair)
def login(
    payload: LoginIn,
    db: DbSession,
    _: None = Depends(enforce_auth_rate_limit),
) -> TokenPair:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("invalid_credentials", "邮箱或密码不正确")
    if not user.is_active:
        raise AppError("forbidden", "账号已被停用，请联系管理员")
    return _issue(user)


@router.get("/me", response_model=UserEnvelope)
def me(user: CurrentUser) -> UserEnvelope:
    return UserEnvelope(user=UserOut.model_validate(user))


@router.patch("/me", response_model=UserEnvelope)
def update_me(payload: UpdateMeIn, user: CurrentUser, db: DbSession) -> UserEnvelope:
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
        db.add(user)
        db.commit()
        db.refresh(user)
    return UserEnvelope(user=UserOut.model_validate(user))
