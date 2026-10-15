#!/usr/bin/env bash
# Citera · 部署前自检（Linux / macOS）
#   用法：bash deploy/scripts/preflight.sh [local|prod]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODE="${1:-local}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || PYTHON_BIN=python
cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" deploy/scripts/preflight.py --mode "${MODE}" --env-file deploy/.env
