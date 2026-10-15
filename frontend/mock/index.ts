/**
 * Citera mock 服务：Vite 中间件，覆盖契约 §4.2 的全部端点（含逐事件伪造的 SSE 流）。
 * 目的：前端不依赖后端进程就能把六个页面全部调通、截屏、自测三态。
 *
 * 开关：`.env.development` 的 VITE_MOCK（vite.config.ts 读取）。
 * 额外调试参数：`?_slow=1200` 强制延迟（看骨架屏）、`?_error=rate_limited` 强制报错（看错误态）。
 */

import type { ServerResponse } from 'node:http'
import type { Connect, Plugin } from 'vite'
import type { Citation, RetrievalMode, User } from '../src/api/types.ts'
import { retrieve, synthesizeAnswer } from './engine.ts'
import type { MockConversation, MockDocument, MockStore, MockUser } from './state.ts'
import { createStore, computeMetrics, nextId, publicChunk, publicDocument, publicEvalItem } from './state.ts'

const V1 = '/api/v1'

interface Ctx {
  req: Connect.IncomingMessage
  res: ServerResponse
  url: URL
  params: Record<string, string>
  body: Record<string, unknown>
  rawBody: Buffer
  store: MockStore
  user: MockUser | null
}

type Handler = (ctx: Ctx) => void | Promise<void>

interface Route {
  method: string
  segments: string[]
  auth: boolean
  admin?: boolean
  handler: Handler
}

const routes: Route[] = []

function route(
  method: string,
  path: string,
  handler: Handler,
  options: { auth?: boolean; admin?: boolean } = {},
): void {
  routes.push({
    method,
    segments: path.split('/').filter(Boolean),
    auth: options.auth ?? true,
    admin: options.admin ?? false,
    handler,
  })
}

/* ------------------------------- 工具函数 ------------------------------- */

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function requestId(): string {
  return Math.random().toString(16).slice(2, 10) + Math.random().toString(16).slice(2, 6)
}

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  })
  res.end(body)
}

function fail(res: ServerResponse, status: number, code: string, message: string, details: unknown = null): void {
  sendJson(res, status, { error: { code, message, details, request_id: requestId() } })
}

function readBody(req: Connect.IncomingMessage): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on('data', (chunk: Buffer) => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

interface MultipartResult {
  fields: Record<string, string>
  file: { filename: string; content: Buffer } | null
}

function parseMultipart(buffer: Buffer, boundary: string): MultipartResult {
  const result: MultipartResult = { fields: {}, file: null }
  const delimiter = Buffer.from(`--${boundary}`)
  let index = buffer.indexOf(delimiter)
  while (index !== -1) {
    const start = index + delimiter.length
    if (buffer.slice(start, start + 2).toString() === '--') break
    const next = buffer.indexOf(delimiter, start)
    if (next === -1) break
    const part = buffer.slice(start, next)
    const headerEnd = part.indexOf('\r\n\r\n')
    if (headerEnd !== -1) {
      const headers = part.slice(0, headerEnd).toString('utf8')
      const raw = part.slice(headerEnd + 4)
      const content = raw.slice(0, Math.max(0, raw.length - 2))
      const nameMatch = /name="([^"]+)"/.exec(headers)
      const fileMatch = /filename="([^"]*)"/.exec(headers)
      const name = nameMatch?.[1]
      if (name && fileMatch && fileMatch[1]) {
        result.file = { filename: fileMatch[1], content }
      } else if (name) {
        result.fields[name] = content.toString('utf8')
      }
    }
    index = next
  }
  return result
}

function paginate<T>(items: T[], url: URL): { items: T[]; total: number; page: number; page_size: number } {
  const page = Math.max(1, Number(url.searchParams.get('page') ?? 1) || 1)
  const rawSize = Number(url.searchParams.get('page_size') ?? 20) || 20
  const pageSize = Math.min(100, Math.max(1, rawSize))
  const start = (page - 1) * pageSize
  return { items: items.slice(start, start + pageSize), total: items.length, page, page_size: pageSize }
}

function publicUser(user: MockUser): User {
  const { password: _password, ...rest } = user
  return rest
}

/** 去掉内部 user_id 字段，返回契约 §4 的 message 对象。 */
function stripUserId<T extends { user_id: number }>(message: T): Omit<T, 'user_id'> {
  const { user_id: _userId, ...rest } = message
  return rest
}

function issueToken(store: MockStore, user: MockUser): string {
  const token = `mock.${user.id}.${Math.random().toString(36).slice(2, 10)}`
  store.sessions.set(token, user.id)
  return token
}

