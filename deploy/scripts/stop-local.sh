#!/usr/bin/env bash
# Citera · 停止本地服务（保留数据库数据卷；加 -v 参数可同时删数据卷）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

if [ "${1:-}" = "-v" ]; then
  echo "[citera] 停止并删除数据卷（下次启动会重新灌种子）..."
  docker compose -f docker-compose.yml down -v
else
  echo "[citera] 停止服务（数据保留在 citera_pgdata 卷）..."
  docker compose -f docker-compose.yml down
fi
