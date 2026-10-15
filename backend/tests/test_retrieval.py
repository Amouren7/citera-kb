"""检索与 RRF 融合单元测试（不依赖数据库）。"""

from __future__ import annotations

from app.services.retrieval import (
    RankedChunk,
    build_snippet,
    query_terms,
    rrf_fuse,
    tokenize,
)
from tests._unit import FakeChunk


def _list(*pairs: tuple[int, float, str]) -> list[tuple[FakeChunk, str, float]]:
    return [(FakeChunk(cid, content), f"文档{cid}", score) for cid, score, content in pairs]


class TestTokenize:
    def test_english_word_level(self) -> None:
        assert "warranty" in tokenize("Warranty period")

    def test_chinese_char_level(self) -> None:
        tokens = tokenize("保修期限")
        assert "保" in tokens and "修" in tokens

    def test_stopwords_removed(self) -> None:
        assert "的" not in tokenize("保修期是多久的")

    def test_query_terms_adds_bigrams(self) -> None:
        terms = query_terms("保修期")
        assert "保修期" not in terms
        assert "保修" in terms and "修期" in terms

    def test_empty(self) -> None:
        assert tokenize("") == []
        assert query_terms("") == []


class TestSnippet:
    def test_short_content_returned_as_is(self) -> None:
        assert build_snippet("短内容", "短") == "短内容"

    def test_centered_on_hit(self) -> None:
        content = "前面无关内容。" * 30 + "关键命中词在这里。" + "后面无关内容。" * 30
        snippet = build_snippet(content, "关键命中词", 80)
        assert "关键命中词" in snippet
        assert snippet.startswith("…") or snippet.endswith("…")

    def test_falls_back_to_prefix(self) -> None:
        snippet = build_snippet("完全无关的长文本" * 50, "不存在的词", 60)
        assert snippet.endswith("…")

    def test_whitespace_collapsed(self) -> None:
        assert "\n" not in build_snippet("第一行\n第二行", "第一")


class TestRrfFusion:
    def test_fused_score_is_sum_of_reciprocal_ranks(self) -> None:
        vector = _list((1, 0.9, "内容一"), (2, 0.8, "内容二"))
        keyword = _list((2, 5.0, "内容二"), (3, 4.0, "内容三"))
        fused = rrf_fuse({"vector": vector, "keyword": keyword}, k=60, limit=3)
        scores = {item.chunk_id: item.score for item in fused}
        # chunk 2 被两路召回，排名应高于只在单路出现的 chunk 1 与 chunk 3
        assert [item.chunk_id for item in fused][0] == 2
        assert scores[2] > scores[1]
        assert scores[2] > scores[3]

    def test_rank_is_sequential_from_one(self) -> None:
        fused = rrf_fuse({"vector": _list((1, 0.9, "a"), (2, 0.8, "b"))}, k=60, limit=5)
        assert [item.rank for item in fused] == [1, 2]

    def test_limit_respected(self) -> None:
        fused = rrf_fuse({"vector": _list(*[(i, 0.5, f"c{i}") for i in range(1, 11)])}, limit=3)
        assert len(fused) == 3

    def test_single_channel_only(self) -> None:
        fused = rrf_fuse({"keyword": _list((1, 2.0, "a"))}, limit=5)
        assert fused[0].retrieval == "keyword"
        assert fused[0].score == 2.0

    def test_retrieval_labels_best_rank_channel(self) -> None:
        # chunk 1 在 keyword 里第 1、在 vector 里第 3 → 标签应为 keyword
        fused = rrf_fuse(
            {
                "vector": _list((9, 0.9, "x"), (8, 0.8, "y"), (1, 0.7, "z")),
                "keyword": _list((1, 3.0, "z")),
            },
            k=60,
            limit=5,
        )
        target = next(item for item in fused if item.chunk_id == 1)
        assert target.retrieval == "keyword"

    def test_keyword_only_candidate_survives_fusion(self) -> None:
        """关键词路独有召回必须进入结果集——否则混合检索等于没做。"""
        fused = rrf_fuse(
            {"vector": _list((1, 0.9, "a")), "keyword": _list((2, 3.0, "b"))},
            limit=5,
        )
        assert {item.chunk_id for item in fused} == {1, 2}

    def test_channel_weights_shift_ranking(self) -> None:
        vector = _list((1, 0.9, "a"))
        keyword = _list((2, 3.0, "b"))
        fused = rrf_fuse(
            {"vector": vector, "keyword": keyword},
            limit=2,
            channel_weights={"vector": 1.0, "keyword": 5.0},
        )
        assert fused[0].chunk_id == 2

    def test_empty_lists(self) -> None:
        assert rrf_fuse({"vector": [], "keyword": []}, limit=5) == []

    def test_scores_are_rounded_floats(self) -> None:
        fused = rrf_fuse({"vector": _list((1, 0.123456789, "a"))}, limit=1)
        assert isinstance(fused[0].score, float)
        assert len(str(fused[0].score).split(".")[-1]) <= 4

    def test_content_and_metadata_are_carried_over(self) -> None:
        chunk = FakeChunk(7, "正文内容", document_id=3, ord=2, heading="标题")
        fused = rrf_fuse({"vector": [(chunk, "文档标题", 0.5)]}, limit=1)
        assert fused[0].content == "正文内容"
        assert fused[0].document_id == 3
        assert fused[0].ord == 2
        assert fused[0].heading == "标题"
        assert fused[0].document_title == "文档标题"

    def test_snippet_uses_query(self) -> None:
        chunk = FakeChunk(1, "无关内容。" * 20 + "保修期为 12 个月。" + "无关内容。" * 20)
        fused = rrf_fuse({"vector": [(chunk, "文档", 0.5)]}, limit=1)
        assert "保修期" in fused[0].snippet("保修期")


class TestRankedChunk:
    def test_defaults(self) -> None:
        chunk = RankedChunk(
            chunk_id=1,
            document_id=2,
            document_title="标题",
            ord=3,
            heading=None,
            content="内容",
            score=0.5,
            retrieval="hybrid",
        )
        assert chunk.rank == 0
        assert chunk.vector_score == 0.0
        assert chunk.keyword_score == 0.0
