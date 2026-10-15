"""pytest 公共装置。

要点：测试默认跑在**临时 SQLite** 上（不依赖 Docker），因此契约里所有依赖
pgvector 原生能力的地方都必须有 Python 退化路径——这是刻意的设计，
保证开发机上 `pytest` 一条命令就能全绿。真实 PostgreSQL 集成测试标记为
``@pytest.mark.postgres``，用 ``CITERA_TEST_PG=1`` 启用。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# 环境必须在导入 app 之前设置：settings 是模块级单例
_TMP_DIR = Path(tempfile.mkdtemp(prefix="citera-test-"))
DB_PATH = _TMP_DIR / "test.db"

os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{DB_PATH.as_posix()}")
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789-abcdefghijklmnop")
os.environ.setdefault("SERVE_FRONTEND", "false")
os.environ.setdefault("SEED_DEMO_DATA", "true")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("DEBUG", "true")

from fastapi.testclient import TestClient  # noqa: E402

from app.core import rate_limit  # noqa: E402
from app.db.init_db import create_schema, seed_all  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def seeded() -> None:
    create_schema()
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


@pytest.fixture()
def client(seeded: None) -> TestClient:
    rate_limit.reset_all()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(seeded: None):  # noqa: ANN201
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def demo_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login", json={"email": "demo@citera.dev", "password": "demo1234"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def demo_headers(demo_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login", json={"email": "admin@citera.dev", "password": "admin1234"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    """未开启 CITERA_TEST_PG 时跳过 postgres 集成测试。"""
    if os.environ.get("CITERA_TEST_PG") == "1":
        return
    skip = pytest.mark.skip(reason="需要真实 PostgreSQL：设 CITERA_TEST_PG=1 启用")
    for item in items:
        if "postgres" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_engine():
    yield
    engine.dispose()
