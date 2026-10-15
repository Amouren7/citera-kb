@echo off
REM Citera · 部署前自检（Windows）
REM   用法：deploy\scripts\preflight.cmd [local|prod]
setlocal
REM 控制台切 UTF-8，避免中文/符号输出乱码或报 UnicodeEncodeError
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=local"
cd /d "%~dp0..\.."
python deploy\scripts\preflight.py --mode %MODE% --env-file deploy\.env
exit /b %errorlevel%
