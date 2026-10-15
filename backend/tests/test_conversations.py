"""会话与问答：非流式、SSE 事件序列、权限、边界。"""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient


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


def new_conversation(client: TestClient, headers: dict, title: str | None = None) -> int:
    payload = {"title": title} if title else {}
    resp = client.post("/api/v1/conversations", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["conversation"]["id"]


class TestConversationCrud:
    def test_create_returns_default_title(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        body = client.get(f"/api/v1/conversations/{cid}", headers=demo_headers).json()
        assert body["conversation"]["title"] == "新会话"
        assert body["conversation"]["messages"] == []

    def test_list_contains_created(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers, "列表测试")
        body = client.get("/api/v1/conversations", headers=demo_headers).json()
        titles = {item["id"]: item["title"] for item in body["items"]}
        assert titles.get(cid) == "列表测试"
        assert body["total"] >= 1

    def test_rename(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        resp = client.patch(
            f"/api/v1/conversations/{cid}", headers=demo_headers, json={"title": "改名后"}
        )
        assert resp.status_code == 200
        assert resp.json()["conversation"]["title"] == "改名后"

    def test_delete_then_not_found(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        assert client.delete(f"/api/v1/conversations/{cid}", headers=demo_headers).status_code == 204
        assert client.get(f"/api/v1/conversations/{cid}", headers=demo_headers).status_code == 404

    def test_missing_conversation(self, client: TestClient, demo_headers: dict) -> None:
        assert client.get("/api/v1/conversations/999999", headers=demo_headers).status_code == 404

    def test_other_user_cannot_read(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        other = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"conv-{uuid.uuid4().hex[:8]}@example.com",
                "password": "abcd1234",
                "display_name": "他人",
            },
        ).json()
        headers = {"Authorization": f"Bearer {other['access_token']}"}
        assert client.get(f"/api/v1/conversations/{cid}", headers=headers).status_code == 404

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/conversations").status_code == 401


class TestAskNonStream:
    def test_returns_both_messages(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        resp = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？", "stream": False, "top_k": 3},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["user_message"]["role"] == "user"
        assert body["assistant_message"]["role"] == "assistant"
        assert body["assistant_message"]["content"]
        assert body["assistant_message"]["latency_ms"] is not None

    def test_citations_match_contract_shape(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        body = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "七天无理由退货的运费谁承担？", "top_k": 3},
        ).json()
        citations = body["assistant_message"]["citations"]
        assert citations, "种子数据下应当能检索到引用"
        first = citations[0]
        assert set(first) == {
            "chunk_id",
            "document_id",
            "document_title",
            "ord",
            "heading",
            "snippet",
            "score",
            "retrieval",
            "rank",
        }
        assert first["rank"] == 1

    def test_citation_markers_reference_real_citations(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        import re

        cid = new_conversation(client, demo_headers)
        body = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "珠三角地区多久能送到？"},
        ).json()
        message = body["assistant_message"]
        for match in re.finditer(r"\[\[c(\d+)\]\]", message["content"]):
            index = int(match.group(1))
            assert 1 <= index <= len(message["citations"])

    def test_first_message_sets_conversation_title(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？"},
        )
        body = client.get(f"/api/v1/conversations/{cid}", headers=demo_headers).json()
        assert body["conversation"]["title"].startswith("整机保修期")

    def test_message_count_and_history(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？"},
        )
        client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "那电池呢？"},
        )
        body = client.get(f"/api/v1/conversations/{cid}", headers=demo_headers).json()
        assert body["conversation"]["message_count"] == 4
        roles = [m["role"] for m in body["conversation"]["messages"]]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_empty_content_rejected(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        resp = client.post(
            f"/api/v1/conversations/{cid}/messages", headers=demo_headers, json={"content": "   "}
        )
        assert resp.status_code == 400

    def test_top_k_bounds(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        resp = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "保修期", "top_k": 99},
        )
        assert resp.status_code == 400

    def test_invalid_retrieval_mode(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        resp = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "保修期", "retrieval_mode": "magic"},
        )
        assert resp.status_code == 400

    def test_vector_and_keyword_modes_work(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        for mode in ("vector", "keyword", "hybrid"):
            resp = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=demo_headers,
                json={"content": "开专票要满足什么条件？", "retrieval_mode": mode, "top_k": 2},
            )
            assert resp.status_code == 200, mode
            assert resp.json()["assistant_message"]["citations"]

    def test_document_ids_filter(self, client: TestClient, demo_headers: dict) -> None:
        documents = client.get("/api/v1/documents", headers=demo_headers).json()["items"]
        target = next(d for d in documents if "保修" in d["title"])
        cid = new_conversation(client, demo_headers)
        body = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？", "document_ids": [target["id"]], "top_k": 3},
        ).json()
        assert all(c["document_id"] == target["id"] for c in body["assistant_message"]["citations"])

    def test_hybrid_falls_back_to_vector_ranked_results(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        """回归护栏：关键词路对某文档零命中时，答案不能退化成"没检索到"。

        早期实现用 RRF 融合排名，关键词路为空会让整条结果集为空（实测表现：
        限定在某篇文档上提问，hybrid 直接答"知识库中没有相关内容"）。
        改成并集候选池后，向量路的低分候选仍会进入结果，由引用角标让人自行核对。
        """
        documents = client.get("/api/v1/documents", headers=demo_headers).json()["items"]
        spec = next(d for d in documents if "参数" in d["title"])
        cid = new_conversation(client, demo_headers)
        body = client.post(
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "退款什么时候到账？", "document_ids": [spec["id"]], "top_k": 3},
        ).json()
        message = body["assistant_message"]
        assert "没有检索到" not in message["content"]
        assert message["citations"]
        assert all(c["document_id"] == spec["id"] for c in message["citations"])


