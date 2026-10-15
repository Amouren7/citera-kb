# PROGRESS · Citera 溯源知识库

> **追加规则（所有成员遵守）**：只允许在文件末尾**追加**自己的行，禁止重写整个文件——三人共用这一个文件。
> 每个人完成一个阶段就追加一行：`日期 | 成员 | 做了什么 | 证据（命令 + 输出摘要）`。
> 分子编号（如 `[infra-3]`）用于三条线各自排序，数字只增不改。

## 进度日志

| 日期 | 成员 | 做了什么 | 证据 |
|---|---|---|---|
| 2026-10-14 | infra-citera | [infra-1] 读契约并 claim `task-3`。发现 Docker 守护进程**原本未运行**，拉起 Docker Desktop 后确认可用 | `docker info` → `29.6.1 \| linux \| overlayfs`；原始报错 `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` |
| 2026-10-14 | infra-citera | [infra-2] 交付 `deploy/Dockerfile`（多阶段：node:22-alpine 构建 SPA → python:3.12-slim 运行时，单容器单端口）+ 入口脚本 `container-entrypoint.sh` / 等库 `db_wait.py` / 健康检查 `healthcheck.py` + 根 `.dockerignore` | 用**桩上下文**在 TEMP 里跑真实 Dockerfile：构建 exit 0；容器起后 `/api/health` → `{"status":"ok","db":"ok","llm_provider":"echo"}`；SPA `/` 返回 vite 产物、`/chat` 回退 200；`docker inspect` HEALTHCHECK=`healthy`；`docker exec id` → `uid=10001(citera)`（非 root）；`PORT=9090` 注入生效 → 监听 9090 |
| 2026-10-14 | infra-citera | [infra-3] 交付 `deploy/docker-compose.yml`（pgvector/pgvector:pg16 + api，healthcheck/数据卷/端口 8000）+ `deploy/docker-compose.prod.yml`（外部库，环境变量可注入）+ `deploy/.env.example` | `docker compose -f deploy/docker-compose.yml config --quiet` → exit 0；prod 版缺 `DATABASE_URL`/`JWT_SECRET` 时按 `:?` 拒绝启动（exit 1 并报中文提示），补齐环境变量后 exit 0 |
| 2026-10-14 | infra-citera | [infra-4] 交付 `.github/workflows/ci.yml`（backend：pgvector service + `alembic upgrade head` + `python -m pytest` + `init_db` 幂等两跑；frontend：`pnpm install`/`build`/`npx vitest run`；integration：compose 起真容器 + `/api/health` + SPA + `smoke_api.py` 端到端问答） | 见 `.github/workflows/ci.yml`；⚠️ 首次运行要等 T1/T2 的测试与 `frontend/package.json` 完整后才会全绿 |
| 2026-10-14 | infra-citera | [infra-5] 交付 `deploy/scripts/`：一键启动 `start-local.cmd` / `start-local.sh`、`stop-local.*`、构建 `build-image.*`、上线前自检 `preflight.py`（环境变量/端口/数据库连通/pgvector 能力/Docker 守护进程）、端到端冒烟 `smoke_api.py`、`healthcheck.py`、`db_wait.py` | `python deploy/scripts/preflight.py --mode local` 可跑；修掉了 Windows GBK 控制台 `UnicodeEncodeError: '\u2713'`（改为 stdout 强制 UTF-8 + `.cmd` 里 `chcp 65001`） |
| 2026-10-14 | infra-citera | [infra-6] 交付 `docs/DEPLOY.md`：ClawCloud Run 主推点选清单（注册→授权 GitHub→建 PostgreSQL→建应用→设环境变量→拿域名）、Zeabur 备选、自有 ECS + 域名 + Caddy 降级路径、pgvector 风险与降级、上线自检、故障排查表 | 文档 §9 免责声明：所有平台额度/UI/门槛均标注 ⚠️ **未实测，以官网为准**；已实测部分单列 |
| 2026-10-14 | infra-citera | [infra-7] 交付 `README.md`：一句话定位、架构 mermaid、截图位、评测数字表、本地启动三步、技术栈、"从 0 自研无上游 fork"声明、API 文档入口、≤200 字面试自述 | ⏳ 截图与评测数字仍为占位（见下方「待填清单」），等真实环境跑通后替换 |
| 2026-10-14 | infra-citera | [infra-8] 交叉校验契约 §2 的版本号是否真实存在（避免上镜像才发现装不上） | pip 解析结果与契约完全一致：`fastapi-0.143.0` `pydantic-2.14.1` `pydantic-settings-2.15.0` `sqlalchemy-2.1.4` `psycopg-3.3.6` `uvicorn-0.54.0`；`npm view vite@^8.0.0` → `vite@8.3.4` 存在；`pgvector/pgvector:pg16` 自带 `vector 0.8.7` |
| 2026-10-14 | infra-citera | [infra-12] 在 compose 单容器里重跑评测，按后端**最新**数据集（22 题 · 含 8 条改写问句）更新 README 数字 | `vector` R@1 **63.6%** / R@3 77.3% / MRR 0.727 / Hit 86.4% / 10.6ms；`keyword` R@1 **81.8%** / R@3 95.5% / MRR 0.886 / 6.5ms；`hybrid` R@1 **81.8%** / R@3 95.5% / MRR 0.886 / 18.5ms。**hybrid 与 keyword 打平、两者都显著优于纯向量（差约 18 个百分点）；README 如实写并解释了「top_k=5 足够宽时融合名次与关键词路一致」，未调参美化** |
| 2026-10-14 | infra-citera | [infra-13] **契约 §8.3 单容器端到端验收**：`docker compose -f deploy/docker-compose.yml up -d --build` → `http://localhost:8000` | 两容器 `healthy`（api `Up 25 seconds (healthy)` / db healthy）；`python deploy/scripts/smoke_api.py` **exit 0**（6 篇种子文档 / 提问 200 / 回答 563 字 / **引用 5 条** / citation[0]=《产品保修条款（2026 版）》ord=2 字段齐全 / 首行是 echo 声明）；`/` `/chat` `/documents` `/evaluation` `/login` `/documents/1` 全部 200 且返回 SPA；`/docs` 200；`/api/v1/nope` → **JSON 404 未落到 SPA 回退**；冷启动 25s 内 healthy（契约目标 <60s）✅ |
| 2026-10-14 | infra-citera | [infra-14] 用 Playwright 拍 5 张真实截图写入 `docs/screenshots/`，并把截图脚本的选择器改对（登录页有「演示账号 点一下自动填入」；**「登录」同时是 tab 文案，必须点 `button[type=submit]`**，否则点到 tab 上不会提交） | `node deploy/scripts/screenshot.mjs --base-url http://localhost:8000` **exit 0**，5 张 1440×900；`01-chat.png` 可见 echo 声明行 + **5 个引用角标 [1]~[5]** + 「检索轨迹 命中 5 块 vector」+ 顶栏 `LLM echo / DB ok`；`02-documents.png` 文档 6 / 已就绪 6 / 片段 36 / 字符 2687；`00-login.png` 与 `04-document-detail.png` 均已人工查看确认 |
| 2026-10-14 | infra-citera | [infra-15] **端到端跑出来的契约违反（已定位到确定原因并报 Lead + fe-citera）**：评测 run 的 id 字段名与契约 §4.2 不符 → 评测页「指标对比」柱状图与「逐题命中排名」**永不渲染** | 三个接口 `runs[]` 实测只有 `id` 没有 `run_id`（`GET /evaluations/runs`、`POST /evaluations/run`、`GET /evaluations/runs/compare` 一致；而 `items[].item_id`、`items[].per_run[].run_id` 是对的）→ 前端 `result.runs.map(r => r.run_id)` 得到 `undefined` → 发出 `GET compare?ids=undefined,undefined,undefined` **实测 HTTP 400** `bad_request: ids 必须是逗号分隔的整数` → `compare.value=null` → `metricRows=[]` → 面板走空状态分支。建议后端 run 序列化**同时输出 `id` 与 `run_id`**，前端无需改动 |
| 2026-10-14 | infra-citera | [infra-9] 用**真实后端**验证容器全链路：在 TEMP 生成临时 Dockerfile，**只把 SPA 阶段换成桩**、runtime 阶段逐字沿用 `deploy/Dockerfile`，构建镜像后接 `pgvector/pgvector:pg16` 跑起来 | 构建 exit 0；空库 `alembic upgrade head` → `Running upgrade  -> 0001_initial, 初始建表迁移` ✅（契约 §8.1）；日志出现 `种子数据就绪`；`python deploy/scripts/smoke_api.py --base-url http://localhost:18000` → **exit 0**：`/api/health` db=ok / 6 篇种子文档 / 提问 200 / 回答 563 字 / **引用 5 条** / citation[0]=《产品保修条款（2026 版）》ord=2 score=0.9885 字段齐全 / 回答首行 `（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）` → **契约 §0「无 Key、无外网也能完整演示」已实测** |
| 2026-10-14 | infra-citera | [infra-10] 在真实容器里跑评测，把实测数字填进 README（数据集 14 题、`top_k=5`、RRF `k=60`） | `vector` R@1 **78.6%** / MRR 0.857 / 10.1ms；`keyword` R@1 **92.9%** / MRR 0.964 / 6.1ms；`hybrid` R@1 **85.7%** / MRR 0.929 / 17.2ms（三者 Hit Rate 与 R@5/R@10 均 100%）。**hybrid 稳定优于纯向量，但本数据集上 keyword 单路最高——README 按实测如实写并解释了原因，没有为了让 hybrid 好看去调数据集或调参** |
| 2026-10-14 | infra-citera | [infra-11] 行尾/编码加固：`.cmd` 转 CRLF（cmd.exe 解析多行 `if` 块需要），`.sh/.py/.mjs` 保持 LF，并新增 `deploy/.gitattributes` 强制 `*.sh eol=lf`（否则 Windows 上 `core.autocrlf=true` 会让容器 entrypoint 变成 CRLF 直接启动失败） | 逐个文件读字节统计：`container-entrypoint.sh` CRLF=0 / LF=59；`start-local.cmd` 等 4 个 .cmd 已全部 CRLF；`.github/workflows/ci.yml` 用 pyyaml 解析通过 → `jobs=['backend','frontend','integration']` |
| 2026-10-15 | lead | [lead-1] 补齐 Alembic 迁移（`0001_initial`）与后端测试套件；空库迁移在本机 PostgreSQL 16 + pgvector 实测通过 | `alembic upgrade head` → `Running upgrade -> 0001_initial`；11 张表；`vector(384)` / `jsonb` / `bigint[]` / HNSW + GIN 索引全部正确；`pytest` **124 passed** |
| 2026-10-15 | lead | [lead-2] 按评测驱动重构检索：RRF 直接排名会让 hybrid **输给单路**（R@1 0.86 < 纯关键词 0.93），改为「并集候选池 → 名次级重排」；关键词路放弃 PG `ts_rank_cd`（中文全 0 分），改 IDF 加权覆盖率 | 契约变更 C-008 / C-009；单测 `test_retrieval.py` 覆盖 RRF 与被否决方案；README 如实写出"hybrid 未超过关键词，因默认向量非语义模型" |
| 2026-10-15 | lead | [lead-3] 评测集扩到 **22 题**（14 原文措辞 + 8 同义改写），并修种子幂等性（重建文档会导致 chunk 主键变化、gold 引用失效、指标归零） | 连续两次 `seed_all` → `documents_rebuilt=0`；`test_admin.py::test_reseed_is_idempotent` 断言 |
| 2026-10-15 | lead | [lead-4] **浏览器端到端验收 13 项全绿**，并抓出 3 个"静默失败"缺陷（tsc/vitest/build 都测不出） | 见 `docs/E2E-REPORT.md`：① `run_id` 契约违反→评测页空白；② Vue SFC 编译器改写箭头参数→`ReferenceError: per_run`；③ 运行评测后 ECharts 实例失效→图表永久空白。修复后 `tools/e2e_final.py` exit 0、零控制台错误、移动视口 overflow=0 |
| 2026-10-15 | lead | [lead-5] 推送 GitHub 公开仓库并修 CI 首跑失败 | 仓库 `https://github.com/Amouren7/citera-kb`（146 文件 / 1.24 MB，依赖目录已忽略）；CI 首跑失败根因：工作流传 `ENV=test` 而配置 Literal 只允许 `dev\|prod` → 已加入 `test`（commit `4d53bac`） |
| 2026-10-15 | lead | [lead-6] 磁盘占用收口：验证完成后删除 `node_modules` / `.venv` / `dist` 等可再生依赖 | 项目占用 **394.9 MB → 2.0 MB**（源码+文档+截图全保留）；恢复命令：`pnpm install` / `python -m venv .venv && pip install -r requirements-dev.txt` |

## 待填清单（基础设施负责人负责收口）

| 位置 | 待填内容 | 阻塞于 |
|---|---|---|
| `README.md` `<!-- DEMO_URL -->` | 公网 HTTPS 链接 | **需要项目所有者本人授权平台账号**（见 `docs/DEPLOY.md`）；技术侧已就绪 |
| ~~`README.md` `<!-- EVAL_NUMBERS -->`~~ | ✅ **已填**（[infra-12] 22 题实测：三模式 Recall@1/3/5/10 + MRR + Hit Rate + 延迟） | 已完成 |
| ~~`README.md` 截图区~~ | ✅ 已填 `docs/screenshots/00-login.png` ~ `04-document-detail.png` | 已完成 |
| `docs/DEPLOY.md` §2/§3 | 平台额度与 UI 文案核实 | 平台官网（当前环境 DNS 受限无法访问，已标注未实测） |
