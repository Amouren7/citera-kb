# Citera 部署手册（DEPLOY.md）

> 目标：把这个仓库变成一个**能贴到简历上的公网 HTTPS 链接**。
> 读者：未来的你（或接手的人）。每一步都写成「点哪里 / 填什么值 / 怎么验证」。
>
> **可信度标注约定**（重要）：
> - ✅ **已实测** —— 我在本机跑过，附命令。
> - ⚠️ **未实测** —— 平台 UI / 免费额度 / 政策类信息，我无法在当前环境核实。
>   这类内容**以官网为准**，数字和按钮文案可能已经变了，请边点边核对。

---

## 0. 三条路径怎么选

| 路径 | 成本 | 难度 | 适用场景 | 本文档 |
|---|---|---|---|---|
| **A. ClawCloud Run**（主推） | 有免费额度（见 §2.1） | 低：点几下 | 主 Demo 链接，给面试官点开 | §2 |
| **B. Zeabur Free Plan**（备选） | 有免费层但限制多（见 §3.1） | 低 | A 不满足注册条件时的替代 | §3 |
| **C. 自有 ECS + 域名**（降级） | 云服务器 + 域名（约 100 元/年起） | 中：要会 ssh | 平台政策变动 / 要长期稳定 | §4 |

**本项目为单容器单端口设计**（FastAPI 同时托管 SPA 与 `/api`），
所以三条路径都只需要「一个 Web 服务 + 一个 PostgreSQL」，不需要 Nginx 反代、不需要两个服务。

---

## 1. 部署前必须先定下来的 4 个值

| 变量 | 怎么取值 | 说明 |
|---|---|---|
| `JWT_SECRET` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` | 必须 ≥32 位随机串，别用仓库里的示例值 |
| `DATABASE_URL` | 平台 PostgreSQL 的连接串，**驱动段必须是 `postgresql+psycopg://`** | 用 psycopg3，不要 psycopg2（契约 §2） |
| `SEED_DEMO_DATA` | `true` | 首次启动自动建表 + 灌演示数据，公网打开就有内容可点 |
| `PORT` | 一般不用自己填 | 平台注入 `PORT` 时容器自动监听该端口 |

> `DATABASE_URL` 常见坑：平台给的串可能是 `postgresql://...`（不带驱动）。
> 本项目的 SQLAlchemy 需要 `postgresql+psycopg://`，**手动补 `+psycopg`**。
> 若平台要求 TLS，加 `?sslmode=require`。

---

## 2. 路线 A：ClawCloud Run（主推）

### 2.1 前置条件（⚠️ 未实测，以官网为准）

