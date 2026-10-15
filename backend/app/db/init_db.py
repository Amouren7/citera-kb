"""建表、建扩展/索引、灌种子数据。

用法：
    python -m app.db.init_db            # 清点 + 灌种子（幂等）
    python -m app.db.init_db --no-seed  # 只建表与索引

幂等性：重复执行不会产生重复用户、重复文档或重复题目；
已存在的演示文档会按最新种子内容重新切分并重建向量。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.seed_demo import (
    DEMO_DATASET_DESCRIPTION,
    DEMO_DATASET_NAME,
    DEMO_DOCUMENTS,
    DEMO_EVAL_QUESTIONS,
    DEMO_PARAPHRASE_QUESTIONS,
)
from app.db.session import SessionLocal, engine
from app.models import ALL_MODELS, AppSetting, EvalDataset, EvalItem, User  # noqa: F401
from app.db.base import Base
from app.services.ingest import build_chunks

logger = logging.getLogger("citera.init")

PG_EXTENSIONS = ("vector", "pg_trgm")

PG_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON document_chunks "
    "USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS ix_chunks_content_trgm ON document_chunks "
    "USING gin (content gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON document_chunks USING gin (to_tsvector('simple', content))",
)


def create_extensions() -> list[str]:
    done: list[str] = []
    if not settings.is_postgres:
        return done
    with engine.begin() as conn:
        for ext in PG_EXTENSIONS:
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
            done.append(ext)
    return done


def run_migrations() -> None:
    """用 Alembic 迁移建表（生产路径，契约 §8.1 要求"空库一次成功"）。"""
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[2]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")


def create_schema() -> None:
    """建表：PostgreSQL 走迁移，SQLite（测试）走 create_all。

    两者最终表结构一致——迁移文件就是按同一套模型写的，且 CI 会在
    PostgreSQL 上显式跑一遍 ``alembic upgrade head`` 来证明这一点。
    """
    if settings.is_postgres:
        run_migrations()
        with engine.begin() as conn:
            for statement in PG_STATEMENTS:
                conn.execute(text(statement))
    else:
        Base.metadata.create_all(bind=engine)


def ensure_user(db: Session, email: str, password: str, display_name: str, role: str) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        # 密码可能被改过；种子账号保持可预期的登录体验
        existing.password_hash = hash_password(password)
        existing.display_name = display_name
        existing.role = role
        existing.is_active = True
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def score_chunk(content: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in content)


def pick_gold_chunks(db: Session, document, keywords: list[str]) -> list[int]:  # noqa: ANN001
    from app.models import DocumentChunk

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.ord.asc())
        .all()
    )
    scored = [(score_chunk(chunk.content, keywords), chunk.id) for chunk in chunks]
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score = scored[0][0] if scored else 0
    if best_score == 0:
        # 关键词一个都没命中：退化为第一个块，保证评测有 gold 而不是空集
        return [scored[0][1]] if scored else []
    return [chunk_id for score, chunk_id in scored if score == best_score][:2]


def seed_documents(db: Session, user: User) -> tuple[int, int]:
    """返回 (新建文档数, 重建向量与切分的文档数)。

    幂等性关键：**已就绪且切分参数未变的文档不重建**。早期版本每次调用都把 chunks
    删掉重建，导致 chunk 主键变化、评测题的 gold_chunk_ids 全部失效（实测评测
    指标直接归零）——所以这里必须按状态与参数快照判断是否需要重建。
    """
    from app.models import Document, DocumentChunk

    created = 0
    rebuilt = 0
    for spec in DEMO_DOCUMENTS:
        document = (
            db.query(Document)
            .filter(Document.user_id == user.id, Document.title == spec["title"])
            .first()
        )
        if document is None:
            document = Document(
                user_id=user.id,
                title=spec["title"],
                source_type="seed",
                filename=f"{spec['code']}.md",
                mime_type="text/markdown",
                size_bytes=len(spec["content"].encode("utf-8")),
                status="pending",
                chunk_count=0,
                char_count=0,
                meta={"seed_code": spec["code"], "fictional": True},
            )
            db.add(document)
            db.commit()
            db.refresh(document)
            created += 1
        else:
            if document.deleted_at is not None:
                document.deleted_at = None
                db.add(document)
                db.commit()

            meta = document.meta or {}
            chunk_rows = (
                db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
            )
            needs_rebuild = (
                document.status != "ready"
                or chunk_rows == 0
                or meta.get("chunk_size") != settings.chunk_size
                or meta.get("chunk_overlap") != settings.chunk_overlap
            )
            if not needs_rebuild:
                continue
            document.status = "pending"
            document.error_message = None
            db.add(document)
            db.commit()
            rebuilt += 1

        build_chunks(db, document, spec["content"])
        document.status = "ready"
        db.add(document)
        db.commit()
    return created, rebuilt


def prune_stale_seed_datasets(db: Session) -> int:
    """删除名字与当前种子不一致的评测数据集，避免旧版本遗留数据混进对比。"""
    stale = db.query(EvalDataset).filter(EvalDataset.name != DEMO_DATASET_NAME).all()
    for dataset in stale:
        db.delete(dataset)
    if stale:
        db.commit()
    return len(stale)


def seed_eval_dataset(db: Session, user: User) -> tuple[int, int]:
    from app.models import Document

    dataset = db.query(EvalDataset).filter(EvalDataset.name == DEMO_DATASET_NAME).first()
    if dataset is None:
        dataset = EvalDataset(
            name=DEMO_DATASET_NAME,
            description=DEMO_DATASET_DESCRIPTION,
            is_seed=True,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

    documents = {
        spec["code"]: db.query(Document)
        .filter(Document.user_id == user.id, Document.title == spec["title"])
        .first()
        for spec in DEMO_DOCUMENTS
    }

    db.query(EvalItem).filter(EvalItem.dataset_id == dataset.id).delete()
    db.commit()

    from app.models import DocumentChunk

    def doc_chunks(document) -> list[int]:  # noqa: ANN001
        return [
            chunk_id
            for (chunk_id,) in db.query(DocumentChunk.id)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.ord.asc())
            .all()
        ]

    for index, question in enumerate(DEMO_EVAL_QUESTIONS):
        document = documents.get(question["doc"])
        if document is None:
            logger.warning("评测题引用的文档不存在：%s", question["doc"])
            continue
        gold_ids = pick_gold_chunks(db, document, question["kw"])
        db.add(
            EvalItem(
                dataset_id=dataset.id,
                question=question["q"],
                gold_chunk_ids=gold_ids,
                gold_document_titles=[document.title],
                tags=[question["doc"], f"q{index + 1:02d}", "原文措辞"],
            )
        )

    for index, question in enumerate(DEMO_PARAPHRASE_QUESTIONS):
        document = documents.get(question["doc"])
        if document is None:
            logger.warning("改写题引用的文档不存在：%s", question["doc"])
            continue
        db.add(
            EvalItem(
                dataset_id=dataset.id,
                question=question["q"],
                # 改写问句无法唯一定位 chunk，gold 取该文档全部块（文档级口径）
                gold_chunk_ids=doc_chunks(document),
                gold_document_titles=[document.title],
                tags=[question["doc"], f"p{index + 1:02d}", question["tag"]],
            )
        )
    db.commit()
    item_count = db.query(EvalItem).filter(EvalItem.dataset_id == dataset.id).count()
    return dataset.id, item_count


def seed_settings(db: Session) -> int:
    defaults = {
        "retrieval_mode": "hybrid",
        "top_k": 5,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "registration_open": True,
    }
    written = 0
    for key, value in defaults.items():
        if db.get(AppSetting, key) is None:
            db.add(AppSetting(key=key, value={"value": value}))
            written += 1
    db.commit()
    return written


def seed_all(db: Session) -> dict:
    admin = ensure_user(db, settings.admin_email, settings.admin_password, "管理员", "admin")
    demo = ensure_user(db, settings.demo_email, settings.demo_password, "演示用户", "user")
    pruned = prune_stale_seed_datasets(db)
    created, rebuilt = seed_documents(db, demo)
    dataset_id, item_count = seed_eval_dataset(db, demo)
    settings_written = seed_settings(db)
    return {
        "users": [admin.email, demo.email],
        "documents_created": created,
        "documents_rebuilt": rebuilt,
        "stale_datasets_pruned": pruned,
        "dataset_id": dataset_id,
        "eval_items": item_count,
        "settings_written": settings_written,
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    parser = argparse.ArgumentParser(description="Citera 数据库初始化")
    parser.add_argument("--no-seed", action="store_true", help="只建表与索引，不灌种子数据")
    args = parser.parse_args(argv)

    extensions = create_extensions()
    create_schema()
    logger.info("数据库：%s", settings.database_url.split("@")[-1])
    logger.info("扩展：%s", ", ".join(extensions) if extensions else "（SQLite，跳过）")

    if args.no_seed:
        logger.info("建表完成，按 --no-seed 跳过种子数据")
        return 0

    if not settings.seed_demo_data:
        logger.info("SEED_DEMO_DATA=false，跳过种子数据")
        return 0

    db = SessionLocal()
    try:
        summary = seed_all(db)
    finally:
        db.close()
    logger.info("种子完成：%s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
