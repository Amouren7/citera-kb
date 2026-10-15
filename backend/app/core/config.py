"""Citera 运行时配置（pydantic-settings，全部可用环境变量覆盖，见 docs/CONTRACT.md §6）。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RetrievalMode = Literal["vector", "keyword", "hybrid"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- 应用 ---
    app_name: str = "Citera"
    app_version: str = "0.1.0"
    env: Literal["dev", "prod"] = "dev"
    debug: bool = True

    # --- 端口与静态资源（免费容器平台会注入 PORT）---
    port: int = 8000
    frontend_dist: str = ""

    # --- 数据库 ---
    database_url: str = "postgresql+psycopg://citera:citera@localhost:5432/citera"

    # --- 认证 ---
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Web ---
    cors_origins: str = "http://localhost:5173"
    serve_frontend: bool = True
    max_upload_mb: int = 10
    max_documents: int = 50
    max_conversations: int = 100

    # --- 检索 ---
    retrieval_mode: RetrievalMode = "hybrid"
    top_k: int = 5
    rrf_k: int = 60
    # 混合检索的两段式参数（权重在离线评测集上实测选定，见 README 对比表）
    # vector 权重刻意压低：本地演示向量不是语义模型，权重给满会把关键词的准确命中挤掉，
    # 实测 vw=1.0 时 R@1 只有 0.86，vw<=0.25 时为 0.93（与纯关键词持平，同时保留向量召回兜底）。
    hybrid_candidate_multiplier: int = 4
    hybrid_pool_size: int = 20
    hybrid_vector_weight: float = 0.25
    hybrid_keyword_weight: float = 1.0
    hybrid_rrf_weight: float = 1.0
    chunk_size: int = 800
    chunk_overlap: int = 120

    # --- 向量化 ---
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_dim: int = 384
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # --- 生成 ---
    llm_provider: Literal["echo", "openai"] = "echo"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    # --- 运行 ---
    seed_demo_data: bool = True
    rate_limit_enabled: bool = True
    demo_email: str = "demo@citera.dev"
    demo_password: str = "demo1234"
    admin_email: str = "admin@citera.dev"
    admin_password: str = "admin1234"

    @field_validator("chunk_overlap")
    @classmethod
    def _overlap_lt_size(cls, v: int, info) -> int:
        size = info.data.get("chunk_size", 800)
        if v >= size:
            raise ValueError("CHUNK_OVERLAP 必须小于 CHUNK_SIZE")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def active_embedding_provider(self) -> str:
        if self.embedding_provider == "openai" and self.embedding_api_key:
            return "openai"
        return "local"

    @property
    def active_llm_provider(self) -> str:
        if self.llm_provider == "openai" and self.llm_api_key and self.llm_model:
            return "openai"
        return "echo"

    def validate_runtime(self) -> list[str]:
        """返回启动期的告警列表（不阻断启动，但生产环境必须为空）。"""
        warnings: list[str] = []
        if self.env == "prod":
            if self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32:
                warnings.append("JWT_SECRET 使用了开发默认值或长度不足 32，生产环境必须替换")
            if self.debug:
                warnings.append("生产环境建议将 DEBUG 设为 false")
        if self.embedding_provider == "openai" and not self.embedding_api_key:
            warnings.append("EMBEDDING_PROVIDER=openai 但未配置 EMBEDDING_API_KEY，已回退 local")
        if self.llm_provider == "openai" and not (self.llm_api_key and self.llm_model):
            warnings.append("LLM_PROVIDER=openai 但未配置 LLM_API_KEY/LLM_MODEL，已回退 echo 演示模式")
        return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
