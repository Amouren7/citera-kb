# DESIGN-frontend · Citera 前端设计决策

> 作者：fe-citera ｜ 日期：2026-10-14 ｜ 依据：`docs/CONTRACT.md` §2 / §7
> 本文件记录**先于编码**确定的设计决策。所有页面必须服从这里的令牌与规则；页面里出现任何本文件未定义的魔法数字视为缺陷。

---

## 1. 设计读数（Design Read）

**Reading this as: a data-dense product console (溯源问答 + 检索评测) for a hiring manager who opens the demo link for 90 seconds, with a technical-instrument language, leaning toward a hand-built CSS token system + Element Plus only for table / form / dialog mechanics.**

依据：

| 信号 | 取值 |
|---|---|
| 页面类型 | 产品控制台（非营销落地页）：列表、流式对话、图表、管理表格 |
| 受众 | 面试官 + 用户（姜高辉，深圳 AI 应用/Agent/全栈岗）。技术审美，扫视快，对"模板感"极敏感 |
| 氛围词 | 溯源、可核实、克制、工程感。**不要**"AI 感"（紫色渐变、玻璃拟态、发光按钮） |
| 硬约束 | 无外网 → 零 CDN 字体/资源；深色+浅色都要能看；1440×900 与 390×844 不破版 |
| 竞品参照 | Linear / Vercel Dashboard / Stripe 文档的**密度与排版**，不是它们的品牌色 |

**技能适用性声明**：`design-taste-frontend` 明确声明其范围是落地页/作品集/改版，**不覆盖密集型产品 UI**。因此本文件**不套用**它的 hero 规则、bento 规则、logo 墙规则（本项目没有 hero 与营销区块）；只采纳其中适用于产品界面的部分：反模板纪律、色彩校准（单强调色锁、禁用 AI 紫）、形状一致性锁、完整三态、对比度强制检查、零 em-dash、动效必须有理由。这一点在契约 §2 的 UI 红线上是一致的。

## 2. 三个旋钮

产品控制台，不是落地页，因此基线下调：

- `DESIGN_VARIANCE: 4`（工具界面，栅格稳定优先；用排版权重与留白制造节奏，不靠错位）
- `MOTION_INTENSITY: 3`（动效只用于状态转换与反馈：流式光标、角标弹层、行悬停；无滚动动画、无 GSAP）
- `VISUAL_DENSITY: 6`（信息密度高，但用 hairline + 字阶分层，不靠卡片堆叠）

## 3. 色彩令牌（`src/styles/tokens.css` 唯一定义处）

浅色主题叫 **Paper**，深色主题叫 **Graphite**。中性色全部是**冷**灰（同一色相族，不混暖灰）。

| 语义 | 浅色 Paper | 深色 Graphite | 用途 |
|---|---|---|---|
| `--c-paper` | `#FAFAF9` | `#0E1013` | 页面底 |
| `--c-surface` | `#FFFFFF` | `#15181D` | 抬升面板 |
| `--c-sunken` | `#F2F3F1` | `#101317` | 凹陷区：表格斑马、代码、井 |
| `--c-ink` | `#14161A` | `#E7E9EE` | 主文本 |
| `--c-ink-2` | `#4A4F58` | `#A2A9B4` | 次文本 |
| `--c-ink-3` | `#7C838F` | `#6E7683` | 元信息 |
| `--c-line` | `#DCDEDB` | `#24282F` | 1px hairline |
| `--c-line-2` | `#C3C6C2` | `#333942` | 强分隔 |
| `--c-accent` | `#3340D8` | `#7C8CFF` | **唯一强调色**（靛青） |
| `--c-accent-ink` | `#FFFFFF` | `#0E1013` | 强调色上的文字 |
| `--c-accent-wash` | `rgba(51,64,216,.08)` | `rgba(124,140,255,.14)` | 强调色淡底 |
| `--c-ok` | `#167A55` | `#3FBF8F` | ready / hit |
| `--c-warn` | `#9A6400` | `#D9A03A` | processing / pending |
| `--c-err` | `#B23A2E` | `#F07167` | failed / error |

规则：

1. **强调色锁**：靛青只用于（a）主操作按钮、（b）当前导航项、（c）引用角标、（d）图表主序列。其它地方一律中性灰。全文不出现第二个非语义强调色。
2. 状态色（ok/warn/err）是**语义色**，只在状态位出现，不做装饰。
3. 禁用 `#409EFF` 及其邻近 Element Plus 默认蓝：构建后 `dist/` 中不得出现该值（随构建产物 grep 自查）。
4. 禁用紫色渐变、mesh 渐变、玻璃拟态、发光按钮。背景永远是纯色。
5. 阴影只用于浮层（popover/dialog/dropdown），且**染色到背景色相**，不用纯黑投影。

## 4. 排版

**字体全部用系统字体栈，零 CDN、零 `@font-face`、零 `<link>` 外部资源**（契约 §7.3）。

```
--font-sans: system-ui, -apple-system, "Segoe UI Variable Text", "Segoe UI",
             "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif
--font-mono: ui-monospace, "Cascadia Mono", "Cascadia Code", Consolas, "SFMono-Regular", Menlo, monospace
```

字阶（px，1.22 比值，工具界面偏小）：

