"""会话与问答接口（契约 §4.2 会话段 + SSE 事件序列）。

流式实现要点：SSE 由 ``StreamingResponse`` 异步产出，而 FastAPI 的 ``get_db`` 依赖会在
响应返回后被关闭——所以生成器内部**自己开一个会话**（``SessionLocal``），
绝不复用请求级 session。这是流式接口最容易踩的坑。
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import AskUser, CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import Conversation, Message
from app.schemas import (
    AskEnvelope,
    AskIn,
    ConversationDetail,
    ConversationDetailEnvelope,
    ConversationEnvelope,
    ConversationOut,
    CreateConversationIn,
    MessageOut,
    Page,
    UpdateConversationIn,
)
from app.services.answer import generate, stream_answer
from app.services.retrieval import retrieve

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])

TITLE_MAX = 30


def _get_owned(db: DbSession, user_id: int, conversation_id: int) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
        .first()
    )
    if conversation is None:
        raise AppError("not_found", "会话不存在")
    return conversation


def _summary(db: DbSession, conversation: Conversation) -> ConversationOut:
    stats = db.execute(
        select(func.count(Message.id), func.max(Message.created_at)).where(
            Message.conversation_id == conversation.id
        )
    ).one()
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=int(stats[0] or 0),
        last_message_at=stats[1],
    )


def _message_out(message: Message) -> MessageOut:
    return MessageOut.model_validate(message)


@router.get("", response_model=Page)
def list_conversations(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page:
    query = db.query(Conversation).filter(
        Conversation.user_id == user.id, Conversation.deleted_at.is_(None)
    )
    total = query.count()
    rows = (
        query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return Page(
        items=[_summary(db, c).model_dump(mode="json") for c in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ConversationEnvelope, status_code=201)
def create_conversation(
    payload: CreateConversationIn, db: DbSession, user: CurrentUser
) -> ConversationEnvelope:
    count = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
        .count()
    )
    if count >= settings.max_conversations:
        raise AppError("quota_exceeded", f"会话数量已达上限（{settings.max_conversations} 个）")

    title = (payload.title or "").strip() or "新会话"
    conversation = Conversation(user_id=user.id, title=title[:255])
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationEnvelope(conversation=_summary(db, conversation))


@router.get("/{conversation_id}", response_model=ConversationDetailEnvelope)
def get_conversation(conversation_id: int, db: DbSession, user: CurrentUser) -> ConversationDetailEnvelope:
    conversation = _get_owned(db, user.id, conversation_id)
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    summary = _summary(db, conversation)
    detail = ConversationDetail(
        **summary.model_dump(),
        messages=[_message_out(m) for m in messages],
    )
    return ConversationDetailEnvelope(conversation=detail)


@router.patch("/{conversation_id}", response_model=ConversationEnvelope)
def update_conversation(
    conversation_id: int, payload: UpdateConversationIn, db: DbSession, user: CurrentUser
) -> ConversationEnvelope:
    conversation = _get_owned(db, user.id, conversation_id)
    conversation.title = payload.title.strip()[:255]
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationEnvelope(conversation=_summary(db, conversation))


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, db: DbSession, user: CurrentUser) -> None:
    conversation = _get_owned(db, user.id, conversation_id)
    conversation.deleted_at = datetime.now(timezone.utc)
    db.add(conversation)
    db.commit()
    return None


# ---------------------------------------------------------------- 提问
def _history(db: DbSession, conversation_id: int) -> list[dict[str, str]]:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(6)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def _prepare_ask(db: DbSession, user: CurrentUser, conversation_id: int, payload: AskIn) -> tuple[Conversation, Message, Message]:
    conversation = _get_owned(db, user.id, conversation_id)
    user_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content=payload.content,
        citations=[],
    )
    db.add(user_message)
    if conversation.title in ("", "新会话"):
        conversation.title = payload.content[:TITLE_MAX]
    db.add(conversation)
    db.commit()
    db.refresh(user_message)

    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content="",
        citations=[],
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    return conversation, user_message, assistant_message


@router.post("/{conversation_id}/messages")
def ask(
    conversation_id: int,
    payload: AskIn,
    db: DbSession,
    user: AskUser,
):
    """非流式返回 AskEnvelope；stream=true 时返回 text/event-stream。"""
    conversation, user_message, assistant_message = _prepare_ask(db, user, conversation_id, payload)

    if not payload.stream:
        started = time.perf_counter()
        result = retrieve(
            db, user.id, payload.content, mode=payload.retrieval_mode,
            top_k=payload.top_k, document_ids=payload.document_ids,
        )
        history = _history(db, conversation.id)
        answer = generate(payload.content, result.chunks, history)
        latency = int((time.perf_counter() - started) * 1000)
        assistant_message.content = answer.content
        assistant_message.citations = answer.citations
        assistant_message.latency_ms = latency
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        return AskEnvelope(
            user_message=_message_out(user_message),
            assistant_message=_message_out(assistant_message),
        )

    conversation_id_value = conversation.id
    user_message_id = user_message.id
    assistant_message_id = assistant_message.id
    query = payload.content
    mode = payload.retrieval_mode
    top_k = payload.top_k
    document_ids = payload.document_ids
    user_id = user.id

    def event(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generator() -> Iterator[str]:
        session = SessionLocal()
        started = time.perf_counter()
        try:
            yield event(
                "meta",
                {
                    "conversation_id": conversation_id_value,
                    "user_message_id": user_message_id,
                    "assistant_message_id": assistant_message_id,
                    "retrieval_mode": mode,
                    "top_k": top_k,
                },
            )
            result = retrieve(
                session, user_id, query, mode=mode, top_k=top_k, document_ids=document_ids
            )
            yield event(
                "retrieval",
                {
                    "chunks": [
                        {
                            "chunk_id": c.chunk_id,
                            "document_id": c.document_id,
                            "document_title": c.document_title,
                            "ord": c.ord,
                            "heading": c.heading,
                            "snippet": c.snippet(query),
                            "score": c.score,
                            "retrieval": c.retrieval,
                            "rank": c.rank,
                        }
                        for c in result.chunks
                    ],
                    "elapsed_ms": result.elapsed_ms,
                },
            )

            history = _history(session, conversation_id_value)
            final = None
            prompt_chars = sum(len(c.content) for c in result.chunks)
            completion_chars = 0
            for kind, value in stream_answer(query, result.chunks, history):
                if kind == "delta":
                    completion_chars += len(value)
                    yield event("delta", {"text": value})
                else:
                    final = value

            latency = int((time.perf_counter() - started) * 1000)
            if final is not None:
                message = session.get(Message, assistant_message_id)
                if message is not None:
                    message.content = final.content
                    message.citations = final.citations
                    message.latency_ms = latency
                    session.add(message)
                    session.commit()
            yield event(
                "done",
                {
                    "assistant_message_id": assistant_message_id,
                    "finish_reason": "stop",
                    "latency_ms": latency,
                    "usage": {
                        "prompt_chars": prompt_chars,
                        "completion_chars": completion_chars,
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001 - 流内异常必须以 error 事件收尾
            session.rollback()
            yield event("error", {"code": "internal_error", "message": str(exc)})
        finally:
            session.close()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
