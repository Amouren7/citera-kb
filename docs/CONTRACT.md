# CONTRACT · Citera 溯源知识库（接口与实现契约 v1）

> **本文件是唯一事实来源。** 前端、后端、部署三方在任何分歧上以本文件为准。
> 变更流程：任何一方需要改契约 → 先在 `docs/CHANGELOG-contract.md` 追加一条（编号 `C-001` 起），再改代码。
> 未记入 CHANGELOG 的接口，视为**不存在**，不要依赖。
> 本文件目前由 Lead 持有，尚未全部完成；标注 `【待补】` 的章节由 Lead 在开工前补齐。

---

## 0. 项目定位（README 与简历用同一套话术）

**Citera（溯源知识库）**：把散在 PDF / Markdown / 平台规则里的一堆资料，做成一个**每条回答都能点回原文**的知识库问答系统。

- 面试一句话：**"做 AI 应用最怕答了没法核实，所以我把『引用可溯源』当第一目标，而不是把『回答像不像人话』当第一目标。"**
- 技术定位：不是又一个 RAG demo，而是**有用户体系、有数据库、有接口契约、有评测口径、能部署上线**的 Web 产品。

**离线可用是硬要求**：平台演示环境没有 LLM Key 时，系统必须完整可用——检索、引用、流式输出全部工作，答案由检索结果**受控合成**并逐句标注来源，绝不伪造"模型回答"。配置了 Key 才切真实 LLM。

---

## 1. 目录与所有权（禁止越界写）

```
citera-kb/
├── docs/                     # CONTRACT.md / CHANGELOG-contract.md / DEPLOY.md
├── backend/                  # ★ 后端负责人（Lead）写
│   ├── app/
│   │   ├── main.py           # FastAPI 实例、路由挂载、SPA 静态托管
│   │   ├── api/              # health.py auth.py documents.py conversations.py evaluations.py admin.py deps.py
│   │   ├── services/         # chunking.py embedding.py retrieval.py answer.py evaluation.py ingest.py
│   │   ├── models/           # SQLAlchemy 2.0 模型
│   │   ├── schemas/          # Pydantic v2
│   │   ├── core/             # config.py security.py errors.py logging.py rate_limit.py
│   │   └── db/               # session.py base.py init_db.py
│   ├── alembic/              # 迁移（必须有，不许只 create_all）
│   ├── tests/                # pytest，目标 ≥70 项
│   ├── pyproject.toml
│   └── .env.example
├── frontend/                 # ★ 前端负责人写
│   ├── src/
│   │   ├── api/              # 唯一出入：按本契约封装的 axios 客户端
│   │   ├── stores/           # Pinia: auth / documents / chat / evaluation
│   │   ├── router/
│   │   ├── views/            # Login Documents Chat Evaluation Admin
│   │   ├── components/
│   │   ├── styles/           # 设计令牌只在这里定义
│   │   └── utils/
│   ├── tests/                # vitest
│   ├── package.json
│   └── .env.development / .env.production
├── deploy/                   # ★ 基础设施负责人写
│   ├── Dockerfile            # 多阶段：前端构建 → 后端运行时
│   ├── docker-compose.yml    # 本地 dev：postgres(pgvector) + api
│   ├── docker-compose.prod.yml
│   ├── scripts/              # 部署步骤稿、一键上线脚本
│   └── .github/workflows/ci.yml
└── README.md                 # 基础设施负责人主笔，后端/前端提供章节
```

**所有权**：`frontend/**` 只有前端负责人写；`backend/**` 只有后端负责人（Lead）写；`deploy/**` + `README.md` 只有基础设施负责人写。`docs/CONTRACT.md` 只有 Lead 改。

---

## 2. 技术栈（版本已实测，禁止擅自升级）

