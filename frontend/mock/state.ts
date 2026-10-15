/**
 * mock 服务的状态与夹具数据。
 * 只用于本地开发（契约 §7：前端必须能脱离后端独立跑通六页）。
 * 内容是**虚构演示资料**，与契约 §3 的种子数据说明一致。
 */

import type {
  DocumentChunk,
  DocumentItem,
  DocumentStatus,
  EvalDataset,
  EvalItem,
  EvalMetrics,
  EvalRunSummary,
  Message,
  RetrievalMode,
  User,
} from '../src/api/types.ts'

export interface MockUser extends User {
  password: string
}

export interface MockDocument extends DocumentItem {
  user_id: number
}

export interface MockChunk extends DocumentChunk {
  document_id: number
  user_id: number
}

export interface MockConversation {
  id: number
  user_id: number
  title: string
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface MockMessage extends Message {
  user_id: number
}

export interface MockDataset extends EvalDataset {}

export interface MockEvalItem extends EvalItem {
  /** mock 内部：三种模式下该题命中名次（null = 未命中） */
  ranks: Record<RetrievalMode, number | null>
}

export interface MockRun extends EvalRunSummary {
  dataset_id: number
  top_k: number
  per_item: Array<{ item_id: number; rank: number | null; hit: boolean }>
}

export interface MockStore {
  users: MockUser[]
  documents: MockDocument[]
  chunks: MockChunk[]
  conversations: MockConversation[]
  messages: MockMessage[]
  datasets: MockDataset[]
  evalItems: MockEvalItem[]
  runs: MockRun[]
  settings: Record<string, unknown>
  seq: Record<string, number>
  sessions: Map<string, number>
}

const BOOT = Date.parse('2026-10-14T09:00:00+08:00')

function isoAgo(minutes: number): string {
  return new Date(BOOT - minutes * 60_000).toISOString()
}

function nextId(store: MockStore, key: string): number {
  store.seq[key] = (store.seq[key] ?? 0) + 1
  return store.seq[key]
}

/* ------------------------------- 文档内容 ------------------------------- */

interface DocSpec {
  title: string
  source_type: DocumentItem['source_type']
  filename: string | null
  mime_type: string | null
  status: DocumentStatus
  error_message?: string | null
  created: number
  sections: Array<{ heading: string; body: string }>
}

const DOC_SPECS: DocSpec[] = [
  {
    title: '售后工单处理规范',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 2880,
    sections: [
      {
        heading: '一、适用范围',
        body: '本规范适用于售后支持中心处理的全部工单，包括产品咨询、故障报修、退换货申请与投诉升级四类。工单进入系统后，一律按创建时间排序进入待分配队列，不得人工插队。所有处理动作必须留痕，包括状态变更、备注与附件。',
      },
      {
        heading: '二、响应时限',
        body: '普通工单需在 4 小时内首次响应，24 小时内给出处理方案；涉及安全问题的工单必须在 30 分钟内响应并升级至值班主管。超时未响应的工单由系统自动标红，并计入当班小组的月度考核。节假日按双倍时限计算。',
      },
      {
        heading: '三、升级路径',
        body: '一级客服无法解决时，应在工单中填写已尝试的处理步骤后升级至二级技术支持；二级仍无法定位根因的，升级至研发接口人并附带复现步骤与日志编号。任何情况下不得直接跳级，也不得在未记录处理过程时关闭工单。',
      },
      {
        heading: '四、关闭与回访',
        body: '工单关闭前必须经用户确认问题已解决；用户 48 小时内未回复的，可标记为"系统自动关闭"并触发一次回访。回访结果分为满意、一般、不满意三档，不满意工单自动重新开启并提升优先级。',
      },
    ],
  },
  {
    title: '产品保修条款',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 2400,
    sections: [
      {
        heading: '一、保修范围',
        body: '本条款适用于通过官方渠道购买的整机产品及其原厂配件。保修范围内的故障指在正常使用条件下出现的材料或工艺缺陷。人为损坏、擅自拆机、非官方渠道维修以及不可抗力造成的损坏不在保修范围内。',
      },
      {
        heading: '二、保修凭证',
        body: '申请保修时需提供订单编号或电子发票，两者提供其一即可。无法提供凭证的，以产品出厂序列号对应的激活日期为起始计算保修期。序列号被篡改或无法识别的设备，按超出保修期处理。',
      },
      {
        heading: '三、保修期限',
        body: '整机保修期为自签收之日起 12 个月。主板、显示屏等核心部件保修期为 24 个月；电池、充电器等易损耗配件保修期为 6 个月。保修期内更换的部件，保修期自更换之日起重新计算 90 天，或延续原保修期，以较长者为准。',
      },
      {
        heading: '四、维修时长与替代机',
        body: '保修期内维修一般在 5 个工作日内完成；需要返厂的，时长不超过 15 个工作日。维修时长超过 7 个工作日的，可为用户提供同型号替代机，替代机需在取回原机时归还。',
      },
    ],
  },
  {
    title: '会员积分与权益说明',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 1900,
    sections: [
      {
        heading: '一、积分获取',
        body: '会员每实际支付 1 元累计 1 积分，退货后对应积分同步扣减。参与评价、晒单、邀请好友等行为可获得额外奖励积分，单月奖励积分上限为 2000 分。积分在订单完成 15 天后入账。',
      },
      {
        heading: '二、积分有效期',
        body: '积分自入账之日起 24 个月内有效，按先进先出顺序过期。每年 12 月 31 日系统会清理到期积分，并在清理前 30 天通过站内信与短信各提醒一次。过期积分不予恢复。',
      },
      {
        heading: '三、等级权益',
        body: '累计积分达到 5000 分升级为银卡，达到 20000 分升级为金卡，达到 50000 分升级为黑卡。等级有效期为 12 个月，到期按最近 12 个月的累计积分重新评定，降级不追溯已享受的权益。',
      },
      {
        heading: '四、积分抵扣',
        body: '积分可在结算时抵扣订单金额，100 积分抵 1 元，单笔订单最多抵扣订单金额的 30%。积分抵扣部分不开具发票，退货时优先返还积分，返还的积分有效期与原积分一致。',
      },
    ],
  },
  {
    title: '配送与签收流程',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 1500,
    sections: [
      {
        heading: '一、发货时效',
        body: '现货订单在付款后 24 小时内发出，预售商品按商品页标注的时间发出。遇大促或不可抗力，发货时效可能顺延，顺延信息通过短信通知。发货后运单号在 2 小时内同步至订单详情页。',
      },
      {
        heading: '二、配送范围与费用',
        body: '默认合作快递覆盖全国大部分地区，偏远地区可能转邮政或加收偏远运费。单笔订单满 99 元包邮，未满 99 元收取 8 元运费；大件商品按体积与重量单独计费，费用在下单前明示。',
      },
      {
        heading: '三、签收与验货',
        body: '签收前请当面检查外包装是否破损。外包装明显破损时应当场拒收并拍照留证，拒收后系统自动发起补发。已签收且外包装完好的订单，视为外观无异议，后续主张外观破损需提供开箱视频。',
      },
      {
        heading: '四、异常件处理',
        body: '物流信息超过 72 小时未更新的，可联系客服发起查件；查件确认丢件的，3 个工作日内补发或全额退款，由用户选择。因用户地址填写错误导致的退回，重新发货的运费由用户承担。',
      },
    ],
  },
  {
    title: '退货与换货细则',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 1080,
    sections: [
      {
        heading: '一、七天无理由退货',
        body: '自签收次日起 7 个自然日内，商品保持完好可申请无理由退货。商品完好指不影响二次销售：配件齐全、无使用痕迹、包装与赠品完整。定制类、生鲜类、已激活的软件类商品不适用无理由退货。',
      },
      {
        heading: '二、质量问题退换',
        body: '商品存在质量问题的，自签收之日起 15 日内可换货或退货，15 日至保修期届满可免费维修。质量问题产生的往返运费由平台承担，换货商品优先发出，不等待原机检测完成。',
      },
      {
        heading: '三、退款时效',
        body: '退货商品签收并完成质检后，退款在 3 个工作日内原路返回。银行卡支付可能因银行处理延迟至 7 个工作日到账。使用积分抵扣的订单，积分与现金按比例分别退还。',
      },
      {
        heading: '四、不予退换的情形',
        body: '下列情形不予办理退换：超出退换期限、人为损坏、缺少配件或赠品、私自撕毁防拆标签、非官方渠道购买。对判定结果有异议的，可在 7 日内提出申诉并提交第三方检测报告。',
      },
    ],
  },
  {
    title: '客服话术与禁用表达',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    status: 'ready',
    created: 720,
    sections: [
      {
        heading: '一、开场与确认',
        body: '首次响应需自报身份并复述用户诉求，例如"您好，我是售后客服小李，您反馈的是保修期内屏幕闪烁的问题，我来为您处理"。禁止使用"这不是我们负责的"等推诿表达，也禁止在未核实前承诺处理结果。',
      },
      {
        heading: '二、禁用表达清单',
        body: '禁止使用"绝对没问题""保证今天就修好""肯定能赔"等无法兑现的承诺；禁止使用"你自己看条款"等对抗性表达；禁止在未获得授权时披露内部成本、供应商与工单编号细节。',
      },
      {
        heading: '三、情绪安抚',
        body: '用户情绪激动时先回应情绪再处理问题，允许一次复述确认。若用户出现辱骂，客服应保持克制并提示"我们可以继续沟通，请您使用文明用语"，连续三次后可按流程结束会话并记录。',
      },
      {
        heading: '四、结束与归档',
        body: '结束会话前需复述处理结论，并告知后续时效与查询方式。会话记录在结束后 10 分钟内归档，敏感信息按脱敏规则处理，工单编号与用户身份不得同时出现在对外文本中。',
      },
    ],
  },
  {
    title: '2026 年渠道政策汇编（上传稿）',
    source_type: 'upload',
    filename: '2026-channel-policy.md',
    mime_type: 'text/markdown',
    status: 'ready',
    created: 300,
    sections: [
      {
        heading: '一、渠道分级',
        body: '渠道分为金牌、银牌、普通三级，按上一年度出货量与合规评分共同评定。金牌渠道享优先供货与专属价格保护，价格保护周期为 30 天。评级每年 1 月重置，年中不调整。',
      },
      {
        heading: '二、返点与结算',
        body: '返点按季度结算，出货量达成 80% 即可获得基础返点，达成 100% 额外获得阶梯返点。返点以货款抵扣形式发放，不允许直接提现。存在窜货记录的渠道，当季返点全额扣减。',
      },
      {
        heading: '三、违规与处罚',
        body: '低价倾销、跨区窜货、伪造出货凭证均属违规。首次违规书面警告并扣除当季返点；二次违规则降级并暂停供货 30 天；三次违规终止合作。处罚决定以书面通知为准，渠道可在 5 个工作日内申诉。',
      },
    ],
  },
  {
    title: '质检抽样标准（导入中）',
    source_type: 'upload',
    filename: 'qc-sampling-standard.txt',
    mime_type: 'text/plain',
    status: 'processing',
    created: 4,
    sections: [
      {
        heading: '一、抽样比例',
        body: '批量到货按 AQL 1.5 抽样，批量小于 150 件时抽检 20 件，150 至 500 件抽检 32 件，超过 500 件按平方根法计算抽样量，单批上限 125 件。',
      },
    ],
  },
  {
    title: '加密样例.pdf',
    source_type: 'upload',
    filename: 'encrypted-sample.pdf',
    mime_type: 'application/pdf',
    status: 'failed',
    error_message: '文档已加密，无法解析文本内容',
    created: 45,
    sections: [],
  },
]

/* ------------------------------- 评测题目 ------------------------------- */

interface EvalSpec {
  question: string
  goldChunkOrd: number
  goldDocumentTitle: string
  tags: string[]
  ranks: Record<RetrievalMode, number | null>
}

const EVAL_SPECS: EvalSpec[] = [
  {
    question: '整机保修期是多久？',
    goldChunkOrd: 3,
    goldDocumentTitle: '产品保修条款',
    tags: ['保修', '时限'],
    ranks: { vector: 1, keyword: 1, hybrid: 1 },
  },
  {
    question: '保修需要提供什么凭证？',
    goldChunkOrd: 2,
    goldDocumentTitle: '产品保修条款',
    tags: ['保修', '凭证'],
    ranks: { vector: 2, keyword: 3, hybrid: 1 },
  },
  {
    question: '七天无理由退货的商品需要保持什么状态？',
    goldChunkOrd: 1,
    goldDocumentTitle: '退货与换货细则',
    tags: ['退货'],
    ranks: { vector: 1, keyword: 2, hybrid: 1 },
  },
  {
    question: '退款多久到账？',
    goldChunkOrd: 3,
    goldDocumentTitle: '退货与换货细则',
    tags: ['退款', '时效'],
    ranks: { vector: 3, keyword: 1, hybrid: 1 },
  },
  {
    question: '普通工单的首次响应时限是多少小时？',
    goldChunkOrd: 2,
    goldDocumentTitle: '售后工单处理规范',
    tags: ['工单', '时限'],
    ranks: { vector: 2, keyword: 2, hybrid: 2 },
  },
  {
    question: '工单什么情况下可以升级到研发？',
    goldChunkOrd: 3,
    goldDocumentTitle: '售后工单处理规范',
    tags: ['工单', '升级'],
    ranks: { vector: 5, keyword: 4, hybrid: 2 },
  },
  {
    question: '积分有效期是多久，过期会恢复吗？',
    goldChunkOrd: 2,
    goldDocumentTitle: '会员积分与权益说明',
    tags: ['积分'],
    ranks: { vector: 4, keyword: 6, hybrid: 2 },
  },
  {
    question: '积分抵扣订单金额有什么限制？',
    goldChunkOrd: 4,
    goldDocumentTitle: '会员积分与权益说明',
    tags: ['积分', '抵扣'],
    ranks: { vector: 6, keyword: 3, hybrid: 3 },
  },
  {
    question: '外包装破损应该怎么处理？',
    goldChunkOrd: 3,
    goldDocumentTitle: '配送与签收流程',
    tags: ['配送', '签收'],
    ranks: { vector: 1, keyword: 1, hybrid: 1 },
  },
  {
    question: '物流信息多久没更新可以发起查件？',
    goldChunkOrd: 4,
    goldDocumentTitle: '配送与签收流程',
    tags: ['配送', '异常件'],
    ranks: { vector: 8, keyword: 12, hybrid: 4 },
  },
  {
    question: '客服有哪些禁用表达？',
    goldChunkOrd: 2,
    goldDocumentTitle: '客服话术与禁用表达',
    tags: ['客服', '合规'],
    ranks: { vector: 1, keyword: 2, hybrid: 1 },
  },
  {
    question: '渠道窜货的处罚是什么？',
    goldChunkOrd: 3,
    goldDocumentTitle: '2026 年渠道政策汇编（上传稿）',
    tags: ['渠道', '违规'],
    ranks: { vector: null, keyword: 9, hybrid: 5 },
  },
]

export function computeMetrics(ranks: Array<number | null>, avgLatency: number): EvalMetrics {
  const total = ranks.length || 1
  const at = (k: number) => ranks.filter((r) => r !== null && r <= k).length / total
  const hits = ranks.filter((r) => r !== null) as number[]
  const mrr = hits.reduce((sum, r) => sum + 1 / r, 0) / total
  return {
    recall_at_1: round4(at(1)),
    recall_at_3: round4(at(3)),
    recall_at_5: round4(at(5)),
    recall_at_10: round4(at(10)),
    mrr: round4(mrr),
    hit_rate: round4(hits.length / total),
    avg_latency_ms: avgLatency,
    item_count: ranks.length,
  }
}

function round4(value: number): number {
  return Math.round(value * 10000) / 10000
}

/* ---------------------------- 构建初始 store ---------------------------- */

export function createStore(): MockStore {
  const store: MockStore = {
    users: [],
    documents: [],
    chunks: [],
    conversations: [],
    messages: [],
    datasets: [],
    evalItems: [],
    runs: [],
    settings: {
      retrieval_mode: 'hybrid',
      top_k: 5,
      chunk_size: 800,
      chunk_overlap: 120,
      registration_open: true,
    },
    seq: {},
    sessions: new Map(),
  }

  const users: Array<[string, string, string, User['role'], number]> = [
    ['demo@citera.dev', 'demo1234', '演示用户', 'user', 100000],
    ['admin@citera.dev', 'admin1234', '姜高辉（管理员）', 'admin', 99999],
    ['lin.z@example.com', 'lin12345', '林知远', 'user', 5400],
    ['chen.yu@example.com', 'chen1234', '陈雨', 'user', 3200],
    ['wang.bo@example.com', 'wang1234', '王博', 'user', 900],
    ['zhou.min@example.com', 'zhou1234', '周敏', 'admin', 2600],
  ]
  for (const [email, password, display_name, role, minutesAgo] of users) {
    const id = nextId(store, 'user')
    store.users.push({
      id,
      email,
      display_name,
      role,
      is_active: email !== 'wang.bo@example.com',
      created_at: isoAgo(minutesAgo),
      password,
    })
  }

  const demoUser = store.users[0] as MockUser

  for (const spec of DOC_SPECS) {
    const id = nextId(store, 'document')
    let charTotal = 0
    let chunkCount = 0
    for (const section of spec.sections) {
      const ord = chunkCount + 1
      chunkCount += 1
      charTotal += section.body.length
      store.chunks.push({
        id: nextId(store, 'chunk'),
        document_id: id,
        user_id: demoUser.id,
        ord,
        heading: section.heading,
        content: section.body,
        token_estimate: Math.round(section.body.length / 2.2),
        has_embedding: spec.status === 'ready',
      })
    }
    store.documents.push({
      id,
      user_id: demoUser.id,
      title: spec.title,
      source_type: spec.source_type,
      filename: spec.filename,
      mime_type: spec.mime_type,
      size_bytes: spec.filename ? charTotal * 2 + 512 : charTotal * 2,
      status: spec.status,
      error_message: spec.error_message ?? null,
      chunk_count: spec.status === 'ready' ? chunkCount : 0,
      char_count: charTotal,
      meta: {
        chunk_size: 800,
        chunk_overlap: 120,
        embedding_provider: 'local',
        demo_notice: '虚构演示资料',
      },
      created_at: isoAgo(spec.created),
      updated_at: isoAgo(spec.created - 1),
    })
  }

  // 会话与消息（其中一条带 citations，便于首屏就能看到引用角标）
  const conv1 = nextId(store, 'conversation')
  store.conversations.push({
    id: conv1,
    user_id: demoUser.id,
    title: '整机保修期与凭证要求',
    created_at: isoAgo(300),
    updated_at: isoAgo(290),
    deleted_at: null,
  })
  const chunkOf = (docTitle: string, ord: number): MockChunk => {
    const doc = store.documents.find((d) => d.title === docTitle) as MockDocument
    return store.chunks.find((c) => c.document_id === doc.id && c.ord === ord) as MockChunk
  }
  const citationOf = (docTitle: string, ord: number, rank: number) => {
    const chunk = chunkOf(docTitle, ord)
    return {
      chunk_id: chunk.id,
      document_id: chunk.document_id,
      document_title: docTitle,
      ord: chunk.ord,
      heading: chunk.heading,
      snippet: chunk.content.slice(0, 160),
      score: round4(0.91 - rank * 0.06),
      retrieval: 'vector' as const,
      rank,
    }
  }
  store.messages.push({
    id: nextId(store, 'message'),
    conversation_id: conv1,
    user_id: demoUser.id,
    role: 'user',
    content: '整机保修期是多久？需要提供什么凭证？',
    citations: [],
    latency_ms: null,
    created_at: isoAgo(300),
  })
  store.messages.push({
    id: nextId(store, 'message'),
    conversation_id: conv1,
    user_id: demoUser.id,
    role: 'assistant',
    content:
      '（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）\n\n### 结论\n\n- 整机保修期为自签收之日起 12 个月，主板与显示屏等核心部件为 24 个月。[[c1]]\n- 保修需提供订单编号或电子发票，二者提供其一即可。[[c2]]\n\n**依据**：\n\n> 整机保修期为自签收之日起 12 个月。主板、显示屏等核心部件保修期为 24 个月；电池、充电器等易损耗配件保修期为 6 个月。\n\n| 项目 | 期限 |\n| --- | --- |\n| 整机 | 12 个月 |\n| 核心部件 | 24 个月 |\n| 易损耗配件 | 6 个月 |\n',
    citations: [citationOf('产品保修条款', 3, 1), citationOf('产品保修条款', 2, 2)],
    latency_ms: 812,
    created_at: isoAgo(299),
  })

  const conv2 = nextId(store, 'conversation')
  store.conversations.push({
    id: conv2,
    user_id: demoUser.id,
    title: '外包装破损的处理方式',
    created_at: isoAgo(1200),
    updated_at: isoAgo(1190),
    deleted_at: null,
  })
  store.messages.push({
    id: nextId(store, 'message'),
    conversation_id: conv2,
    user_id: demoUser.id,
    role: 'user',
    content: '收到货外包装破了怎么办？',
    citations: [],
    latency_ms: null,
    created_at: isoAgo(1200),
  })
  store.messages.push({
    id: nextId(store, 'message'),
    conversation_id: conv2,
    user_id: demoUser.id,
    role: 'assistant',
    content:
      '（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）\n\n### 结论\n\n- 外包装明显破损时应当场拒收并拍照留证，拒收后系统自动发起补发。[[c1]]\n- 已签收且外包装完好的订单视为外观无异议，后续主张外观破损需提供开箱视频。[[c1]]\n',
    citations: [citationOf('配送与签收流程', 3, 1)],
    latency_ms: 640,
    created_at: isoAgo(1199),
  })

  const datasetId = nextId(store, 'dataset')
  store.datasets.push({
    id: datasetId,
    name: '售后知识库评测集 v1',
    description: '覆盖保修、退货、积分、配送、工单与合规六类共 12 题，gold 标注到块级。',
    is_seed: true,
    created_at: isoAgo(10080),
    item_count: EVAL_SPECS.length,
  })
  for (const spec of EVAL_SPECS) {
    const gold = chunkOf(spec.goldDocumentTitle, spec.goldChunkOrd)
    store.evalItems.push({
      id: nextId(store, 'eval_item'),
      dataset_id: datasetId,
      question: spec.question,
      gold_chunk_ids: [gold.id],
      gold_document_titles: [spec.goldDocumentTitle],
      tags: spec.tags,
      created_at: isoAgo(10080),
      ranks: spec.ranks,
    })
  }

  for (const [mode, latency] of [
    ['vector', 46],
    ['keyword', 12],
    ['hybrid', 58],
  ] as Array<[RetrievalMode, number]>) {
    const ranks = store.evalItems.map((item) => item.ranks[mode])
    store.runs.push({
      run_id: nextId(store, 'run'),
      mode,
      metrics: computeMetrics(ranks, latency),
      item_count: store.evalItems.length,
      duration_ms: latency * store.evalItems.length + 240,
      created_at: isoAgo(600 - latency),
      dataset_id: datasetId,
      top_k: 5,
      per_item: store.evalItems.map((item) => ({
        item_id: item.id,
        rank: item.ranks[mode],
        hit: item.ranks[mode] !== null,
      })),
    })
  }

  return store
}

/** 去掉内部字段，保证响应体与契约 §4 的字段表一致。 */
export function publicDocument(doc: MockDocument): DocumentItem {
  const { user_id: _userId, ...rest } = doc
  return rest
}

export function publicChunk(chunk: MockChunk): DocumentChunk {
  const { document_id: _d, user_id: _u, ...rest } = chunk
  return rest
}

export function publicEvalItem(item: MockEvalItem): EvalItem {
  const { ranks: _ranks, ...rest } = item
  return rest
}

export { BOOT, isoAgo, nextId }
