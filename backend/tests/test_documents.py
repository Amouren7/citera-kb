"""文档接口：上传、摄取、分页、权限与配额。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

MD_CONTENT = """# 供应商管理办法

## 一、准入条件
新供应商需提供营业执照、质检报告与近一年财务报表。

## 二、付款账期
标准账期为月结 60 天，战略供应商可申请 90 天。
""".encode("utf-8")


def upload(client: TestClient, headers: dict, name: str = "供应", content: bytes = MD_CONTENT):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (f"{name}-{uuid.uuid4().hex[:6]}.md", content, "text/markdown")},
        data={"title": name},
    )


class TestUpload:
    def test_upload_markdown_becomes_ready(self, client: TestClient, demo_headers: dict) -> None:
        resp = upload(client, demo_headers, "供应商管理办法")
        assert resp.status_code == 201
        document = resp.json()["document"]
        assert document["status"] in {"pending", "ready"}
        detail = client.get(f"/api/v1/documents/{document['id']}", headers=demo_headers).json()[
            "document"
        ]
        assert detail["status"] == "ready"
        assert detail["chunk_count"] >= 2
        assert detail["char_count"] > 0
        assert detail["meta"]["chunk_size"] > 0

    def test_paste_mode(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            data={"title": "粘贴文档", "raw_text": "第一段内容。\n\n第二段内容。"},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["document"]["id"]
        detail = client.get(f"/api/v1/documents/{doc_id}", headers=demo_headers).json()["document"]
        assert detail["status"] == "ready"
        assert detail["source_type"] == "paste"

    def test_missing_payload(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post("/api/v1/documents", headers=demo_headers, data={"title": "空"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "bad_request"

    def test_unsupported_extension(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            files={"file": ("binary.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert resp.status_code == 415
        assert resp.json()["error"]["code"] == "unsupported_file_type"

    def test_empty_file_rejected(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "unprocessable_upload"

    def test_oversized_file_rejected(
        self, client: TestClient, demo_headers: dict, monkeypatch
    ) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "max_upload_mb", 1)
        big = ("x" * 2000 + "\n") * 700  # 约 1.4MB
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            files={"file": ("big.txt", big.encode("utf-8"), "text/plain")},
        )
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "file_too_large"

    def test_gbk_file_is_decoded(self, client: TestClient, demo_headers: dict) -> None:
        content = "中文编码测试内容。\n\n第二段。".encode("gbk")
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            files={"file": ("gbk.txt", content, "text/plain")},
        )
        assert resp.status_code == 201
        doc_id = resp.json()["document"]["id"]
        detail = client.get(f"/api/v1/documents/{doc_id}", headers=demo_headers).json()["document"]
        assert detail["status"] == "ready"
        assert detail["chunk_count"] >= 1

    def test_pdf_without_text_is_unprocessable(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        resp = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            files={"file": ("bad.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        )
        assert resp.status_code == 201
        detail = client.get(
            f"/api/v1/documents/{resp.json()['document']['id']}", headers=demo_headers
        ).json()["document"]
        assert detail["status"] == "failed"
        assert detail["error_message"]

    def test_upload_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/documents", files={"file": ("a.md", MD_CONTENT, "text/markdown")}
        )
        assert resp.status_code == 401

    def test_quota_exceeded(self, client: TestClient, demo_headers: dict, monkeypatch) -> None:
        from app.core.config import settings

        # 演示账号已有 6 篇种子文档，把上限压到当前数量即触发配额
        current = client.get("/api/v1/documents/stats", headers=demo_headers).json()["total"]
        monkeypatch.setattr(settings, "max_documents", current)
        resp = upload(client, demo_headers, "超配额文档")
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "quota_exceeded"

    def test_quota_allows_under_limit(self, client: TestClient, demo_headers: dict, monkeypatch) -> None:
        from app.core.config import settings

        current = client.get("/api/v1/documents/stats", headers=demo_headers).json()["total"]
        monkeypatch.setattr(settings, "max_documents", current + 1)
        assert upload(client, demo_headers, "配额内文档").status_code == 201


class TestListAndFilter:
    def test_seed_documents_present(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get("/api/v1/documents", headers=demo_headers).json()
        assert body["total"] >= 6
        assert body["page"] == 1
        assert len(body["items"]) <= body["page_size"]

    def test_search_by_title(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get("/api/v1/documents", headers=demo_headers, params={"q": "保修"}).json()
        assert body["total"] >= 1
        assert all("保修" in item["title"] for item in body["items"])

    def test_filter_by_status(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get(
            "/api/v1/documents", headers=demo_headers, params={"status": "ready"}
        ).json()
        assert all(item["status"] == "ready" for item in body["items"])

    def test_pagination(self, client: TestClient, demo_headers: dict) -> None:
        first = client.get(
            "/api/v1/documents", headers=demo_headers, params={"page": 1, "page_size": 2}
        ).json()
        second = client.get(
            "/api/v1/documents", headers=demo_headers, params={"page": 2, "page_size": 2}
        ).json()
        assert len(first["items"]) == 2
        assert {i["id"] for i in first["items"]}.isdisjoint({i["id"] for i in second["items"]})

    def test_sort_by_title(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get(
            "/api/v1/documents", headers=demo_headers, params={"sort": "title"}
        ).json()
        titles = [item["title"] for item in body["items"]]
        assert titles == sorted(titles)

    def test_page_size_upper_bound(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.get("/api/v1/documents", headers=demo_headers, params={"page_size": 500})
        assert resp.status_code == 400


class TestDetailChunksAndStats:
    def test_stats_shape(self, client: TestClient, demo_headers: dict) -> None:
        body = client.get("/api/v1/documents/stats", headers=demo_headers).json()
        assert body["ready"] >= 6
        assert body["chunk_total"] >= 20
        assert body["char_total"] > 0
        assert isinstance(body["by_status"], list)

    def test_chunks_pagination_and_no_embedding_leak(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        doc_id = client.get("/api/v1/documents", headers=demo_headers).json()["items"][0]["id"]
        body = client.get(
            f"/api/v1/documents/{doc_id}/chunks", headers=demo_headers, params={"page_size": 2}
        ).json()
        assert body["total"] >= 1
        for chunk in body["items"]:
            assert set(chunk) == {
                "id",
                "ord",
                "heading",
                "content",
                "token_estimate",
                "has_embedding",
            }
            assert chunk["has_embedding"] is True

    def test_rename_document(self, client: TestClient, demo_headers: dict) -> None:
        created = upload(client, demo_headers, "待改名")
        doc_id = created.json()["document"]["id"]
        resp = client.patch(
            f"/api/v1/documents/{doc_id}", headers=demo_headers, json={"title": "改名成功"}
        )
        assert resp.status_code == 200
        assert resp.json()["document"]["title"] == "改名成功"

    def test_rename_blank_rejected(self, client: TestClient, demo_headers: dict) -> None:
        doc_id = client.get("/api/v1/documents", headers=demo_headers).json()["items"][0]["id"]
        resp = client.patch(f"/api/v1/documents/{doc_id}", headers=demo_headers, json={"title": ""})
        assert resp.status_code == 400


class TestDeleteAndOwnership:
    def test_soft_delete_then_missing(self, client: TestClient, demo_headers: dict) -> None:
        created = upload(client, demo_headers, "待删除")
        doc_id = created.json()["document"]["id"]
        assert client.delete(f"/api/v1/documents/{doc_id}", headers=demo_headers).status_code == 204
        assert client.get(f"/api/v1/documents/{doc_id}", headers=demo_headers).status_code == 404
        body = client.get("/api/v1/documents", headers=demo_headers).json()
        assert doc_id not in [item["id"] for item in body["items"]]

    def test_other_user_document_is_not_found(self, client: TestClient, demo_headers: dict) -> None:
        created = upload(client, demo_headers, "私有文档")
        doc_id = created.json()["document"]["id"]

        other = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"other-{uuid.uuid4().hex[:8]}@example.com",
                "password": "abcd1234",
                "display_name": "他人",
            },
        ).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        resp = client.get(f"/api/v1/documents/{doc_id}", headers=other_headers)
        assert resp.status_code == 404  # 不暴露资源是否存在

    def test_reprocess_paste_document(self, client: TestClient, demo_headers: dict) -> None:
        created = client.post(
            "/api/v1/documents",
            headers=demo_headers,
            data={"title": "可重跑", "raw_text": "第一段。\n\n第二段。"},
        )
        doc_id = created.json()["document"]["id"]
        resp = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=demo_headers)
        assert resp.status_code == 202
        detail = client.get(f"/api/v1/documents/{doc_id}", headers=demo_headers).json()["document"]
        assert detail["status"] == "ready"
        assert detail["chunk_count"] >= 1

    def test_reprocess_upload_document_rejected(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        created = upload(client, demo_headers, "上传件不可重跑")
        doc_id = created.json()["document"]["id"]
        resp = client.post(f"/api/v1/documents/{doc_id}/reprocess", headers=demo_headers)
        assert resp.status_code == 400

    def test_delete_missing_document(self, client: TestClient, demo_headers: dict) -> None:
        assert client.delete("/api/v1/documents/999999", headers=demo_headers).status_code == 404
