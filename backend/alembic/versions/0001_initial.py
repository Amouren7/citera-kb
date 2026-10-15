"""初始建表迁移（契约 §3 全量模型）。

写法说明：为了让**同一份迁移**既能跑在 PostgreSQL（生产）又能跑在 SQLite（测试），
列类型与 server_default 均按方言分支解析：
- 向量列：PG 用 pgvector `vector(384)`，SQLite 用 TEXT（存 JSON）
- 数组列：PG 用原生 ARRAY，SQLite 用 TEXT
- JSON 列：PG 用 jsonb，SQLite 用 TEXT
- 默认值：PG 需要 `'{}'::jsonb` / `'{}'::bigint[]` 这类显式 cast，SQLite 用 `'{}'` / `'[]'`
- 索引：HNSW 与 GIN 只在 PostgreSQL 上创建，SQLite 跳过

生产环境的扩展与 HNSW/GIN 索引同时由 `app.db.init_db.create_schema()` 幂等创建。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def _pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _vector_type():  # noqa: ANN202
    if _pg():
        from pgvector.sqlalchemy import Vector

        return Vector(EMBEDDING_DIM)
    return sa.Text()


def _array_type(inner):  # noqa: ANN001, ANN202
    if _pg():
        from sqlalchemy.dialects.postgresql import ARRAY

        return ARRAY(inner)
    return sa.Text()


def _json_type():  # noqa: ANN202
    if _pg():
        from sqlalchemy.dialects.postgresql import JSONB

        return JSONB()
    return sa.Text()


def _json_default(kind: str = "object"):  # noqa: ANN202
    """JSON 列的 server_default 必须带方言 cast，否则 PG 会把 '{}' 当 jsonb 解析失败。"""
    if _pg():
        return sa.text("'{}'::jsonb" if kind == "object" else "'[]'::jsonb")
    return sa.text("'{}'" if kind == "object" else "'[]'")


def _array_default(inner: str = "bigint"):  # noqa: ANN202
    """数组列同理：PG 需要 '{}'::bigint[] 这种显式形式。"""
    if _pg():
        return sa.text(f"'{{}}'::{inner}[]")
    return sa.text("'[]'")


def _big_int():  # noqa: ANN202
    return sa.BigInteger().with_variant(sa.Integer, "sqlite")


def upgrade() -> None:
    if _pg():
        # 迁移自带扩展创建，保证"空库 → alembic upgrade head"一步到位
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "documents",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column("user_id", _big_int(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="upload"),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", _big_int(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", _json_type(), nullable=False, server_default=_json_default("object")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_user_deleted", "documents", ["user_id", "deleted_at"])

    op.create_table(
        "document_chunks",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column(
            "document_id", _big_int(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", _big_int(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("heading", sa.String(255), nullable=True),
        sa.Column("embedding", _vector_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
    op.create_index("ix_chunks_document_ord", "document_chunks", ["document_id", "ord"])

    op.create_table(
        "conversations",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column("user_id", _big_int(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default="新会话"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column(
            "conversation_id",
            _big_int(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", _big_int(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations", _json_type(), nullable=False, server_default=_json_default("array")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])

    op.create_table(
        "eval_datasets",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_eval_datasets_name"),
    )

    op.create_table(
        "eval_items",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column(
            "dataset_id", _big_int(), sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "gold_chunk_ids",
            _array_type(sa.BigInteger()),
            nullable=False,
            server_default=_array_default("bigint"),
        ),
        sa.Column(
            "gold_document_titles",
            _array_type(sa.String()),
            nullable=False,
            server_default=_array_default("text"),
        ),
        sa.Column("tags", _array_type(sa.String()), nullable=False, server_default=_array_default("text")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_eval_items_dataset_id", "eval_items", ["dataset_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column(
            "dataset_id", _big_int(), sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", _big_int(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metrics", _json_type(), nullable=False, server_default=_json_default("object")),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])

    op.create_table(
        "eval_results",
        sa.Column("id", _big_int(), primary_key=True),
        sa.Column("run_id", _big_int(), sa.ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "item_id", _big_int(), sa.ForeignKey("eval_items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "retrieved_chunk_ids",
            _array_type(sa.BigInteger()),
            nullable=False,
            server_default=_array_default("bigint"),
        ),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", _json_type(), nullable=False, server_default=_json_default("object")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    if _pg():
        # 向量索引与中文兜底索引只在 PostgreSQL 上建
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON document_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_chunks_content_trgm ON document_chunks "
            "USING gin (content gin_trgm_ops)"
        )


def downgrade() -> None:
    if _pg():
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_chunks_content_trgm")
    for table in (
        "eval_results",
        "eval_runs",
        "eval_items",
        "eval_datasets",
        "messages",
        "conversations",
        "document_chunks",
        "documents",
        "app_settings",
        "users",
    ):
        op.drop_table(table)
