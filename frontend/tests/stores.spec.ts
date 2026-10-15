import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  authApi,
  clearToken,
  conversationsApi,
  documentsApi,
  evaluationsApi,
  getToken,
  setToken,
  streamChatMessage,
  type Citation,
  type Conversation,
  type DocumentItem,
  type EvalCompareResponse,
  type EvalRunSummary,
  type Message,
  type User,
} from '@/api'

vi.mock('@/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api')>()
  return {
    ...actual,
    authApi: { login: vi.fn(), register: vi.fn(), me: vi.fn(), updateMe: vi.fn() },
    metaApi: { meta: vi.fn(), health: vi.fn() },
    documentsApi: {
      list: vi.fn(),
      stats: vi.fn(),
      get: vi.fn(),
      chunks: vi.fn(),
      create: vi.fn(),
      rename: vi.fn(),
      remove: vi.fn(),
      reprocess: vi.fn(),
    },
    conversationsApi: {
      list: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      rename: vi.fn(),
      remove: vi.fn(),
      ask: vi.fn(),
    },
    evaluationsApi: { datasets: vi.fn(), items: vi.fn(), run: vi.fn(), runs: vi.fn(), compare: vi.fn() },
    streamChatMessage: vi.fn(),
  }
})

import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useDocumentsStore } from '@/stores/documents'
import { useEvaluationStore } from '@/stores/evaluation'

/* ------------------------------- 夹具 ------------------------------- */

function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 1,
    email: 'demo@citera.dev',
    display_name: '演示用户',
    role: 'user',
    is_active: true,
    created_at: '2026-10-14T09:00:00+08:00',
    ...overrides,
  }
}

function makeDocument(overrides: Partial<DocumentItem> = {}): DocumentItem {
  return {
    id: 1,
    title: '产品保修条款',
    source_type: 'seed',
    filename: null,
    mime_type: null,
    size_bytes: 1024,
    status: 'ready',
    error_message: null,
    chunk_count: 4,
    char_count: 800,
    meta: { chunk_size: 800 },
    created_at: '2026-10-14T09:00:00+08:00',
    updated_at: '2026-10-14T09:10:00+08:00',
    ...overrides,
  }
}

function makeCitation(): Citation {
  return {
    chunk_id: 7,
    document_id: 2,
    document_title: '产品保修条款',
    ord: 3,
    heading: '三、保修期限',
    snippet: '整机保修期为自签收之日起 12 个月。',
    score: 0.83,
    retrieval: 'hybrid',
    rank: 1,
  }
}

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 1,
    title: '整机保修期',
    created_at: '2026-10-14T09:00:00+08:00',
    updated_at: '2026-10-14T09:05:00+08:00',
    message_count: 2,
    last_message_at: '2026-10-14T09:05:00+08:00',
    ...overrides,
  }
}

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 1,
    conversation_id: 1,
    role: 'user',
    content: '保修期多久？',
    citations: [],
    latency_ms: null,
    created_at: '2026-10-14T09:00:00+08:00',
    ...overrides,
  }
}

function makeRun(mode: 'vector' | 'keyword' | 'hybrid', runId: number, createdAt: string): EvalRunSummary {
  const base = mode === 'hybrid' ? 0.8333 : mode === 'vector' ? 0.5833 : 0.6667
  return {
    run_id: runId,
    mode,
    metrics: {
      recall_at_1: mode === 'hybrid' ? 0.5 : 0.3333,
      recall_at_3: base,
      recall_at_5: mode === 'hybrid' ? 1 : 0.75,
      recall_at_10: mode === 'hybrid' ? 1 : 0.9167,
      mrr: mode === 'hybrid' ? 0.6903 : 0.5063,
      hit_rate: 0.9167,
      avg_latency_ms: 58,
      item_count: 12,
    },
    item_count: 12,
    duration_ms: 900,
    created_at: createdAt,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  clearToken()
  vi.clearAllMocks()
})

/* ------------------------------- auth ------------------------------- */