### 后端
| 组件 | 版本 | 备注 |
|---|---|---|
| Python | 3.12（容器）/ 3.14（本地已装） | 代码需同时兼容两者 |
| FastAPI | 0.143.0 | |
| SQLAlchemy | 2.1.4 | 2.0 风格 `Mapped[]` + `mapped_column` |
| Alembic | 1.20.0 | 迁移必须可用 |
| Pydantic | 2.14.1 / pydantic-settings 2.15.0 | |
| psycopg | 3.3.6 | `postgresql+psycopg://`，**不要用 psycopg2** |
| pgvector | 0.5.1（Python 包） | 数据库扩展 `vector` |
| pwdlib[argon2] | — | ⚠️ **已废弃**：改用标准库 `hashlib.scrypt`（见 `CHANGELOG-contract.md` C-004）。Python 3.14 移除了 `crypt`，passlib 1.7.4 会崩，故不引入任何第三方密码哈希库 |
| PyJWT | 2.15.1 | HS256 |
| uvicorn | 0.54.0 | |
| httpx | 0.28.1 | LLM 调用 |
| pytest | 9.1.1 | |
| pypdf | latest | PDF 解析；缺失时降级并返回 `unprocessable_upload` |

### 前端
| 组件 | 版本 |
|---|---|
| Vue | 3.5.44（`<script setup>` + TS） |
| Vite | 8.3.4 |
| TypeScript | 7.0.2 |
| Element Plus | 2.14.7（**只用于表格/表单/弹窗等交互件，视觉必须自定义**） |
| Pinia | 4.1.0 |
| Vue Router | 5.4.0 |
| Axios | 1.20.0 |
| ECharts | 6.1.0（评测页图表） |
| marked + dompurify | 18.1.1 / 3.4.17（渲染回答必须 sanitize） |
| Vitest | 5.0.4 |

**UI 红线（面试官一眼能看出"套模板"）**：禁止 Element Plus 默认蓝 `#409EFF`、禁止 `el-card` 大圆角白卡堆叠、禁止默认 `el-menu` 侧边栏、禁止紫色渐变、禁止把 Element Plus 组件当唯一视觉。设计令牌统一放 `src/styles/tokens.css`，深色/浅色都要能看。

---

## 3. 数据库模型

统一约定：主键 `id BIGSERIAL`；时间 `created_at / updated_at TIMESTAMPTZ DEFAULT now()`；软删除 `deleted_at TIMESTAMPTZ NULL`；按用户隔离的表都带 `user_id` 并建索引。

### users
`id` PK / `email` varchar(255) UNIQUE NOT NULL（存前 `.strip().lower()`）/ `password_hash` varchar(255) / `display_name` varchar(64) / `role` varchar(16) ∈ `user|admin` / `is_active` bool / `created_at` / `updated_at`

### documents
`id` PK / `user_id` FK users ON DELETE CASCADE / `title` varchar(255) / `source_type` varchar(16) ∈ `upload|paste|seed` / `filename` NULL / `mime_type` NULL / `size_bytes` bigint / `status` varchar(16) ∈ `pending|processing|ready|failed` / `error_message` text NULL / `chunk_count` int / `char_count` int / `meta` jsonb 默认 `{}` / `deleted_at` / `created_at` / `updated_at`

### document_chunks
`id` PK / `document_id` FK ON DELETE CASCADE / `user_id` FK / `ord` int（从 1 起）/ `content` text / `token_estimate` int / `heading` varchar(255) NULL / `embedding` vector(384) NULL（维度 = `EMBEDDING_DIM`）/ `tsv` tsvector 生成列（`to_tsvector('simple', content)`）/ `created_at`

索引：`(document_id, ord)`、`(user_id)`、`embedding` **HNSW** `vector_cosine_ops`、`tsv` GIN。

### conversations / messages
- `conversations`：id / user_id / title varchar(255)（默认取首问前 30 字）/ created_at / updated_at / deleted_at
- `messages`：id / conversation_id FK / user_id / role ∈ `user|assistant` / content text / citations jsonb / latency_ms int NULL / token_estimate int NULL / created_at

