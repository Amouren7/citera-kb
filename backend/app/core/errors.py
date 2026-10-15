"""统一错误类型与全局异常处理（契约 §4.1）。

所有对外错误一律是：
    {"error": {"code": ..., "message": ..., "details": ..., "request_id": ...}}
禁止任何例外，包括 FastAPI 自带的 422 校验错误。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("citera.errors")

# 业务错误码 → HTTP 状态码
ERROR_STATUS: dict[str, int] = {
    "bad_request": 400,
    "unauthorized": 401,
    "invalid_credentials": 401,
    "token_expired": 401,
    "forbidden": 403,
    "quota_exceeded": 403,
    "not_found": 404,
    "method_not_allowed": 405,
    "email_taken": 409,
    "conflict": 409,
    "file_too_large": 413,
    "unsupported_file_type": 415,
    "unprocessable_upload": 422,
    "rate_limited": 429,
    "internal_error": 500,
}

DEFAULT_MESSAGES: dict[str, str] = {
    "bad_request": "请求参数不合法",
    "unauthorized": "请先登录",
    "invalid_credentials": "邮箱或密码不正确",
    "token_expired": "登录已过期，请重新登录",
    "forbidden": "没有权限执行该操作",
    "quota_exceeded": "已达配额上限",
    "not_found": "资源不存在",
    "method_not_allowed": "请求方法不被支持",
    "email_taken": "该邮箱已被注册",
    "conflict": "资源状态冲突",
    "file_too_large": "文件超过大小限制",
    "unsupported_file_type": "不支持的文件类型",
    "unprocessable_upload": "文件内容无法解析",
    "rate_limited": "操作过于频繁，请稍后再试",
    "internal_error": "服务器内部错误",
}


class AppError(Exception):
    """业务异常：抛出后由全局处理器转换为标准错误体。"""

    def __init__(
        self,
        code: str = "bad_request",
        message: str | None = None,
        details: Any = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "请求失败")
        self.details = details
        self.status_code = status_code or ERROR_STATUS.get(code, 400)
        super().__init__(self.message)


def error_body(code: str, message: str, details: Any, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:  # noqa: ANN202
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details, _request_id(request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ANN202
        mapping = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        code = mapping.get(exc.status_code, "bad_request")
        detail = exc.detail if isinstance(exc.detail, str) else DEFAULT_MESSAGES.get(code, "请求失败")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, detail, None, _request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ANN202
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])[1:]), "reason": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content=error_body("bad_request", "请求参数校验未通过", details, _request_id(request)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ANN202
        rid = _request_id(request)
        logger.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
        from app.core.config import settings

        message = str(exc) if settings.debug else DEFAULT_MESSAGES["internal_error"]
        return JSONResponse(
            status_code=500, content=error_body("internal_error", message, None, rid)
        )
