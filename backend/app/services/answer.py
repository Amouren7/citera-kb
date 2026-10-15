"""回答生成（契约 §5.3）。

两条路径，同一套输出结构：
- ``echo``（默认）：**受控合成**。从检索到的块里挑出与问题词重合度最高的句子，
  按块顺序组织成结构化回答，每句挂 ``[[cN]]``。开头显式声明"非模型生成"，
  绝不伪造模型输出。这是演示环境没有 LLM Key 时仍然完整可用的关键。
- ``openai``：OpenAI 兼容 ``/chat/completions`` 真流式，system prompt 强约束
  "只依据给定资料、每句标注 [[cN]]、资料不足就说不知道"。

引用编号规则：正文里的 ``[[cN]]`` 中 N 是**该回答 citations 数组的 1-based 下标**，
由本模块统一重排，前端只负责渲染。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.services.retrieval import RankedChunk, build_snippet, tokenize

logger = logging.getLogger("citera.answer")

DEMO_NOTICE = "（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）"
NO_CONTEXT_REPLY = "知识库中没有检索到与这个问题相关的内容。请先上传相关资料，或换一种问法。"

_SENTENCE_SPLIT = re.compile(r"[^。！？；!?;\n]+[。！？；!?;\n]?")
_CITE_RE = re.compile(r"\[\[c(\d+)\]\]")


@dataclass
class AnswerResult:
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "echo"
    finish_reason: str = "stop"


# ---------------------------------------------------------------- 引用构造
def build_citations(chunks: list[RankedChunk], query: str) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        citations.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "ord": chunk.ord,
                "heading": chunk.heading,
                "snippet": build_snippet(chunk.content, query, 220),
                "score": float(chunk.score),
                "retrieval": chunk.retrieval,
                "rank": chunk.rank,
            }
        )
    return citations


# ---------------------------------------------------------------- echo 路径
def _sentence_score(sentence: str, terms: list[str]) -> float:
    lowered = sentence.lower()
    score = 0.0
    for term in terms:
        if term in lowered:
            score += 1.6 if len(term) >= 2 else 1.0
    return score


def _pick_sentences(content: str, terms: list[str], limit: int = 2, max_chars: int = 220) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT.findall(content) if s.strip()]
    if not sentences:
        return []
    scored = [(i, s, _sentence_score(s, terms)) for i, s in enumerate(sentences)]
    hits = [item for item in scored if item[2] > 0]
    picked = sorted(hits, key=lambda item: (-item[2], item[0]))[:limit] if hits else scored[:1]
    picked.sort(key=lambda item: item[0])
    out: list[str] = []
    total = 0
    for _, sentence, _score in picked:
        if total + len(sentence) > max_chars and out:
            break
        out.append(sentence)
        total += len(sentence)
    return out


def synthesize_answer(query: str, chunks: list[RankedChunk]) -> AnswerResult:
    citations = build_citations(chunks, query)
    if not chunks:
        return AnswerResult(content=NO_CONTEXT_REPLY, citations=[], provider="echo")

    terms = tokenize(query)
    lines: list[str] = [DEMO_NOTICE, ""]
    for index, chunk in enumerate(chunks, start=1):
        sentences = _pick_sentences(chunk.content, terms)
        if not sentences:
            continue
        heading = f"（{chunk.heading}）" if chunk.heading else ""
        body = "".join(sentences)
        lines.append(f"- 来自《{chunk.document_title}》{heading}：{body}[[c{index}]]")

    if len(lines) <= 2:  # 所有块都没命中任何查询词，退化为按排名列出要点
        for index, chunk in enumerate(chunks, start=1):
            lines.append(f"- 《{chunk.document_title}》第 {chunk.ord} 段：{build_snippet(chunk.content, query, 120)}[[c{index}]]")

    lines.append("")
    lines.append(
        f"以上要点来自 {len(chunks)} 条检索命中，点击角标可核对原文；"
        "如需模型生成的自然语言答复，请配置 LLM_API_KEY 后切换 LLM_PROVIDER=openai。"
    )
    return AnswerResult(content="\n".join(lines), citations=citations, provider="echo")


def stream_echo(answer: AnswerResult, chunk_size: int = 18) -> Iterator[str]:
    """把答案切成小块流式吐出：优先按标点/换行断开，避免半个词。"""
    text = answer.content
    buffer = ""
    for char in text:
        buffer += char
        if len(buffer) >= chunk_size and (char in "。！？；\n，、" or len(buffer) >= chunk_size * 2):
            yield buffer
            buffer = ""
    if buffer:
        yield buffer


# ---------------------------------------------------------------- LLM 路径
SYSTEM_PROMPT = """你是企业知识库问答助手。严格遵守：
1. 只依据「资料」回答，不得引入资料之外的事实；
2. 每个事实句末尾标注来源，格式为 [[cN]]，N 是资料编号；
3. 资料不足以回答时，明确说"现有资料无法回答该问题"，不要猜测；
4. 用简洁的书面中文，先给结论再给依据。"""


def _build_context(chunks: list[RankedChunk], max_chars: int = 6000) -> str:
    parts: list[str] = []
    used = 0
    for index, chunk in enumerate(chunks, start=1):
        block = (
            f"[c{index}] 文档《{chunk.document_title}》"
            f"{'·' + chunk.heading if chunk.heading else ''} 第 {chunk.ord} 段：\n{chunk.content}"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def _llm_messages(query: str, chunks: list[RankedChunk], history: list[dict[str, str]]) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append(
        {
            "role": "user",
            "content": f"资料：\n{_build_context(chunks)}\n\n问题：{query}\n\n请依据资料回答，每句标注 [[cN]]。",
        }
    )
    return messages


def _endpoint() -> str:
    return (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"


def stream_llm(
    query: str, chunks: list[RankedChunk], history: list[dict[str, str]] | None = None
) -> Iterator[str]:
    """真流式：逐 delta 产出文本片段。异常向上抛，由调用方转成 SSE error 事件。"""
    payload = {
        "model": settings.llm_model,
        "messages": _llm_messages(query, chunks, history or []),
        "stream": True,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", _endpoint(), headers=headers, json=payload) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", "ignore")[:300]
                raise RuntimeError(f"模型接口返回 {response.status_code}：{body}")
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    yield piece


def renumber_citations(
    content: str, chunks: list[RankedChunk], query: str
) -> tuple[str, list[dict[str, Any]]]:
    """把模型输出里的 [[cN]] 重排成连续编号，并只返回被真正引用到的资料。"""
    all_citations = build_citations(chunks, query)
    used: list[int] = []
    for match in _CITE_RE.finditer(content):
        idx = int(match.group(1))
        if 1 <= idx <= len(all_citations) and idx not in used:
            used.append(idx)

    if not used:
        return content, []

    mapping = {old: new for new, old in enumerate(used, start=1)}

    def _replace(match: re.Match[str]) -> str:
        old = int(match.group(1))
        if old in mapping:
            return f"[[c{mapping[old]}]]"
        return ""

    new_content = _CITE_RE.sub(_replace, content)
    new_citations = [all_citations[old - 1] for old in used]
    for position, citation in enumerate(new_citations, start=1):
        citation["rank"] = position
    return new_content, new_citations


def generate(
    query: str,
    chunks: list[RankedChunk],
    history: list[dict[str, str]] | None = None,
) -> AnswerResult:
    """非流式：echo 直接返回；openai 攒完整个流再重排引用。"""
    if settings.active_llm_provider != "openai":
        return synthesize_answer(query, chunks)

    pieces: list[str] = []
    try:
        for piece in stream_llm(query, chunks, history):
            pieces.append(piece)
    except Exception as exc:  # 模型不可用时降级到受控合成，保证功能不中断
        logger.warning("模型调用失败，降级为受控合成：%s", exc)
        fallback = synthesize_answer(query, chunks)
        fallback.content = f"（模型调用失败，已降级为检索结果受控合成）\n\n{fallback.content}"
        return fallback

    raw = "".join(pieces).strip()
    if not raw:
        return synthesize_answer(query, chunks)
    content, citations = renumber_citations(raw, chunks, query)
    return AnswerResult(content=content, citations=citations, provider="openai")


def stream_answer(
    query: str,
    chunks: list[RankedChunk],
    history: list[dict[str, str]] | None = None,
) -> Iterator[tuple[str, Any]]:
    """统一流式接口：产出 ``("delta", text)`` 与 ``("final", AnswerResult)``。"""
    if settings.active_llm_provider != "openai":
        answer = synthesize_answer(query, chunks)
        for piece in stream_echo(answer):
            yield "delta", piece
        yield "final", answer
        return

    buffer: list[str] = []
    try:
        for piece in stream_llm(query, chunks, history):
            buffer.append(piece)
            yield "delta", piece
    except Exception as exc:
        logger.warning("模型流式失败，降级为受控合成：%s", exc)
        fallback = synthesize_answer(query, chunks)
        notice = "（模型调用失败，已降级为检索结果受控合成）\n\n"
        yield "delta", notice
        for piece in stream_echo(fallback):
            yield "delta", piece
        yield "final", fallback
        return

    raw = "".join(buffer).strip()
    if not raw:
        yield "final", synthesize_answer(query, chunks)
        return
    content, citations = renumber_citations(raw, chunks, query)
    yield "final", AnswerResult(content=content, citations=citations, provider="openai")
