#!/bin/sh
# =============================================================================
# Citera 容器入口：等数据库 → 迁移/灌种子 → 单 worker 启动 uvicorn
# 以 PID 1 运行，用 exec 交接信号，SIGTERM 能正常优雅退出。
# =============================================================================
set -eu

PORT="${PORT:-8000}"
APP_DIR="${APP_DIR:-/app/backend}"
DB_WAIT_SECONDS="${DB_WAIT_SECONDS:-90}"

log() { printf '[citera] %s\n' "$*"; }

cd "$APP_DIR"

# --- 1. 等数据库可连接 -------------------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
  log "等待数据库就绪（最多 ${DB_WAIT_SECONDS}s）..."
  if python /usr/local/bin/citera-db-wait.py --timeout "$DB_WAIT_SECONDS"; then
    log "数据库已就绪"
  else
    log "错误：数据库在 ${DB_WAIT_SECONDS}s 内不可用，退出（容器会按重启策略重试）"
    exit 1
  fi
else
  log "警告：未设置 DATABASE_URL，跳过等待"
fi

# --- 2. 建表 / 灌种子 -------------------------------------------------------
if [ "${SKIP_MIGRATIONS:-false}" = "true" ]; then
  log "SKIP_MIGRATIONS=true，跳过迁移与种子数据"
elif [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  # 契约 §3：python -m app.db.init_db 幂等 —— 建扩展 → 建表/迁移 → 灌演示数据
  log "初始化数据库（建扩展 + 迁移 + 灌演示数据，幂等）..."
  if ! python -m app.db.init_db; then
    log "错误：app.db.init_db 执行失败"
    exit 1
  fi
  log "种子数据就绪：demo@citera.dev / demo1234 · admin@citera.dev / admin1234"
else
  if [ -f alembic.ini ]; then
    log "SEED_DEMO_DATA=false，只执行 alembic upgrade head"
    if ! alembic upgrade head; then
      log "错误：alembic upgrade head 失败"
      exit 1
    fi
  else
    log "警告：未找到 alembic.ini，且 SEED_DEMO_DATA=false，跳过迁移"
  fi
fi

# --- 3. 启动服务（单 worker：小内存平台硬约束）------------------------------
log "启动 uvicorn：0.0.0.0:${PORT}（单 worker）"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips '*'