- 需要 **GitHub 账号**注册登录；社区资料普遍提到免费额度与 **GitHub 账号注册时长（约 180 天）** 挂钩，
  ⚠️ **具体门槛和额度数字我没有实测，请以 [ClawCloud 官网](https://claw.cloud/) 的 Pricing 页为准**，不要照抄本文档里的数字。
- 参考（第三方资料，非官方，仅供了解形态）：
  [ClawCloud Run 免费空间说明（CSDN）](https://blog.csdn.net/skywalk8163/article/details/147356334)、
  [用 ClawCloud Run 免费额度部署应用（Halo 论坛）](https://bbs.halo.run/d/6903)、
  [薅一个 ClawCloud 的免费容器（博客园）](https://www.cnblogs.com/jsccc520/p/18902034)
- 平台形态：K8s 底座的多租户 PaaS，有 **App Launchpad（部署容器应用）** 和 **Database（托管数据库）** 两类资源。
  [官方文档：从 Docker 迁移](https://docs.run.claw.cloud/)、[官方文档：从 Docker Compose 迁移](https://docs.run.claw.cloud/)

### 2.2 逐屏清单（照着点）

> ⚠️ **未实测**：下面的按钮文案是我按常见 PaaS 界面写的，你实际看到的可能不一样——
> **看功能，不要看文案**。预计总耗时 10–15 分钟（其中构建 3–8 分钟）。

#### Step 0 · 先自查资格（不满足就别往下走）

```bash
# 你的 GitHub 账号注册时间（本机 gh CLI 已登录 Amouren7）
gh api users/Amouren7 --jq '.created_at'
```

- 社区资料普遍反馈：免费额度要求 GitHub 账号**注册满 180 天**（⚠️ 未实测，以官网为准）。
- 若 `created_at` 距今**不足 180 天**：很可能拿不到免费额度，
  **直接跳到 §3（Zeabur）或 §4（自有 ECS）**，不要在这里耗时间。
- 顺手确认仓库已在 GitHub 上（CI 和平台构建都需要）：
  ```bash
  gh repo view --json nameWithOwner,defaultBranchRef
  ```

#### Step 1 · 登录

| 点哪里 | 填什么 | 应该看到 |
|---|---|---|
| 打开 [run.claw.cloud](https://run.claw.cloud/) | 点 **Continue with GitHub** → **Authorize** | 进入控制台首页（可能是空白项目列表） |

#### Step 2 · 选区域

| 点哪里 | 填什么 | 应该看到 |
|---|---|---|
| 右上角/顶部的区域选择器 | 选**新加坡**或**日本**（离深圳近，国内访问更快） | 区域名出现在顶部 |

> 所有资源（数据库 + 应用）**必须建在同一个区域**，否则内网连不上、只能走公网。

#### Step 3 · 建 PostgreSQL

| 点哪里 | 填什么 | 应该看到 |
|---|---|---|
| 左侧 **Database** → **Create Database** | 类型选 **PostgreSQL**；版本优先 16（pgvector 生态最稳）；规格选最小档 | 几秒后状态变成 **Running** |
| 详情页 → **Connection / 连接信息** | 复制 host / port / database / username / password | 一串连接信息 |

**立刻做两件事，别跳过：**

1. **改造连接串**（平台给的通常不能直接给 SQLAlchemy 用）：
   ```
   平台给的：  postgresql://user:pass@host:5432/db
   你要用的：  postgresql+psycopg://user:pass@host:5432/db?sslmode=require
                  ^^^^^^^^^^  必须补这一段        ^^^^^^^^^^^^^^^^^^^^ 平台要求 TLS 时加
   ```
2. **验证 pgvector 可用**（在平台的 SQL 控制台 / Query 页执行，见 §6）：
   ```sql
   SELECT name, default_version FROM pg_available_extensions WHERE name IN ('vector','pg_trgm');
   ```
   - 两行都有 → ✅ 继续。
   - **缺 `vector` → 停手**，走 §6 的降级方案（要么换平台，要么用自有 ECS）。
     契约 §3 的向量检索、HNSW 索引全都依赖它，缺了这步后面必炸。

#### Step 4 · 建应用

| 点哪里 | 填什么 | 应该看到 |
|---|---|---|
| 左侧 **App Launchpad** → **Create App** | 应用名随意，如 `citera-kb` | 进入创建表单 |
| **Source / Image** | 选 **GitHub Repo**（不是 Docker Image），授权并选中你的 `citera-kb` 仓库 | 出现分支选择 |
| **Branch** | `main` | — |
| **Build / Dockerfile path** | `deploy/Dockerfile` | — |
| **Build context** | 仓库根（留空或 `/`，**不要**填 `deploy`） | — |
| **Container Port** | `8000` | — |
| **Resources** | 256–512MB 内存、**1 副本** | — |

> 构建上下文必须是**仓库根**：Dockerfile 要从 `frontend/` 和 `backend/` 两个目录 COPY。
> 若平台只允许仓库根的同名 `Dockerfile`，见 §5.1。

#### Step 5 · 设环境变量

应用详情 → **Environment Variables / 环境变量** → 逐个添加：

```bash
# 先生成一个强随机 JWT_SECRET（本机跑，粘进平台）
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

| Key | Value |
|---|---|
| `ENV` | `prod` |
| `DEBUG` | `false` |
| `DATABASE_URL` | Step 3 改造后的 `postgresql+psycopg://...?sslmode=require` |
| `JWT_SECRET` | 上面命令的输出（≥32 位） |
| `SEED_DEMO_DATA` | `true` ← **公网 Demo 打开就有内容的前提** |
| `EMBEDDING_PROVIDER` | `local` ← 无外网也能向量化 |
| `EMBEDDING_DIM` | `384` |
| `LLM_PROVIDER` | `echo` ← 无 Key 也能完整问答 |
| `SERVE_FRONTEND` | `true` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` |
| `RATE_LIMIT_ENABLED` | `true` |
| `MAX_UPLOAD_MB` | `10` |

> **现在不要填 `LLM_API_KEY`。** `echo` 模式下答案由检索结果**受控合成**并逐句标注来源（契约 §0），
> 演示环境没有 Key、甚至没有外网也能完整跑通，这对公网链接的稳定性更重要。

#### Step 6 · 部署，并确认日志走到了最后一行

点 **Deploy / Create**，然后在 **Logs** 里盯这几行（✅ 这些行的格式我已在本地容器实测过）：

```
[citera] 等待数据库就绪（最多 90s）...
[db-wait] 第 1 次尝试成功：<host>:5432/<db>
[citera] 数据库已就绪
[citera] 初始化数据库（建扩展 + 迁移 + 灌演示数据，幂等）...
[citera] 种子数据就绪：demo@citera.dev / demo1234 · admin@citera.dev / admin1234
[citera] 启动 uvicorn：0.0.0.0:8000（单 worker）
```

- 卡在 `等待数据库就绪` 超时 → 见 §8 第 2 行。
- 看到 `种子数据就绪` 但没看到 `uvicorn` → 看后面有没有 Python traceback。
- **首次部署请给 2–3 分钟**：要建扩展 + 建表 + 灌 6 篇文档 + 12 题评测集。

#### Step 7 · 拿公网域名

| 点哪里 | 填什么 | 应该看到 |
|---|---|---|
| 应用详情 → **Networking / Domains / 网络** | 点 **Add / Generate Domain**（部分平台要先把 8000 端口暴露） | 一个 `https://xxx.xxxx.xxx` 域名 |

把域名记下来 → 下一步 + 回填 `README.md` 的 `<!-- DEMO_URL -->`。

#### Step 8 · 验证（4 条命令，全绿才算上线成功）

```bash
BASE=https://你的域名

curl -fsS $BASE/api/health          # 期望 {"status":"ok",...,"db":"ok",...}
curl -fsSI $BASE/docs | head -1      # 期望 200（接口文档可访问）
curl -fsS $BASE/ | head -5           # 期望 HTML，不是 JSON 错误
python deploy/scripts/smoke_api.py --base-url $BASE   # 端到端：登录→提问→校验引用
```

#### Step 9 · 回填仓库

1. 把域名填进 `README.md` 的 `<!-- DEMO_URL -->` 之间（删掉"部署完成后填这里"那句）。
2. 在 `README.md` 里贴一张真实截图（`docs/screenshots/`）。
3. 把这次部署的结论追加一行到 `docs/PROGRESS.md`。


### 2.3 环境变量速查

完整清单和默认值见契约 §6 与 [`deploy/.env.example`](../deploy/.env.example)。
免费平台**只填下面这 10 个**即可跑通：

```
ENV=prod
DEBUG=false
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=<48 位随机串>
SEED_DEMO_DATA=true
EMBEDDING_PROVIDER=local
LLM_PROVIDER=echo
SERVE_FRONTEND=true
MAX_UPLOAD_MB=10
RATE_LIMIT_ENABLED=true
```

---

## 3. 路线 B：Zeabur Free Plan（备选）

### 3.1 前置条件（⚠️ 未实测，以官网为准）

- Zeabur 的免费层历史上变化过好几次，**限制（是否可建数据库、是否只能部署静态站、
  是否有冷启动）请以 [Zeabur Pricing](https://zeabur.com/pricing) 为准**，我不在这里给数字。
- 相关官方资料：[Zeabur 计费方案文档（GitHub 源）](https://github.com/zeabur/zeabur/blob/main/docs/pages/zh-CN/billing/plans.mdx)

### 3.2 步骤

1. **登录**：[zeabur.com](https://zeabur.com/) → **Sign in with GitHub**。
2. **建项目**：Dashboard → **新建项目**（选离深圳近的区域，如香港 / 新加坡）。
3. **建 PostgreSQL**：项目内 **+ 添加服务 → 数据库 → PostgreSQL**。
   - ⚠️ 同样先确认它带不带 `pgvector`（§6）。
4. **部署应用**：**+ 添加服务 → 从 GitHub 部署** → 授权并选择 `citera-kb` 仓库。
   - 若它不是自动识别：手动设 **Dockerfile 路径 = `deploy/Dockerfile`**。
5. **设环境变量**：与 §2.2 第 5 步完全一致。
   `DATABASE_URL` 可以直接引用平台内数据库变量（Zeabur 支持变量引用/绑定），
   但**要确保最终串里是 `postgresql+psycopg://`**。
6. **暴露端口**：在服务的「网络 / Networking」里生成公网域名，容器端口填 **8000**。
7. **验证**：§7。

---

## 4. 路线 C：降级路径（自有阿里云 ECS + 域名）

平台政策不可控，这条路径一定能通。**已有的 ECS（2C2G 起）就够**。

### 4.1 服务器准备（Ubuntu 22.04/24.04 示例）

```bash
# 1) 装 Docker（官方脚本）
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker

# 2) 开防火墙（阿里云安全组也要放行 80/443）
sudo ufw allow 22,80,443/tcp        # 或只用安全组
```

### 4.2 起服务（用仓库自带的 compose）

```bash
git clone <你的仓库地址> citera-kb
cd citera-kb

# 本地 compose（自带 pgvector 数据库，最简单）
docker compose -f deploy/docker-compose.yml up -d --build

# 等健康检查通过
docker compose -f deploy/docker-compose.yml ps
curl -fsS http://localhost:8000/api/health
```

### 4.3 域名 + HTTPS（Caddy 两行搞定）

```bash
sudo apt install -y caddy     # 或按官方源安装
```

`/etc/caddy/Caddyfile`：

```caddyfile
citera.你的域名.com {
    reverse_proxy 127.0.0.1:8000
}
```

```bash
sudo systemctl reload caddy    # Caddy 自动申请并续期 Let's Encrypt 证书
```

> 阿里云域名需先完成**备案**才能用 80/443 对外提供网站服务（中国大陆节点）。
> 若不想备案：用香港/新加坡节点，或直接用 §2 的免费平台域名。

### 4.4 安全底线

- `JWT_SECRET` 换成随机串；`DEBUG=false`。
- `deploy/docker-compose.yml` 里数据库端口默认只绑 `127.0.0.1`，**不要**改成 `0.0.0.0`。
- 演示完把 `SEED_DEMO_DATA` 保持 `true` 没关系（`init_db` 幂等），但别把 `admin` 密码当真密码用在别处。

---

## 5. 平台侧配置要点

### 5.1 Dockerfile 路径

本项目 Dockerfile 在 **`deploy/Dockerfile`**，**构建上下文必须是仓库根**
（因为要 COPY `frontend/` 和 `backend/`）。

- 支持自定义 Dockerfile 路径的平台（ClawCloud / Zeabur / 大多数 PaaS）：填 `deploy/Dockerfile`，上下文留空/默认。
- **如果平台只认仓库根的 `Dockerfile`**：在仓库根放一个同名内容的 Dockerfile 即可（内容与
  `deploy/Dockerfile` 完全相同）。⚠️ 仓库根文件不在基础设施负责人的写作用域内，
  **要先跟 Lead 确认**，或者干脆在本地构建好镜像推到镜像仓库、让平台直接拉镜像（见 §8 最后一行）。

### 5.2 端口

- 容器内部监听 `PORT`（默认 8000），入口脚本会读平台注入的 `PORT`。
- 平台「容器端口 / Container Port」填 **8000**；「公有端口」由平台分配。

### 5.3 资源与常驻进程

- **单副本 + 单 worker**：uvicorn `--workers 1`，没有 Celery / Redis / Nginx。
- 冷启动包含建表 + 灌种子，入口脚本里数据库等待默认 90s，
  健康检查 `start-period` 90s。**首次部署请留出 2–3 分钟再刷新。**

---

## 6. 最大风险点：pgvector

契约 §3 要求 `vector(384)` + HNSW 索引 + `pg_trgm`。**托管数据库不一定给这些扩展。**

**上线前必须先确认**（这是唯一会让部署白做的硬依赖）：

```sql
-- 在平台数据库的 SQL 控制台执行
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name IN ('vector', 'pg_trgm');
```

- 两行都有 → ✅ 放心部署。
- 只有 `pg_trgm` → 先和 Lead 商量：可选降级方案是
  - 换一个带 pgvector 的平台/镜像（自建 ECS 用 `pgvector/pgvector:pg16` 一定有）；
  - 或临时把 `RETRIEVAL_MODE=keyword`（会牺牲向量检索的对比效果，**面试演示不建议**）。

**实测确认**（本机已验证）：`pgvector/pgvector:pg16` 镜像自带 `vector` 扩展，
`docker compose` 起本地环境不会有这个问题。

---

## 7. 上线后自检清单（照抄即可）

```bash
BASE=https://你的公网域名

# 1) 健康检查：status=ok 且 db=ok
curl -fsS $BASE/api/health

# 2) 前端由同一端口托管（SPA 入口）
curl -fsS $BASE/ | head -20

# 3) 接口文档（面试官会看这个）
curl -fsSI $BASE/docs | head -1

# 4) 端到端问答：登录 → 建会话 → 提问 → 校验引用（真·验收，契约 §8.3）
python deploy/scripts/smoke_api.py --base-url $BASE
```

`smoke_api.py` 全绿 = 「公网链接能打开 + 种子数据在 + 回答带引用」三件事同时成立。

**别忘了**：把公网域名填回 `README.md` 的 `<!-- DEMO_URL -->`，
并把截图放进 `docs/screenshots/`（截图脚本见 `deploy/scripts/`）。

---

## 8. 常见故障排查

| 症状 | 大概率原因 | 处理 |
|---|---|---|
| 容器起来就退出，日志 `DATABASE_URL 未设置` | 环境变量没配到应用上 | 检查平台环境变量是否绑定到该服务 |
| 日志 `数据库在 90s 内不可用` | PostgreSQL 还没起 / 网络策略不通 / 串写错 | 用 §7 的 SQL 控制台确认库在；核对 host/port/密码；确认 `+psycopg` |
| `/api/health` 返回 `db:"error"` | 认证失败或库未就绪 | 看容器日志里 db_wait 的重试信息 |
| 首页 404 或 JSON 报错 | 前端 stage 没产出 `dist`，或 `FRONTEND_DIST` 指错 | 看构建日志里 `pnpm run build` 是否成功；确认镜像内 `/app/frontend/dist/index.html` 存在 |
| 页面能开但接口全 404 | 前端 `VITE_API_BASE_URL` 指向了别的域名 | 同源部署下应为空/相对路径 |
| 构建超时 / OOM | 平台构建机内存小 | 本地 `deploy/scripts/build-image.cmd` 构建好推到镜像仓库，平台改成拉镜像 |
| 演示环境提问报模型错误 | 误配了 `LLM_PROVIDER=openai` 但没 Key 或没外网 | 改回 `LLM_PROVIDER=echo` |
| 上传 PDF 报 `unprocessable_upload` | 加密 PDF 或 pypdf 缺失 | 预期行为（契约 §4.1 定义了该错误码） |

---

## 9. 免责声明

- 本文档中所有**平台 UI 文案、免费额度、注册门槛、区域名称**均为 ⚠️ **未实测**，
  写这些内容时我无法从当前环境访问平台官网（网络受限）。
  **一切以官网实时信息为准**，不要基于本文档的数字做付费决策。
- ✅ **已实测**的部分：`deploy/Dockerfile` 多阶段构建、
  `pgvector/pgvector:pg16` 提供 `vector` 扩展、`deploy/docker-compose.yml` 的单容器启动与
  端到端问答（见 `docs/PROGRESS.md` 里的证据行）。