function resolveUser(store: MockStore, header: string | string[] | undefined): MockUser | null {
  const value = Array.isArray(header) ? header[0] : header
  if (!value || !value.startsWith('Bearer ')) return null
  const token = value.slice(7).trim()
  let userId = store.sessions.get(token)
  if (!userId) {
    const parts = token.split('.')
    if (parts[0] === 'mock' && parts[1]) userId = Number(parts[1])
  }
  if (!userId) return null
  return store.users.find((user) => user.id === userId) ?? null
}

function chunkTextToDeltas(text: string): string[] {
  const pieces: string[] = []
  let index = 0
  while (index < text.length) {
    const size = 6 + Math.floor(Math.random() * 14)
    pieces.push(text.slice(index, index + size))
    index += size
  }
  return pieces
}

function findDocument(store: MockStore, id: number, userId: number): MockDocument | null {
  const doc = store.documents.find((item) => item.id === id && item.user_id === userId)
  return doc ?? null
}

function conversationSummary(store: MockStore, conversation: MockConversation): Record<string, unknown> {
  const messages = store.messages.filter((message) => message.conversation_id === conversation.id)
  const sorted = [...messages].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
  return {
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    message_count: messages.length,
    last_message_at: sorted.length > 0 ? (sorted[sorted.length - 1] as { created_at: string }).created_at : null,
  }
}

/* ------------------------------ 健康与元信息 ------------------------------ */

route('GET', '/api/health', (ctx) => sendJson(ctx.res, 200, {
  status: 'ok',
  version: '0.1.0',
  db: 'ok',
  llm_provider: 'echo',
}), { auth: false })

route('GET', `${V1}/meta`, (ctx) => sendJson(ctx.res, 200, {
  app_name: 'Citera',
  version: '0.1.0',
  registration_open: Boolean(ctx.store.settings.registration_open),
  limits: { max_upload_mb: 10, max_documents: 50, max_conversations: 100 },
}), { auth: false })

/* --------------------------------- 认证 --------------------------------- */

const PASSWORD_RULE = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/

route('POST', `${V1}/auth/register`, (ctx) => {
  const { store, body, res } = ctx
  const email = String(body.email ?? '').trim().toLowerCase()
  const password = String(body.password ?? '')
  const displayName = String(body.display_name ?? '').trim()
  if (!store.settings.registration_open) {
    return fail(res, 403, 'forbidden', '当前未开放注册')
  }
  if (!email.includes('@') || email.length < 5) {
    return fail(res, 400, 'bad_request', '邮箱格式不正确')
  }
  if (!PASSWORD_RULE.test(password)) {
    return fail(res, 400, 'bad_request', '密码至少 8 位且需同时包含字母与数字')
  }
  if (displayName.length === 0 || displayName.length > 64) {
    return fail(res, 400, 'bad_request', '昵称需为 1 到 64 个字符')
  }
  if (store.users.some((user) => user.email === email)) {
    return fail(res, 409, 'email_taken', '该邮箱已注册')
  }
  const user: MockUser = {
    id: nextId(store, 'user'),
    email,
    display_name: displayName,
    role: 'user',
    is_active: true,
    created_at: new Date().toISOString(),
    password,
  }
  store.users.push(user)
  return sendJson(res, 201, { user: publicUser(user), access_token: issueToken(store, user), token_type: 'bearer' })
}, { auth: false })

route('POST', `${V1}/auth/login`, (ctx) => {
  const { store, body, res } = ctx
  const email = String(body.email ?? '').trim().toLowerCase()
  const password = String(body.password ?? '')
  const user = store.users.find((item) => item.email === email)
  if (!user || user.password !== password) {
    return fail(res, 401, 'invalid_credentials', '邮箱或密码不正确')
  }
  if (!user.is_active) {
    return fail(res, 403, 'forbidden', '账号已被停用')
  }
  return sendJson(res, 200, { user: publicUser(user), access_token: issueToken(store, user), token_type: 'bearer' })
}, { auth: false })

route('GET', `${V1}/auth/me`, (ctx) => {
  if (!ctx.user) return fail(ctx.res, 401, 'unauthorized', '未登录')
  return sendJson(ctx.res, 200, { user: publicUser(ctx.user) })
})

route('PATCH', `${V1}/auth/me`, (ctx) => {
  const user = ctx.user as MockUser
  const displayName = ctx.body.display_name
  if (typeof displayName === 'string') {
    const trimmed = displayName.trim()
    if (trimmed.length === 0 || trimmed.length > 64) {
      return fail(ctx.res, 400, 'bad_request', '昵称需为 1 到 64 个字符')
    }
    user.display_name = trimmed
  }
  return sendJson(ctx.res, 200, { user: publicUser(user) })
})