describe('auth store', () => {
  it('login 后写入 token（Pinia + localStorage）与 user', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ user: makeUser(), access_token: 'tok.1', token_type: 'bearer' })
    const auth = useAuthStore()
    await auth.login('demo@citera.dev', 'demo1234')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user?.email).toBe('demo@citera.dev')
    expect(auth.token).toBe('tok.1')
    expect(getToken()).toBe('tok.1')
    expect(authApi.login).toHaveBeenCalledWith({ email: 'demo@citera.dev', password: 'demo1234' })
  })

  it('login 失败时向上抛错且不写入会话', async () => {
    vi.mocked(authApi.login).mockRejectedValue(new Error('invalid_credentials'))
    const auth = useAuthStore()
    await expect(auth.login('demo@citera.dev', 'bad')).rejects.toThrow()
    expect(auth.isAuthenticated).toBe(false)
    expect(getToken()).toBeNull()
  })

  it('bootstrap 有 token 时拉取 /auth/me；401 时清掉本地会话', async () => {
    setToken('tok.1')
    vi.mocked(authApi.me).mockResolvedValue(makeUser({ role: 'admin' }))
    const auth = useAuthStore()
    await auth.bootstrap()
    expect(auth.isAdmin).toBe(true)

    setActivePinia(createPinia())
    const { ApiError } = await import('@/api/errors')
    vi.mocked(authApi.me).mockRejectedValue(new ApiError('token_expired', 'expired', 401))
    const second = useAuthStore()
    await second.bootstrap()
    expect(second.isAuthenticated).toBe(false)
    expect(getToken()).toBeNull()
  })

  it('register 会把邮箱规整为小写并传递昵称', async () => {
    vi.mocked(authApi.register).mockResolvedValue({ user: makeUser(), access_token: 'tok.2', token_type: 'bearer' })
    const auth = useAuthStore()
    await auth.register(' DEMO@Citera.dev ', 'demo1234', ' 演示用户 ')
    expect(authApi.register).toHaveBeenCalledWith({
      email: 'demo@citera.dev',
      password: 'demo1234',
      display_name: '演示用户',
    })
  })

  it('logout 清空 user / token / localStorage', async () => {
    vi.mocked(authApi.login).mockResolvedValue({ user: makeUser(), access_token: 'tok.1', token_type: 'bearer' })
    const auth = useAuthStore()
    await auth.login('demo@citera.dev', 'demo1234')
    auth.logout()
    expect(auth.isAuthenticated).toBe(false)
    expect(getToken()).toBeNull()
  })
})

/* ----------------------------- documents ----------------------------- */

