"""文档摄取：解析 → 切分 → 向量化 → 落库（契约 §4.2 文档段）。

设计取舍：不使用 Celery/Redis（免费容器内存有限，契约 §8.3 禁止新增常驻进程），
改用 FastAPI BackgroundTasks + 独立数据库会话；任务状态落在 documents.status 上，
前端按 status 轮询即可，不需要额外的任务表。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Document, DocumentChunk
from app.services.chunking import estimate_tokens, split_document
from app.services.embedding import embed_texts

logger = logging.getLogger("citera.ingest")

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log", ".json"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS
DECODE_CHAIN = ("utf-8", "utf-8-sig", "gbk", "latin-1")
PDF_FOOTER_NOTE = "\n\n（本文件为虚构演示资料，仅用于产品演示）"


class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ParsedFile:
    text: str
    mime_type: str
    meta: dict


def extension_of(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[1].lower()


def decode_text(raw: bytes) -> str:
    for encoding in DECODE_CHAIN:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError("unprocessable_upload", "文件编码无法识别（已尝试 utf-8/utf-8-sig/gbk/latin-1）")


def parse_pdf(raw: bytes) -> ParsedFile:
    try:
        import io

        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover
        raise IngestError("unprocessable_upload", "服务端缺少 PDF 解析组件") from exc
    try:
        reader = PdfReader(io.BytesIO(raw))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception as exc:
                raise IngestError("unprocessable_upload", "PDF 已加密，无法解析") from exc
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError("unprocessable_upload", f"PDF 解析失败：{exc}") from exc

    text = "\n\n".join(p for p in pages if p)
    if not text.strip():
        raise IngestError("unprocessable_upload", "PDF 中未提取到文本（可能是扫描件，需要 OCR）")
    return ParsedFile(
        text=text,
        mime_type="application/pdf",
        meta={"page_count": len(reader.pages), "parsed_pages": sum(1 for p in pages if p)},
    )


def parse_upload(filename: str, raw: bytes) -> ParsedFile:
    ext = extension_of(filename)
    if ext in PDF_EXTENSIONS:
        return parse_pdf(raw)
    if ext not in TEXT_EXTENSIONS:
        raise IngestError(
            "unsupported_file_type",
            f"不支持的文件类型 {ext or '(无扩展名)'}，支持：{', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    text = decode_text(raw)
    mime = {
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".csv": "text/csv",
        ".json": "application/json",
        ".log": "text/plain",
    }.get(ext, "text/plain")
    return ParsedFile(text=text, mime_type=mime, meta={"encoding_chain": list(DECODE_CHAIN)})


def build_chunks(db: Session, document: Document, text: str) -> int:
    """切分 + 向量化 + 落库，返回块数。调用方负责 commit。"""
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    pieces = split_document(
        text, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    if not pieces:
        raise IngestError("unprocessable_upload", "文档内容为空，没有可切分的文本")

    vectors = embed_texts([p.content for p in pieces])
    for piece, vector in zip(pieces, vectors, strict=True):
        db.add(
            DocumentChunk(
                document_id=document.id,
                user_id=document.user_id,
                ord=piece.ord,
                content=piece.content,
                token_estimate=piece.token_estimate or estimate_tokens(piece.content),
                heading=piece.heading,
                embedding=vector,
            )
        )
    document.chunk_count = len(pieces)
    document.char_count = len(text)
    document.meta = {
        **(document.meta or {}),
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "embedding_provider": settings.active_embedding_provider,
        "embedding_dim": settings.embedding_dim,
    }
    return len(pieces)


def process_document_text(db: Session, document: Document, text: str) -> int:
    document.status = "processing"
    document.error_message = None
    db.commit()
    try:
        count = build_chunks(db, document, text)
        document.status = "ready"
        db.commit()
        return count
    except IngestError as exc:
        db.rollback()
        document.status = "failed"
        document.error_message = exc.message
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("文档处理失败 document_id=%s", document.id)
        document.status = "failed"
        document.error_message = f"处理失败：{exc}"
        db.commit()
        raise


def process_document_task(document_id: int, raw: bytes | None = None, filename: str | None = None) -> None:
    """后台任务入口：自己开会话、自己兜异常，绝不让异常冒泡到请求线程。"""
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("后台任务找不到文档 document_id=%s", document_id)
            return
        if raw is None:
            # 粘贴模式：正文已存在 meta.raw_text
            text = str((document.meta or {}).get("raw_text", ""))
            if not text.strip():
                document.status = "failed"
                document.error_message = "缺少可处理的正文"
                db.commit()
                return
        else:
            try:
                parsed = parse_upload(filename or document.filename or "upload.txt", raw)
            except IngestError as exc:
                document.status = "failed"
                document.error_message = exc.message
                db.commit()
                return
            text = parsed.text
            document.mime_type = parsed.mime_type
            document.meta = {**(document.meta or {}), **parsed.meta}
        process_document_text(db, document, text)
    finally:
        db.close()


def document_stats(db: Session, user_id: int) -> dict:
    base = select(Document).where(Document.user_id == user_id, Document.deleted_at.is_(None))
    rows = db.execute(
        select(Document.status, func.count()).where(
            Document.user_id == user_id, Document.deleted_at.is_(None)
        ).group_by(Document.status)
    ).all()
    by_status = [{"status": status, "count": count} for status, count in rows]
    counts = {item["status"]: item["count"] for item in by_status}
    totals = db.execute(
        select(
            func.coalesce(func.sum(Document.chunk_count), 0),
            func.coalesce(func.sum(Document.char_count), 0),
        ).where(Document.user_id == user_id, Document.deleted_at.is_(None))
    ).one()
    total = sum(counts.values())
    return {
        "total": total,
        "ready": counts.get("ready", 0),
        "processing": counts.get("processing", 0) + counts.get("pending", 0),
        "failed": counts.get("failed", 0),
        "chunk_total": int(totals[0] or 0),
        "char_total": int(totals[1] or 0),
        "by_status": by_status,
    }
