# E2E 验收报告 · Citera 溯源知识库

> 执行人：Lead ·  日期：**2026-10-15**
> 判定依据：`docs/CONTRACT.md` §8 交付与验收
> 原则：**每一条结论都附实际命令与输出**。没有证据的项一律记为未验证。

---

## 一、环境

| 项 | 值 |
|---|---|
| 形态 | **模拟单容器**：FastAPI 同时托管 `/api` 与 `frontend/dist`（`SERVE_FRONTEND=true`），端口 8010 |
| 数据库 | SQLite（本机无 Docker 守护进程时的等价形态；PostgreSQL 路径另见 §四） |
| 浏览器 | 系统 Chrome（`channel="chrome"`），未下载 Playwright 自带浏览器（省磁盘） |
| 视口 | 桌面 1440×900、移动 390×844 |

命令：

```powershell
cd backend
$env:DATABASE_URL="sqlite+pysqlite:///.../e2e.db"; $env:SERVE_FRONTEND="true"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010

cd ..
& "D:\Deepseek Project\amz-harness\.venv\Scripts\python.exe" tools\e2e_final.py --base-url http://127.0.0.1:8010
```

---

## 二、浏览器端到端结果（13 项断言，全部 PASS）

```
PASS  登录后进入 /chat  http://127.0.0.1:8010/chat
PASS  问答：echo 声明行
PASS  问答：渲染出引用角标（原始 [[cN]] 已被消费）
PASS  问答：检索轨迹存在
PASS  文档库：渲染种子文档统计
PASS  文档库：出现 6 篇种子文档
PASS  文档详情：分块预览渲染
PASS  评测页：首屏图表已绘制  {"hasCanvas": true, "painted": 76217}
PASS  评测页：运行后图表仍在  {"hasCanvas": true, "painted": 76217}
PASS  评测页：逐题命中表渲染
PASS  评测页：无 undefined 泄漏
PASS  移动视口：无横向溢出  overflow=0px
PASS  全流程零控制台错误

✅ 全部通过   （exit 0）
```

---

## 三、本轮端到端抓出的 3 个真实缺陷（全部已修复并复测）

这三个都是**单元测试、类型检查、构建都无法发现**的问题，只有"真浏览器 + 真后端"才暴露。
这一节是本报告最重要的部分。

### E2E-1 · 评测 run 的 `run_id` 缺失 → 评测页静默空白（契约违反）

- **现象**：评测页「指标对比」柱状图与「逐题命中排名」永远不渲染，**控制台无报错**。
- **根因**：契约 §4.2 规定对外字段是 `run_id`，后端实际只输出 `id`。前端 `result.runs.map(r => r.run_id)`
  得到 `undefined` → 发起 `GET /evaluations/runs/compare?ids=undefined,undefined,undefined` →
  后端按设计返回 **400** `bad_request` → `compare` 为 null → 面板走空状态分支。
- **修法**：`EvalRunOut` 同时输出 `id` 与 `run_id`（值相同），前端无需改动；登记为契约变更 **C-007**。
- **护栏**：`tests/test_evaluations.py` 断言 `run_id == id > 0`；契约 §4.2 已注明两字段并存。
- **复测**：`compare` 返回 200、22 题、`per_run[].run_id` 正确。

### E2E-2 · Vue SFC 编译器把箭头函数参数改写错位 → 整块渲染崩溃

- **现象**：控制台 `ReferenceError: per_run is not defined`（连续 19 次），逐题命中表渲染失败。
- **根因**：源码
  ```ts
  const entry = item.per_run.find((perRun) => perRun.run_id === runId)
  ```
  位于**模板内联表达式**（`el-table-column` 的默认插槽里调用该函数）时，
  Vue SFC 编译器在 inline 模式下把函数体里的 `perRun` 改写成了 `per_run`，参数声明却仍是 `perRun`，
  生成 `item.per_run.find((perRun) => per_run.run_id === runId)`。
- **关键证据（排除误判）**：
  - `--minify false` 的产物**同样是坏的** → 不是压缩器的问题；
  - 换 terser 压缩器**仍然坏** → 进一步排除压缩器；
  - `vue/compiler-sfc` 直接编译该模板**输出正确** → 说明是构建链路组合下的改写问题。
