# 契约变更记录（CHANGELOG-contract）

> 规则：任何人改接口、字段、环境变量、依赖或部署约定，先在这里追加一条，再改代码。
> 编号连续递增；Lead 负责把已确认的变更同步回 `docs/CONTRACT.md`。

---

## C-001 · CI 工作流必须放仓库根
- **日期**：2026-10-14
- **提出**：infra-citera
- **原契约**：§1 目录树写成 `deploy/.github/workflows/ci.yml`
- **问题**：GitHub Actions 只识别仓库根 `.github/workflows/`，放 `deploy/` 下永远不触发
- **决定**：CI 放**仓库根** `.github/workflows/ci.yml`；`deploy/` 只放容器与部署脚本
- **附加**：批准 infra-citera 在仓库根写 `.dockerignore`（构建上下文瘦身必须放根才生效）
- **契约同步**：已更新 §1

## C-002 · 新增环境变量 `PORT`
- **日期**：2026-10-14
- **提出**：infra-citera
- **原因**：免费容器平台（ClawCloud / Zeabur）会注入 `PORT`，容器入口必须读它
- **决定**：`app/core/config.py` 增加 `port: int = 8000`；容器 entrypoint 用 `PORT` 决定 uvicorn 监听端口
- **默认值**：8000（本地与 compose 不受影响）
- **契约同步**：已更新 §6

## C-003 · 新增环境变量 `FRONTEND_DIST`
- **日期**：2026-10-14
- **提出**：infra-citera（与 Lead 确认）
- **原因**：单容器镜像里前端产物路径与仓库布局不同，需要可覆盖
- **决定**：`frontend_dist: str = ""`；为空时按仓库布局解析 `Path(__file__).parents[2] / "frontend" / "dist"`，非空时直接用该路径
- **契约同步**：已更新 §6

## C-004 · 密码哈希改用标准库 `hashlib.scrypt`，不引入 pwdlib/passlib
- **日期**：2026-10-14
- **提出**：Lead
- **原契约**：§2 写 `pwdlib[argon2]`
- **原因**：本地与容器目标是 Python 3.12/3.14 双兼容；`passlib` 依赖的 `crypt` 模块在 Python 3.14 已被移除（会直接崩），而 argon2 系依赖带二进制 wheel，徒增构建风险。scrypt 是内存硬化 KDF，本身即可用于密码哈希。
- **决定**：用 `hashlib.scrypt`（N=2^14, r=8, p=1, dklen=32，16 字节随机 salt），存储格式 `scrypt$N$r$p$salt_b64$hash_b64`，参数自带便于未来升级
- **影响**：`requirements.txt` 不出现 pwdlib / argon2-cffi / passlib
- **契约同步**：已更新 §2

## C-005 · `messages.citations` 用 JSON/JSONB 而非 `text[]`
- **日期**：2026-10-14
- **提出**：Lead
- **原契约**：§3 只写 `citations jsonb`，但附件说明里曾写成 text array
- **决定**：PostgreSQL 用 `jsonb`，SQLite 测试用 JSON 文本；元素结构见 §4.2 `Citation` 模型
- **契约同步**：§3 已明确

## C-006 · 向量与数组列的跨数据库退化路径
- **日期**：2026-10-14
- **提出**：Lead
- **原因**：开发机不一定常驻 Docker；单元测试必须能用 SQLite 一条命令跑完
- **决定**：
  - `embedding` 列：PostgreSQL 用 `vector(EMBEDDING_DIM)`，SQLite 用 JSON 文本；相似度在 SQLite 下用 Python 计算
  - 数组列：PostgreSQL 用原生 `ARRAY`，SQLite 用 JSON 文本
  - PostgreSQL 生产路径走 pgvector `<=>` + HNSW 索引；关键词路走 `ts_rank_cd`，中文场景用 pg_trgm 兜底
- **影响**：检索实现需保持 SQL 与 Python 两条路径结果口径一致（RRF 名次一致）
- **契约同步**：§5.1 已说明
- **⚠️ 后续修正**：关键词路的 `ts_rank_cd` 方案已被 **C-009** 推翻（中文打不出分），保留此行作为决策演进记录

