#!/usr/bin/env bash
# =============================================================================
# Citera 溯源知识库 · 本地一键启动（Linux / macOS / WSL）
#   用法：bash deploy/scripts/start-local.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.yml"
BASE_URL="${BASE_URL:-http://localhost:8000}"

cd "${DEPLOY_DIR}"
echo "[citera] 工作目录：${DEPLOY_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[citera] 错误：未找到 docker 命令。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[citera] 错误：Docker 守护进程未运行（docker info 失败）。" >&2
  exit 1
fi

echo "[citera] 构建镜像并启动容器（首次构建需几分钟）..."
docker compose -f "${COMPOSE_FILE}" up -d --build

echo "[citera] 等待 ${BASE_URL}/api/health 就绪（最长 180s，含建表+灌种子）..."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then PYTHON_BIN=python; fi

if ! "${PYTHON_BIN}" "${SCRIPT_DIR}/healthcheck.py" --base-url "${BASE_URL}" --wait 180; then
  echo "[citera] 健康检查未通过，输出 api 容器最后 120 行日志：" >&2
  docker compose -f "${COMPOSE_FILE}" logs --tail 120 api
  exit 1
fi

cat <<EOF

[citera] 启动成功 ✅  ${BASE_URL}
[citera] 演示账号：demo@citera.dev / demo1234   管理员：admin@citera.dev / admin1234
[citera] 接口文档：${BASE_URL}/docs
[citera] 停止服务：bash deploy/scripts/start-local.sh 的同级 stop-local.sh
EOF

if command -v xdg-open >/dev/null 2>&1; then xdg-open "${BASE_URL}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then open "${BASE_URL}" >/dev/null 2>&1 || true
fi
