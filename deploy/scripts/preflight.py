#!/usr/bin/env python
"""Citera 部署前自检（不修改任何东西，只检查）。

检查项：
  1. 仓库结构：backend/ 依赖清单、frontend/、frontend/dist（构建镜像前必需）
  2. 必需环境变量：DATABASE_URL、JWT_SECRET（生产要求 ≥32 位）、ENV/DEBUG 一致性
  3. 端口占用：本地 8000（或 PORT）、PostgreSQL 端口
  4. 数据库连通性：TCP → 认证 → SELECT 1
  5. pgvector 能力：vector 扩展是否可用/已安装（契约 §3 硬依赖），pg_trgm 同理
  6. Docker 守护进程是否在跑（构建/本地 compose 需要）

退出码：0 = 无致命问题（可能有告警）；1 = 存在致命问题，不要上线。

用法：
    python deploy/scripts/preflight.py --env-file deploy/.env --mode prod
    python deploy/scripts/preflight.py --mode local
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Windows 控制台默认 GBK，直接 print ✓/中文 会 UnicodeEncodeError。
# 统一把标准输出切到 UTF-8（errors=replace 兜底），配合 .cmd 里的 chcp 65001。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

FATAL = "FATAL"
WARN = "WARN"
OK = "OK"
INFO = "INFO"

results: list[tuple[str, str, str]] = []


def record(level: str, name: str, detail: str) -> None:
    results.append((level, name, detail))


def load_env_file(path: Path) -> dict[str, str]:
    """极简 .env 解析：KEY=VALUE，# 注释，支持引号。不覆盖已存在的环境变量。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def cfg(key: str, file_values: dict[str, str], default: str = "") -> str:
    return os.environ.get(key) or file_values.get(key) or default


def check_repo(mode: str) -> None:
    backend = REPO_ROOT / "backend"
    frontend = REPO_ROOT / "frontend"

    if not backend.is_dir():
        record(FATAL, "仓库结构", f"缺少 {backend}（后端由 Lead 负责，镜像无法构建）")
    else:
        has_req = (backend / "requirements.txt").is_file()
        has_pyproject = (backend / "pyproject.toml").is_file()
        if has_req:
            record(OK, "后端依赖清单", "backend/requirements.txt 存在（Dockerfile 优先使用）")
        elif has_pyproject:
            record(WARN, "后端依赖清单", "只有 backend/pyproject.toml，Dockerfile 会从 pyproject 提取 dependencies")
        else:
            record(FATAL, "后端依赖清单", "backend/ 下既无 requirements.txt 也无 pyproject.toml")
        if not (backend / "app" / "main.py").is_file():
            record(WARN, "后端入口", "未找到 backend/app/main.py（尚未落地？）")

    if not frontend.is_dir():
        record(FATAL, "仓库结构", f"缺少 {frontend}（前端由 fe-citera 负责，镜像无法构建）")
    else:
        if (frontend / "package.json").is_file():
            record(OK, "前端 manifest", "frontend/package.json 存在")
        else:
            record(FATAL, "前端 manifest", "缺少 frontend/package.json")
        if not (frontend / "pnpm-lock.yaml").is_file():
            record(WARN, "前端 lockfile", "没有 pnpm-lock.yaml，镜像里会退化为 pnpm install --no-frozen-lockfile")
        if mode == "prod" and not (frontend / "dist").is_dir():
            record(
                INFO,
                "前端产物",
                "frontend/dist 不存在——正常：镜像构建时由 stage1 现场生成，无需本地 dist",
            )

    if (REPO_ROOT / "deploy" / "Dockerfile").is_file():
        record(OK, "Dockerfile", "deploy/Dockerfile 存在")
    else:
        record(FATAL, "Dockerfile", "缺少 deploy/Dockerfile")

    if (REPO_ROOT / ".dockerignore").is_file():
        record(OK, ".dockerignore", "根 .dockerignore 存在（构建上下文瘦身）")
    else:
        record(WARN, ".dockerignore", "缺少根 .dockerignore，构建上下文会很大很慢")