### 评测四表
- `eval_datasets`：id / name / description / is_seed bool / created_at
- `eval_items`：id / dataset_id FK / question text / gold_chunk_ids bigint[] / gold_document_titles text[] / tags text[] / created_at
- `eval_runs`：id / dataset_id FK / user_id NULL / mode varchar(16) ∈ `vector|keyword|hybrid` / top_k int / metrics jsonb / item_count int / duration_ms int / created_at
- `eval_results`：id / run_id FK / item_id FK / retrieved_chunk_ids bigint[] / rank int NULL / hit bool / latency_ms int

### app_settings（KV）
`key` varchar(64) PK / `value` jsonb / `updated_at`。默认键：`retrieval_mode`、`top_k`、`chunk_size`、`chunk_overlap`、`registration_open`。

**种子数据**：`python -m app.db.init_db` 必须：建扩展（`vector`、`pg_trgm`）→ `alembic upgrade head`（或等价建表）→ 灌入 1 个评测数据集（≥12 题）+ 6 篇**虚构**演示文档 + 2 个演示账号。
演示账号：`demo@citera.dev` / `demo1234`；管理员：`admin@citera.dev` / `admin1234`。
种子文档必须是虚构内容（如《售后工单处理规范》《产品保修条款》），正文页脚注明"虚构演示资料"。

---

## 4. REST API 契约

- 前缀 `/api/v1`（`/api/health` 除外）
- 认证：`Authorization: Bearer <access_token>`
- 分页统一：query `page`（默认 1）、`page_size`（默认 20，上限 100）；响应 `{"items":[...],"total":N,"page":P,"page_size":S}`
- 时间 ISO 8601 带时区；ID 为 number

### 4.1 错误格式（全局统一，禁止例外）
```json
{ "error": { "code": "invalid_credentials", "message": "邮箱或密码不正确", "details": null, "request_id": "0f3c..." } }
```
| HTTP | code | 触发 |
|---|---|---|
| 400 | `bad_request` | 参数非法 |
| 401 | `unauthorized` / `invalid_credentials` / `token_expired` | 未登录 / 登录失败 / token 过期 |
| 403 | `forbidden` / `quota_exceeded` | 无权限 / 超配额 |
| 404 | `not_found` | 不存在**或越权访问他人资源**（不暴露存在性） |
| 409 | `email_taken` | 邮箱已注册 |
| 413 | `file_too_large` | 超 `MAX_UPLOAD_MB` |
| 415 | `unsupported_file_type` | 扩展名不支持 |
| 422 | `unprocessable_upload` | 内容无法解析（加密 PDF 等） |
| 429 | `rate_limited` | 触发限流 |
| 500 | `internal_error` | 兜底，不泄露堆栈 |

### 4.2 端点清单

**健康与元信息**
| 方法 | 路径 | 认证 | 响应 |
|---|---|---|---|
| GET | `/api/health` | 否 | `{"status":"ok","version":"0.1.0","db":"ok"\|"error","llm_provider":"echo"\|"openai"}` |
| GET | `/api/v1/meta` | 否 | `{"app_name":"Citera","version":"0.1.0","registration_open":true,"limits":{"max_upload_mb":10,"max_documents":50,"max_conversations":100}}` |

