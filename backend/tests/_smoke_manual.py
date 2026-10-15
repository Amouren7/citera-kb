"""手工冒烟脚本：把 SSE 流、上传链路、评测指标一次看清。

运行（不依赖 Docker）：
    cd backend
    .venv\\Scripts\\python.exe tests\\_smoke_manual.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="citera-smoke-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(_TMP / 'smoke.db').as_posix()}"
os.environ["JWT_SECRET"] = "smoke-secret-0123456789-abcdefghijklmnop"
os.environ["SERVE_FRONTEND"] = "false"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["RATE_LIMIT_ENABLED"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.db.init_db import create_schema, seed_all  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402


def read_sse(raw: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in raw.strip().split("\n\n"):
        name = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                name = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()
        if name and data:
            events.append((name, json.loads(data)))
    return events


def main() -> int:
    create_schema()
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login", json={"email": "demo@citera.dev", "password": "demo1234"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        print("LOGIN", login.status_code)

        # 1) 上传 + 后台摄取
        content = (
            "# 采购与供应商管理规范\n\n## 一、供应商准入\n"
            "新供应商需提供营业执照、质检报告与近一年财务报表，由采购部初审后交质量部复核。\n\n"
            "## 二、付款账期\n标准账期为月结 60 天，战略供应商可申请月结 90 天，需财务总监审批。\n"
        ).encode("utf-8")
        resp = client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("procurement.md", content, "text/markdown")},
            data={"title": "采购与供应商管理规范"},
        )
        doc_id = resp.json()["document"]["id"]
        print("UPLOAD", resp.status_code, "->", resp.json()["document"]["status"])

        # 2) 流式问答
        conv = client.post("/api/v1/conversations", headers=headers, json={}).json()
        conv_id = conv["conversation"]["id"]
        with client.stream(
            "POST",
            f"/api/v1/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": "七天无理由退货的运费由谁承担？", "stream": True, "top_k": 3},
        ) as stream:
            body = "".join(stream.iter_text())
        events = read_sse(body)
        print("SSE events:", [name for name, _ in events])
        retrieval = next((data for name, data in events if name == "retrieval"), None)
        if retrieval:
            print(
                "SSE retrieval:",
                [(c["retrieval"], round(c["score"], 4), c["document_title"]) for c in retrieval["chunks"]],
            )
        print("SSE done:", next((data for name, data in events if name == "done"), None))

        # 3) 上传文档是否处理完成
        detail = client.get(f"/api/v1/documents/{doc_id}", headers=headers).json()["document"]
        print("UPLOADED DOC:", detail["status"], "chunks =", detail["chunk_count"], "chars =", detail["char_count"])

        # 4) 评测三模式
        resp = client.post(
            "/api/v1/evaluations/run",
            headers=headers,
            json={"dataset_id": 1, "modes": ["vector", "keyword", "hybrid"], "top_k": 5},
        )
        print("EVAL", resp.status_code)
        for run in resp.json()["runs"]:
            m = run["metrics"]
            print(
                f"  {run['mode']:8s} R@1={m['recall_at_1']:.2f} R@3={m['recall_at_3']:.2f} "
                f"R@5={m['recall_at_5']:.2f} R@10={m['recall_at_10']:.2f} MRR={m['mrr']:.3f} "
                f"hit={m['hit_rate']:.2f} {m['avg_latency_ms']}ms"
            )

        admin = client.post(
            "/api/v1/auth/login", json={"email": "admin@citera.dev", "password": "admin1234"}
        )
        ah = {"Authorization": f"Bearer {admin.json()['access_token']}"}
        print("ADMIN STATS:", client.get("/api/v1/admin/stats", headers=ah).json())
        print("ERROR FORMAT:", client.get("/api/v1/documents/999999", headers=headers).json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