/* --------------------------------- 文档 --------------------------------- */

route('GET', `${V1}/documents/stats`, (ctx) => {
  const { store, user, res } = ctx
  const docs = store.documents.filter((doc) => doc.user_id === (user as MockUser).id)
  const byStatus = new Map<string, number>()
  for (const doc of docs) byStatus.set(doc.status, (byStatus.get(doc.status) ?? 0) + 1)
  return sendJson(res, 200, {
    total: docs.length,
    ready: byStatus.get('ready') ?? 0,
    processing: (byStatus.get('processing') ?? 0) + (byStatus.get('pending') ?? 0),
    failed: byStatus.get('failed') ?? 0,
    chunk_total: docs.reduce((sum, doc) => sum + doc.chunk_count, 0),
    char_total: docs.reduce((sum, doc) => sum + doc.char_count, 0),
    by_status: [...byStatus.entries()].map(([status, count]) => ({ status, count })),
  })
})

route('GET', `${V1}/documents`, (ctx) => {
  const { store, user, url, res } = ctx
  const query = (url.searchParams.get('q') ?? '').trim().toLowerCase()
  const status = url.searchParams.get('status') ?? ''
  const sort = url.searchParams.get('sort') ?? '-created_at'
  let items = store.documents.filter((doc) => doc.user_id === (user as MockUser).id)
  if (query) {
    items = items.filter(
      (doc) =>
        doc.title.toLowerCase().includes(query) ||
        (doc.filename ?? '').toLowerCase().includes(query) ||
        store.chunks.some(
          (chunk) => chunk.document_id === doc.id && chunk.content.toLowerCase().includes(query),
        ),
    )
  }
  if (status) items = items.filter((doc) => doc.status === status)
  items = [...items].sort((a, b) => {
    if (sort === 'title') return a.title.localeCompare(b.title, 'zh-Hans-CN')
    if (sort === 'created_at') return Date.parse(a.created_at) - Date.parse(b.created_at)
    return Date.parse(b.created_at) - Date.parse(a.created_at)
  })
  const paged = paginate(items, url)
  return sendJson(res, 200, { ...paged, items: paged.items.map(publicDocument) })
})

route('POST', `${V1}/documents`, async (ctx) => {
  const { store, user, req, res, rawBody } = ctx
  const contentType = String(req.headers['content-type'] ?? '')
  let title = ''
  let rawText = ''
  let filename: string | null = null
  let mimeType: string | null = null
  let sizeBytes = 0

  if (contentType.includes('multipart/form-data')) {
    const boundary = /boundary=(?:"([^"]+)"|([^;]+))/.exec(contentType)
    const value = boundary?.[1] ?? boundary?.[2]
    if (!value) return fail(res, 400, 'bad_request', '缺少 multipart boundary')
    const parsed = parseMultipart(rawBody, value.trim())
    title = (parsed.fields.title ?? '').trim()
    rawText = parsed.fields.raw_text ?? ''
    if (parsed.file) {
      filename = parsed.file.filename
      mimeType = contentType.includes('pdf') ? 'application/pdf' : 'application/octet-stream'
      sizeBytes = parsed.file.content.length
      if (!rawText && (filename.endsWith('.txt') || filename.endsWith('.md'))) {
        rawText = parsed.file.content.toString('utf8')
      }
    }
  } else {
    title = String(ctx.body.title ?? '').trim()
    rawText = String(ctx.body.raw_text ?? '')
    sizeBytes = Buffer.byteLength(rawText, 'utf8')
  }

  if (!filename && rawText.trim().length === 0) {
    return fail(res, 400, 'bad_request', '请提供文件，或同时提供 title 与 raw_text')
  }
  if (filename && !/\.(txt|md|markdown|csv|log|json|pdf)$/i.test(filename)) {
    return fail(res, 415, 'unsupported_file_type', '不支持该文件类型')
  }
  if (sizeBytes > 10 * 1024 * 1024) {
    return fail(res, 413, 'file_too_large', '文件超过 10 MB 上限')
  }
  if (/encrypted|加密/i.test(filename ?? '')) {
    return fail(res, 422, 'unprocessable_upload', '文档已加密，无法解析文本内容')
  }

  const isPaste = !filename
  const document: MockDocument = {
    id: nextId(store, 'document'),
    user_id: (user as MockUser).id,
    title: title || (isPaste ? rawText.trim().slice(0, 24) : (filename as string)),
    source_type: isPaste ? 'paste' : 'upload',
    filename,
    mime_type: mimeType,
    size_bytes: sizeBytes,
    status: 'pending',
    error_message: null,
    chunk_count: 0,
    char_count: 0,
    meta: { chunk_size: 800, chunk_overlap: 120, embedding_provider: 'local' },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
  store.documents.push(document)

  // 后台异步切分 + 向量化（契约：POST 立即返回 pending）
  const store$ = store
  void (async () => {
    await sleep(1800)
    const target = store$.documents.find((doc) => doc.id === document.id)
    if (!target) return
    target.status = 'processing'
    await sleep(2200)
    const content = rawText || `${target.title}：本地演示环境未保留上传文件的原始字节，此处为占位切分结果。`
    const paragraphs = content.split(/\n{2,}|(?<=。)/).filter((line) => line.trim().length > 8)
    const grouped: string[] = []
    let current = ''
    for (const paragraph of paragraphs) {
      current += paragraph
      if (current.length >= 300) {
        grouped.push(current)
        current = ''
      }
    }
    if (current.trim()) grouped.push(current)
    const chunks = grouped.length > 0 ? grouped : [content]
    chunks.forEach((text, index) => {
      store$.chunks.push({
        id: nextId(store$, 'chunk'),
        document_id: target.id,
        user_id: target.user_id,
        ord: index + 1,
        heading: index === 0 ? '自动切分' : null,
        content: text,
        token_estimate: Math.round(text.length / 2.2),
        has_embedding: true,
      })
    })
    target.chunk_count = chunks.length
    target.char_count = content.length
    target.status = 'ready'
    target.updated_at = new Date().toISOString()
  })()

  return sendJson(res, 201, { document: publicDocument(document) })
})

