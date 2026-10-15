#!/usr/bin/env bash
# =============================================================================
# Citera · 构建镜像（等价于 CI 里的 docker build，用于本地/上线前验证）
#   用法：bash deploy/scripts/build-image.sh [tag]
#   默认 tag：citera-kb:local
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TAG="${1:-citera-kb:local}"

cd "${REPO_ROOT}"
echo "[citera] 构建上下文：${REPO_ROOT}"
echo "[citera] 镜像标签：${TAG}"

docker build -f deploy/Dockerfile -t "${TAG}" .

echo "[citera] 构建完成 ✅"
docker images "${TAG}"