**认证**
| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/api/v1/auth/register` | `{email,password,display_name}` | 201 `{user,access_token,token_type:"bearer"}` |
| POST | `/api/v1/auth/login` | `{email,password}` | 200 同上 |
| GET | `/api/v1/auth/me` | Bearer | `{user}` |
| PATCH | `/api/v1/auth/me` | `{display_name?}` | `{user}` |

`password`：≥8 位且含字母与数字。
`user` 对象统一：`{id,email,display_name,role,is_active,created_at}`。
Token：access 12 小时；JWT payload `{sub:"<user_id>",role,exp,iat,typ:"access"}`。

**文档**
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/documents` | `multipart/form-data`：`file`（必填）**或** `title`+`raw_text` 二选一。201 返回 `{document}`，`status=pending`，**后台异步**切分+向量化 |
| GET | `/api/v1/documents` | query：`page,page_size,q,status,sort`（`sort` ∈ `created_at,-created_at,title`） |
| GET | `/api/v1/documents/{id}` | 详情（不含 chunk 正文） |
| GET | `/api/v1/documents/{id}/chunks` | 分页：`{id,ord,heading,content,token_estimate,has_embedding}` |
| PATCH | `/api/v1/documents/{id}` | `{title?}` |
| DELETE | `/api/v1/documents/{id}` | 软删除，204 |
| POST | `/api/v1/documents/{id}/reprocess` | 重新切分+向量化，202 |
| GET | `/api/v1/documents/stats` | `{total,ready,processing,failed,chunk_total,char_total,by_status:[{status,count}]}` |

支持扩展名：`.txt .md .markdown .csv .log .json .pdf`；纯文本按 `utf-8 → utf-8-sig → gbk → latin-1` 依次解码。
`document` 对象：`{id,title,source_type,filename,mime_type,size_bytes,status,error_message,chunk_count,char_count,meta,created_at,updated_at}`。

**会话与问答**
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/conversations` | 分页，含 `message_count`、`last_message_at` |
| POST | `/api/v1/conversations` | `{title?}` → 201 `{conversation}` |
| GET | `/api/v1/conversations/{id}` | 含 `messages`（按 `created_at` 升序） |
| PATCH | `/api/v1/conversations/{id}` | `{title}` |
| DELETE | `/api/v1/conversations/{id}` | 204 |
| POST | `/api/v1/conversations/{id}/messages` | 见下 |

`message` 对象：`{id,conversation_id,role,content,citations,latency_ms,created_at}`

非流式请求/响应：
```json
// 请求
{ "content":"保修期是多久？", "stream":false, "top_k":5, "retrieval_mode":"hybrid", "document_ids":[1,2] }
// 响应 200
{ "user_message":{message}, "assistant_message":{message} }
```

流式（`"stream": true`）→ `text/event-stream`，事件顺序**固定**：
```
event: meta
data: {"conversation_id":1,"user_message_id":9,"assistant_message_id":10,"retrieval_mode":"hybrid","top_k":5}

event: retrieval
data: {"chunks":[{"chunk_id":31,"document_id":2,"document_title":"产品保修条款","ord":4,"heading":"三、保修期限","snippet":"...","score":0.83,"retrieval":"vector","rank":1}],"elapsed_ms":37}

event: delta
data: {"text":"整机保修期为 "}

event: done
data: {"assistant_message_id":10,"finish_reason":"stop","latency_ms":812,"usage":{"prompt_chars":1200,"completion_chars":210}}

event: error
data: {"code":"internal_error","message":"生成失败"}
```
规则：**先 `meta` → 再 `retrieval` → 若干 `delta` → 最后 `done`**；异常发 `error` 后关闭（HTTP 仍 200）。客户端断连时后端必须停止生成。

`citations` 结构：
```json
[{ "chunk_id":31,"document_id":2,"document_title":"产品保修条款","ord":4,"heading":"三、保修期限",
   "snippet":"整机保修期为自签收之日起 12 个月……","score":0.83,"retrieval":"vector","rank":1 }]
```
正文引用标注格式**固定** `[[c1]]`、`[[c2]]`（数字 = 该消息 citations 的 1-based 下标）。前端渲染成可点击角标。

**评测**
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/evaluations/datasets` | 列出数据集（含 `item_count`） |
| GET | `/api/v1/evaluations/datasets/{id}/items` | 分页列出题目 |
| POST | `/api/v1/evaluations/run` | `{dataset_id,modes:["vector","keyword","hybrid"],top_k:5}` → 200 `{runs:[{run_id,mode,metrics}]}`（同步执行） |
| GET | `/api/v1/evaluations/runs` | 分页历史（含 `metrics`） |
| GET | `/api/v1/evaluations/runs/compare?ids=1,2,3` | `{runs:[{id,run_id,mode,metrics,item_count,duration_ms,created_at}],items:[{item_id,question,per_run:[{run_id,rank,hit}]}]}` |