route('GET', `${V1}/documents/:id`, (ctx) => {
  const doc = findDocument(ctx.store, Number(ctx.params.id), (ctx.user as MockUser).id)
  if (!doc) return fail(ctx.res, 404, 'not_found', '文档不存在')
  return sendJson(ctx.res, 200, { document: publicDocument(doc) })
})

route('GET', `${V1}/documents/:id/chunks`, (ctx) => {
  const { store, url, res } = ctx
  const doc = findDocument(store, Number(ctx.params.id), (ctx.user as MockUser).id)
  if (!doc) return fail(res, 404, 'not_found', '文档不存在')
  const chunks = store.chunks
    .filter((chunk) => chunk.document_id === doc.id)
    .sort((a, b) => a.ord - b.ord)
  const paged = paginate(chunks, url)
  return sendJson(res, 200, { ...paged, items: paged.items.map(publicChunk) })
})

route('PATCH', `${V1}/documents/:id`, (ctx) => {
  const doc = findDocument(ctx.store, Number(ctx.params.id), (ctx.user as MockUser).id)
  if (!doc) return fail(ctx.res, 404, 'not_found', '文档不存在')
  const title = ctx.body.title
  if (typeof title !== 'string' || title.trim().length === 0 || title.trim().length > 255) {
    return fail(ctx.res, 400, 'bad_request', '标题需为 1 到 255 个字符')
  }
  doc.title = title.trim()
  doc.updated_at = new Date().toISOString()
  return sendJson(ctx.res, 200, { document: publicDocument(doc) })
})

route('DELETE', `${V1}/documents/:id`, (ctx) => {
  const { store, res } = ctx
  const id = Number(ctx.params.id)
  const index = store.documents.findIndex(
    (doc) => doc.id === id && doc.user_id === (ctx.user as MockUser).id,
  )
  if (index === -1) return fail(res, 404, 'not_found', '文档不存在')
  store.documents.splice(index, 1)
  store.chunks = store.chunks.filter((chunk) => chunk.document_id !== id)
  res.writeHead(204)
  res.end()
})