- **修法**：**不绕过、不降级**，把这类闭包从模板里彻底移出——在 `setup` 里预先摊平成
  `cellMap`（`Map<"itemId:runId", {rank,hit}>`），模板只做 O(1) 取值。
  顺带把"每格一次 `find`"的 O(n) 扫描降成 O(1)。
- **护栏**：`tools/e2e_final.py` 断言"零控制台错误"；`tools/diag_eval.py` 可复现 DOM 诊断。
- **全量排查**：扫描全部 `src/**` 的同类模式，已确认无第二处。

### E2E-3 · 运行评测后图表画布消失（ECharts 实例失效）

- **现象**：首屏图表正常（76,217 个非空像素）→ 点「运行评测」→ canvas 消失、图表永久空白。
- **根因**：点击后 `store.status` 短暂变为 `loading`，根模板的 `v-else` 分支被销毁重建，
  图表容器变成**新 DOM 元素**，旧 ECharts 实例随之被自动 dispose；
  而 `renderChart()` 只在 `chart === null` 时才 `init`，于是后续 `setOption` 打在已销毁实例上，
  画布保持空白且**不报错**。
- **修法**：`renderChart()` 改为通过 `echarts.getInstanceByDom(el)` **重新取实例**，
  取不到才 `init`；并监听容器 ref 变化，在容器重建后重画。
- **复测**：运行前后均为 `{"hasCanvas": true, "painted": 76217}`。

---

## 四、PostgreSQL 生产路径验证（2026-10-14 实测，非本轮）

| 项 | 结果 |
|---|---|
| 空库 `alembic upgrade head` | ✅ `Running upgrade -> 0001_initial` 一次成功 |
| 表数量 | 11 张（含 `alembic_version`） |
| 扩展 | `vector`、`pg_trgm` 自动创建 |
| `document_chunks.embedding` | `vector(384)` |
| `messages.citations` | `jsonb` |
| `eval_items.gold_chunk_ids` | `bigint[]` |
| 索引 | `ix_chunks_embedding_hnsw`（HNSW 余弦）、`ix_chunks_content_trgm`（GIN） |
| pgvector `<=>` 往返 | ✅ 同向量距离 ≈ 0 |
| 种子幂等 | ✅ 第二次 `documents_rebuilt=0` |

> 本轮因重启后 Docker 守护进程未运行而未复跑该套；`tests/test_postgres.py` 已就绪，
> 设 `CITERA_TEST_PG=1` + `DATABASE_URL` 即可复跑（CI 的 backend job 会跑）。

---

## 五、测试与构建证据

| 项 | 命令 | 结果 |
|---|---|---|
| 后端单测 | `python -m pytest -q` | **124 passed** |
| 前端单测 | `npx vitest run` | **91 passed**（5 个文件） |
| 前端类型检查 | `pnpm run typecheck`（tsc + vue-tsc 兼容层） | **exit 0** |
| 前端构建 | `npx vite build` | ✅ 产物无裸变量改写（`per_run` 裸引用数 = 0） |
| 浏览器 E2E | `tools/e2e_final.py` | **13/13 PASS，exit 0** |

---

## 六、未验证 / 已知缺口（如实列出）

1. **真实容器（docker compose）本轮未复跑**：Docker 守护进程在系统重启后未启动。
   `deploy/` 资产与 compose 配置在 2026-10-14 由 infra-citera 实测通过（见 `docs/PROGRESS.md` `[infra-9]`、`[infra-13]`）。
2. **公网链接尚未生成**：需要平台账号授权（GitHub 账号 + 平台注册），这一步必须由项目所有者本人完成；
   部署清单见 `docs/DEPLOY.md`。
3. **真实 LLM / 真实 embedding 路径未接 Key 实测**：代码路径与降级逻辑已实现并有单测，
   但未用真实 Key 跑过端到端。
4. **移动端仅验证"无横向溢出"**，未做逐页视觉走查。

---

## 七、本轮的诚实结论

- 前后端在**真实浏览器里端到端可用**：登录 → 提问（流式）→ 引用角标 → 检索轨迹 → 文档库 → 评测图表 → 移动端。
- 三个"静默失败"型缺陷已修复：它们的共同特征是**不报错、不崩测试，只是功能不出现**——
  这类问题只有端到端走查能抓，这正是我在交付前坚持跑浏览器验证的原因。
- 仍缺少**公网链接**这一项交付，阻塞点是账号授权，不在技术侧。