def check_env(mode: str, file_values: dict[str, str]) -> dict[str, str]:
    database_url = cfg("DATABASE_URL", file_values)
    jwt_secret = cfg("JWT_SECRET", file_values)
    env_name = cfg("ENV", file_values, "dev")
    debug = cfg("DEBUG", file_values, "true")
    llm = cfg("LLM_PROVIDER", file_values, "echo")
    embedding = cfg("EMBEDDING_PROVIDER", file_values, "local")
    seed = cfg("SEED_DEMO_DATA", file_values, "true")

    if not database_url:
        record(FATAL, "DATABASE_URL", "未设置：容器会启动失败（prod compose 用 :? 强制校验）")
    elif not database_url.startswith("postgresql+psycopg://"):
        record(
            FATAL,
            "DATABASE_URL",
            f"驱动必须是 psycopg（契约 §2）：以 {database_url.split('://')[0]}:// 开头，"
            "请改成 postgresql+psycopg://",
        )
    else:
        record(OK, "DATABASE_URL", "格式正确（postgresql+psycopg://）")

    if not jwt_secret:
        record(FATAL, "JWT_SECRET", "未设置：登录会失败")
    elif jwt_secret == "dev-only-change-me-not-for-production-32chars":
        record(WARN, "JWT_SECRET", "还是示例默认值，公网部署务必换成随机串")
    elif len(jwt_secret) < 32:
        record(WARN if mode != "prod" else FATAL, "JWT_SECRET", f"长度 {len(jwt_secret)} < 32")
    else:
        record(OK, "JWT_SECRET", f"长度 {len(jwt_secret)} ≥ 32")

    if mode == "prod":
        if env_name != "prod":
            record(WARN, "ENV", f"生产部署建议 ENV=prod，当前 {env_name!r}")
        else:
            record(OK, "ENV", "prod")
        if str(debug).lower() in ("true", "1", "yes"):
            record(FATAL, "DEBUG", "生产环境 DEBUG 必须为 false（契约 §6）")
        else:
            record(OK, "DEBUG", "false")

    if llm == "echo":
        record(INFO, "LLM_PROVIDER", "echo（演示模式：检索结果受控合成，无外网/无 Key 可完整演示，契约 §0）")
    elif not cfg("LLM_API_KEY", file_values):
        record(WARN, "LLM_PROVIDER", f"{llm} 但 LLM_API_KEY 为空，运行时可能报错")
    else:
        record(OK, "LLM_PROVIDER", llm)

    if embedding == "local":
        record(INFO, "EMBEDDING_PROVIDER", "local（确定性哈希向量，无网络依赖，契约 §5.4）")
    elif not cfg("LLM_API_KEY", file_values):
        record(WARN, "EMBEDDING_PROVIDER", f"{embedding} 但未提供 Key")

    if str(seed).lower() in ("true", "1", "yes"):
        record(INFO, "SEED_DEMO_DATA", "true：容器首次启动自动灌演示数据，公网 Demo 打开即有内容")
    else:
        record(WARN, "SEED_DEMO_DATA", "false：公网 Demo 打开会是空库，面试官看不到东西")

    return {"DATABASE_URL": database_url}


def parse_db_url(database_url: str) -> dict:
    parsed = urllib.parse.urlsplit(database_url.replace("postgresql+psycopg", "postgresql", 1))
    parts = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/postgres").lstrip("/") or "postgres",
    }
    if parsed.username:
        parts["user"] = urllib.parse.unquote(parsed.username)
    if parsed.password:
        parts["password"] = urllib.parse.unquote(parsed.password)
    return parts