route('POST', `${V1}/documents/:id/reprocess`, async (ctx) => {
  const { store, res } = ctx
  const doc = findDocument(store, Number(ctx.params.id), (ctx.user as MockUser).id)
  if (!doc) return fail(res, 404, 'not_found', '文档不存在')
  doc.status = 'processing'
  doc.updated_at = new Date().toISOString()
  res.writeHead(202, { 'Content-Type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify({ document: publicDocument(doc) }))
  await sleep(1500)
  doc.status = doc.error_message ? 'failed' : 'ready'
  doc.chunk_count = store.chunks.filter((chunk) => chunk.document_id === doc.id).length
})

/* ------------------------------- 会话与问答 ------------------------------- */

route('GET', `${V1}/conversations`, (ctx) => {
  const { store, user, url, res } = ctx
  const items = store.conversations
    .filter((conversation) => conversation.user_id === (user as MockUser).id && !conversation.deleted_at)
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .map((conversation) => conversationSummary(store, conversation))
  return sendJson(res, 200, paginate(items, url))
})

route('POST', `${V1}/conversations`, (ctx) => {
  const { store, user, res } = ctx
  const title = typeof ctx.body.title === 'string' ? (ctx.body.title as string).trim() : ''
  const conversation: MockConversation = {
    id: nextId(store, 'conversation'),
    user_id: (user as MockUser).id,
    title: title || '新会话',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    deleted_at: null,
  }
  store.conversations.push(conversation)
  return sendJson(res, 201, { conversation: conversationSummary(store, conversation) })
})

route('GET', `${V1}/conversations/:id`, (ctx) => {
  const { store, user, res } = ctx
  const id = Number(ctx.params.id)
  const conversation = store.conversations.find(
    (item) => item.id === id && item.user_id === (user as MockUser).id && !item.deleted_at,
  )
  if (!conversation) return fail(res, 404, 'not_found', '会话不存在')
  const messages = store.messages
    .filter((message) => message.conversation_id === id)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at))
    .map(({ user_id: _userId, ...rest }) => rest)
  return sendJson(res, 200, { conversation: { ...conversationSummary(store, conversation), messages } })
})

route('PATCH', `${V1}/conversations/:id`, (ctx) => {
  const { store, user, res } = ctx
  const conversation = store.conversations.find(
    (item) => item.id === Number(ctx.params.id) && item.user_id === (user as MockUser).id && !item.deleted_at,
  )
  if (!conversation) return fail(res, 404, 'not_found', '会话不存在')
  const title = ctx.body.title
  if (typeof title !== 'string' || title.trim().length === 0 || title.trim().length > 255) {
    return fail(res, 400, 'bad_request', '标题需为 1 到 255 个字符')
  }
  conversation.title = title.trim()
  conversation.updated_at = new Date().toISOString()
  return sendJson(res, 200, { conversation: conversationSummary(store, conversation) })
})

route('DELETE', `${V1}/conversations/:id`, (ctx) => {
  const { store, user, res } = ctx
  const conversation = store.conversations.find(
    (item) => item.id === Number(ctx.params.id) && item.user_id === (user as MockUser).id,
  )
  if (!conversation) return fail(res, 404, 'not_found', '会话不存在')
  conversation.deleted_at = new Date().toISOString()
  res.writeHead(204)
  res.end()
})

