@echo off
REM ============================================================================
REM Citera 溯源知识库 · 本地一键启动（Windows / Docker Desktop）
REM   用法：双击，或在仓库任意位置执行 deploy\scripts\start-local.cmd
REM   做的事：检查 Docker → compose 构建并启动 → 等健康检查 → 打开浏览器
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "COMPOSE_FILE=docker-compose.yml"
set "BASE_URL=http://localhost:8000"

echo [citera] 工作目录：%CD%

where docker >nul 2>nul
if errorlevel 1 (
  echo [citera] 错误：未找到 docker 命令，请先安装 Docker Desktop。
  exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
  echo [citera] 错误：Docker 守护进程未运行。请先启动 Docker Desktop 再重试。
  exit /b 1
)

echo [citera] 构建镜像并启动容器（首次构建需几分钟）...
docker compose -f "%COMPOSE_FILE%" up -d --build
if errorlevel 1 (
  echo [citera] 错误：docker compose up 失败，上方是构建日志。
  exit /b 1
)

echo [citera] 等待 %BASE_URL%/api/health 就绪（最长 180s，含建表+灌种子）...
python "%~dp0healthcheck.py" --base-url %BASE_URL% --wait 180
if errorlevel 1 (
  echo [citera] 健康检查未通过，输出 api 容器最后 120 行日志：
  docker compose -f "%COMPOSE_FILE%" logs --tail 120 api
  exit /b 1
)

echo.
echo [citera] 启动成功 ✅  %BASE_URL%
echo [citera] 演示账号：demo@citera.dev / demo1234   管理员：admin@citera.dev / admin1234
echo [citera] 接口文档：%BASE_URL%/docs
echo [citera] 停止服务：deploy\scripts\stop-local.cmd
start "" %BASE_URL%
endlocal
