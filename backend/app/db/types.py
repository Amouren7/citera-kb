"""跨数据库兼容的自定义列类型。

生产环境是 PostgreSQL + pgvector；单元测试用 SQLite（不依赖 Docker），
因此向量与数组需要两种底层表示：
- ``VectorType`` → PostgreSQL 用 pgvector 的 ``vector(dim)``；SQLite 用 JSON 字符串
- ``ArrayType``  → PostgreSQL 用 ``bigint[]`` / ``text[]``；SQLite 用 JSON 字符串

向量相似度计算同样分两条路：PostgreSQL 用 ``<=>`` 走 HNSW 索引，
SQLite 用 numpy 在 Python 层算——见 app/services/retrieval.py。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.types import TypeDecorator

try:  # pgvector 在 SQLite 测试环境里不是必需的
    from pgvector.sqlalchemy import Vector as _PgVector
except Exception:  # pragma: no cover - 仅在缺依赖时触发
    _PgVector = None


class VectorType(TypeDecorator):
    """向量列：PG 原生 vector(dim)，SQLite 存 JSON 文本。"""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            if _PgVector is None:  # pragma: no cover
                raise RuntimeError("PostgreSQL 需要安装 pgvector 包")
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        vec = [float(x) for x in value]
        if dialect.name == "postgresql":
            return vec
        return json.dumps(vec, separators=(",", ":"))

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            return [float(x) for x in json.loads(value)]
        return [float(x) for x in value]


class ArrayType(TypeDecorator):
    """数组列：PG 用原生 ARRAY，SQLite 用 JSON 字符串。"""

    impl = Text
    cache_ok = True

    def __init__(self, item_type: str = "bigint") -> None:
        self.item_type = item_type
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import ARRAY
            from sqlalchemy import BigInteger

            inner = BigInteger() if self.item_type == "bigint" else String()
            return dialect.type_descriptor(ARRAY(inner))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        seq = list(value)
        if dialect.name == "postgresql":
            return seq
        return json.dumps(seq, ensure_ascii=False)

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return []
        if isinstance(value, str):
            return json.loads(value)
        return list(value)


class JSONText(TypeDecorator):
    """JSON 列：PG 用 jsonb，SQLite 用 TEXT（SQLAlchemy 的 JSON 在两边都能用，这里显式化）。"""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return {} if dialect.name != "sqlite" else "{}"
        if dialect.name == "postgresql":
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return {}
        if isinstance(value, str):
            return json.loads(value)
        return value
