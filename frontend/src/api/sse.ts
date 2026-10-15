/**
 * SSE 客户端。
 * 契约 §7.2.3：必须用 fetch + ReadableStream 手写解析（不能用 EventSource，因为要带 Authorization 头）。
 * 事件顺序固定：meta → retrieval → delta* → done（异常为 error 后关闭）。
 */

import { ApiError, codeFromStatus, parseErrorEnvelope } from './errors'
import { apiUrl, authHeader, V1 } from './client'
import type {
  AskRequest,
  SseDeltaPayload,
  SseDonePayload,
  SseErrorPayload,
  SseMetaPayload,
  SseRetrievalPayload,
} from './types'

export interface SseFrame {
  event: string
  data: string
  id: string | null
}

/**
 * 纯解析器（无 IO，可单测）。遵循 SSE 规范：
 * 空行分帧、`data:` 多行以 \n 连接、`:` 开头为注释、字段名与冒号后的单个空格处理、
 * CRLF / LF / CR 三种换行、UTF-8 BOM 剔除。
 */
export class SseParser {
  private buffer = ''
  private dataLines: string[] = []
  private eventName = ''
  private lastId: string | null = null
  private first = true

  push(chunk: string): SseFrame[] {
    if (this.first) {
      this.first = false
      if (chunk.charCodeAt(0) === 0xfeff) chunk = chunk.slice(1)
    }
    this.buffer += chunk
    const frames: SseFrame[] = []
    for (const line of this.takeLines()) {
      const frame = this.consumeLine(line)
      if (frame) frames.push(frame)
    }
    return frames
  }

  /** 流结束时的宽容处理：服务端漏了末尾空行也要把最后一个事件交出来。 */
  flush(): SseFrame[] {
    const frames: SseFrame[] = []
    if (this.buffer.length > 0) {
      const rest = this.buffer
      this.buffer = ''
      const frame = this.consumeLine(rest)
      if (frame) frames.push(frame)
    }
    const pending = this.dispatch()
    if (pending) frames.push(pending)
    return frames
  }

  private takeLines(): string[] {
    const lines: string[] = []
    let start = 0
    for (let i = 0; i < this.buffer.length; i += 1) {
      const ch = this.buffer[i]
      if (ch === '\n') {
        lines.push(this.buffer.slice(start, i))
        start = i + 1
      } else if (ch === '\r') {
        if (i + 1 >= this.buffer.length) break // 可能是 \r\n，等下一个块
        lines.push(this.buffer.slice(start, i))
        if (this.buffer[i + 1] === '\n') i += 1
        start = i + 1
      }
    }
    this.buffer = this.buffer.slice(start)
    return lines
  }

  private consumeLine(line: string): SseFrame | null {
    if (line === '') return this.dispatch()
    if (line.startsWith(':')) return null
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)

    switch (field) {
      case 'event':
        this.eventName = value
        break
      case 'data':
        this.dataLines.push(value)
        break
      case 'id':
        this.lastId = value
        break
      default:
        break // retry 与未知字段忽略
    }
    return null
  }

  private dispatch(): SseFrame | null {
    if (this.dataLines.length === 0 && this.eventName === '') return null
    const frame: SseFrame = {
      event: this.eventName || 'message',
      data: this.dataLines.join('\n'),
      id: this.lastId,
    }
    this.dataLines = []
    this.eventName = ''
    return frame
  }
}

export interface SseHandlers {
  onMeta?: (payload: SseMetaPayload) => void
  onRetrieval?: (payload: SseRetrievalPayload) => void
  onDelta?: (payload: SseDeltaPayload) => void
  onDone?: (payload: SseDonePayload) => void
  onError?: (payload: SseErrorPayload) => void
  /** 未知事件或无法解析的 data，交给调用方决定是否记录 */
  onUnknown?: (frame: SseFrame) => void
}

/** 把一帧派发到对应回调；data 非 JSON 或事件名未知时走 onUnknown。 */
export function dispatchFrame(frame: SseFrame, handlers: SseHandlers): void {
  let payload: unknown
  try {
    payload = JSON.parse(frame.data) as unknown
  } catch {
    handlers.onUnknown?.(frame)
    return
  }
  switch (frame.event) {
    case 'meta':
      handlers.onMeta?.(payload as SseMetaPayload)
      break
    case 'retrieval':
      handlers.onRetrieval?.(payload as SseRetrievalPayload)
      break
    case 'delta':
      handlers.onDelta?.(payload as SseDeltaPayload)
      break
    case 'done':
      handlers.onDone?.(payload as SseDonePayload)
      break
    case 'error':
      handlers.onError?.(payload as SseErrorPayload)
      break
    default:
      handlers.onUnknown?.(frame)
  }
}

export interface StreamChatOptions extends SseHandlers {
  /** AbortController.signal：用于"停止生成"（§7.2.2） */
  signal?: AbortSignal
}

async function throwHttpError(response: Response): Promise<never> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const payload = parseErrorEnvelope(body)
  if (payload) {
    throw new ApiError(payload.code, payload.message, response.status, payload.details ?? null, payload.request_id ?? null)
  }
  const code = codeFromStatus(response.status)
  throw new ApiError(code, `请求失败（HTTP ${response.status}）`, response.status)
}

/**
 * 流式提问。事件按契约顺序回调；调用方中断时（AbortController）本函数正常返回。
 */
export async function streamChatMessage(
  conversationId: number,
  body: AskRequest,
  options: StreamChatOptions = {},
): Promise<void> {
  const payload: AskRequest & { stream: true } = { ...body, stream: true }

  let response: Response
  try {
    response = await fetch(apiUrl(`${V1}/conversations/${conversationId}/messages`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...authHeader(),
      },
      body: JSON.stringify(payload),
      signal: options.signal,
    })
  } catch (error) {
    if (isAbortError(error)) return
    throw new ApiError('network_error', '网络不可用，请检查连接后重试', 0)
  }

  if (!response.ok) await throwHttpError(response)

  const reader = response.body?.getReader()
  if (!reader) {
    // 兜底：服务端没给流（例如被中间层缓冲），尝试当 JSON 处理
    let text = ''
    try {
      text = await response.text()
    } catch {
      return
    }
    if (text.trim().length > 0) {
      const parser = new SseParser()
      for (const frame of parser.push(text)) dispatchFrame(frame, options)
      for (const frame of parser.flush()) dispatchFrame(frame, options)
    }
    return
  }

  const decoder = new TextDecoder('utf-8')
  const parser = new SseParser()
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
        dispatchFrame(frame, options)
      }
    }
    for (const frame of parser.push(decoder.decode())) dispatchFrame(frame, options)
    for (const frame of parser.flush()) dispatchFrame(frame, options)
  } catch (error) {
    if (!isAbortError(error)) throw new ApiError('network_error', '流式连接中断，请重试', 0)
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* 已释放 */
    }
  }
}

export function isAbortError(error: unknown): boolean {
  if (typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError') {
    return true
  }
  return (error as { name?: string } | null)?.name === 'AbortError'
}
