"""回答合成与引用重排单元测试。"""

from __future__ import annotations

import re

import pytest

from app.core.config import settings
from app.services.answer import (
    DEMO_NOTICE,
    NO_CONTEXT_REPLY,
    _CITE_RE,
    _build_context,
    build_citations,
    generate,
    renumber_citations,
    stream_echo,
    synthesize_answer,
)
from tests._unit import make_ranked

CHUNKS = [
    make_ranked(
        11,
        content="整机保修期为自签收之日起 12 个月。电源适配器保修期为 6 个月。",
        title="产品保修条款",
        score=0.83,
        rank=1,
        heading="二、保修期限",
        document_id=1,
        ord=2,
    ),
    make_ranked(
        12,
        content="不属于保修范围的情形包括人为损坏与私自拆机。",
        title="产品保修条款",
        score=0.61,
        rank=2,
        retrieval="keyword",
        heading="四、不属于保修范围的情形",
        document_id=1,
        ord=4,
    ),
]


class TestCitations:
    def test_fields_match_contract(self) -> None:
        citations = build_citations(CHUNKS, "保修期")
        required = {
            "chunk_id",
            "document_id",
            "document_title",
            "ord",
            "heading",
            "snippet",
            "score",
            "retrieval",
            "rank",
        }
        assert set(citations[0].keys()) == required

    def test_rank_order_preserved(self) -> None:
        citations = build_citations(CHUNKS, "保修期")
        assert [c["rank"] for c in citations] == [1, 2]

    def test_snippet_limited(self) -> None:
        long_chunk = make_ranked(1, content="保修期" * 500)
        citations = build_citations([long_chunk], "保修期")
        assert len(citations[0]["snippet"]) <= 260


class TestSynthesize:
    def test_empty_chunks_returns_guided_message(self) -> None:
        result = synthesize_answer("保修期", [])
        assert result.content == NO_CONTEXT_REPLY
        assert result.citations == []

    def test_demo_notice_is_explicit(self) -> None:
        result = synthesize_answer("保修期是多久", CHUNKS)
        assert result.content.startswith(DEMO_NOTICE)
        assert "非模型生成" in result.content

    def test_every_bullet_has_citation_marker(self) -> None:
        result = synthesize_answer("保修期是多久", CHUNKS)
        bullets = [line for line in result.content.split("\n") if line.startswith("- ")]
        assert bullets
        for line in bullets:
            assert _CITE_RE.search(line), line

    def test_citation_markers_within_range(self) -> None:
        result = synthesize_answer("保修期是多久", CHUNKS)
        for match in _CITE_RE.finditer(result.content):
            index = int(match.group(1))
            assert 1 <= index <= len(result.citations)

    def test_provider_is_echo(self) -> None:
        assert synthesize_answer("保修期", CHUNKS).provider == "echo"

    def test_irrelevant_query_still_returns_points(self) -> None:
        result = synthesize_answer("完全无关的问题xyz", CHUNKS)
        assert result.citations
        assert "[[" in result.content

    def test_heading_is_rendered(self) -> None:
        result = synthesize_answer("保修期是多久", CHUNKS)
        assert "二、保修期限" in result.content


class TestStreamEcho:
    def test_reassembles_to_original(self) -> None:
        answer = synthesize_answer("保修期是多久", CHUNKS)
        assert "".join(stream_echo(answer)) == answer.content

    def test_multiple_pieces(self) -> None:
        answer = synthesize_answer("保修期是多久", CHUNKS)
        assert len(list(stream_echo(answer, chunk_size=10))) > 1


class TestRenumberCitations:
    def test_renumbers_to_contiguous_indexes(self) -> None:
        content = "结论一[[c2]] 结论二[[c1]]"
        new_content, citations = renumber_citations(content, CHUNKS, "保修期")
        assert "[[c1]]" in new_content and "[[c2]]" in new_content
        assert len(citations) == 2
        assert citations[0]["chunk_id"] == CHUNKS[1].chunk_id  # 原文先引用 c2

    def test_duplicate_marker_kept_once(self) -> None:
        content = "甲[[c1]] 乙[[c1]]"
        _, citations = renumber_citations(content, CHUNKS, "保修期")
        assert len(citations) == 1

    def test_out_of_range_marker_kept_when_nothing_valid(self) -> None:
        """全部标记都越界时不做重排，原样返回——纯文本扫描下这比静默删字更安全。"""
        content = "甲[[c99]]"
        new_content, citations = renumber_citations(content, CHUNKS, "保修期")
        assert citations == []
        assert new_content == content

    def test_out_of_range_marker_dropped_when_others_valid(self) -> None:
        content = "甲[[c1]] 乙[[c99]]"
        new_content, citations = renumber_citations(content, CHUNKS, "保修期")
        assert "[[c99]]" not in new_content
        assert "[[c1]]" in new_content
        assert len(citations) == 1

    def test_no_markers_returns_empty_citations(self) -> None:
        content = "模型没有标注任何引用"
        new_content, citations = renumber_citations(content, CHUNKS, "保修期")
        assert new_content == content
        assert citations == []

    def test_ranks_renumbered_in_citation_order(self) -> None:
        _, citations = renumber_citations("甲[[c2]]乙[[c1]]", CHUNKS, "保修期")
        assert [c["rank"] for c in citations] == [1, 2]


class TestBuildContext:
    def test_contains_numbered_blocks(self) -> None:
        context = _build_context(CHUNKS)
        assert context.startswith("[c1]")
        assert "[c2]" in context

    def test_respects_char_budget(self) -> None:
        many = [make_ranked(i, content="内容" * 2000) for i in range(1, 6)]
        assert len(_build_context(many, max_chars=3000)) <= 3200


class TestGenerateEchoMode:
    def test_generate_uses_echo_without_api_key(self) -> None:
        assert settings.active_llm_provider == "echo"
        result = generate("保修期是多久", CHUNKS)
        assert result.provider == "echo"
        assert result.citations

    def test_generate_with_no_chunks(self) -> None:
        result = generate("保修期", [])
        assert result.content == NO_CONTEXT_REPLY

    def test_marker_pattern_is_stable(self) -> None:
        """前端按 [[cN]] 渲染，格式不能变。"""
        assert re.fullmatch(r"\[\[c\d+\]\]", "[[c12]]")