`metrics` 字段固定：`{recall_at_1,recall_at_3,recall_at_5,recall_at_10,mrr,hit_rate,avg_latency_ms,item_count}`（全部 0–1 小数，`avg_latency_ms` 为毫秒数）。

> **run 的标识字段同时输出 `id` 与 `run_id`（值相同）**，见 `CHANGELOG-contract.md` C-007：
> 只输出 `id` 时前端取 `run_id` 会拿到 `undefined`，对比接口直接 400，评测页静默空白。

**管理**
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/admin/stats` | `{users,documents,chunks,conversations,messages,eval_runs,recent_7d:{documents,messages}}` |
| GET | `/api/v1/admin/users` | 分页 |
| PATCH | `/api/v1/admin/users/{id}` | `{is_active?,role?}` |
| GET | `/api/v1/admin/settings` | `{settings:{key:value}}` |
| PUT | `/api/v1/admin/settings` | `{settings:{key:value}}`（只接受白名单键） |
| POST | `/api/v1/admin/reseed` | 重新灌种子数据（幂等），200 |

管理端点必须校验 `role == "admin"`，否则 403 `forbidden`。

**限流**：登录/注册按 IP 每分钟 10 次；提问按用户每分钟 20 次；上传按用户每分钟 10 次。超限 → 429 `rate_limited`。

---

## 5. 检索与回答（后端内部契约）

### 5.1 检索排序：并集候选池 → 名次级重排（C-008 / C-009 修订版）

**两段式**，代码在 `app/services/retrieval.py`，面试可指着讲：

1. **召回**：`vector` 与 `keyword` 两路各取 `hybrid_pool_size * hybrid_candidate_multiplier`（默认 20×4=80）条，
   取**并集**构成候选池（`candidate_pool()`），保留每路的原始名次与分数。
2. **精排**：名次级融合（`hybrid_rerank()`）
```
score(d) = w_vector/(k + rank_vector(d)) + w_keyword/(k + rank_keyword(d)) + w_best/(k + rank_best(d))
k = 60，默认 w_vector=0.25, w_keyword=1.0, w_best=1.0
某一路未召回该块时，该路名次按 pool_size + 1 计入（"没召回"要付出代价）
```

- 各路召回定义：
  - `vector`：PostgreSQL 走 pgvector `<=>` + HNSW 索引；SQLite 走 Python 余弦
  - `keyword`：**两库统一走进程内 IDF 加权覆盖率打分**。不使用 PostgreSQL 的 `ts_rank_cd`——
    `simple` 配置对中文无分词器，中文查询全部 0 分（实测 R@1 仅 0.07，见 C-009）；
    表上保留 `tsvector` GIN 索引作为接入中文分词器后的切换点
- citations 里 `retrieval` 记录**名次最好的那个通道名**，`rank` 为重排后名次
- 每条 chunk 必须附 `snippet`：命中词附近优先（按完整查询串 → 长词 → 单字依次定位），上限约 220 字
- **为什么不用 RRF 直接排名**（`rrf_fuse()` 仍在库中且有单测，作为被评测否决的方案保留）：
  RRF 会把"被两路同时召回但名次都不靠前"的块排到"只被一路召回但排第一"的块之后，
  实测导致 hybrid R@1（0.86）低于纯关键词（0.93）——混合检索输给单路，见 C-008
- **权重不是拍脑袋**：在 22 题评测集上扫描 `w_vector ∈ {0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0}`
  选出的最优区间；扫描结果与最终数字见 README「评测数字」

### 5.2 切分
- 默认 `chunk_size=800` 字符、`chunk_overlap=120`
- 两级：先按 Markdown 标题/空行切"语义段"，超长再按句子边界递归切；**不得在句中硬切**
- 每块记录最近标题为 `heading`
- 参数快照写入 `documents.meta`

### 5.3 回答生成（两条路径，同一接口）
- `LLM_PROVIDER=echo`（默认，无需 Key）：**受控合成**——从检索块中选出与问题词重合度最高的句子，按块顺序组织成结构化回答，每句句尾挂 `[[cN]]`；开头固定输出一行说明：`（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）`
- `LLM_PROVIDER=openai`（`LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL`）：OpenAI 兼容 `/chat/completions`，`stream=true` 真流式；system prompt 必须要求"只依据给定资料回答、每句标注 [[cN]]、资料不足时明确说不知道"
- 两条路径都必须产出同样结构的 `citations` 与同样的 SSE 事件序列

### 5.4 向量化
- `EMBEDDING_PROVIDER=local`（默认）：确定性哈希向量（字符 n-gram 哈希到 384 维后 L2 归一化），**相同输入必须得到相同向量**，无网络依赖
- `EMBEDDING_PROVIDER=openai`：OpenAI 兼容 `/embeddings`，维度必须等于 `EMBEDDING_DIM`
- 向量维度由配置决定，**不得硬编码在 SQL 里**；迁移用 `vector({EMBEDDING_DIM})` 需在建表时固定为 384 并提供改维度的说明

---

## 6. 环境变量（`.env.example` 必须全列，带注释）

| 变量 | 默认 | 说明 |
|---|---|---|
| `APP_NAME` | `Citera` | |
| `APP_VERSION` | `0.1.0` | |
| `ENV` | `dev` | `dev`/`prod` |
| `DEBUG` | `true` | prod 必须 false |
| `PORT` | `8000` | 免费容器平台会注入（C-002） |
| `FRONTEND_DIST` | `""` | 为空按仓库布局 `frontend/dist`（C-003） |
| `DATABASE_URL` | `postgresql+psycopg://citera:citera@localhost:5432/citera` | |
| `JWT_SECRET` | `dev-only-change-me` | prod 必须改，长度 ≥32 |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | |
| `CORS_ORIGINS` | `http://localhost:5173` | 逗号分隔；生产同源可为空 |
| `SERVE_FRONTEND` | `true` | true 时 FastAPI 托管 `frontend/dist` |
| `MAX_UPLOAD_MB` | `10` | |
| `EMBEDDING_PROVIDER` | `local` | `local`/`openai` |
| `EMBEDDING_DIM` | `384` | |
| `LLM_PROVIDER` | `echo` | `echo`/`openai` |
| `LLM_BASE_URL` | `""` | |
| `LLM_API_KEY` | `""` | |
| `LLM_MODEL` | `""` | |
| `RETRIEVAL_MODE` | `hybrid` | `vector`/`keyword`/`hybrid` |
| `TOP_K` | `5` | |
| `RRF_K` | `60` | |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `800` / `120` | |
| `SEED_DEMO_DATA` | `true` | 容器首次启动自动灌种子 |
| `RATE_LIMIT_ENABLED` | `true` | |