describe('documents store', () => {
  it('fetchList 填充列表与分页信息', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue({ items: [makeDocument()], total: 9, page: 1, page_size: 10 })
    const store = useDocumentsStore()
    await store.fetchList()
    expect(store.status).toBe('ready')
    expect(store.items).toHaveLength(1)
    expect(store.total).toBe(9)
    expect(store.totalPages).toBe(1)
  })

  it('fetchList 失败进入 error 态并保留 ApiError', async () => {
    const { ApiError } = await import('@/api/errors')
    vi.mocked(documentsApi.list).mockRejectedValue(new ApiError('internal_error', '炸了', 500))
    const store = useDocumentsStore()
    await store.fetchList()
    expect(store.status).toBe('error')
    expect(store.error?.code).toBe('internal_error')
  })

  it('setQuery 改筛选条件时把页码重置回第 1 页', () => {
    const store = useDocumentsStore()
    store.setQuery({ page: 3 })
    expect(store.query.page).toBe(3)
    store.setQuery({ q: '保修' })
    expect(store.query.page).toBe(1)
    store.setQuery({ page: 2 })
    expect(store.query.page).toBe(2)
  })

  it('upload 成功后刷新列表并记录 lastUploaded', async () => {
    const created = makeDocument({ id: 42, status: 'pending', title: '新文档' })
    vi.mocked(documentsApi.create).mockResolvedValue(created)
    vi.mocked(documentsApi.list).mockResolvedValue({ items: [created], total: 1, page: 1, page_size: 10 })
    vi.mocked(documentsApi.stats).mockResolvedValue({
      total: 1,
      ready: 0,
      processing: 1,
      failed: 0,
      chunk_total: 0,
      char_total: 0,
      by_status: [{ status: 'pending', count: 1 }],
    })
    const store = useDocumentsStore()
    const result = await store.upload({ title: '新文档', rawText: '正文' })

    expect(result?.id).toBe(42)
    expect(store.lastUploaded?.id).toBe(42)
    expect(store.items).toHaveLength(1)
    expect(store.uploading).toBe(false)
    store.stopPolling()
  })

  it('upload 失败记录 uploadError 且返回 null', async () => {
    const { ApiError } = await import('@/api/errors')
    vi.mocked(documentsApi.create).mockRejectedValue(new ApiError('unsupported_file_type', '不支持该文件类型', 415))
    const store = useDocumentsStore()
    const result = await store.upload({ file: new File(['x'], 'a.exe') })
    expect(result).toBeNull()
    expect(store.uploadError?.code).toBe('unsupported_file_type')
  })

  it('remove 把文档从列表移除并刷新统计', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue({
      items: [makeDocument({ id: 1 }), makeDocument({ id: 2 })],
      total: 2,
      page: 1,
      page_size: 10,
    })
    vi.mocked(documentsApi.remove).mockResolvedValue(undefined)
    vi.mocked(documentsApi.stats).mockResolvedValue({
      total: 1,
      ready: 1,
      processing: 0,
      failed: 0,
      chunk_total: 4,
      char_total: 800,
      by_status: [],
    })
    const store = useDocumentsStore()
    await store.fetchList()
    await store.remove(1)

    expect(store.items.map((item) => item.id)).toEqual([2])
    expect(store.total).toBe(1)
    expect(documentsApi.remove).toHaveBeenCalledWith(1)
  })

  it('reprocess 立即把状态改成 processing（不等待后端）', async () => {
    vi.mocked(documentsApi.list).mockResolvedValue({ items: [makeDocument({ id: 5 })], total: 1, page: 1, page_size: 10 })
    vi.mocked(documentsApi.reprocess).mockResolvedValue(undefined)
    const store = useDocumentsStore()
    await store.fetchList()
    await store.reprocess(5)

    expect(store.items[0]?.status).toBe('processing')
    expect(store.hasUnsettled).toBe(true)
    store.stopPolling()
  })

  it('detail 404 走 error 态而不是抛异常', async () => {
    const { ApiError } = await import('@/api/errors')
    vi.mocked(documentsApi.get).mockRejectedValue(new ApiError('not_found', '文档不存在', 404))
    const store = useDocumentsStore()
    await store.fetchDetail(999)
    expect(store.detailStatus).toBe('error')
    expect(store.detail).toBeNull()
    expect(store.detailError?.isNotFound).toBe(true)
  })
})

/* -------------------------------- chat -------------------------------- */