class TestAskStream:
    def test_event_sequence(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？", "stream": True, "top_k": 3},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())
        events = read_sse(body)
        names = [name for name, _ in events]
        assert names[0] == "meta"
        assert names[1] == "retrieval"
        assert names[-1] == "done"
        assert "delta" in names

    def test_meta_event_fields(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "保修期是多久？", "stream": True},
        ) as response:
            events = read_sse("".join(response.iter_text()))
        meta = events[0][1]
        assert set(meta) == {
            "conversation_id",
            "user_message_id",
            "assistant_message_id",
            "retrieval_mode",
            "top_k",
        }
        assert meta["conversation_id"] == cid

    def test_retrieval_event_fields(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "七天无理由退货运费谁承担？", "stream": True, "top_k": 2},
        ) as response:
            events = read_sse("".join(response.iter_text()))
        retrieval = events[1][1]
        assert retrieval["elapsed_ms"] >= 0
        assert len(retrieval["chunks"]) <= 2
        chunk = retrieval["chunks"][0]
        assert set(chunk) == {
            "chunk_id",
            "document_id",
            "document_title",
            "ord",
            "heading",
            "snippet",
            "score",
            "retrieval",
            "rank",
        }

    def test_delta_reassembles_to_stored_message(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？", "stream": True, "top_k": 2},
        ) as response:
            events = read_sse("".join(response.iter_text()))
        streamed = "".join(data["text"] for name, data in events if name == "delta")
        history = client.get(f"/api/v1/conversations/{cid}", headers=demo_headers).json()
        stored = history["conversation"]["messages"][-1]["content"]
        assert stored == streamed

    def test_done_event_usage(self, client: TestClient, demo_headers: dict) -> None:
        cid = new_conversation(client, demo_headers)
        with client.stream(
            "POST",
            f"/api/v1/conversations/{cid}/messages",
            headers=demo_headers,
            json={"content": "整机保修期是多久？", "stream": True},
        ) as response:
            events = read_sse("".join(response.iter_text()))
        done = next(data for name, data in events if name == "done")
        assert done["finish_reason"] == "stop"
        assert done["latency_ms"] >= 0
        assert set(done["usage"]) == {"prompt_chars", "completion_chars"}
        assert done["usage"]["completion_chars"] > 0

    def test_stream_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/conversations/1/messages", json={"content": "保修期", "stream": True}
        )
        assert resp.status_code == 401

    def test_stream_on_missing_conversation(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post(
            "/api/v1/conversations/999999/messages",
            headers=demo_headers,
            json={"content": "保修期", "stream": True},
        )
        assert resp.status_code == 404
