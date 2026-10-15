"""文档切分（契约 §5.2）。

两级策略：
1. 先按 Markdown 标题 / 空行切成"语义段"，并记住每个语义段最近的标题 → ``heading``
2. 语义段超长时按句子边界递归切，**不得在句中硬切**（中文以 。！？；换行 为界，
   英文以 .!?; 为界），块之间保留 ``chunk_overlap`` 字符的重叠

参数快照写入 documents.meta，便于面试时说明"同一个文档可以用不同切分参数重跑"。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_NUMBERED_HEADING_RE = re.compile(r"^\s*(?:第[一二三四五六七八九十百]+[章节条]|[一二三四五六七八九十]+[、.．]|\d+[、.．])\s*\S")
_SENTENCE_RE = re.compile(r"[^。！？；!?;\n]+[。！？；!?;\n]?")


@dataclass
class Chunk:
    ord: int
    content: str
    heading: str | None = None
    token_estimate: int = 0
    meta: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """粗略估算：中日韩字符按 1 token，其余按 4 字符 1 token。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def _split_sentences(text: str) -> list[str]:
    return [s for s in (m.group(0).strip() for m in _SENTENCE_RE.finditer(text)) if s]


def _split_long_block(block: str, size: int, overlap: int) -> list[str]:
    """把超长语义段按句子边界切成 <= size 的块，块间重叠 overlap 字符。"""
    sentences = _split_sentences(block)
    if not sentences:
        return [block[:size]]

    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        # 单句本身超长：退化为按字符切（无句读的长串，如表格/代码）
        if len(sentence) > size:
            if current.strip():
                pieces.append(current.strip())
                current = ""
            for i in range(0, len(sentence), size):
                pieces.append(sentence[i : i + size].strip())
            continue
        if not current:
            current = sentence
            continue
        if len(current) + len(sentence) > size:
            pieces.append(current.strip())
            tail = current[-overlap:] if overlap > 0 else ""
            current = (tail + sentence).strip() if tail else sentence
        else:
            current += sentence
    if current.strip():
        pieces.append(current.strip())
    return [p for p in pieces if p]


def split_document(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[Chunk]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")

    # --- 第一级：语义段（标题 + 空行分隔）---
    blocks: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            blocks.append((current_heading, body))
        buffer.clear()

    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        heading_match = _HEADING_RE.match(line)
        is_heading = bool(heading_match) or (
            len(line) <= 40 and bool(_NUMBERED_HEADING_RE.match(line)) and not line.endswith("。")
        )
        if is_heading:
            flush()
            current_heading = (heading_match.group(2) if heading_match else line).strip()
            continue
        if not line.strip():
            flush()
            continue
        buffer.append(line)
    flush()

    # 无标题、无空行的纯文本：整体作为一段
    if not blocks and text:
        blocks = [(None, text)]

    # --- 第二级：超长语义段按句子递归切 ---
    chunks: list[Chunk] = []
    ord_counter = 0
    for heading, body in blocks:
        parts = [body] if len(body) <= chunk_size else _split_long_block(body, chunk_size, chunk_overlap)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            ord_counter += 1
            chunks.append(
                Chunk(
                    ord=ord_counter,
                    content=part,
                    heading=heading,
                    token_estimate=estimate_tokens(part),
                )
            )
    return chunks
