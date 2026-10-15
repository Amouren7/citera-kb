"""FastAPI 应用装配：路由、中间件、异常处理、SPA 静态托管。

单容器部署要点：同一个进程同时服务 ``/api/*`` 与前端的 ``index.html``，
所以 SPA 的 history 路由回退必须让 API 优先匹配（见 ``_mount_frontend``）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api import admin, auth, conversations, documents, evaluations, health
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging

logger = logging.getLogger("citera.main")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def frontend_dist() -> Path:
    if settings.frontend_dist:
        return Path(settings.frontend_dist)
    return DEFAULT_FRONTEND_DIST


def _bootstrap_database() -> None:
    """容器首次启动自动建表 + 灌种子，保证公网 Demo 打开就有内容。"""
    if not settings.seed_demo_data:
        return
    try:
        from app.db.init_db import create_extensions, create_schema, seed_all
        from app.db.session import SessionLocal

        create_extensions()
        create_schema()
        db = SessionLocal()
        try:
            summary = seed_all(db)
            logger.info("种子数据就绪：%s", summary)
        finally:
            db.close()
    except Exception:  # 启动不应因种子失败而崩，但要留清晰日志
        logger.exception("数据库初始化失败，请检查 DATABASE_URL 是否可连通")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    for warning in settings.validate_runtime():
        logger.warning("配置告警：%s", warning)
    _bootstrap_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=(
            "Citera 溯源知识库：文档摄取 → 混合检索（向量 + 关键词 + RRF 融合）→ "
            "带引用的问答 → 离线评测。"
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
        )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(conversations.router)
    app.include_router(evaluations.router)
    app.include_router(admin.router)

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    if not settings.serve_frontend:
        return
    dist = frontend_dist()
    index = dist / "index.html"
    if not index.exists():
        logger.info("未找到前端产物 %s，仅提供 API（开发模式下前端跑在 Vite dev server）", dist)
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request):  # noqa: ANN202
        if full_path.startswith(("api/", "assets/")):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "not_found",
                        "message": "接口不存在",
                        "details": None,
                        "request_id": getattr(request.state, "request_id", ""),
                    }
                },
            )
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    logger.info("已挂载前端静态资源：%s", dist)


app = create_app()
