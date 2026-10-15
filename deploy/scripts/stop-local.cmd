@echo off
REM Citera · 停止本地服务（保留数据库数据卷；加 -v 参数可同时删数据卷）
setlocal
cd /d "%~dp0.."
if /i "%~1"=="-v" (
  echo [citera] 停止并删除数据卷（下次启动会重新灌种子）...
  docker compose -f docker-compose.yml down -v
) else (
  echo [citera] 停止服务（数据保留在 citera_pgdata 卷）...
  docker compose -f docker-compose.yml down
)
endlocal
