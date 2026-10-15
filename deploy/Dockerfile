# =============================================================================
# Citera 溯源知识库 · 单容器镜像（前端 SPA + FastAPI 同端口）
#
#   构建上下文（build context）= 仓库根目录 citera-kb/
#     docker build -f deploy/Dockerfile -t citera-kb:local .
#   或直接用 compose：
#     docker compose -f deploy/docker-compose.yml up -d --build
#
# 设计取舍：
#   * 单容器单端口 —— 免费容器平台（ClawCloud Run / Zeabur）按「一个服务一个端口」
#     计费，开两个服务容易超额度。FastAPI 既服务 /api 又托管 SPA（SERVE_FRONTEND=true）。
#   * 无外网 / 无 LLM Key 也必须能演示 —— 默认 EMBEDDING_PROVIDER=local（本地确定性
#     哈希向量）+ LLM_PROVIDER=echo（检索结果受控合成），见契约 §0 / §5.3 / §5.4。
#   * 小内存平台（256–512MB）—— uvicorn 单 worker，不引入 Celery/Redis 等常驻进程。
# =============================================================================

# -----------------------------------------------------------------------------
# stage 1 · 构建前端（node 只出现在这一层，不进最终镜像）
# -----------------------------------------------------------------------------
FROM node:22-alpine AS frontend-build

WORKDIR /src/frontend

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    CI=true

# 固定 pnpm 版本，避免与本地 / CI 不一致
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

# 先只拷 manifest，让依赖层在源码变化时仍能命中缓存。
# pnpm-lock.yaml 可能尚未生成，此处用通配；package.json 一定存在。
COPY frontend/package.json frontend/pnpm-lock.yaml* ./

RUN if [ -f pnpm-lock.yaml ]; then \
      pnpm install --frozen-lockfile; \
    else \
      echo "[citera] 未找到 pnpm-lock.yaml，退化为 pnpm install"; \
      pnpm install --no-frozen-lockfile; \
    fi

COPY frontend/ ./

# 契约 §8.2：产物必须是 frontend/dist，且不得依赖联网字体/CDN
RUN pnpm run build

# -----------------------------------------------------------------------------
# stage 2 · Python 运行时（FastAPI 托管 /api + SPA）
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    PORT=8000 \
    SERVE_FRONTEND=true \
    SEED_DEMO_DATA=true \
    EMBEDDING_PROVIDER=local \
    EMBEDDING_DIM=384 \
    LLM_PROVIDER=echo \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖层：requirements.txt 由后端负责人维护（固定版本，Docker 优先用它）；
# 没有时退回 pip install ./backend（读 pyproject.toml）。
COPY backend/requirements.txt backend/pyproject.toml* ./backend/
RUN python -m pip install --upgrade pip setuptools wheel && \
    if [ -f backend/requirements.txt ]; then \
      echo "[citera] 使用 backend/requirements.txt 安装依赖"; \
      pip install -r backend/requirements.txt; \
    elif [ -f backend/pyproject.toml ]; then \
      echo "[citera] 未找到 backend/requirements.txt，从 pyproject.toml 提取 dependencies"; \
      python -c "import tomllib,pathlib;d=tomllib.loads(pathlib.Path('backend/pyproject.toml').read_text('utf-8'));print(chr(10).join(d.get('project',{}).get('dependencies',[])))" > /tmp/deps.txt && \
      cat /tmp/deps.txt && \
      pip install -r /tmp/deps.txt; \
    else \
      echo "错误：backend/ 下既没有 requirements.txt 也没有 pyproject.toml" >&2; \
      exit 1; \
    fi

# 应用代码 + 前端产物 + 容器内脚本
# 前端产物落在 /app/frontend/dist，与仓库布局一致：
#   main.py 里 Path(__file__).resolve().parents[2] / "frontend" / "dist"
#   → /app/frontend/dist ✅（uvicorn 的 cwd = /app/backend）
COPY backend/ ./backend/
COPY --from=frontend-build /src/frontend/dist ./frontend/dist
COPY deploy/scripts/container-entrypoint.sh /usr/local/bin/citera-entrypoint
COPY deploy/scripts/db_wait.py /usr/local/bin/citera-db-wait.py
COPY deploy/scripts/healthcheck.py /usr/local/bin/citera-healthcheck.py

RUN chmod +x /usr/local/bin/citera-entrypoint \
             /usr/local/bin/citera-db-wait.py \
             /usr/local/bin/citera-healthcheck.py && \
    useradd --create-home --uid 10001 --shell /usr/sbin/nologin citera && \
    chown -R citera:citera /app

USER citera
WORKDIR /app/backend

EXPOSE 8000

# start-period 给「建表 + 灌种子」留时间；冷启动到可问答目标 < 60s（契约 §8.3）
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=6 \
    CMD ["python", "/usr/local/bin/citera-healthcheck.py"]

ENTRYPOINT ["/usr/local/bin/citera-entrypoint"]
