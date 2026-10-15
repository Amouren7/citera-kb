"""检索与排名融合（契约 §5.1 / §5.5）。

三路检索：
- ``vector``：向量余弦相似度。PostgreSQL 走 pgvector `<=>` + HNSW 索引；SQLite 走 Python 余弦。
- ``keyword``：关键词召回。PostgreSQL 走 `ts_rank_cd` + pg_trgm；SQLite 走 Python 词重叠打分。
- ``hybrid``：两路候选做 RRF 融合，RRF 名次写在 citations 里，面试可以照着代码讲。

RRF 公式：``score(d) = Σ 1 / (k + rank_r(d))``，k 默认 60。
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document, DocumentChunk
from app.services.embedding import cosine_similarity, embed_text

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")

_CN_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "有", "我", "你", "他", "它", "们", "吗", "呢", "吧",
    "请问", "怎么", "如何", "什么", "多少", "哪", "哪个", "哪些", "可以", "是否", "需要", "以及",
    "为", "对", "从", "到", "被", "把", "就", "都", "还", "也", "要", "会", "一个", "这个", "那个",
}


def tokenize(text: str) -> list[str]:
    """中英混排分词：英文数字按词，中文按字。"""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _CN_STOPWORDS]


def query_terms(text: str) -> list[str]:
    """查询词：单字 + 相邻二元组，提升中文短语召回。"""
    base = tokenize(text)
    terms = list(dict.fromkeys(base))
    for i in range(len(base) - 1):
        terms.append(base[i] + base[i + 1])
    return terms


def _term_set(text: str) -> set[str]:
    """文档侧词集：**单字 + 相邻二元组**。

    必须与 ``query_terms()`` 的口径一致——只放单字的话，两字以上的查询词
    在文档侧永远匹配不上（这是实现中真实踩过的坑：关键词路整路返回空，
    评测 R@1 掉到 0.07）。
    """
    raw = [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _CN_STOPWORDS]
    terms = set(raw)
    terms.update(raw[i] + raw[i + 1] for i in range(len(raw) - 1))
    return terms


@dataclass
class RankedChunk:
    chunk_id: int
    document_id: int
    document_title: str
    ord: int
    heading: str | None
    content: str
    score: float
    retrieval: str
    rank: int = 0
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0
    vector_rank: int = 0
    keyword_rank: int = 0

    def snippet(self, query: str = "", limit: int = 220) -> str:
        return build_snippet(self.content, query, limit)


def build_snippet(content: str, query: str = "", limit: int = 220) -> str:
    """以命中词附近为中心截取片段，命中词不在正文时退回开头。

    中文没有词边界，把查询拆成单字后（如「关」「键」「命」「中」「词」）会在正文里到处误命中，
    导致片段中心落在完全无关的位置。所以定位顺序是：完整查询串 → 长词（>=2 字）→ 单字。
    """
    text = re.sub(r"\s+", " ", content or "").strip()
    if len(text) <= limit:
        return text

    needle = (query or "").strip()
    candidates: list[str] = []
    if needle and len(needle) >= 2 and needle.lower() in text.lower():
        candidates.append(needle.lower())
    terms = list(_term_set(needle)) if needle else []
    # 长词优先（二元组 > 单字），单字里再过滤高频虚词
    candidates += sorted((t for t in terms if len(t) >= 2), key=len, reverse=True)
    candidates += [t for t in terms if len(t) < 2 and t not in _CN_STOPWORDS]

    lowered = text.lower()
    hit = -1
    for candidate in candidates:
        index = lowered.find(candidate)
        if index >= 0:
            hit = index + len(candidate) // 2
            break
    if hit < 0:
        return text[:limit] + "…"
    start = max(0, hit - limit // 3)
    end = min(len(text), start + limit)
    snippet = text[start:end]
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


def _base_query(db: Session, user_id: int, document_ids: list[int] | None):
    stmt = (
        select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.user_id == user_id,
            Document.deleted_at.is_(None),
            Document.status == "ready",
        )
    )
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    return stmt


def _fetch_candidates(
    db: Session, user_id: int, document_ids: list[int] | None
) -> list[tuple[DocumentChunk, str]]:
    return list(db.execute(_base_query(db, user_id, document_ids)).all())


# ---------------------------------------------------------------- 向量路
def _vector_search_pg(
    db: Session, user_id: int, document_ids: list[int] | None, query_vec: list[float], limit: int
) -> list[tuple[DocumentChunk, str, float]]:
    distance = DocumentChunk.embedding.cosine_distance(query_vec).label("distance")
    stmt = (
        select(DocumentChunk, Document.title, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.user_id == user_id,
            Document.deleted_at.is_(None),
            Document.status == "ready",
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
    rows = db.execute(stmt).all()
    return [(chunk, title, 1.0 - float(dist)) for chunk, title, dist in rows]


def _vector_search_python(
    rows: list[tuple[DocumentChunk, str]], query_vec: list[float], limit: int
) -> list[tuple[DocumentChunk, str, float]]:
    scored: list[tuple[DocumentChunk, str, float]] = []
    for chunk, title in rows:
        sim = cosine_similarity(chunk.embedding, query_vec)
        if sim > 0:
            scored.append((chunk, title, sim))
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:limit]


def vector_search(
    db: Session, user_id: int, query: str, limit: int = 20, document_ids: list[int] | None = None
) -> list[tuple[DocumentChunk, str, float]]:
    query_vec = embed_text(query)
    if settings.is_postgres:
        try:
            return _vector_search_pg(db, user_id, document_ids, query_vec, limit)
        except Exception:  # 索引/扩展未就绪时退化为 Python 计算，保证功能可用
            db.rollback()
    rows = _fetch_candidates(db, user_id, document_ids)
    return _vector_search_python(rows, query_vec, limit)


# ---------------------------------------------------------------- 关键词路
def _keyword_scores(
    query: str,
    contents: list[str],
    *,
    single_char_weight: float = 0.25,
    bigram_only: bool = True,
) -> list[float]:
    """IDF 加权的覆盖率打分（BM25 的核心思想：越稀有的词越值钱）。

    为什么不用裸词频：中文里"的/是/可以"这类词几乎块块都有，按出现次数打分会把
    又长又泛的块顶到前面，把真正命中的块挤下去（实测 R@1 只有 0.79）。
    改为"IDF 加权覆盖率"后，稀有词（如"珠三角""199 元""IP65"）主导排序。

    ``bigram_only=True`` 时只让二元组参与分母/分子，单字仅以 ``single_char_weight``
    的折扣权重计入命中——单字区分度太低（"退""货"几乎处处出现），全权重会明显拉低
    R@1；折扣后既保留"命中即相关"的正向信号，又不至于淹没有区分度的二元组。
    这是在同一评测集上实测选定的口径，不是先验假设。

    ⚠️ 查询侧必须用 ``query_terms()``（单字 + 二元组）而不是 ``tokenize()``：
    后者只产单字，当语料 >= 4 块时查询词与文档词集完全不重叠，关键词路会静默归零
    （实测关键词 R@1 = 0.07，且小语料单测发现不了）。
    """
    if not contents:
        return []
    use_single = len(contents) < 4
    per_doc_terms: list[set[str]] = []
    for content in contents:
        terms = _term_set(content)
        if not use_single and bigram_only:
            terms = {t for t in terms if len(t) >= 2}
        per_doc_terms.append(terms)

    query_tokens = query_terms(query)
    if not query_tokens:
        return [0.0] * len(contents)

    weights: dict[str, float] = {}
    for token in query_tokens:
        is_single = len(token) < 2
        if is_single and not use_single:
            continue
        df = sum(1 for terms in per_doc_terms if token in terms)
        if df == 0:
            continue
        weights[token] = math.log((len(contents) + 1) / (df + 1)) + 1.0
        if is_single:
            weights[token] *= single_char_weight

    if not weights:
        return [0.0] * len(contents)

    total_weight = sum(weights.values())
    scores: list[float] = []
    for position, content in enumerate(contents):
        lowered = (content or "").lower()
        matched_weight = 0.0
        frequency_bonus = 0.0
        for token, weight in weights.items():
            occurrences = lowered.count(token)
            if occurrences:
                matched_weight += weight
                frequency_bonus += min(occurrences, 3) / 3.0
        coverage = matched_weight / total_weight if total_weight else 0.0
        # 覆盖率为主，词频只给轻微加成，避免长块碾压短块
        scores.append(round(coverage * (1.0 + 0.08 * min(frequency_bonus, 4.0)), 6))
    return scores


def _keyword_search_python(
    rows: list[tuple[DocumentChunk, str]], query: str, limit: int
) -> list[tuple[DocumentChunk, str, float]]:
    scores = _keyword_scores(query, [chunk.content for chunk, _title in rows])
    scored = [
        (chunk, title, score)
        for (chunk, title), score in zip(rows, scores, strict=True)
        if score > 0
    ]
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:limit]


def keyword_search(
    db: Session, user_id: int, query: str, limit: int = 20, document_ids: list[int] | None = None
) -> list[tuple[DocumentChunk, str, float]]:
    """关键词召回。

    刻意**不**使用 PostgreSQL 的 ``ts_rank_cd``：``simple`` 配置对中文没有分词器，
    中文查询会全部打出 0 分（实测 R@1 只有 0.07），而 ``pg_trgm`` 的 similarity 又
    不适合"查询词覆盖度"这种语义。这里统一用进程内 IDF 加权覆盖率打分：
    - 与 SQLite 测试环境口径完全一致（同一份代码，不存在"生产/测试结果不同"的坑）
    - 用户级语料规模小（演示库 36 块 / 单用户上限几十篇文档），全量打分延迟可忽略
    - 表上仍保留 ``tsvector`` 的 GIN 索引作为探索记录，未来接入中文分词器时可随时切换
    """
    return _keyword_search_python(_fetch_candidates(db, user_id, document_ids), query, limit)


# ---------------------------------------------------------------- RRF 融合
def candidate_pool(
    ranked_lists: dict[str, list[tuple[DocumentChunk, str, float]]],
    limit: int = 20,
) -> list[RankedChunk]:
    """把多路召回结果**并集**成一个候选池（不是融合成排名）。

    为什么要并集而不是直接 RRF：RRF 只看名次，会把"被两路同时召回但名次都不算最前"
    的块排在"只被一路召回但名次第一"的块之后。实测中真正的 gold chunk 在关键词路排第 1、
    在向量路排第 3，RRF 融合后掉到第 3，反而输给了只被向量路召回的块（hybrid R@1 0.86 <
    纯关键词 0.93）。并集保留每路的原始名次与分数，把"怎么排序"这件事交给下游的
    名次级重排（``hybrid_rerank``）——这是可以指着评测数字讲的实现取舍。
    """
    pool: dict[int, RankedChunk] = {}
    for channel, items in ranked_lists.items():
        for position, (chunk, title, score) in enumerate(items, start=1):
            entry = pool.get(chunk.id)
            if entry is None:
                entry = RankedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=title,
                    ord=chunk.ord,
                    heading=chunk.heading,
                    content=chunk.content,
                    score=0.0,
                    retrieval=channel,
                    rank=position,
                )
                pool[chunk.id] = entry
            if channel == "vector":
                entry.vector_score = max(entry.vector_score, score)
                entry.vector_rank = entry.vector_rank or position
            elif channel == "keyword":
                entry.keyword_score = max(entry.keyword_score, score)
                entry.keyword_rank = entry.keyword_rank or position
            if position < entry.rank:
                entry.rank = position
                entry.retrieval = channel
    ordered = sorted(pool.values(), key=lambda c: c.rank)[:limit]
    for item in ordered:
        candidates = [s for s in (item.vector_score, item.keyword_score) if s > 0]
        item.score = round(max(candidates), 4) if candidates else 0.0
    return ordered


def rrf_fuse(
    ranked_lists: dict[str, list[tuple[DocumentChunk, str, float]]],
    k: int = 60,
    limit: int = 5,
    channel_weights: dict[str, float] | None = None,
) -> list[RankedChunk]:
    """分数相加式 RRF：``score(d) = Σ w_c / (k + rank_c(d))``。

    - 同一个 chunk 在多路出现则各通道贡献累加（这是融合优于单路的来源）
    - ``retrieval`` 记录**名次最好的那个通道**，便于面试讲清"这条是靠谁召回的"
    - 某一通道独有的候选也会进入结果集，这正是混合检索补召回的地方
    """
    weights = {"vector": 1.0, "keyword": 1.0, **(channel_weights or {})}
    fused: dict[int, RankedChunk] = {}
    best_rank: dict[int, int] = {}
    for channel, items in ranked_lists.items():
        weight = weights.get(channel, 1.0)
        for position, (chunk, title, score) in enumerate(items, start=1):
            contribution = weight / (k + position)
            entry = fused.get(chunk.id)
            if entry is None:
                entry = RankedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=title,
                    ord=chunk.ord,
                    heading=chunk.heading,
                    content=chunk.content,
                    score=0.0,
                    retrieval=channel,
                )
                fused[chunk.id] = entry
            entry.score += contribution
            if channel == "vector":
                entry.vector_score = max(entry.vector_score, score)
            elif channel == "keyword":
                entry.keyword_score = max(entry.keyword_score, score)
            if position < best_rank.get(chunk.id, 10**9):
                best_rank[chunk.id] = position
                entry.retrieval = channel

    ordered = sorted(fused.values(), key=lambda c: c.score, reverse=True)[:limit]
    for index, item in enumerate(ordered, start=1):
        item.rank = index
        # 对外暴露的 score 统一成人类可读口径：向量路给余弦相似度、关键词路给词重叠分。
        # ⚠️ 纯 RRF 模式下这个字段只用于展示；hybrid 的最终排序由 hybrid_rerank 决定，
        # 所以不要用这里返回的顺序当作 hybrid 结果（retrieve() 会再做一次精排）。
        candidates = [s for s in (item.vector_score, item.keyword_score) if s > 0]
        item.score = round(max(candidates), 4) if candidates else round(item.score, 4)
    return ordered


def _ordered(
    rows: list[tuple[DocumentChunk, str, float]], channel: str, limit: int
) -> list[RankedChunk]:
    out: list[RankedChunk] = []
    for index, (chunk, title, score) in enumerate(rows[:limit], start=1):
        out.append(
            RankedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=title,
                ord=chunk.ord,
                heading=chunk.heading,
                content=chunk.content,
                score=round(float(score), 4),
                retrieval=channel,
                rank=index,
                vector_score=float(score) if channel == "vector" else 0.0,
                keyword_score=float(score) if channel == "keyword" else 0.0,
            )
        )
    return out


@dataclass
class RetrievalResult:
    chunks: list[RankedChunk]
    elapsed_ms: int
    mode: str

    @property
    def chunk_ids(self) -> list[int]:
        return [c.chunk_id for c in self.chunks]


def _min_max(values: list[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-12:
        return [1.0 if high > 1e-12 else 0.0 for _ in values]
    return [(v - low) / (high - low) for v in values]


def hybrid_rerank(
    candidates: list[RankedChunk],
    query: str,
    limit: int,
    vector_weight: float | None = None,
    keyword_weight: float | None = None,
    rrf_weight: float | None = None,
) -> list[RankedChunk]:
    """混合检索第二段：在并集候选池上做**名次级**重排。

    为什么不用"分数归一化后线性混合"：向量相似度与关键词覆盖度的动态范围差异极大
    （实测 0.18–0.41 vs 0.11–1.12），min-max 归一化会把弱信号放大成强信号，
    实测 R@1 掉到 0.86（低于纯关键词 0.93）。名次级融合天然免疫量纲问题。

    三个信号，全部基于名次，得分 = Σ w_channel / (rrf_k + rank_channel)：
    - ``vector``：向量路名次（缺失时按 ``pool_size + 1`` 计入，即"该路没召回"要付出代价）
    - ``keyword``：关键词路名次
    - ``best``：并集名次（best rank），保留"被多路同时召回"的互补性

    权重是在离线评测集上实测选定的，README 里的对比表来自同一口径。
    """
    if not candidates:
        return []
    vw = settings.hybrid_vector_weight if vector_weight is None else vector_weight
    kw = settings.hybrid_keyword_weight if keyword_weight is None else keyword_weight
    rw = settings.hybrid_rrf_weight if rrf_weight is None else rrf_weight
    k = settings.rrf_k
    missing = len(candidates) + 1

    for candidate in candidates:
        score = 0.0
        if vw > 0:
            score += vw / (k + (candidate.vector_rank or missing))
        if kw > 0:
            score += kw / (k + (candidate.keyword_rank or missing))
        if rw > 0:
            score += rw / (k + (candidate.rank or missing))
        candidate.rerank_score = round(score, 8)

    ordered_result = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)[:limit]
    for rank, item in enumerate(ordered_result, start=1):
        item.rank = rank
    return ordered_result


def retrieve(
    db: Session,
    user_id: int,
    query: str,
    mode: str | None = None,
    top_k: int | None = None,
    document_ids: list[int] | None = None,
) -> RetrievalResult:
    mode = mode or settings.retrieval_mode
    top_k = top_k or settings.top_k
    started = time.perf_counter()

    if mode == "vector":
        chunks = _ordered(vector_search(db, user_id, query, top_k, document_ids), "vector", top_k)
    elif mode == "keyword":
        chunks = _ordered(keyword_search(db, user_id, query, top_k, document_ids), "keyword", top_k)
    else:
        pool_size = max(settings.hybrid_pool_size, top_k)
        fetch_size = max(pool_size * settings.hybrid_candidate_multiplier, top_k)
        ranked = {
            "vector": vector_search(db, user_id, query, fetch_size, document_ids),
            "keyword": keyword_search(db, user_id, query, fetch_size, document_ids),
        }
        candidates = candidate_pool(ranked, limit=pool_size)
        chunks = hybrid_rerank(candidates, query, top_k)

    elapsed = int((time.perf_counter() - started) * 1000)
    return RetrievalResult(chunks=chunks, elapsed_ms=elapsed, mode=mode)