## C-007 · 评测 run 序列化同时输出 `id` 与 `run_id`
- **日期**：2026-10-15
- **提出**：infra-citera（真实容器端到端实测发现）
- **问题**：契约 §4.2 规定对外字段名是 `run_id`，但实现只输出 `id`。前端 `runs.map(r => r.run_id)`
  得到 `undefined` → 对比接口收到 `ids=undefined,undefined` → HTTP 400 →
  评测页的指标对比柱状图与逐题命中排名**永不渲染**（静默失败，只有端到端走查才能发现）
- **决定**：`EvalRunOut` 同时输出 `id` 与 `run_id`（值相同），前端无需改动；
  `compare` 的 `per_run[].run_id` 保持原样
- **护栏**：`tests/test_evaluations.py` 断言 `run_id == id > 0`
- **契约同步**：§4.2 评测段已注明两个字段并存

## C-008 · 混合检索改为「并集候选池 → 名次级重排」
- **日期**：2026-10-15
- **提出**：Lead（评测驱动）
- **原契约**：§5.1 写的是"两路候选做 RRF 融合，RRF 名次写进 citations"
- **问题**：RRF 只看名次，会把"被两路同时召回但名次都不靠前"的块排到"只被一路召回但排第一"的块之后。
  实测：真正的 gold chunk 在关键词路排第 1、向量路排第 3，RRF 融合后掉到第 3，
  导致 **hybrid R@1 0.86 < 纯关键词 0.93**（混合检索输给单路，等于白做）
- **决定**：
  - 召回阶段：两路结果的**并集**构成候选池（保留每路原始名次与分数），不再用 RRF 直接排名
  - 精排阶段：名次级融合 `score = Σ w_ch / (60 + rank_ch)`，三路信号 = 向量名次 / 关键词名次 / 并集名次
  - 权重实测选定：`vector=0.25`、`keyword=1.0`、`rrf=1.0`（在 22 题评测集上扫描得到）
  - `rrf_fuse()` 保留并单测（`tests/test_retrieval.py`），作为"被评测否决的方案"记录在案
- **结果**：hybrid R@1 0.82、R@3 0.95，与纯关键词持平且显著优于纯向量（0.64），
  且**关键词零命中时会回退到向量候选**（此前 RRF 版本会直接答"没有检索到"）
- **局限（如实记录）**：本地默认向量是确定性哈希向量、并非语义模型，因此改写问句子集上
  vector 5/8、keyword 7/8、hybrid 7/8 —— **hybrid 没有超过关键词，只因向量侧语义能力不足**。
  接入真实 embedding 后应重跑评测再下结论，README 已如实写出这一点
- **契约同步**：§5.1 已改写

## C-009 · 关键词路不使用 PostgreSQL `ts_rank_cd`
- **日期**：2026-10-15
- **提出**：Lead（实测发现）
- **问题**：`to_tsvector('simple', ...)` 对中文没有分词器，中文查询全部打出 0 分
  （实测关键词 R@1 = 0.07，几乎等于关键词路失效）
- **决定**：两库统一走进程内 **IDF 加权覆盖率**打分（BM25 的 IDF 思路），
  文档侧词集 = 单字 + 相邻二元组，查询侧同理；`tsvector` 的 GIN 索引保留作为接入中文分词器后的切换点
- **踩坑记录**：查询侧一度误用 `tokenize()`（只产单字）而文档侧用二元组，
  语料 ≥4 块时两边词集完全不重叠 → 关键词路静默归零（R@1 0.07）；
  小语料单测发现不了，是评测集暴露的
- **契约同步**：§5.1 已改写

## C-010 · 密码哈希实现为 `hashlib.scrypt`（落地核对）
- **日期**：2026-10-15
- **说明**：C-004 已记录该决定；此处补充**落地核对结果**：`backend/requirements.txt` 与虚拟环境
  实测均无 `pwdlib` / `argon2-cffi` / `passlib`，`app/core/security.py` 使用标准库 `hashlib.scrypt`，
  存储格式 `scrypt$n$r$p$salt$hash`
- **README 修正**：README「技术栈」表原写 `pwdlib[argon2]`，已改为标准库 scrypt（文档与实现对齐）