---

## 7. 前端行为契约

### 7.1 路由与鉴权
| 路径 | 页面 | 鉴权 |
|---|---|---|
| `/login` | 登录/注册（同页切换） | 否 |
| `/` | 重定向到 `/chat` | 是 |
| `/chat` `/chat/:conversationId` | 问答主界面 | 是 |
| `/documents` | 文档库 | 是 |
| `/documents/:id` | 文档详情（块预览 + 状态） | 是 |
| `/evaluation` | 评测对比 | 是 |
| `/admin` | 管理台（仅 admin 可见入口） | 是 + role=admin |
| `/:pathMatch(.*)*` | 404 页 | 否 |

- token 存 Pinia + `localStorage`（键名 `citera.token`）
- axios 拦截器：401 且 code=`token_expired`/`unauthorized` → 清 token 跳 `/login`；错误统一用 `ElMessage` 提示 `error.message`
- 守卫：未登录访问受保护页 → `/login?redirect=<path>`
- 业务错误码：`unauthorized` 类跳登录；`rate_limited` 提示"操作过于频繁"；`quota_exceeded` 提示配额；其余提示 message 原文

### 7.2 问答页必须做到
1. 左侧会话列表（新建/重命名/删除），右侧消息流；移动端会话列表收起为抽屉
2. 输入框支持 `Enter` 发送 / `Shift+Enter` 换行；发送中禁用并显示"停止生成"
3. SSE 用 `fetch` + `ReadableStream` 解析（**不要用 EventSource**，因为要带 Authorization 头）
4. 收到 `retrieval` 事件后，在回答上方渲染"命中的资料片段"卡片（默认折叠，可展开看全文片段）
5. `[[cN]]` 渲染成上标角标，悬浮/点击弹出该 citation 的 `document_title / heading / ord / snippet / score`，并提供"查看文档"跳转
6. Markdown 渲染必须过 DOMPurify
7. 空状态、加载骨架、错误重试三态齐全