route('POST', `${V1}/conversations/:id/messages`, async (ctx) => {
  const { store, user, res } = ctx
  const currentUser = user as MockUser
  const conversation = store.conversations.find(
    (item) => item.id === Number(ctx.params.id) && item.user_id === currentUser.id && !item.deleted_at,
  )
  if (!conversation) return fail(res, 404, 'not_found', '会话不存在')

  const content = String(ctx.body.content ?? '').trim()
  if (!content) return fail(res, 400, 'bad_request', '提问内容不能为空')
  if (content.length > 4000) return fail(res, 400, 'bad_request', '提问内容过长')

  const mode = (ctx.body.retrieval_mode as RetrievalMode | undefined)
    ?? (store.settings.retrieval_mode as RetrievalMode)
  const topK = Number(ctx.body.top_k ?? store.settings.top_k ?? 5)
  const documentIds = Array.isArray(ctx.body.document_ids) ? (ctx.body.document_ids as number[]) : undefined
  const result = retrieve(store, content, mode, topK, documentIds)

  const now = new Date()
  const userMessage = {
    id: nextId(store, 'message'),
    conversation_id: conversation.id,
    user_id: currentUser.id,
    role: 'user' as const,
    content,
    citations: [] as Citation[],
    latency_ms: null,
    created_at: now.toISOString(),
  }
  store.messages.push(userMessage)
  conversation.updated_at = now.toISOString()
  if (conversation.title === '新会话') {
    conversation.title = content.slice(0, 30)
  }

  const answer = synthesizeAnswer(content, result.citations, result.chunks)

  if (ctx.body.stream !== true) {
    const assistant = {
      id: nextId(store, 'message'),
      conversation_id: conversation.id,
      user_id: currentUser.id,
      role: 'assistant' as const,
      content: answer,
      citations: result.citations,
      latency_ms: 420 + result.elapsed_ms,
      created_at: new Date().toISOString(),
    }
    store.messages.push(assistant)
    return sendJson(res, 200, { user_message: stripUserId(userMessage), assistant_message: stripUserId(assistant) })
  }

  /* ------------------------------ SSE 流式 ------------------------------ */
  const assistantId = nextId(store, 'message')
  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  })

  // 客户端断连检测：只有"响应尚未结束就 close"才是真的断开
  // （IncomingMessage 的 close 在请求体读完时也会触发，不能用它判断）
  let aborted = false
  res.on('close', () => {
    if (!res.writableEnded) aborted = true
  })

  const send = (event: string, data: unknown): void => {
    if (aborted) return
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  }

  send('meta', {
    conversation_id: conversation.id,
    user_message_id: userMessage.id,
    assistant_message_id: assistantId,
    retrieval_mode: mode,
    top_k: topK,
  })

  await sleep(120)
  send('retrieval', { chunks: result.citations, elapsed_ms: result.elapsed_ms })

  const startedAt = Date.now()
  let produced = ''
  for (const piece of chunkTextToDeltas(answer)) {
    if (aborted) break
    produced += piece
    send('delta', { text: piece })
    await sleep(16)
  }

  if (produced.length > 0) {
    store.messages.push({
      id: assistantId,
      conversation_id: conversation.id,
      user_id: currentUser.id,
      role: 'assistant',
      content: produced,
      citations: result.citations,
      latency_ms: Date.now() - startedAt,
      created_at: new Date().toISOString(),
    })
    conversation.updated_at = new Date().toISOString()
  }

  if (!aborted) {
    send('done', {
      assistant_message_id: assistantId,
      finish_reason: 'stop',
      latency_ms: Date.now() - startedAt,
      usage: {
        prompt_chars: result.chunks.reduce((sum, chunk) => sum + chunk.content.length, 0),
        completion_chars: produced.length,
      },
    })
  }
  res.end()
})

/* --------------------------------- 评测 --------------------------------- */

route('GET', `${V1}/evaluations/datasets`, (ctx) => {
  const items = ctx.store.datasets.map((dataset) => ({
    ...dataset,
    item_count: ctx.store.evalItems.filter((item) => item.dataset_id === dataset.id).length,
  }))
  return sendJson(ctx.res, 200, { items, total: items.length, page: 1, page_size: items.length })
})

route('GET', `${V1}/evaluations/datasets/:id/items`, (ctx) => {
  const datasetId = Number(ctx.params.id)
  const items = ctx.store.evalItems.filter((item) => item.dataset_id === datasetId)
  const paged = paginate(items, ctx.url)
  return sendJson(ctx.res, 200, { ...paged, items: paged.items.map(publicEvalItem) })
})

route('POST', `${V1}/evaluations/run`, async (ctx) => {
  const { store, res } = ctx
  const datasetId = Number(ctx.body.dataset_id)
  const modes = Array.isArray(ctx.body.modes) ? (ctx.body.modes as RetrievalMode[]) : []
  const topK = Number(ctx.body.top_k ?? 5)
  const dataset = store.datasets.find((item) => item.id === datasetId)
  if (!dataset) return fail(res, 404, 'not_found', '数据集不存在')
  if (modes.length === 0 || modes.some((mode) => !['vector', 'keyword', 'hybrid'].includes(mode))) {
    return fail(res, 400, 'bad_request', 'modes 必须是 vector/keyword/hybrid 的子集')
  }

  await sleep(900) // 让前端能真实看到"评测进行中"

  const items = store.evalItems.filter((item) => item.dataset_id === datasetId)
  const runs = modes.map((mode) => {
    const perItem = items.map((item) => {
      const stored = item.ranks[mode]
      const rank = stored !== null && stored <= Math.max(topK, 10) ? stored : null
      return { item_id: item.id, rank, hit: rank !== null && rank <= topK }
    })
    const latency = mode === 'keyword' ? 11 : mode === 'vector' ? 44 : 56
    const run = {
      run_id: nextId(store, 'run'),
      mode,
      metrics: computeMetrics(perItem.map((entry) => entry.rank), latency),
      item_count: items.length,
      duration_ms: latency * items.length + 180,
      created_at: new Date().toISOString(),
      dataset_id: datasetId,
      top_k: topK,
      per_item: perItem,
    }
    store.runs.push(run)
    return { run_id: run.run_id, mode: run.mode, metrics: run.metrics }
  })
  return sendJson(res, 200, { runs })
})

