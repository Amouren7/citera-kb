"""健康检查与元信息（无需认证）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import AppSetting
from app.schemas import LimitsOut, MetaOut

router = APIRouter(tags=["meta"])


@router.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    db_status = "ok"
    try:
        db.execute(select(1)).scalar()
    except Exception:
        db_status = "error"
    return {
        "status": "ok",
        "version": settings.app_version,
        "db": db_status,
        "llm_provider": settings.active_llm_provider,
    }


@router.get("/api/v1/meta", response_model=MetaOut)
def meta(db: Session = Depends(get_db)) -> MetaOut:
    registration_open = True
    try:
        row = db.get(AppSetting, "registration_open")
        if row is not None and isinstance(row.value, dict):
            registration_open = bool(row.value.get("value", True))
        elif row is not None:
            registration_open = bool(row.value)
    except Exception:
        registration_open = True
    return MetaOut(
        app_name=settings.app_name,
        version=settings.app_version,
        registration_open=registration_open,
        limits=LimitsOut(
            max_upload_mb=settings.max_upload_mb,
            max_documents=settings.max_documents,
            max_conversations=settings.max_conversations,
        ),
    )