def port_free(host: str, port: int) -> tuple[bool, str]:
    """True = 端口空闲（能 bind）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host if host not in ("", "localhost") else "127.0.0.1", port))
        return True, "空闲"
    except OSError as exc:
        return False, f"被占用（{exc.strerror or exc}）"


def check_ports(mode: str, file_values: dict[str, str]) -> None:
    api_port = int(cfg("PORT", file_values, "8000") or 8000)
    if mode == "local":
        free, detail = port_free("127.0.0.1", api_port)
        (record(OK, f"端口 {api_port}", detail) if free
         else record(WARN, f"端口 {api_port}", f"{detail} —— 若已在跑旧容器，先 stop-local；否则改 API_PORT"))
    else:
        record(INFO, f"端口 {api_port}", "生产由平台注入/映射，本机占用检测跳过")


def check_database(database_url: str, file_values: dict[str, str]) -> None:
    if not database_url:
        return
    parts = parse_db_url(database_url)

    # 1) TCP 可达性
    try:
        with socket.create_connection((parts["host"], parts["port"]), timeout=5):
            record(OK, "数据库 TCP", f"{parts['host']}:{parts['port']} 可连接")
    except OSError as exc:
        record(FATAL, "数据库 TCP", f"{parts['host']}:{parts['port']} 连不上（{exc}）")
        return

    # 2) 认证 + SELECT 1 + pgvector 能力（需要 psycopg）
    try:
        import psycopg
    except ImportError:
        record(
            WARN,
            "数据库深度检查",
            "本机未安装 psycopg，跳过 SELECT 1 / pgvector 检查"
            "（可 pip install psycopg[binary] 后用本脚本复查）",
        )
        return

    try:
        with psycopg.connect(connect_timeout=8, **parts) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = str(cur.fetchone()[0]).split(" on ")[0]
                record(OK, "数据库认证", version)

                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                has_vector = cur.fetchone() is not None
                cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
                vector_available = cur.fetchone() is not None

                if has_vector:
                    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    record(OK, "pgvector 扩展", f"已安装 v{cur.fetchone()[0]}")
                elif vector_available:
                    record(
                        WARN,
                        "pgvector 扩展",
                        "可用但未安装：init_db 首次启动会 CREATE EXTENSION，"
                        "需要数据库账号有权限（平台托管库通常给主账号）",
                    )
                else:
                    record(
                        FATAL,
                        "pgvector 扩展",
                        "该数据库不提供 vector 扩展（契约 §3 硬依赖）。"
                        "免费平台要选带 pgvector 的 PostgreSQL 镜像/插件；"
                        "否则只能退化为 keyword 检索，请先和 Lead 商量降级方案",
                    )

                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
                if cur.fetchone() is not None:
                    record(OK, "pg_trgm 扩展", "已安装")
                else:
                    cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'")
                    record(
                        OK if cur.fetchone() is not None else WARN,
                        "pg_trgm 扩展",
                        "可用，init_db 会安装" if cur.fetchone() is not None else "不可用（中文短语兜底召回会变弱）",
                    )
    except Exception as exc:  # noqa: BLE001
        record(FATAL, "数据库认证", f"{type(exc).__name__}: {exc}")


def check_docker() -> None:
    import shutil
    import subprocess

    if not shutil.which("docker"):
        record(WARN, "Docker", "未找到 docker 命令（只部署到云平台可以忽略）")
        return
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        record(WARN, "Docker", f"docker info 执行失败：{exc}")
        return
    if proc.returncode == 0 and proc.stdout.strip():
        record(OK, "Docker 守护进程", f"运行中，Server {proc.stdout.strip()}")
    else:
        record(WARN, "Docker 守护进程", "未运行：请先启动 Docker Desktop 再做本地验证/构建镜像")


def main() -> int:
    parser = argparse.ArgumentParser(description="Citera 部署前自检")
    parser.add_argument("--env-file", default=None, help=".env 路径，默认尝试 deploy/.env")
    parser.add_argument("--mode", choices=["local", "prod"], default="local", help="检查口径")
    parser.add_argument("--skip-docker", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_file) if args.env_file else REPO_ROOT / "deploy" / ".env"
    file_values = load_env_file(env_path)

    print(f"[preflight] 仓库根：{REPO_ROOT}")
    print(f"[preflight] 环境文件：{env_path if env_path.exists() else '（不存在，仅用进程环境变量）'}")
    print(f"[preflight] 模式：{args.mode}\n")

    check_repo(args.mode)
    env = check_env(args.mode, file_values)
    check_ports(args.mode, file_values)
    check_database(env["DATABASE_URL"], file_values)
    if not args.skip_docker:
        check_docker()

    icon = {FATAL: "✗", WARN: "!", OK: "✓", INFO: "·"}
    order = {FATAL: 0, WARN: 1, OK: 2, INFO: 3}
    for level, name, detail in sorted(results, key=lambda r: order[r[0]]):
        print(f"  {icon[level]} [{level:<5}] {name}: {detail}")

    fatals = [r for r in results if r[0] == FATAL]
    warns = [r for r in results if r[0] == WARN]
    print(f"\n[preflight] 致命 {len(fatals)} 项 / 告警 {len(warns)} 项 / 共 {len(results)} 项")
    if fatals:
        print("[preflight] 结论：存在致命问题，先修掉再上线 ❌")
        return 1
    print("[preflight] 结论：可以上线 ✅" + ("（有告警，建议逐条确认）" if warns else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