### 7.3 视觉要求
- 设计令牌集中在 `src/styles/tokens.css`：颜色、字号阶、间距阶、圆角、阴影、动效时长
- 主色不得为 `#409EFF`；建议**石墨黑 + 靛青强调色 + 纸白背景**，深色模式反相
- 至少一处"非模板"细节：引用角标交互、检索片段卡片、评测对比图表
- 不使用任何需要联网加载的字体/CDN（演示环境可能无外网）
- 评测页：三种模式指标对比柱状图（ECharts）+ 逐题命中排名表，能一眼看出 hybrid 优于纯向量

---

## 8. 交付与验收（Lead 最终判定）

### 8.1 后端验收
- [ ] `pytest` 全绿，用例数 ≥70，含：认证 10+、文档 15+、问答 12+、检索/切分 15+、评测 10+、权限与错误 10+
- [ ] 至少 1 个真实数据库集成测试（连 PostgreSQL+pgvector，非 mock）
- [ ] `alembic upgrade head` 从空库一次成功
- [ ] `python -m app.db.init_db` 幂等（跑两次结果一致）
- [ ] `/api/health` 与 `/docs` 可访问
- [ ] 所有错误路径返回 §4.1 标准格式

### 8.2 前端验收
- [ ] `npm run build` 成功，无 TS 错误，产物 `dist/`
- [ ] `npx vitest run` 全绿，含 composable/工具/API 层测试
- [ ] 手动走通：注册 → 上传 → 等 ready → 提问（流式）→ 点引用 → 看原文 → 评测页跑一次
- [ ] 1440×900 与 390×844 两个视口都不破版

### 8.3 集成验收
- [ ] 单容器启动：`docker compose up` 后访问 `http://localhost:8000` 能看到前端并完成一次完整问答
- [ ] 无外网、无 LLM Key 时功能完整（echo 模式）
- [ ] 冷启动到可问答 < 60s

### 8.4 展示验收
- [ ] 公网 HTTPS 链接可打开
- [ ] README 含截图、架构图（mermaid）、评测数字、二次开发说明（本项目为**从 0 自研**，须写明"无上游 fork"）
- [ ] 提供一段可直接讲的项目自述（面试用，≤200 字）

---

## 9. 协作纪律

1. **契约优先**：接口先写契约再写实现；发现不合理先提 CHANGELOG。
2. **不越界**：只写自己所有权内的文件；需要别人改，发消息说明文件+行+原因。
3. **完成即自检**：任何"完成"声明必须附带实际命令与输出（测试通过数、构建产物路径），不接受"应该能跑"。
4. **每日一条**：在 `docs/PROGRESS.md` 追加一行（日期 / 人 / 做了什么 / 证据），Lead 汇总给用户。
5. **不确定就问**：宁可停下来发消息，不要猜一个接口然后让三方返工。
