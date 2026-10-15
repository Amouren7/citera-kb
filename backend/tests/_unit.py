"""单元测试公共工具：不依赖数据库的轻量对象。

RRF 融合、切片、回答合成这些纯函数逻辑用假的 chunk 对象测试，
跑得快且不引入数据库噪声；涉及 SQL 的部分放到集成测试里。
"""

from __future__ import annotations

from app.services.retrieval import RankedChunk


class FakeChunk:
    """模拟 ORM 的 DocumentChunk，只提供检索层需要的属性。"""

    def __init__(
        self,
        chunk_id: int,
        content: str,
        document_id: int = 1,
        ord: int = 1,
        heading: str | None = None,
        embedding: list[float] | None = None,
    ) -> None:
        self.id = chunk_id
        self.document_id = document_id
        self.ord = ord
        self.heading = heading
        self.content = content
        self.embedding = embedding


def make_ranked(
    chunk_id: int,
    content: str = "内容",
    title: str = "文档",
    score: float = 0.5,
    retrieval: str = "vector",
    rank: int = 1,
    document_id: int = 1,
    ord: int = 1,
    heading: str | None = None,
) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title=title,
        ord=ord,
        heading=heading,
        content=content,
        score=score,
        retrieval=retrieval,
        rank=rank,
    )
