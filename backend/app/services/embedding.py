"""向量化（契约 §5.4）。

两种 provider：
- ``local``（默认）：确定性哈希向量。对中英文都做字符 n-gram 哈希投影 + 子线性词频加权，
  再 L2 归一化。**同一文本永远得到同一向量**，零网络依赖——这是演示环境能离线跑通的关键。
  它不是语义模型，但能真实反映"检索链路、排名融合、评测口径"是否正确，README 里如实说明。
- ``openai``：OpenAI 兼容 ``/embeddings``，需配 ``EMBEDDING_API_KEY``，维度必须等于 ``EMBEDDING_DIM``。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter

import httpx

from app.core.config import settings

logger = logging.getLogger("citera.embedding")

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def _ngrams(text: str, n_min: int = 1, n_max: int = 3) -> list[str]:
    """字符级 n-gram（中文按字，英文按词）：对中文分词缺失的兜底，召回更稳。"""
    tokens = _TOKEN_RE.findall(text.lower())
    grams: list[str] = []
    for n in range(n_min, n_max + 1):
        if len(tokens) < n:
            continue
        for i in range(len(tokens) - n + 1):
            grams.append("".join(tokens[i : i + n]))
    return grams


def _hash_index(gram: str, dim: int) -> int:
    digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def local_embed(text: str, dim: int | None = None) -> list[float]:
    dim = dim or settings.embedding_dim
    vec = [0.0] * dim
    grams = _ngrams(text or "")
    if not grams:
        return vec
    counts = Counter(grams)
    for gram, count in counts.items():
        # 子线性词频：避免高频虚词主导向量
        weight = 1.0 + math.log(count)
        idx = _hash_index(gram, dim)
        # 符号哈希：冲突时正负相消，降低哈希碰撞带来的相似度虚高
        sign = 1.0 if int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=1).digest(), "big") % 2 else -1.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    na = math.sqrt(sum(x * x for x in a[:size]))
    nb = math.sqrt(sum(x * x for x in b[:size]))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _openai_embed(texts: list[str]) -> list[list[float]]:
    url = (settings.embedding_base_url or "https://api.openai.com/v1").rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {settings.embedding_api_key}"}
    out: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            resp = client.post(
                url, headers=headers, json={"model": settings.embedding_model, "input": batch}
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda d: d.get("index", 0))
            for item in data:
                vec = [float(x) for x in item["embedding"]]
                if len(vec) != settings.embedding_dim:
                    raise RuntimeError(
                        f"返回向量维度 {len(vec)} 与 EMBEDDING_DIM={settings.embedding_dim} 不一致"
                    )
                out.append(vec)
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if settings.active_embedding_provider == "openai":
        try:
            return _openai_embed(texts)
        except Exception as exc:  # 网络/额度问题不应让整个系统不可用
            logger.warning("远程向量化失败，回退本地确定性向量：%s", exc)
    return [local_embed(t) for t in texts]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