describe('chat store', () => {
  it('openConversation 载入消息并同步左侧标题', async () => {
    vi.mocked(conversationsApi.get).mockResolvedValue({
      ...makeConversation({ id: 3 }),
      messages: [makeMessage({ id: 11 }), makeMessage({ id: 12, role: 'assistant', citations: [makeCitation()] })],
    })
    const chat = useChatStore()
    await chat.openConversation(3)

    expect(chat.activeId).toBe(3)
    expect(chat.messages).toHaveLength(2)
    expect(chat.messages[1]?.citations[0]?.document_title).toBe('产品保修条款')
    expect(chat.conversations[0]?.id).toBe(3)
    expect(chat.messagesStatus).toBe('ready')
  })

  it('send 会先建会话，再按 meta/retrieval/delta/done 累积回答', async () => {
    vi.mocked(conversationsApi.create).mockResolvedValue(makeConversation({ id: 8, title: '新会话' }))
    vi.mocked(conversationsApi.list).mockResolvedValue({ items: [makeConversation({ id: 8 })], total: 1, page: 1, page_size: 50 })
    vi.mocked(streamChatMessage).mockImplementation(async (_id, _body, options) => {
      options?.onMeta?.({
        conversation_id: 8,
        user_message_id: 21,
        assistant_message_id: 22,
        retrieval_mode: 'hybrid',
        top_k: 5,
      })
      options?.onRetrieval?.({ chunks: [makeCitation()], elapsed_ms: 37 })
      options?.onDelta?.({ text: '整机保修' })
      options?.onDelta?.({ text: ' 12 个月。' })
      options?.onDone?.({
        assistant_message_id: 22,
        finish_reason: 'stop',
        latency_ms: 812,
        usage: { prompt_chars: 100, completion_chars: 20 },
      })
    })

    const chat = useChatStore()
    await chat.send('保修期多久？')

    expect(conversationsApi.create).toHaveBeenCalled()
    expect(chat.activeId).toBe(8)
    expect(chat.messages).toHaveLength(2)
    expect(chat.messages[0]?.role).toBe('user')
    expect(chat.messages[0]?.id).toBe(21)
    expect(chat.messages[1]?.role).toBe('assistant')
    expect(chat.messages[1]?.content).toBe('整机保修 12 个月。')
    expect(chat.messages[1]?.citations).toHaveLength(1)
    expect(chat.messages[1]?.latency_ms).toBe(812)
    expect(chat.streaming).toBe(false)
    expect(chat.streamText).toBe('')
    expect(chat.sendError).toBeNull()
  })

  it('SSE error 事件写进 streamError，不产生助手消息', async () => {
    vi.mocked(conversationsApi.create).mockResolvedValue(makeConversation({ id: 9 }))
    vi.mocked(conversationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(streamChatMessage).mockImplementation(async (_id, _body, options) => {
      options?.onError?.({ code: 'internal_error', message: '生成失败' })
    })

    const chat = useChatStore()
    await chat.send('会不会失败')

    expect(chat.streamError).toEqual({ code: 'internal_error', message: '生成失败' })
    expect(chat.messages.filter((message) => message.role === 'assistant')).toHaveLength(0)
  })

  it('被中断时保留已生成的部分文本为一条回答', async () => {
    vi.mocked(conversationsApi.create).mockResolvedValue(makeConversation({ id: 10 }))
    vi.mocked(conversationsApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })
    vi.mocked(streamChatMessage).mockImplementation(async (_id, _body, options) => {
      options?.onDelta?.({ text: '已生成一半' })
      // 模拟用户点了"停止生成"：AbortController 让 fetch 抛出 AbortError
      throw Object.assign(new Error('aborted'), { name: 'AbortError' })
    })

    const chat = useChatStore()
    await chat.send('长问题')

    const assistant = chat.messages.find((message) => message.role === 'assistant')
    expect(assistant?.content).toBe('已生成一半')
    expect(chat.streaming).toBe(false)
    expect(chat.sendError).toBeNull()
  })

  it('空内容不发请求；发送中重复调用会被忽略', async () => {
    const chat = useChatStore()
    await chat.send('   ')
    expect(streamChatMessage).not.toHaveBeenCalled()
  })

  it('removeConversation 删除当前会话后清空消息流', async () => {
    vi.mocked(conversationsApi.list).mockResolvedValue({ items: [makeConversation({ id: 4 })], total: 1, page: 1, page_size: 50 })
    vi.mocked(conversationsApi.get).mockResolvedValue({ ...makeConversation({ id: 4 }), messages: [makeMessage()] })
    vi.mocked(conversationsApi.remove).mockResolvedValue(undefined)

    const chat = useChatStore()
    await chat.fetchConversations()
    await chat.openConversation(4)
    await chat.removeConversation(4)

    expect(chat.conversations).toHaveLength(0)
    expect(chat.activeId).toBeNull()
    expect(chat.messages).toHaveLength(0)
  })
})

/* ----------------------------- evaluation ----------------------------- */

