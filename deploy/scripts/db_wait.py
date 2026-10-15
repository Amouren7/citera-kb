#!/usr/bin/env python
"""等待 DATABASE_URL 指向的 PostgreSQL 可连接。

容器入口用：db_wait.py --timeout 90
退出码 0 = 可连接；1 = 超时仍不可用。

只依赖标准库 + sqlalchemy（后端已有）+ psycopg（后端已有）。
不引入额外包，避免影响镜像体积。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse


def _dsn_parts(database_url: str) -> dict:
    """把 SQLAlchemy URL 拆成 psycopg.connect 能用的参数。"""
    # postgresql+psycopg://user:pass@host:5432/db  →  scheme 里带 +driver
    parsed = urllib.parse.urlsplit(database_url.replace("postgresql+psycopg", "postgresql", 1))
    parts = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/postgres").lstrip("/") or "postgres",
    }
    if parsed.username:
        parts["user"] = urllib.parse.unquote(parsed.username)
    if parsed.password:
        parts["password"] = urllib.parse.unquote(parsed.password)
    return parts


def try_connect(database_url: str) -> tuple[bool, str]:
    try:
        import psycopg
    except ImportError:  # pragma: no cover - 镜像里一定有
        return False, "未安装 psycopg，无法检查数据库"

    parts = _dsn_parts(database_url)
    try:
        with psycopg.connect(connect_timeout=5, **parts) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, f"{parts['host']}:{parts['port']}/{parts['dbname']}"
    except Exception as exc:  # noqa: BLE001 - 任何连接错误都只用于重试
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="等待 PostgreSQL 就绪")
    parser.add_argument("--timeout", type=int, default=90, help="最长等待秒数，默认 90")
    parser.add_argument("--interval", type=float, default=2.0, help="重试间隔秒数，默认 2")
    parser.add_argument("--database-url", default=None, help="默认读环境变量 DATABASE_URL")
    args = parser.parse_args()

    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("[db-wait] 未提供 DATABASE_URL，跳过等待")
        return 0

    deadline = time.monotonic() + args.timeout
    attempt = 0
    last_error = ""
    while True:
        attempt += 1
        ok, detail = try_connect(database_url)
        if ok:
            print(f"[db-wait] 第 {attempt} 次尝试成功：{detail}")
            return 0
        last_error = detail
        if time.monotonic() >= deadline:
            print(f"[db-wait] {args.timeout}s 超时，最后错误：{last_error}", file=sys.stderr)
            return 1
        print(f"[db-wait] 第 {attempt} 次未就绪（{detail}），{args.interval}s 后重试")
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
