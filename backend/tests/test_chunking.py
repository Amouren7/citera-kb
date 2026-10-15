"""切分与向量化单元测试（不依赖数据库）。"""

from __future__ import annotations

import pytest

from app.services.chunking import estimate_tokens, split_document
from app.services.embedding import cosine_similarity, embed_texts, local_embed


class TestSplitDocument:
    def test_markdown_headings_become_chunk_headings(self) -> None:
        text = "# 标题一\n\n第一段内容。\n\n## 标题二\n\n第二段内容。"
        chunks = split_document(text, chunk_size=200, chunk_overlap=20)
        assert [c.heading for c in chunks] == ["标题一", "标题二"]
        assert [c.ord for c in chunks] == [1, 2]

    def test_blank_lines_split_blocks(self) -> None:
        chunks = split_document("段落一。\n\n段落二。\n\n段落三。", chunk_size=50, chunk_overlap=5)
        assert len(chunks) == 3

    def test_numbered_heading_is_recognized(self) -> None:
        text = "一、保修期限\n整机保修 12 个月。\n\n二、保修范围\n人为损坏不保。"
        chunks = split_document(text, chunk_size=200, chunk_overlap=10)
        assert chunks[0].heading == "一、保修期限"
        assert chunks[1].heading == "二、保修范围"

    def test_long_block_is_split_on_sentence_boundary(self) -> None:
        sentence = "这是一个用于测试的句子。"
        text = sentence * 60
        chunks = split_document(text, chunk_size=100, chunk_overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.content) <= 130  # 允许重叠带来的少量超出
            assert chunk.content.endswith("。")  # 不得在句中硬切

    def test_overlap_produces_shared_text(self) -> None:
        sentence = "重叠测试句子。"
        chunks = split_document(sentence * 40, chunk_size=60, chunk_overlap=20)
        assert len(chunks) >= 2

    def test_empty_text_returns_no_chunks(self) -> None:
        assert split_document("", 100, 10) == []
        assert split_document("   \n  \n ", 100, 10) == []

    def test_crlf_is_normalized(self) -> None:
        chunks = split_document("第一行。\r\n\r\n第二行。", chunk_size=100, chunk_overlap=10)
        assert len(chunks) == 2

    def test_overlap_must_be_smaller_than_size(self) -> None:
        with pytest.raises(ValueError):
            split_document("内容", chunk_size=100, chunk_overlap=100)

    def test_estimate_tokens_counts_cjk_higher(self) -> None:
        assert estimate_tokens("中文内容") == 4
        assert estimate_tokens("abcd") == 1

    def test_plain_text_without_headings(self) -> None:
        chunks = split_document("没有任何标题的正文内容。", chunk_size=100, chunk_overlap=10)
        assert len(chunks) == 1
        assert chunks[0].heading is None


class TestLocalEmbedding:
    def test_deterministic(self) -> None:
        assert local_embed("整机保修期为 12 个月") == local_embed("整机保修期为 12 个月")

    def test_dimension(self) -> None:
        assert len(local_embed("测试")) == 384

    def test_normalized(self) -> None:
        vec = local_embed("保修期限说明")
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_is_zero_vector(self) -> None:
        vec = local_embed("")
        assert all(v == 0 for v in vec)

    def test_similar_texts_score_higher(self) -> None:
        base = local_embed("整机保修期为自签收之日起十二个月")
        near = local_embed("整机保修期为自签收之日起十二个月，电源适配器六个月")
        far = local_embed("珠三角地区次日达，偏远地区三到七个工作日")
        assert cosine_similarity(base, near) > cosine_similarity(base, far)

    def test_batch_embedding_matches_single(self) -> None:
        texts = ["第一段", "第二段"]
        batch = embed_texts(texts)
        assert len(batch) == 2
        assert batch[0] == local_embed("第一段")

    def test_empty_batch(self) -> None:
        assert embed_texts([]) == []

    def test_cosine_handles_none(self) -> None:
        assert cosine_similarity(None, [1.0, 0.0]) == 0.0
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