| 令牌 | 值 | 用途 |
|---|---|---|
| `--fs-11` | 11 | mono 微标签（大写 + `.08em` 字距）：字段名、图表轴、块序号 |
| `--fs-12` | 12 | 元信息、徽标 |
| `--fs-13` | 13 | 控件、二级正文 |
| `--fs-14` | 14 | 正文基线（根字号） |
| `--fs-16` | 16 | 回答正文、输入框 |
| `--fs-20` | 20 | 区块标题 |
| `--fs-26` | 26 | 页面标题 |
| `--fs-34` | 34 | 空状态主标题 / 详情页标题 |
| `--fs-46` | 46 | 登录页宣言（唯一的展示级字号） |

字重固定三档：400 / 500 / 600。**不使用 700+**（工具界面显重）。中文标题用 600 + `letter-spacing: -.01em`。

数字一律 `font-variant-numeric: tabular-nums`（表格、指标、耗时、分数）。

## 5. 间距 / 圆角 / 动效

- 间距阶：`4 8 12 16 20 24 32 40 56 72` → `--sp-1..--sp-10`。
- **形状一致性锁：全站直角（radius 0）。** 容器、卡片（本项目基本不用卡）、输入框、按钮、弹窗、徽标一律 0 圆角。**唯一例外**是语义状态圆点（`.dot`，6px 圆），因为它是"点"不是"面"。这条规则是刻意的"仪表盘"语言，也是与 Element Plus 默认 4/8px 圆角最直接的区分。
- 动效时长：`--dur-1: 120ms`（悬停/按下）、`--dur-2: 180ms`（展开/折叠）、`--dur-3: 260ms`（浮层进出）；缓动 `--ease: cubic-bezier(.2,.7,.3,1)`。
- 全局 `@media (prefers-reduced-motion: reduce)` 把时长压到 0.01ms，并关闭流式光标闪烁。**零滚动动画、零视差。**

## 6. 记忆点（"一眼非模板"的三处，均为产品语义服务）

1. **引用页边批注（marginalia citation）** — 回答正文里的 `[[cN]]` 渲染为靛青上标小方块（直角、mono 数字、`--fs-11`）。点击/悬浮弹出**来源卡**：顶部 mono 元信息行 `产品保修条款 · §三、保修期限 · 块 4 · RRF 0.83 · vector`，中部片段原文（引用词高亮），底部"打开原文 →"跳 `/documents/:id?chunk=4`。这是整个产品的卖点视觉化：**回答里的每一句都能点回原文**。
2. **检索轨迹（retrieval trace）** — 每条助手回答上方一条可折叠的 hairline 轨迹条：`检索 6 块 · 37ms · hybrid` + 三条通道命中量竖条（vector/keyword/融合）。展开即"命中的资料片段"卡片列，每张卡带 rank 与 score 的等宽数字。答不出来时这里就是线索，直接支撑"可核实"叙事。
3. **仪表盘式登录页** — 左 55% 是一段宣言式排版 + 一枚可交互的**真实引用角标演示**（点开就是来源卡），右侧是直角、hairline 分栏的登录/注册表单（同页切换，不跳路由）。**没有居中的白卡**，没有插图，没有任何渐变。

## 7. 布局与响应式

- 应用外壳：左侧 **56px 图标轨 + 144px 标签列**（≥1024px）、顶部 **52px** hairline 工具栏。**不使用 `el-menu` 侧边栏**（契约红线）。导航项用 mono 两位序号 `01…05` 编号 —— 因为"文档块有 ord 序号"是本产品的核心概念，导航复用这个语言是自洽的。
- 内容容器：`max-width: 1400px`，主区左对齐，不用居中窄栏（列表/表格需要横向空间）。
- 断点：`640 / 768 / 1024 / 1280`。**≤768px**：图标轨变为底部标签栏；问答页会话列表收缩为抽屉（`el-drawer`，仅用其交互件能力）；表格转卡片列。
- 全站高度用 `min-height: 100dvh`，不用 `100vh`。
- 1440×900 与 390×844 是**验收视口**，必须截图确认不破版。

## 8. 三态规范（契约 §7.2.7，每个列表/图表/对话都必须有）

- **加载**：与最终布局**同形**的骨架（列表=行骨架，回答=段落骨架+光标，图表=直角占位块）。禁止居中转圈 spinner。
- **空**：构图完整 + 明确的下一步动作（`还没有文档 → 上传第一篇` / `还没有会话 → 提一个问题`）。禁止只写"暂无数据"。
- **错**：行内错误块（mono 错误码 + message + `重试` 按钮），不用 toast 掩盖。toast 只用于瞬时反馈（如"已复制"）。

## 9. 对比度与可用性强制检查

- 主按钮：`--c-accent` 底 + `--c-accent-ink` 字（浅色下 8.9:1，深色下 9.6:1，均过 AA）。
- 输入框 placeholder 用 `--c-ink-3`，在 `--c-surface` 上 ≥4.5:1；focus 环用 2px 靛青实线，不用默认 outline 颜色。
- 表格斑马用 `--c-sunken`，不用半透明叠加。
- 所有可点元素有 `:active` 位移反馈（`translateY(1px)`），键盘可达，focus-visible 可见。
- 文案自查：全站零 em-dash（`—`），零 emoji 装饰，零占位文字（`TODO`/`Lorem`）。

## 10. 与契约的偏差记录

无。契约 §2/§7 全部满足；若后续需改接口，走 `docs/CHANGELOG-contract.md` + 通知 Lead。
