"""请求日志、request_id 与耗时。"""

from __future__ import annotations

import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings


def configure_logging() -> None:
    level = logging.DEBUG if settings.debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s :: %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """给每个请求挂 request_id 并记录耗时。request_id 透传到错误体，便于对账。"""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001, ANN201
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        if request.url.path.startswith("/api"):
            logging.getLogger("citera.access").info(
                "%s %s -> %s (%.1fms) rid=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                rid,
            )
        return response