route('GET', `${V1}/evaluations/runs`, (ctx) => {
  const runs = [...ctx.store.runs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
  return sendJson(ctx.res, 200, paginate(runs, ctx.url))
})

route('GET', `${V1}/evaluations/runs/compare`, (ctx) => {
  const { store, url, res } = ctx
  const raw = url.searchParams.get('ids') ?? ''
  let ids = raw
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value) && value > 0)
  if (ids.length === 0) {
    ids = [...store.runs]
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
      .slice(0, 3)
      .map((run) => run.run_id)
  }
  const runs = ids
    .map((id) => store.runs.find((run) => run.run_id === id))
    .filter((run): run is NonNullable<typeof run> => Boolean(run))
  if (runs.length === 0) return fail(res, 404, 'not_found', '评测记录不存在')
  const items = store.evalItems
    .filter((item) => item.dataset_id === runs[0]?.dataset_id)
    .map((item) => ({
      item_id: item.id,
      question: item.question,
      per_run: runs.map((run) => {
        const entry = run.per_item.find((perItem) => perItem.item_id === item.id)
        return { run_id: run.run_id, rank: entry?.rank ?? null, hit: entry?.hit ?? false }
      }),
    }))
  return sendJson(res, 200, {
    runs: runs.map(({ dataset_id: _d, top_k: _t, per_item: _p, ...rest }) => rest),
    items,
  })
})

/* --------------------------------- 管理 --------------------------------- */

route('GET', `${V1}/admin/stats`, (ctx) => {
  const { store, res } = ctx
  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
  return sendJson(res, 200, {
    users: store.users.length,
    documents: store.documents.length,
    chunks: store.chunks.length,
    conversations: store.conversations.filter((item) => !item.deleted_at).length,
    messages: store.messages.length,
    eval_runs: store.runs.length,
    recent_7d: {
      documents: store.documents.filter((doc) => Date.parse(doc.created_at) >= weekAgo).length,
      messages: store.messages.filter((message) => Date.parse(message.created_at) >= weekAgo).length,
    },
  })
}, { admin: true })

route('GET', `${V1}/admin/users`, (ctx) => {
  const query = (ctx.url.searchParams.get('q') ?? '').trim().toLowerCase()
  let users = ctx.store.users
  if (query) {
    users = users.filter(
      (user) => user.email.toLowerCase().includes(query) || user.display_name.toLowerCase().includes(query),
    )
  }
  const paged = paginate(users, ctx.url)
  return sendJson(ctx.res, 200, { ...paged, items: paged.items.map(publicUser) })
}, { admin: true })

route('PATCH', `${V1}/admin/users/:id`, (ctx) => {
  const { store, res } = ctx
  const user = store.users.find((item) => item.id === Number(ctx.params.id))
  if (!user) return fail(res, 404, 'not_found', '用户不存在')
  if (typeof ctx.body.is_active === 'boolean') user.is_active = ctx.body.is_active
  if (ctx.body.role === 'user' || ctx.body.role === 'admin') user.role = ctx.body.role
  return sendJson(res, 200, { user: publicUser(user) })
}, { admin: true })

route('GET', `${V1}/admin/settings`, (ctx) => sendJson(ctx.res, 200, { settings: ctx.store.settings }), {
  admin: true,
})

route('PUT', `${V1}/admin/settings`, (ctx) => {
  const { store, res } = ctx
  const incoming = ctx.body.settings
  if (typeof incoming !== 'object' || incoming === null) {
    return fail(res, 400, 'bad_request', 'settings 必须是对象')
  }
  const whitelist = ['retrieval_mode', 'top_k', 'chunk_size', 'chunk_overlap', 'registration_open']
  const next: Record<string, unknown> = { ...store.settings }
  for (const [key, value] of Object.entries(incoming as Record<string, unknown>)) {
    if (!whitelist.includes(key)) {
      return fail(res, 400, 'bad_request', `不支持的设置项：${key}`)
    }
    if (key === 'retrieval_mode' && !['vector', 'keyword', 'hybrid'].includes(String(value))) {
      return fail(res, 400, 'bad_request', 'retrieval_mode 取值非法')
    }
    if (key === 'registration_open' && typeof value !== 'boolean') {
      return fail(res, 400, 'bad_request', 'registration_open 必须是布尔值')
    }
    if (['top_k', 'chunk_size', 'chunk_overlap'].includes(key)) {
      const num = Number(value)
      if (!Number.isFinite(num) || num <= 0) return fail(res, 400, 'bad_request', `${key} 必须是正数`)
      next[key] = Math.round(num)
      continue
    }
    next[key] = value
  }
  store.settings = next
  return sendJson(res, 200, { settings: next })
}, { admin: true })