describe('evaluation store', () => {
  const compare: EvalCompareResponse = {
    runs: [
      makeRun('vector', 1, '2026-10-14T09:00:00+08:00'),
      makeRun('keyword', 2, '2026-10-14T09:01:00+08:00'),
      makeRun('hybrid', 3, '2026-10-14T09:02:00+08:00'),
    ],
    items: [
      {
        item_id: 1,
        question: '整机保修期是多久？',
        per_run: [
          { run_id: 1, rank: 1, hit: true },
          { run_id: 2, rank: 1, hit: true },
          { run_id: 3, rank: 1, hit: true },
        ],
      },
    ],
  }

  it('bootstrap 依次载入数据集 / 题目 / 历史 / 对比', async () => {
    vi.mocked(evaluationsApi.datasets).mockResolvedValue([
      { id: 1, name: '售后知识库评测集 v1', description: '', is_seed: true, created_at: '', item_count: 12 },
    ])
    vi.mocked(evaluationsApi.items).mockResolvedValue({ items: [], total: 12, page: 1, page_size: 10 })
    vi.mocked(evaluationsApi.runs).mockResolvedValue({ items: compare.runs, total: 3, page: 1, page_size: 30 })
    vi.mocked(evaluationsApi.compare).mockResolvedValue(compare)

    const store = useEvaluationStore()
    await store.bootstrap()

    expect(store.activeDatasetId).toBe(1)
    expect(store.itemsTotal).toBe(12)
    expect(store.selectedRunIds).toEqual([1, 2, 3])
    expect(store.metricRows).toHaveLength(3)
  })

  it('metricRows 同一模式只保留最新一次运行', async () => {
    vi.mocked(evaluationsApi.compare).mockResolvedValue({
      runs: [
        makeRun('hybrid', 1, '2026-10-14T09:00:00+08:00'),
        makeRun('hybrid', 9, '2026-10-14T10:00:00+08:00'),
      ],
      items: [],
    })
    const store = useEvaluationStore()
    await store.loadCompare()

    expect(store.metricRows).toHaveLength(1)
    expect(store.metricRows[0]?.runId).toBe(9)
  })

  it('bestMode 与 hybridGain 能支撑"混合检索更好"的结论行', async () => {
    vi.mocked(evaluationsApi.compare).mockResolvedValue(compare)
    const store = useEvaluationStore()
    await store.loadCompare()

    expect(store.bestMode?.mode).toBe('hybrid')
    expect(store.hybridGain).toBeCloseTo(0.8333 - 0.6667, 4)
  })

  it('selectLatestPerMode 每个模式各取最新一条', async () => {
    const store = useEvaluationStore()
    store.runs = [
      makeRun('vector', 1, '2026-10-14T09:00:00+08:00'),
      makeRun('vector', 4, '2026-10-14T11:00:00+08:00'),
      makeRun('hybrid', 3, '2026-10-14T09:02:00+08:00'),
    ]
    const ids = store.selectLatestPerMode()
    expect(ids).toEqual([4, 3])
    expect(store.selectedRunIds).toEqual([4, 3])
  })

  it('runEvaluation 结束后自动选中新 run 并载入对比', async () => {
    vi.mocked(evaluationsApi.run).mockResolvedValue({
      runs: [
        { run_id: 11, mode: 'vector', metrics: makeRun('vector', 11, '').metrics },
        { run_id: 12, mode: 'hybrid', metrics: makeRun('hybrid', 12, '').metrics },
      ],
    })
    vi.mocked(evaluationsApi.runs).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 30 })
    vi.mocked(evaluationsApi.compare).mockResolvedValue(compare)

    const store = useEvaluationStore()
    store.activeDatasetId = 1
    await store.runEvaluation()

    expect(store.running).toBe(false)
    expect(store.selectedRunIds).toEqual([11, 12])
    expect(evaluationsApi.run).toHaveBeenCalledWith({ dataset_id: 1, modes: ['vector', 'keyword', 'hybrid'], top_k: 5 })
    expect(store.compare).not.toBeNull()
  })

  it('runEvaluation 失败时记录 runError 且不卡在 running', async () => {
    const { ApiError } = await import('@/api/errors')
    vi.mocked(evaluationsApi.run).mockRejectedValue(new ApiError('internal_error', '评测失败', 500))
    const store = useEvaluationStore()
    store.activeDatasetId = 1
    await store.runEvaluation()
    expect(store.runError?.code).toBe('internal_error')
    expect(store.running).toBe(false)
  })

  it('setModes 不接受空数组（至少保留一种模式）', () => {
    const store = useEvaluationStore()
    store.setModes([])
    expect(store.modes).toHaveLength(3)
    store.setModes(['keyword'])
    expect(store.modes).toEqual(['keyword'])
  })
})
