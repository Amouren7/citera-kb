/**
 * 契约 §4.1 错误格式与 §7.1 前端分流规则的唯一实现处。
 * 纯函数、零副作用，便于单测。
 */

export interface ApiErrorPayload {
  code: string
  message: string
  details?: unknown
  request_id?: string
}

export interface ApiErrorEnvelope {
  error: ApiErrorPayload
}

export const ERROR_CODES = [
  'bad_request',
  'unauthorized',
  'invalid_credentials',
  'token_expired',
  'forbidden',
  'quota_exceeded',
  'not_found',
  'email_taken',
  'file_too_large',
  'unsupported_file_type',
  'unprocessable_upload',
  'rate_limited',
  'internal_error',
  // 仅前端产生的本地错误码（不来自后端）
  'network_error',
  'request_aborted',
  'invalid_response',
] as const

export type ApiErrorCode = (typeof ERROR_CODES)[number] | (string & {})

/** 后端 message 缺失时的兜底文案；后端给了 message 一律以后端为准。 */
export const CODE_FALLBACK_MESSAGE: Record<string, string> = {
  bad_request: '请求参数不合法',
  unauthorized: '登录状态已失效，请重新登录',
  invalid_credentials: '邮箱或密码不正确',
  token_expired: '登录已过期，请重新登录',
  forbidden: '没有权限执行该操作',
  quota_exceeded: '已达配额上限',
  not_found: '资源不存在或无权访问',
  email_taken: '该邮箱已注册',
  file_too_large: '文件超出大小限制',
  unsupported_file_type: '不支持该文件类型',
  unprocessable_upload: '文件内容无法解析',
  rate_limited: '操作过于频繁，请稍后再试',
  internal_error: '服务内部错误，请稍后重试',
  network_error: '网络不可用，请检查连接后重试',
  request_aborted: '请求已取消',
  invalid_response: '服务返回了无法解析的数据',
}

/** 会触发"清 token + 跳登录"的错误码（§7.1）。 */
const AUTH_CODES = new Set(['unauthorized', 'token_expired'])

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly details: unknown
  readonly requestId: string | null

  constructor(
    code: ApiErrorCode,
    message: string,
    status = 0,
    details: unknown = null,
    requestId: string | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
    this.requestId = requestId
  }

  /** 是否是"需要重新登录"的错误（§7.1：unauthorized / token_expired）。 */
  get isAuthError(): boolean {
    return this.status === 401 || AUTH_CODES.has(this.code)
  }

  get isRateLimited(): boolean {
    return this.code === 'rate_limited' || this.status === 429
  }

  get isQuotaExceeded(): boolean {
    return this.code === 'quota_exceeded'
  }

  get isNotFound(): boolean {
    return this.code === 'not_found' || this.status === 404
  }

  /** 是否值得给用户"重试"按钮。 */
  get isRetryable(): boolean {
    return (
      this.code === 'network_error' ||
      this.code === 'internal_error' ||
      this.code === 'rate_limited' ||
      this.status >= 500
    )
  }

  toJSON(): ApiErrorPayload {
    return {
      code: this.code,
      message: this.message,
      details: this.details,
      request_id: this.requestId ?? undefined,
    }
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError
}

/** 从任意后端响应体里按 §4.1 抽取错误包络；不符合则返回 null。 */
export function parseErrorEnvelope(body: unknown): ApiErrorPayload | null {
  if (typeof body !== 'object' || body === null) return null
  const envelope = body as Partial<ApiErrorEnvelope>
  const err = envelope.error
  if (typeof err !== 'object' || err === null) return null
  const code = (err as ApiErrorPayload).code
  if (typeof code !== 'string' || code.length === 0) return null
  const message = (err as ApiErrorPayload).message
  const requestId = (err as ApiErrorPayload).request_id
  return {
    code,
    message: typeof message === 'string' && message.length > 0 ? message : CODE_FALLBACK_MESSAGE[code] ?? '请求失败',
    details: (err as ApiErrorPayload).details ?? null,
    request_id: typeof requestId === 'string' ? requestId : undefined,
  }
}

/** HTTP 状态码 → 契约错误码兜底（后端未给标准包络时使用）。 */
export function codeFromStatus(status: number): ApiErrorCode {
  switch (status) {
    case 400:
      return 'bad_request'
    case 401:
      return 'unauthorized'
    case 403:
      return 'forbidden'
    case 404:
      return 'not_found'
    case 409:
      return 'email_taken'
    case 413:
      return 'file_too_large'
    case 415:
      return 'unsupported_file_type'
    case 422:
      return 'unprocessable_upload'
    case 429:
      return 'rate_limited'
    default:
      return status >= 500 ? 'internal_error' : 'bad_request'
  }
}

interface AxiosLikeError {
  isAxiosError?: boolean
  code?: string
  name?: string
  message?: string
  response?: { status: number; data: unknown; headers?: Record<string, unknown> }
  request?: unknown
}

function isAbort(error: unknown): boolean {
  const e = error as AxiosLikeError | null
  if (!e) return false
  if (e.code === 'ERR_CANCELED') return true
  // fetch 中断会给 DOMException(AbortError)；某些运行环境（含测试桩、polyfill）给的是
  // 普通 Error 但 name 仍是 AbortError。两者都必须判为"用户主动停止"而不是失败。
  if (e.name === 'AbortError') return true
  return typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError'
}

/** 任意异常 → ApiError。axios 错误、fetch 错误、AbortError、网络错误全覆盖。 */
export function toApiError(error: unknown): ApiError {
  if (isApiError(error)) return error

  if (isAbort(error)) {
    return new ApiError('request_aborted', CODE_FALLBACK_MESSAGE.request_aborted, 0)
  }

  const e = error as AxiosLikeError

  if (e && e.response) {
    const status = e.response.status
    const payload = parseErrorEnvelope(e.response.data)
    if (payload) {
      return new ApiError(payload.code, payload.message, status, payload.details ?? null, payload.request_id ?? null)
    }
    const code = codeFromStatus(status)
    const headerId = e.response.headers?.['x-request-id']
    return new ApiError(
      code,
      CODE_FALLBACK_MESSAGE[code] ?? '请求失败',
      status,
      null,
      typeof headerId === 'string' ? headerId : null,
    )
  }

  if (e && e.isAxiosError) {
    return new ApiError('network_error', CODE_FALLBACK_MESSAGE.network_error, 0)
  }

  if (error instanceof Error) {
    return new ApiError('internal_error', error.message || CODE_FALLBACK_MESSAGE.internal_error, 0)
  }

  return new ApiError('internal_error', CODE_FALLBACK_MESSAGE.internal_error, 0)
}

/**
 * §7.1 的用户可见文案分流：
 *  unauthorized 类 → 提示重新登录；rate_limited → 频繁；quota_exceeded → 配额；其余用 message 原文。
 */
export function describeError(error: unknown): { code: ApiErrorCode; message: string; retryable: boolean } {
  const api = toApiError(error)
  if (api.isAuthError) {
    return { code: api.code, message: CODE_FALLBACK_MESSAGE.unauthorized, retryable: false }
  }
  if (api.isRateLimited) {
    return { code: api.code, message: CODE_FALLBACK_MESSAGE.rate_limited, retryable: true }
  }
  if (api.isQuotaExceeded) {
    return { code: api.code, message: api.message || CODE_FALLBACK_MESSAGE.quota_exceeded, retryable: false }
  }
  return { code: api.code, message: api.message, retryable: api.isRetryable }
}

/** 供 UI 直接使用的消息文本。 */
export function errorMessage(error: unknown): string {
  return describeError(error).message
}
