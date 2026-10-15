"""Pydantic v2 请求/响应模型（严格对齐契约 §4，字段名不得擅自改动）。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

RetrievalMode = Literal["vector", "keyword", "hybrid"]

PASSWORD_MIN = 8


def _validate_password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"密码至少 {PASSWORD_MIN} 位")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("密码需同时包含字母和数字")
    return value


# ---------------------------------------------------------------- 通用
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class TokenPair(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "bearer"


class OkOut(BaseModel):
    ok: bool = True


# ---------------------------------------------------------------- 认证
class RegisterIn(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=PASSWORD_MIN, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("显示名称不能为空")
        return cleaned


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UpdateMeIn(BaseModel):
    display_name: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None


class UserEnvelope(BaseModel):
    user: UserOut


# ---------------------------------------------------------------- 文档
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    filename: str | None
    mime_type: str | None
    size_bytes: int
    status: str
    error_message: str | None
    chunk_count: int
    char_count: int
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class DocumentEnvelope(BaseModel):
    document: DocumentOut


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ord: int
    heading: str | None
    content: str
    token_estimate: int
    has_embedding: bool = False


class UpdateDocumentIn(BaseModel):
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=255)] = None


class StatusCount(BaseModel):
    status: str
    count: int


class DocumentStats(BaseModel):
    total: int
    ready: int
    processing: int
    failed: int
    chunk_total: int
    char_total: int
    by_status: list[StatusCount]


# ---------------------------------------------------------------- 会话 / 消息
class Citation(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    ord: int
    heading: str | None = None
    snippet: str
    score: float
    retrieval: Literal["vector", "keyword", "hybrid"]
    rank: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    latency_ms: int | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)


class ConversationEnvelope(BaseModel):
    conversation: ConversationOut


class ConversationDetailEnvelope(BaseModel):
    conversation: ConversationDetail


class CreateConversationIn(BaseModel):
    title: Annotated[str | None, Field(default=None, max_length=255)] = None


class UpdateConversationIn(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]


class AskIn(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=4000)]
    stream: bool = False
    top_k: Annotated[int, Field(default=5, ge=1, le=20)] = 5
    retrieval_mode: RetrievalMode = "hybrid"
    document_ids: list[int] | None = None

    @field_validator("content")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("提问内容不能为空")
        return v


class AskEnvelope(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut


class RetrievedChunk(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    ord: int
    heading: str | None = None
    snippet: str
    score: float
    retrieval: Literal["vector", "keyword", "hybrid"]
    rank: int


# ---------------------------------------------------------------- 评测
class EvalDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    is_seed: bool
    created_at: datetime
    item_count: int = 0


class EvalItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    gold_chunk_ids: list[int] = Field(default_factory=list)
    gold_document_titles: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvalMetrics(BaseModel):
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    hit_rate: float
    avg_latency_ms: float
    item_count: int


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int = 0
    dataset_id: int
    mode: str
    top_k: int
    metrics: EvalMetrics
    item_count: int
    duration_ms: int
    created_at: datetime

    @model_validator(mode="after")
    def _sync_run_id(self) -> EvalRunOut:
        """契约 §4.2 的对外字段名是 ``run_id``，而 ORM/分页/compare 里同一实体也叫 ``id``。

        两个都输出：``id`` 与其它资源写法一致，``run_id`` 满足契约。
        只输出 ``id`` 时前端 `runs.map(r => r.run_id)` 拿到 undefined，
        对比接口收到 `ids=undefined,...` 直接 400 —— infra-citera 在真实容器里实测到过。
        """
        if not self.run_id:
            object.__setattr__(self, "run_id", self.id)
        return self


class EvalRunRequest(BaseModel):
    dataset_id: int
    modes: list[Literal["vector", "keyword", "hybrid"]] = Field(
        default_factory=lambda: ["vector", "keyword", "hybrid"]
    )
    top_k: Annotated[int, Field(default=5, ge=1, le=20)] = 5

    @field_validator("modes")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("至少选择一种检索模式")
        seen: list[str] = []
        for mode in v:
            if mode not in seen:
                seen.append(mode)
        return seen


class EvalRunEnvelope(BaseModel):
    runs: list[EvalRunOut]


class EvalPerRun(BaseModel):
    run_id: int
    rank: int | None
    hit: bool


class EvalItemCompare(BaseModel):
    item_id: int
    question: str
    per_run: list[EvalPerRun]


class EvalCompareOut(BaseModel):
    runs: list[EvalRunOut]
    items: list[EvalItemCompare]


# ---------------------------------------------------------------- 管理
class Recent7d(BaseModel):
    documents: int
    messages: int


class AdminStats(BaseModel):
    users: int
    documents: int
    chunks: int
    conversations: int
    messages: int
    eval_runs: int
    recent_7d: Recent7d


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


class SettingsEnvelope(BaseModel):
    settings: dict[str, Any]


class SettingsUpdateIn(BaseModel):
    settings: dict[str, Any]


# ---------------------------------------------------------------- 元信息
class LimitsOut(BaseModel):
    max_upload_mb: int
    max_documents: int
    max_conversations: int


class MetaOut(BaseModel):
    app_name: str
    version: str
    registration_open: bool
    limits: LimitsOut


class HealthOut(BaseModel):
    status: str
    version: str
    db: str
    llm_provider: str
