"""文档接口（契约 §4.2 文档段）。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile

from app.api.deps import CurrentUser, DbSession, UploadUser
from app.core.config import settings
from app.core.errors import AppError
from app.models import Document, DocumentChunk
from app.schemas import (
    ChunkOut,
    DocumentEnvelope,
    DocumentOut,
    DocumentStats,
    Page,
    StatusCount,
    UpdateDocumentIn,
)
from app.services.ingest import (
    IngestError,
    document_stats,
    extension_of,
    process_document_task,
    SUPPORTED_EXTENSIONS,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

SORT_FIELDS = {
    "created_at": Document.created_at.asc(),
    "-created_at": Document.created_at.desc(),
    "title": Document.title.asc(),
}


def _get_owned(db: DbSession, user_id: int, document_id: int) -> Document:
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    if document is None:
        raise AppError("not_found", "文档不存在")
    return document


def _to_out(document: Document) -> DocumentOut:
    return DocumentOut.model_validate(document)


@router.post("", response_model=DocumentEnvelope, status_code=201)
async def upload_document(
    background: BackgroundTasks,
    db: DbSession,
    user: UploadUser,
    file: UploadFile | None = File(default=None),
    title: str | None = Form(default=None),
    raw_text: str | None = Form(default=None),
) -> DocumentEnvelope:
    if file is None and not (raw_text or "").strip():
        raise AppError("bad_request", "请提供 file 或 title + raw_text")

    count = (
        db.query(Document)
        .filter(Document.user_id == user.id, Document.deleted_at.is_(None))
        .count()
    )
    if count >= settings.max_documents:
        raise AppError("quota_exceeded", f"文档数量已达上限（{settings.max_documents} 篇）")

    meta: dict = {}
    filename: str | None = None
    mime_type: str | None = None
    size_bytes = 0
    payload: bytes | None = None
    source_type = "upload"

    if file is not None:
        filename = file.filename or "upload.txt"
        ext = extension_of(filename)
        if ext not in SUPPORTED_EXTENSIONS:
            raise AppError(
                "unsupported_file_type",
                f"不支持的文件类型 {ext or '(无扩展名)'}，支持：{', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )
        payload = await file.read()
        size_bytes = len(payload)
        if size_bytes == 0:
            raise AppError("unprocessable_upload", "上传的文件是空的")
        if size_bytes > settings.max_upload_bytes:
            raise AppError(
                "file_too_large", f"文件超过 {settings.max_upload_mb}MB 限制", {"size_bytes": size_bytes}
            )
        doc_title = (title or "").strip() or filename.rsplit(".", 1)[0] or filename
        mime_type = file.content_type or "application/octet-stream"
    else:
        text = (raw_text or "").strip()
        if not text:
            raise AppError("bad_request", "raw_text 不能为空")
        if len(text.encode("utf-8")) > settings.max_upload_bytes:
            raise AppError("file_too_large", f"内容超过 {settings.max_upload_mb}MB 限制")
        source_type = "paste"
        doc_title = (title or "").strip() or text[:30]
        size_bytes = len(text.encode("utf-8"))
        mime_type = "text/plain"
        meta = {"raw_text": text}

    document = Document(
        user_id=user.id,
        title=doc_title[:255],
        source_type=source_type,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        status="pending",
        chunk_count=0,
        char_count=0,
        meta=meta,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    if payload is not None:
        background.add_task(process_document_task, document.id, payload, filename)
    else:
        background.add_task(process_document_task, document.id, None, None)

    return DocumentEnvelope(document=_to_out(document))


@router.get("", response_model=Page)
def list_documents(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None),
    sort: str = Query(default="-created_at"),
) -> Page:
    query = db.query(Document).filter(Document.user_id == user.id, Document.deleted_at.is_(None))
    if q:
        query = query.filter(Document.title.ilike(f"%{q.strip()}%"))
    if status:
        query = query.filter(Document.status == status)
    total = query.count()
    order = SORT_FIELDS.get(sort, SORT_FIELDS["-created_at"])
    rows = query.order_by(order).offset((page - 1) * page_size).limit(page_size).all()
    return Page(
        items=[_to_out(d).model_dump(mode="json") for d in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DocumentStats)
def stats(db: DbSession, user: CurrentUser) -> DocumentStats:
    raw = document_stats(db, user.id)
    return DocumentStats(
        total=raw["total"],
        ready=raw["ready"],
        processing=raw["processing"],
        failed=raw["failed"],
        chunk_total=raw["chunk_total"],
        char_total=raw["char_total"],
        by_status=[StatusCount(**item) for item in raw["by_status"]],
    )


@router.get("/{document_id}", response_model=DocumentEnvelope)
def get_document(document_id: int, db: DbSession, user: CurrentUser) -> DocumentEnvelope:
    return DocumentEnvelope(document=_to_out(_get_owned(db, user.id, document_id)))


@router.get("/{document_id}/chunks", response_model=Page)
def list_chunks(
    document_id: int,
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    document = _get_owned(db, user.id, document_id)
    query = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id)
    total = query.count()
    rows = (
        query.order_by(DocumentChunk.ord.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for chunk in rows:
        data = ChunkOut.model_validate(chunk)
        data.has_embedding = chunk.embedding is not None
        items.append(data.model_dump(mode="json"))
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.patch("/{document_id}", response_model=DocumentEnvelope)
def update_document(
    document_id: int, payload: UpdateDocumentIn, db: DbSession, user: CurrentUser
) -> DocumentEnvelope:
    document = _get_owned(db, user.id, document_id)
    if payload.title is not None:
        document.title = payload.title.strip()
        db.add(document)
        db.commit()
        db.refresh(document)
    return DocumentEnvelope(document=_to_out(document))


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, db: DbSession, user: CurrentUser) -> None:
    document = _get_owned(db, user.id, document_id)
    document.deleted_at = datetime.now(timezone.utc)
    db.add(document)
    db.commit()
    return None


@router.post("/{document_id}/reprocess", status_code=202)
def reprocess_document(
    document_id: int, background: BackgroundTasks, db: DbSession, user: CurrentUser
) -> dict:
    document = _get_owned(db, user.id, document_id)
    if document.source_type == "upload" and not document.meta.get("raw_text"):
        raise AppError(
            "bad_request",
            "上传的原始文件未保留，无法重新切分；请重新上传该文档",
        )
    document.status = "pending"
    document.error_message = None
    db.add(document)
    db.commit()
    background.add_task(process_document_task, document.id, None, None)
    return {"ok": True, "document_id": document.id, "status": "pending"}
