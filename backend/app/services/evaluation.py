"""离线检索评测（契约 §4.2 评测段 / §5.5）。

指标口径固定为：Recall@1/3/5/10、MRR、HitRate、平均延迟。
- ``rank`` = 第一条命中 gold 的位置（1-based），未命中为 None
- ``Recall@k`` = 命中且 rank<=k 的题目数 / 总题数
- ``MRR`` = mean(1/rank)，未命中按 0
- ``HitRate`` = 至少命中一条 gold 的题目数 / 总题数

这套指标可以直接跑在 seed 数据集上，把"混合检索 vs 纯向量"的差异量化出来，
是面试里最硬的证据之一（README 里的数字就来自这里）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import EvalDataset, EvalItem, EvalResult, EvalRun
from app.services.retrieval import retrieve

ALL_MODES = ("vector", "keyword", "hybrid")


@dataclass
class ItemOutcome:
    item_id: int
    question: str
    retrieved_chunk_ids: list[int]
    rank: int | None
    hit: bool
    latency_ms: int


def first_hit_rank(retrieved: list[int], gold: list[int]) -> int | None:
    gold_set = set(gold or [])
    if not gold_set:
        return None
    for position, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold_set:
            return position
    return None


def compute_metrics(outcomes: list[ItemOutcome]) -> dict:
    total = len(outcomes)
    if total == 0:
        return {
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "mrr": 0.0,
            "hit_rate": 0.0,
            "avg_latency_ms": 0.0,
            "item_count": 0,
        }

    def recall_at(k: int) -> float:
        return round(sum(1 for o in outcomes if o.rank is not None and o.rank <= k) / total, 4)

    mrr = round(sum(1.0 / o.rank for o in outcomes if o.rank) / total, 4)
    hit_rate = round(sum(1 for o in outcomes if o.hit) / total, 4)
    avg_latency = round(sum(o.latency_ms for o in outcomes) / total, 1)
    return {
        "recall_at_1": recall_at(1),
        "recall_at_3": recall_at(3),
        "recall_at_5": recall_at(5),
        "recall_at_10": recall_at(10),
        "mrr": mrr,
        "hit_rate": hit_rate,
        "avg_latency_ms": avg_latency,
        "item_count": total,
    }


def run_mode(
    db: Session,
    dataset: EvalDataset,
    user_id: int,
    mode: str,
    top_k: int = 5,
) -> tuple[dict, list[ItemOutcome], int]:
    items = (
        db.query(EvalItem)
        .filter(EvalItem.dataset_id == dataset.id)
        .order_by(EvalItem.id)
        .all()
    )
    outcomes: list[ItemOutcome] = []
    # 评测要求看得更远：召回@10 需要至少 10 条候选
    candidate_k = max(top_k, 10)
    started = time.perf_counter()
    for item in items:
        item_started = time.perf_counter()
        result = retrieve(db, user_id, item.question, mode=mode, top_k=candidate_k)
        latency = int((time.perf_counter() - item_started) * 1000)
        retrieved = result.chunk_ids[:top_k]
        rank = first_hit_rank(retrieved, list(item.gold_chunk_ids or []))
        outcomes.append(
            ItemOutcome(
                item_id=item.id,
                question=item.question,
                retrieved_chunk_ids=retrieved,
                rank=rank,
                hit=rank is not None,
                latency_ms=latency,
            )
        )
    duration_ms = int((time.perf_counter() - started) * 1000)
    return compute_metrics(outcomes), outcomes, duration_ms


def persist_run(
    db: Session,
    dataset: EvalDataset,
    mode: str,
    top_k: int,
    metrics: dict,
    outcomes: list[ItemOutcome],
    duration_ms: int,
    user_id: int | None = None,
) -> EvalRun:
    run = EvalRun(
        dataset_id=dataset.id,
        user_id=user_id,
        mode=mode,
        top_k=top_k,
        metrics=metrics,
        item_count=len(outcomes),
        duration_ms=duration_ms,
    )
    db.add(run)
    db.flush()
    for outcome in outcomes:
        db.add(
            EvalResult(
                run_id=run.id,
                item_id=outcome.item_id,
                retrieved_chunk_ids=outcome.retrieved_chunk_ids,
                rank=outcome.rank,
                hit=outcome.hit,
                latency_ms=outcome.latency_ms,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def run_evaluation(
    db: Session,
    dataset: EvalDataset,
    user_id: int,
    modes: list[str] | None = None,
    top_k: int = 5,
) -> list[EvalRun]:
    modes = modes or list(ALL_MODES)
    runs: list[EvalRun] = []
    for mode in modes:
        if mode not in ALL_MODES:
            raise ValueError(f"不支持的检索模式：{mode}")
        metrics, outcomes, duration_ms = run_mode(db, dataset, user_id, mode, top_k)
        runs.append(persist_run(db, dataset, mode, top_k, metrics, outcomes, duration_ms, user_id))
    return runs
