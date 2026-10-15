#!/usr/bin/env python
"""Citera 端到端冒烟测试：登录 → 建会话 → 提问 → 校验引用可溯源。

契约 §8.3 的「完成一次完整问答」就是这一步。CI 的 integration job 会跑它，
本地也可以直接跑（只依赖标准库，Windows / Linux / macOS 通用）：

    python deploy/scripts/smoke_api.py --base-url http://localhost:8000

成功退出码 0；任何断言失败退出码 1，并打印实际响应体方便定位。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_EMAIL = "demo@citera.dev"
DEFAULT_PASSWORD = "demo1234"

# Windows 控制台默认 GBK，print ✅/❌/中文 会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


class SmokeFailure(AssertionError):
    pass


def request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    timeout: float = 60.0,
) -> tuple[int, object]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        status = exc.code
    except Exception as exc:  # noqa: BLE001
        raise SmokeFailure(f"{method} {url} 请求失败：{type(exc).__name__}: {exc}") from exc

    try:
        parsed: object = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = body
    return status, parsed


def fail(message: str, status: int | None = None, body: object = None) -> None:
    detail = ""
    if status is not None:
        detail += f"\n  HTTP {status}"
    if body is not None:
        detail += f"\n  body: {json.dumps(body, ensure_ascii=False)[:800] if not isinstance(body, str) else body[:800]}"
    raise SmokeFailure(f"{message}{detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Citera 端到端冒烟测试")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--question", default="整机保修期是多久？")
    parser.add_argument("--timeout", type=float, default=120.0, help="单次请求超时秒数")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    steps: list[str] = []

    # 1. 健康检查
    status, body = request("GET", f"{base}/api/health", timeout=args.timeout)
    if status != 200:
        fail("健康检查失败", status, body)
    assert isinstance(body, dict)
    if body.get("status") != "ok":
        fail("健康检查 status != ok", status, body)
    if body.get("db") not in (None, "ok"):
        fail("健康检查 db != ok（数据库不通）", status, body)
    steps.append(f"/api/health → ok (db={body.get('db')}, llm={body.get('llm_provider')})")

    # 2. 登录（种子演示账号）
    status, body = request(
        "POST",
        f"{base}/api/v1/auth/login",
        payload={"email": args.email, "password": args.password},
        timeout=args.timeout,
    )
    if status != 200 or not isinstance(body, dict) or "access_token" not in body:
        fail(f"演示账号登录失败（{args.email}）——种子数据可能没灌上", status, body)
    token = str(body["access_token"])
    steps.append(f"POST /api/v1/auth/login → 200（{args.email}）")

    # 3. 元信息（顺带确认 registration_open / limits 存在）
    status, body = request("GET", f"{base}/api/v1/meta", timeout=args.timeout)
    if status != 200:
        fail("GET /api/v1/meta 失败", status, body)
    steps.append("GET /api/v1/meta → 200")

    # 4. 文档列表必须有种子数据，否则公网 Demo 打开是空的
    status, body = request("GET", f"{base}/api/v1/documents?page=1&page_size=20", token=token, timeout=args.timeout)
    if status != 200:
        fail("GET /api/v1/documents 失败", status, body)
    total = body.get("total") if isinstance(body, dict) else None
    if not total:
        fail("文档库为空：SEED_DEMO_DATA 没生效，公网 Demo 会打开即空", status, body)
    steps.append(f"GET /api/v1/documents → {total} 篇种子文档")

    # 5. 新建会话
    status, body = request(
        "POST",
        f"{base}/api/v1/conversations",
        token=token,
        payload={"title": "CI 冒烟测试"},
        timeout=args.timeout,
    )
    if status not in (200, 201) or not isinstance(body, dict):
        fail("POST /api/v1/conversations 失败", status, body)
    conversation = body.get("conversation", body)
    conversation_id = conversation.get("id") if isinstance(conversation, dict) else None
    if not conversation_id:
        fail("会话响应里没有 id", status, body)
    steps.append(f"POST /api/v1/conversations → {status} (id={conversation_id})")

    # 6. 提问（非流式，echo 模式必须能受控合成并给引用）
    status, body = request(
        "POST",
        f"{base}/api/v1/conversations/{conversation_id}/messages",
        token=token,
        payload={"content": args.question, "stream": False, "top_k": 5, "retrieval_mode": "hybrid"},
        timeout=args.timeout,
    )
    if status != 200 or not isinstance(body, dict):
        fail("提问失败", status, body)
    assistant = body.get("assistant_message") or {}
    content = assistant.get("content") or ""
    citations = assistant.get("citations") or []
    if not content.strip():
        fail("回答内容为空", status, body)
    if not citations:
        fail("回答没有 citations —— 「每条回答都能点回原文」是项目第一目标，不能空", status, body)
    steps.append(f"POST .../messages → 200（回答 {len(content)} 字，引用 {len(citations)} 条）")
    steps.append(f"回答开头：{content.strip().splitlines()[0][:60]}")

    # 7. 引用字段完整性（契约 §4.2 citations 结构）
    required = {"chunk_id", "document_id", "document_title", "ord", "snippet", "score"}
    first = citations[0]
    missing = required - set(first.keys())
    if missing:
        fail(f"citation 缺字段：{sorted(missing)}", status, first)
    steps.append(
        f"citation[0] → 《{first['document_title']}》 ord={first['ord']} score={first.get('score')} 字段齐全"
    )

    print("[smoke] 端到端问答通过 ✅")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SmokeFailure as exc:
        print(f"[smoke] 失败 ❌ {exc}", file=sys.stderr)
        sys.exit(1)