route('POST', `${V1}/admin/reseed`, async (ctx) => {
  const { store, res } = ctx
  const sessions = store.sessions
  Object.assign(store, createStore())
  store.sessions = sessions
  await sleep(400)
  return sendJson(res, 200, { status: 'ok', documents: store.documents.length, users: store.users.length })
}, { admin: true })

/* ------------------------------- 中间件本体 ------------------------------- */

export function createMockHandler(): Connect.NextHandleFunction {
  const store = createStore()

  return async (req, res, next) => {
    const rawUrl = req.url ?? '/'
    if (!rawUrl.startsWith('/api/')) return next()

    const url = new URL(rawUrl, 'http://localhost')
    const pathname = url.pathname.replace(/\/+$/, '') || '/'
    const method = (req.method ?? 'GET').toUpperCase()

    // 允许跨源调用（把 VITE_API_BASE 指向 dev server 时用得上）
    res.setHeader('Access-Control-Allow-Origin', req.headers.origin ?? '*')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,PUT,DELETE,OPTIONS')
    if (method === 'OPTIONS') {
      res.writeHead(204)
      res.end()
      return
    }

    const segments = pathname.split('/').filter(Boolean)
    let matched: { route: Route; params: Record<string, string> } | null = null
    for (const candidate of routes) {
      if (candidate.method !== method || candidate.segments.length !== segments.length) continue
      const params: Record<string, string> = {}
      let ok = true
      for (let i = 0; i < candidate.segments.length; i += 1) {
        const expected = candidate.segments[i] as string
        const actual = segments[i] as string
        if (expected.startsWith(':')) params[expected.slice(1)] = decodeURIComponent(actual)
        else if (expected !== actual) {
          ok = false
          break
        }
      }
      if (ok) {
        matched = { route: candidate, params }
        break
      }
    }

    if (!matched) {
      return fail(res, 404, 'not_found', '接口不存在')
    }

    const rawBody = method === 'GET' || method === 'DELETE' ? Buffer.alloc(0) : await readBody(req)
    let body: Record<string, unknown> = {}
    const contentType = String(req.headers['content-type'] ?? '')
    if (rawBody.length > 0 && contentType.includes('application/json')) {
      try {
        body = JSON.parse(rawBody.toString('utf8')) as Record<string, unknown>
      } catch {
        return fail(res, 400, 'bad_request', '请求体不是合法 JSON')
      }
    }

    const user = resolveUser(store, req.headers.authorization)
    if (matched.route.auth && !user) {
      return fail(res, 401, 'unauthorized', '未登录')
    }
    if (matched.route.admin && user?.role !== 'admin') {
      return fail(res, 403, 'forbidden', '需要管理员权限')
    }

    // 调试开关：?_slow=1200 强制延迟（看骨架屏） / ?_error=rate_limited 强制报错（看错误态）
    const slow = Number(url.searchParams.get('_slow') ?? 0)
    if (Number.isFinite(slow) && slow > 0) await sleep(Math.min(slow, 8000))
    const forced = url.searchParams.get('_error')
    if (forced) {
      return fail(res, forced === 'rate_limited' ? 429 : 500, forced, `（mock 强制错误）${forced}`)
    }
    if (!pathname.startsWith(`${V1}/conversations/`) || method !== 'POST') {
      await sleep(40 + Math.random() * 90)
    }

    try {
      await matched.route.handler({
        req,
        res,
        url,
        params: matched.params,
        body,
        rawBody,
        store,
        user,
      })
    } catch (error) {
      if (!res.headersSent) {
        fail(res, 500, 'internal_error', error instanceof Error ? error.message : 'mock 内部错误')
      } else {
        res.end()
      }
    }
  }
}

export interface MockPluginOptions {
  /** 是否启用（由 VITE_MOCK 决定） */
  enabled?: boolean
}

export function citeraMockPlugin(options: MockPluginOptions = {}): Plugin {
  const enabled = options.enabled !== false
  return {
    name: 'citera-mock-server',
    configureServer(server) {
      if (!enabled) return
      server.middlewares.use(createMockHandler())
      server.config.logger.info(
        '  \u279c  Citera mock API 已挂载：/api/**（契约 §4 全端点 + SSE；?_slow= / ?_error= 可调试三态）',
      )
    },
    configurePreviewServer(server) {
      if (!enabled) return
      server.middlewares.use(createMockHandler())
    },
  }
}
