"""PostgreSQL + pgvector 集成测试（默认跳过）。

启用方式：
    $env:CITERA_TEST_PG=1
    $env:DATABASE_URL="postgresql+psycopg://citera:citera@localhost:55432/citera_test"
    pytest tests/test_postgres.py -v

覆盖"迁移从空库一次成功"这条硬验收（契约 §8.1），以及生产路径特有的
`vector(384)` 列、HNSW 索引、jsonb、bigint[] 与 pgvector `<=>` 检索。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect, text

from app.core.config import settings

pytestmark = pytest.mark.postgres

if os.environ.get("CITERA_TEST_PG") != "1":
    pytest.skip("需要真实 PostgreSQL：设 CITERA_TEST_PG=1 启用", allow_module_level=True)

if not settings.is_postgres:
    pytest.skip("DATABASE_URL 不是 PostgreSQL 连接串", allow_module_level=True)


@pytest.fixture(scope="module")
def pg_engine():
    from app.db.session import engine

    yield engine
    engine.dispose()


class TestMigrationFromEmptyDatabase:
    def test_alembic_upgrade_head_created_all_tables(self, pg_engine) -> None:
        """CI 里在迁移前会 DROP SCHEMA，因此这里断言的是迁移后的完整表集合。"""
        from app.db.init_db import run_migrations

        run_migrations()
        tables = set(inspect(pg_engine).get_table_names())
        expected = {
            "users",
            "documents",
            "document_chunks",
            "conversations",
            "messages",
            "eval_datasets",
            "eval_items",
            "eval_runs",
            "eval_results",
            "app_settings",
            "alembic_version",
        }
        assert expected <= tables

    def test_extensions_installed(self, pg_engine) -> None:
        with pg_engine.begin() as conn:
            names = {row[0] for row in conn.execute(text("select extname from pg_extension"))}
        assert "vector" in names
        assert "pg_trgm" in names

    def test_embedding_column_is_native_vector(self, pg_engine) -> None:
        with pg_engine.begin() as conn:
            column_type = conn.execute(
                text(
                    "select format_type(atttypid, atttypmod) from pg_attribute "
                    "where attrelid = 'document_chunks'::regclass and attname = 'embedding'"
                )
            ).scalar()
        assert column_type == f"vector({settings.embedding_dim})"

    def test_json_and_array_columns(self, pg_engine) -> None:
        with pg_engine.begin() as conn:
            citations = conn.execute(
                text(
                    "select format_type(atttypid, atttypmod) from pg_attribute "
                    "where attrelid = 'messages'::regclass and attname = 'citations'"
                )
            ).scalar()
            gold = conn.execute(
                text(
                    "select format_type(atttypid, atttypmod) from pg_attribute "
                    "where attrelid = 'eval_items'::regclass and attname = 'gold_chunk_ids'"
                )
            ).scalar()
        assert citations == "jsonb"
        assert gold == "bigint[]"

    def test_hnsw_and_gin_indexes_exist(self, pg_engine) -> None:
        with pg_engine.begin() as conn:
            indexes = {
                row[0]
                for row in conn.execute(
                    text("select indexname from pg_indexes where tablename = 'document_chunks'")
                )
            }
        assert "ix_chunks_embedding_hnsw" in indexes
        assert "ix_chunks_content_trgm" in indexes


class TestProductionRetrievalPath:
    def test_pgvector_cosine_operator_round_trip(self, pg_engine) -> None:
        """证明向量确实以 pgvector 原生格式存取，且 `<=>` 可用。"""
        from app.services.embedding import embed_text

        vector = embed_text("整机保修期为自签收之日起 12 个月")
        with pg_engine.begin() as conn:
            distance = conn.execute(
                text("select (:v)::vector <=> (:v)::vector as d"),
                {"v": "[" + ",".join(str(x) for x in vector) + "]"},
            ).scalar()
        assert float(distance) == pytest.approx(0.0, abs=1e-6)

    def test_seed_then_retrieve(self, pg_engine) -> None:
        """真实 PG 上跑一遍种子与检索，确保生产路径与 SQLite 口径一致。"""
        from app.db.init_db import create_extensions, create_schema, seed_all
        from app.db.session import SessionLocal
        from app.models import User
        from app.services.retrieval import hybrid_rerank, candidate_pool, keyword_search, vector_search
        from app.services.evaluation import first_hit_rank

        create_extensions()
        create_schema()
        db = SessionLocal()
        try:
            seed_all(db)
            demo = db.query(User).filter(User.email == settings.demo_email).one()
            query = "七天无理由退货的运费由谁承担？"
            candidates = candidate_pool(
                {
                    "vector": vector_search(db, demo.id, query, 20),
                    "keyword": keyword_search(db, demo.id, query, 20),
                },
                limit=20,
            )
            assert candidates, "PostgreSQL 检索路径不应返回空候选"
            ordered = hybrid_rerank(candidates, query, 5)
            assert ordered
            assert [c.rank for c in ordered] == list(range(1, len(ordered) + 1))
            gold = next(
                (
                    item
                    for item in candidates
                    if "无理由退货" in item.content
                ),
                None,
            )
            assert gold is not None
            assert first_hit_rank([c.chunk_id for c in ordered], [gold.chunk_id]) is not None
        finally:
            db.close()
