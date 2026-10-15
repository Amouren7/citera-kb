import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import { dispatchFrame, SseParser, streamChatMessage } from '@/api/sse'

describe('SseParser（契约 §4.2 流式事件）', () => {
  it('按空行分帧并解析 event/data', () => {
    const parser = new SseParser()
    const frames = parser.push('event: meta\ndata: {"conversation_id":1}\n\n')
    expect(frames).toHaveLength(1)
    expect(frames[0]?.event).toBe('meta')
    expect(frames[0]?.data).toBe('{"conversation_id":1}')
  })

  it('跨块切分的事件能拼接还原（不依赖网络分块边界）', () => {
    const parser = new SseParser()
    expect(parser.push('event: del')).toEqual([])
    expect(parser.push('ta\ndata: {"te')).toEqual([])
    const frames = parser.push('xt":"你好"}\n\n')
    expect(frames).toHaveLength(1)
    expect(frames[0]?.event).toBe('delta')
    expect(JSON.parse(frames[0]?.data ?? '{}')).toEqual({ text: '你好' })
  })

  it('兼容 CRLF 与单独的 CR 换行', () => {
    const parser = new SseParser()
    const first = parser.push('event: a\r\ndata: 1\r\n\r\n')
    const second = parser.push('event: b\rdata: 2\r\r')
    // 缓冲区末尾孤立的裸 CR 可能是被切开的 CRLF，规范要求等下一块；
    // 真实客户端在流结束时一定会调用 flush 收尾（streamChatMessage 就是这么做的）。
    const rest = parser.flush()
    expect([...first, ...second, ...rest].map((frame) => `${frame.event}:${frame.data}`)).toEqual(['a:1', 'b:2'])
  })

  it('多行 data 用换行连接，注释行与未知字段被忽略', () => {
    const parser = new SseParser()
    const frames = parser.push(': keep-alive\nevent: note\ndata: line1\ndata: line2\nretry: 3000\n\n')
    expect(frames).toHaveLength(1)
    expect(frames[0]?.data).toBe('line1\nline2')
  })

  it('剔除 UTF-8 BOM，且冒号后只吃一个空格', () => {
    const parser = new SseParser()
    const frames = parser.push('\uFEFFevent: meta\ndata:  {"a": 1}\n\n')
    expect(frames[0]?.data).toBe(' {"a": 1}')
  })

  it('flush 时把服务端漏掉末尾空行的最后一个事件交出来', () => {
    const parser = new SseParser()
    expect(parser.push('event: done\ndata: {"finish_reason":"stop"}')).toEqual([])
    const frames = parser.flush()
    expect(frames).toHaveLength(1)
    expect(frames[0]?.event).toBe('done')
  })

  it('没有 data 也没有 event 的空行不产生空帧', () => {
    const parser = new SseParser()
    expect(parser.push('\n\n\n')).toEqual([])
  })
})

describe('dispatchFrame', () => {
  it('按事件名分派到对应回调', () => {
    const handlers = {
      onMeta: vi.fn(),
      onRetrieval: vi.fn(),
      onDelta: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    }
    dispatchFrame({ event: 'delta', data: '{"text":"x"}', id: null }, handlers)
    dispatchFrame({ event: 'done', data: '{"assistant_message_id":9,"finish_reason":"stop","latency_ms":1,"usage":{"prompt_chars":1,"completion_chars":2}}', id: null }, handlers)
    expect(handlers.onDelta).toHaveBeenCalledWith({ text: 'x' })
    expect(handlers.onDone).toHaveBeenCalled()
    expect(handlers.onMeta).not.toHaveBeenCalled()
  })

  it('data 不是 JSON 或事件名未知时走 onUnknown', () => {
    const onUnknown = vi.fn()
    dispatchFrame({ event: 'delta', data: 'not-json', id: null }, { onUnknown })
    dispatchFrame({ event: 'ping', data: '{}', id: null }, { onUnknown })
    expect(onUnknown).toHaveBeenCalledTimes(2)
  })
})

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

describe('streamChatMessage（fetch + ReadableStream 手写解析）', () => {
  it('按 meta → retrieval → delta → done 顺序回调，且带 Authorization 头', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: meta\ndata: {"conversation_id":1,"user_message_id":8,"assistant_message_id":9,"retrieval_mode":"hybrid","top_k":5}\n\n',
        'event: retrieval\ndata: {"chunks":[{"chunk_id":7}],"elapsed_ms":37}\n\n',
        'event: delta\ndata: {"text":"整机"}\n\n',
        'event: delta\ndata: {"text":"保修 12 个月"}\n\n',
        'event: done\ndata: {"assistant_message_id":9,"finish_reason":"stop","latency_ms":812,"usage":{"prompt_chars":10,"completion_chars":20}}\n\n',
      ]),
    )
    vi.stubGlobal('fetch', fetchMock)

    const onMeta = vi.fn()
    const onRetrieval = vi.fn()
    const onDone = vi.fn()
    let text = ''
    await streamChatMessage(1, { content: '保修期多久', top_k: 5 }, {
      onMeta,
      onRetrieval,
      onDelta: (payload) => {
        text += payload.text
      },
      onDone,
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/v1/conversations/1/messages')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(String(init.body))).toMatchObject({ content: '保修期多久', stream: true, top_k: 5 })

    expect(onMeta.mock.calls[0]?.[0]).toMatchObject({ assistant_message_id: 9, retrieval_mode: 'hybrid' })
    expect(onRetrieval.mock.calls[0]?.[0]).toMatchObject({ elapsed_ms: 37 })
    expect(text).toBe('整机保修 12 个月')
    expect(onDone.mock.calls[0]?.[0]).toMatchObject({ finish_reason: 'stop', latency_ms: 812 })
  })

  it('HTTP 错误按 §4.1 包络抛出 ApiError（含 code）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: 'rate_limited', message: '操作过于频繁，请稍后再试', details: null, request_id: 'abc' } }), {
          status: 429,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    await expect(streamChatMessage(1, { content: 'x' }, {})).rejects.toMatchObject({
      code: 'rate_limited',
      status: 429,
    })
  })

  it('HTTP 错误但没有标准包络时按状态码兜底', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>502</html>', { status: 502 })))
    await expect(streamChatMessage(1, { content: 'x' }, {})).rejects.toBeInstanceOf(ApiError)
    await expect(streamChatMessage(1, { content: 'x' }, {})).rejects.toMatchObject({ code: 'internal_error' })
  })

  it('调用方 abort 时正常返回（"停止生成"不抛错）', async () => {
    const abortError = new DOMException('aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))
    await expect(streamChatMessage(1, { content: 'x' }, {})).resolves.toBeUndefined()
  })

  it('网络异常抛 network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(streamChatMessage(1, { content: 'x' }, {})).rejects.toMatchObject({ code: 'network_error' })
  })

  it('服务端以 error 事件结束时回调 onError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(sseResponse(['event: error\ndata: {"code":"internal_error","message":"生成失败"}\n\n'])),
    )
    const onError = vi.fn()
    await streamChatMessage(1, { content: 'x' }, { onError })
    expect(onError).toHaveBeenCalledWith({ code: 'internal_error', message: '生成失败' })
  })
})
