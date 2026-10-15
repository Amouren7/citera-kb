@echo off
REM ============================================================================
REM Citera · 构建镜像（等价于 CI 里的 docker build，用于本地/上线前验证）
REM   用法：deploy\scripts\build-image.cmd [tag]
REM   默认 tag：citera-kb:local
REM ============================================================================
setlocal
set "TAG=%~1"
if "%TAG%"=="" set "TAG=citera-kb:local"

REM 构建上下文必须是仓库根（frontend/ 与 backend/ 都在根下）
cd /d "%~dp0..\.."
echo [citera] 构建上下文：%CD%
echo [citera] 镜像标签：%TAG%

docker build -f deploy\Dockerfile -t "%TAG%" .
if errorlevel 1 (
  echo [citera] 错误：镜像构建失败。
  exit /b 1
)

echo [citera] 构建完成 ✅
docker images "%TAG%"
endlocal
