#!/usr/bin/env python
"""Citera 健康检查 / 就绪等待。

两种用法：

1) 容器 HEALTHCHECK（无参数）
   GET http://127.0.0.1:$PORT/api/health
   契约 §4.2 响应 {"status":"ok","version":"0.1.0","db":"ok"|"error",...}
   判定：HTTP 200 且 status == "ok" → 退出码 0；否则 1。
   （db=error 也算不健康，容器重启能自愈常见的启动竞态。）

2) 本地 / CI 等待服务起来
   python healthcheck.py --base-url http://localhost:8000 --wait 180
   反复探测直到成功或超时，超时退出码 1。

只用标准库（镜像里没有 curl/wget，省体积）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = float(os.environ.get("HEALTHCHECK_TIMEOUT", "4"))


def probe(url: str, timeout: float = TIMEOUT) -> tuple[bool, str]:
    """返回 (是否健康, 说明)。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status_code = resp.status
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if status_code != 200:
        return False, f"HTTP {status_code}"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False, f"响应不是 JSON：{body[:160]!r}"

    app_status = payload.get("status")
    db_status = payload.get("db")
    if app_status == "ok" and db_status in (None, "ok"):
        return True, json.dumps(payload, ensure_ascii=False)
    return False, f"status={app_status} db={db_status}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Citera 健康检查")
    parser.add_argument("--base-url", default=None, help="默认用 http://127.0.0.1:$PORT")
    parser.add_argument("--url", default=None, help="直接指定完整 /api/health 地址")
    parser.add_argument("--wait", type=float, default=0, help="最长等待秒数，0 = 只探测一次")
    parser.add_argument("--interval", type=float, default=2.0, help="重试间隔秒数")
    args = parser.parse_args()

    if args.url:
        url = args.url
    else:
        base = args.base_url or os.environ.get("HEALTHCHECK_BASE_URL") or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}"
        url = base.rstrip("/") + "/api/health"

    if args.wait <= 0:
        ok, detail = probe(url)
        print(f"[healthcheck] {'healthy' if ok else 'unhealthy'} {url} → {detail}")
        return 0 if ok else 1

    deadline = time.monotonic() + args.wait
    attempt = 0
    detail = "未开始"
    while True:
        attempt += 1
        ok, detail = probe(url)
        if ok:
            print(f"[healthcheck] 第 {attempt} 次探测成功：{url} → {detail}")
            return 0
        if time.monotonic() >= deadline:
            print(f"[healthcheck] {args.wait}s 超时，最后结果：{detail}", file=sys.stderr)
            return 1
        print(f"[healthcheck] 第 {attempt} 次未就绪（{detail}），{args.interval}s 后重试")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
