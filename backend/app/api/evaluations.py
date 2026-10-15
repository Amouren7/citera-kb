"""评测接口（契约 §4.2 评测段）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.models import EvalDataset, EvalItem, EvalResult, EvalRun
from app.schemas import (
    EvalCompareOut,
    EvalDatasetOut,
    EvalItemCompare,
    EvalItemOut,
    EvalMetrics,
    EvalPerRun,
    EvalRunEnvelope,
    EvalRunOut,
    EvalRunRequest,
    Page,
)

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


def _dataset_out(db: DbSession, dataset: EvalDataset) -> EvalDatasetOut:
    count = db.query(EvalItem).filter(EvalItem.dataset_id == dataset.id).count()
    return EvalDatasetOut(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        is_seed=dataset.is_seed,
        created_at=dataset.created_at,
        item_count=count,
    )


def _run_out(run: EvalRun) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        dataset_id=run.dataset_id,
        mode=run.mode,
        top_k=run.top_k,
        metrics=EvalMetrics(**run.metrics),
        item_count=run.item_count,
        duration_ms=run.duration_ms,
        created_at=run.created_at,
    )


def _get_dataset(db: DbSession, dataset_id: int) -> EvalDataset:
    dataset = db.get(EvalDataset, dataset_id)
    if dataset is None:
        raise AppError("not_found", "评测数据集不存在")
    return dataset


@router.get("/datasets", response_model=list[EvalDatasetOut])
def list_datasets(db: DbSession, user: CurrentUser) -> list[EvalDatasetOut]:
    rows = db.query(EvalDataset).order_by(EvalDataset.id.asc()).all()
    return [_dataset_out(db, d) for d in rows]


@router.get("/datasets/{dataset_id}/items", response_model=Page)
def list_items(
    dataset_id: int,
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    dataset = _get_dataset(db, dataset_id)
    query = db.query(EvalItem).filter(EvalItem.dataset_id == dataset.id)
    total = query.count()
    rows = query.order_by(EvalItem.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(
        items=[EvalItemOut.model_validate(item).model_dump(mode="json") for item in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/run", response_model=EvalRunEnvelope)
def run_evaluation(payload: EvalRunRequest, db: DbSession, user: CurrentUser) -> EvalRunEnvelope:
    from app.services.evaluation import run_evaluation as _run

    dataset = _get_dataset(db, payload.dataset_id)
    item_count = db.query(EvalItem).filter(EvalItem.dataset_id == dataset.id).count()
    if item_count == 0:
        raise AppError("bad_request", "该数据集没有题目，无法评测")

    runs = _run(db, dataset, user.id, modes=payload.modes, top_k=payload.top_k)
    return EvalRunEnvelope(runs=[_run_out(run) for run in runs])


@router.get("/runs", response_model=Page)
def list_runs(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    query = db.query(EvalRun)
    total = query.count()
    rows = (
        query.order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page(
        items=[_run_out(run).model_dump(mode="json") for run in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/runs/compare", response_model=EvalCompareOut)
def compare_runs(ids: str, db: DbSession, user: CurrentUser) -> EvalCompareOut:
    try:
        run_ids = [int(part) for part in ids.split(",") if part.strip()]
    except ValueError as exc:
        raise AppError("bad_request", "ids 必须是逗号分隔的整数") from exc
    if not run_ids:
        raise AppError("bad_request", "请至少指定一个 run id")
    if len(run_ids) > 6:
        raise AppError("bad_request", "一次最多对比 6 个 run")

    runs = db.query(EvalRun).filter(EvalRun.id.in_(run_ids)).all()
    if len(runs) != len(set(run_ids)):
        raise AppError("not_found", "部分 run 不存在")
    runs.sort(key=lambda r: run_ids.index(r.id))

    results = db.query(EvalResult).filter(EvalResult.run_id.in_(run_ids)).all()
    by_item: dict[int, list[EvalResult]] = {}
    for result in results:
        by_item.setdefault(result.item_id, []).append(result)

    item_rows = (
        db.query(EvalItem)
        .filter(EvalItem.id.in_(list(by_item.keys())))
        .order_by(EvalItem.id.asc())
        .all()
    )
    items: list[EvalItemCompare] = []
    for item in item_rows:
        per_run = []
        for run in runs:
            match = next((r for r in by_item[item.id] if r.run_id == run.id), None)
            per_run.append(
                EvalPerRun(
                    run_id=run.id,
                    rank=match.rank if match else None,
                    hit=bool(match.hit) if match else False,
                )
            )
        items.append(EvalItemCompare(item_id=item.id, question=item.question, per_run=per_run))

    return EvalCompareOut(runs=[_run_out(run) for run in runs], items=items)
