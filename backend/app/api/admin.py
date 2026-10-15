"""管理接口（契约 §4.2 管理段，全部要求 role=admin）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.core.errors import AppError
from app.models import (
    AppSetting,
    Conversation,
    Document,
    DocumentChunk,
    EvalRun,
    Message,
    User,
)
from app.schemas import (
    AdminStats,
    AdminUserUpdate,
    Page,
    Recent7d,
    SettingsEnvelope,
    SettingsUpdateIn,
    UserOut,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

SETTING_KEYS = {"retrieval_mode", "top_k", "chunk_size", "chunk_overlap", "registration_open"}


def _count(db: DbSession, model, *conditions) -> int:  # noqa: ANN001
    stmt = select(func.count()).select_from(model)
    if conditions:
        stmt = stmt.where(*conditions)
    return int(db.execute(stmt).scalar() or 0)


@router.get("/stats", response_model=AdminStats)
def stats(db: DbSession, admin: AdminUser) -> AdminStats:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    return AdminStats(
        users=_count(db, User),
        documents=_count(db, Document, Document.deleted_at.is_(None)),
        chunks=_count(db, DocumentChunk),
        conversations=_count(db, Conversation, Conversation.deleted_at.is_(None)),
        messages=_count(db, Message),
        eval_runs=_count(db, EvalRun),
        recent_7d=Recent7d(
            documents=_count(db, Document, Document.created_at >= since),
            messages=_count(db, Message, Message.created_at >= since),
        ),
    )


@router.get("/users", response_model=Page)
def list_users(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    query = db.query(User)
    total = query.count()
    rows = query.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(
        items=[UserOut.model_validate(u).model_dump(mode="json") for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, payload: AdminUserUpdate, db: DbSession, admin: AdminUser
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise AppError("not_found", "用户不存在")
    if target.id == admin.id and payload.role == "user":
        raise AppError("bad_request", "不能把自己降级为普通用户")
    if payload.is_active is not None:
        if target.id == admin.id and not payload.is_active:
            raise AppError("bad_request", "不能停用自己的账号")
        target.is_active = payload.is_active
    if payload.role is not None:
        target.role = payload.role
    db.add(target)
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)


@router.get("/settings", response_model=SettingsEnvelope)
def get_settings(db: DbSession, admin: AdminUser) -> SettingsEnvelope:
    rows = db.query(AppSetting).all()
    data: dict = {}
    for row in rows:
        value = row.value
        data[row.key] = value.get("value") if isinstance(value, dict) and "value" in value else value
    return SettingsEnvelope(settings=data)


@router.put("/settings", response_model=SettingsEnvelope)
def update_settings(payload: SettingsUpdateIn, db: DbSession, admin: AdminUser) -> SettingsEnvelope:
    unknown = set(payload.settings.keys()) - SETTING_KEYS
    if unknown:
        raise AppError("bad_request", f"不允许修改的设置项：{', '.join(sorted(unknown))}")

    _validate_settings(payload.settings)

    for key, value in payload.settings.items():
        row = db.get(AppSetting, key)
        if row is None:
            row = AppSetting(key=key, value={"value": value})
        else:
            row.value = {"value": value}
        db.add(row)
    db.commit()
    return get_settings(db, admin)


def _validate_settings(values: dict) -> None:
    if "retrieval_mode" in values and values["retrieval_mode"] not in {"vector", "keyword", "hybrid"}:
        raise AppError("bad_request", "retrieval_mode 只能是 vector / keyword / hybrid")
    for key in ("top_k", "chunk_size", "chunk_overlap"):
        if key in values:
            try:
                number = int(values[key])
            except (TypeError, ValueError) as exc:
                raise AppError("bad_request", f"{key} 必须是整数") from exc
            if number <= 0:
                raise AppError("bad_request", f"{key} 必须大于 0")
            values[key] = number
    if "chunk_overlap" in values and "chunk_size" in values:
        if values["chunk_overlap"] >= values["chunk_size"]:
            raise AppError("bad_request", "chunk_overlap 必须小于 chunk_size")


@router.post("/reseed")
def reseed(db: DbSession, admin: AdminUser) -> dict:
    from app.db.init_db import seed_all

    summary = seed_all(db)
    return {"ok": True, **summary}
