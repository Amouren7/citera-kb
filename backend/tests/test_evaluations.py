"""评测接口与指标计算。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.evaluation import ItemOutcome, compute_metrics, first_hit_rank

METRIC_KEYS = {
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "recall_at_10",
    "mrr",
    "hit_rate",
    "avg_latency_ms",
    "item_count",
}


def outcome(item_id: int, retrieved: list[int], gold: list[int], latency: int = 10) -> ItemOutcome:
    rank = first_hit_rank(retrieved, gold)
    return ItemOutcome(item_id, f"q{item_id}", retrieved, rank, rank is not None, latency)


class TestFirstHitRank:
    def test_hit_at_first(self) -> None:
        assert first_hit_rank([5, 6, 7], [5]) == 1

    def test_hit_later(self) -> None:
        assert first_hit_rank([5, 6, 7], [7]) == 3

    def test_miss_returns_none(self) -> None:
        assert first_hit_rank([5, 6], [9]) is None

    def test_multiple_gold_takes_best_rank(self) -> None:
        assert first_hit_rank([5, 6, 7], [7, 6]) == 2

    def test_empty_gold(self) -> None:
        assert first_hit_rank([1, 2], []) is None

    def test_empty_retrieved(self) -> None:
        assert first_hit_rank([], [1]) is None


class TestComputeMetrics:
    def test_perfect_scores(self) -> None:
        metrics = compute_metrics([outcome(1, [1, 2], [1]), outcome(2, [3, 4], [3])])
        assert metrics["recall_at_1"] == 1.0
        assert metrics["mrr"] == 1.0
        assert metrics["hit_rate"] == 1.0

    def test_all_miss(self) -> None:
        metrics = compute_metrics([outcome(1, [1], [9]), outcome(2, [2], [9])])
        assert metrics["recall_at_10"] == 0.0
        assert metrics["mrr"] == 0.0
        assert metrics["hit_rate"] == 0.0

    def test_recall_at_k_is_monotonic(self) -> None:
        outcomes = [outcome(1, [1, 2, 3, 4, 5], [5]), outcome(2, [9], [1])]
        metrics = compute_metrics(outcomes)
        assert metrics["recall_at_1"] <= metrics["recall_at_3"]
        assert metrics["recall_at_3"] <= metrics["recall_at_5"]
        assert metrics["recall_at_5"] <= metrics["recall_at_10"]

    def test_mrr_uses_reciprocal_rank(self) -> None:
        metrics = compute_metrics([outcome(1, [1, 2], [2]), outcome(2, [1], [1])])
        assert metrics["mrr"] == round((0.5 + 1.0) / 2, 4)

    def test_avg_latency(self) -> None:
        metrics = compute_metrics([outcome(1, [1], [1], 10), outcome(2, [1], [1], 30)])
        assert metrics["avg_latency_ms"] == 20.0

    def test_empty_input(self) -> None:
        metrics = compute_metrics([])
        assert metrics["item_count"] == 0
        assert metrics["mrr"] == 0.0
        assert set(metrics) == METRIC_KEYS

    def test_hit_rate_can_exceed_recall_at_1(self) -> None:
        metrics = compute_metrics([outcome(1, [1, 2], [2])])
        assert metrics["hit_rate"] == 1.0
        assert metrics["recall_at_1"] == 0.0


class TestEvaluationApi:
    def _dataset_id(self, client: TestClient, headers: dict) -> int:
        datasets = client.get("/api/v1/evaluations/datasets", headers=headers).json()
        assert datasets
        return datasets[0]["id"]

    def test_list_datasets(self, client: TestClient, demo_headers: dict) -> None:
        datasets = client.get("/api/v1/evaluations/datasets", headers=demo_headers).json()
        assert datasets[0]["item_count"] >= 20
        assert datasets[0]["is_seed"] is True

    def test_list_items_pagination(self, client: TestClient, demo_headers: dict) -> None:
        dataset_id = self._dataset_id(client, demo_headers)
        body = client.get(
            f"/api/v1/evaluations/datasets/{dataset_id}/items",
            headers=demo_headers,
            params={"page_size": 5},
        ).json()
        assert body["total"] >= 20
        assert len(body["items"]) == 5
        assert body["items"][0]["gold_chunk_ids"]

    def test_run_all_modes(self, client: TestClient, demo_headers: dict) -> None:
        dataset_id = self._dataset_id(client, demo_headers)
        resp = client.post(
            "/api/v1/evaluations/run",
            headers=demo_headers,
            json={"dataset_id": dataset_id, "modes": ["vector", "keyword", "hybrid"], "top_k": 5},
        )
        assert resp.status_code == 200, resp.text
        runs = resp.json()["runs"]
        assert [run["mode"] for run in runs] == ["vector", "keyword", "hybrid"]
        for run in runs:
            assert set(run["metrics"]) == METRIC_KEYS
            assert run["item_count"] >= 20
            # 契约 §4.2 要求对外字段是 run_id，同时保留 id 以与其它资源写法一致
            assert run["run_id"] == run["id"]
            assert run["run_id"] > 0

    def test_run_single_mode_dedupes(self, client: TestClient, demo_headers: dict) -> None:
        dataset_id = self._dataset_id(client, demo_headers)
        resp = client.post(
            "/api/v1/evaluations/run",
            headers=demo_headers,
            json={"dataset_id": dataset_id, "modes": ["hybrid", "hybrid"]},
        )
        assert len(resp.json()["runs"]) == 1

    def test_run_empty_modes_rejected(self, client: TestClient, demo_headers: dict) -> None:
        dataset_id = self._dataset_id(client, demo_headers)
        resp = client.post(
            "/api/v1/evaluations/run",
            headers=demo_headers,
            json={"dataset_id": dataset_id, "modes": []},
        )
        assert resp.status_code == 400

    def test_run_missing_dataset(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.post(
            "/api/v1/evaluations/run", headers=demo_headers, json={"dataset_id": 999999}
        )
        assert resp.status_code == 404

    def test_runs_history_and_compare(self, client: TestClient, demo_headers: dict) -> None:
        dataset_id = self._dataset_id(client, demo_headers)
        created = client.post(
            "/api/v1/evaluations/run",
            headers=demo_headers,
            json={"dataset_id": dataset_id, "modes": ["vector", "hybrid"]},
        ).json()["runs"]
        run_ids = [run["id"] for run in created]

        history = client.get("/api/v1/evaluations/runs", headers=demo_headers).json()
        assert history["total"] >= 2

        compare = client.get(
            "/api/v1/evaluations/runs/compare",
            headers=demo_headers,
            params={"ids": ",".join(str(i) for i in run_ids)},
        )
        assert compare.status_code == 200
        body = compare.json()
        assert [run["id"] for run in body["runs"]] == run_ids
        assert [run["run_id"] for run in body["runs"]] == run_ids
        assert body["items"]
        assert len(body["items"][0]["per_run"]) == 2
        assert [entry["run_id"] for entry in body["items"][0]["per_run"]] == run_ids

    def test_compare_bad_ids(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.get(
            "/api/v1/evaluations/runs/compare", headers=demo_headers, params={"ids": "abc"}
        )
        assert resp.status_code == 400

    def test_compare_missing_run(self, client: TestClient, demo_headers: dict) -> None:
        resp = client.get(
            "/api/v1/evaluations/runs/compare", headers=demo_headers, params={"ids": "999999"}
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/evaluations/datasets").status_code == 401

    def test_hybrid_is_not_worse_than_vector_on_keyword_queries(
        self, client: TestClient, demo_headers: dict
    ) -> None:
        """回归护栏：混合检索至少要强于纯向量（这是混合检索的存在理由）。

        早期版本用 min-max 分数混合，hybrid 的 R@1 反而低于纯关键词（0.86 vs 0.93）；
        改成并集候选池 + 名次级重排后，hybrid 必须 >= 纯向量。若这条测试红了，
        说明检索参数被改坏了。
        """
        dataset_id = self._dataset_id(client, demo_headers)
        runs = client.post(
            "/api/v1/evaluations/run",
            headers=demo_headers,
            json={"dataset_id": dataset_id, "modes": ["vector", "hybrid"], "top_k": 5},
        ).json()["runs"]
        vector_metrics = next(run["metrics"] for run in runs if run["mode"] == "vector")
        hybrid_metrics = next(run["metrics"] for run in runs if run["mode"] == "hybrid")
        assert hybrid_metrics["recall_at_1"] >= vector_metrics["recall_at_1"], (
            f"hybrid R@1 {hybrid_metrics['recall_at_1']} < vector R@1 {vector_metrics['recall_at_1']}"
        )
        assert hybrid_metrics["mrr"] >= vector_metrics["mrr"]
