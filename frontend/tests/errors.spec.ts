import { describe, expect, it } from 'vitest'
import {
  ApiError,
  CODE_FALLBACK_MESSAGE,
  codeFromStatus,
  describeError,
  errorMessage,
  isApiError,
  parseErrorEnvelope,
  toApiError,
} from '@/api/errors'

describe('parseErrorEnvelope（契约 §4.1 错误格式）', () => {
  it('解析标准包络并保留 request_id', () => {
    const payload = parseErrorEnvelope({
      error: { code: 'invalid_credentials', message: '邮箱或密码不正确', details: null, request_id: '0f3c' },
    })
    expect(payload).toEqual({
      code: 'invalid_credentials',
      message: '邮箱或密码不正确',
      details: null,
      request_id: '0f3c',
    })
  })

  it('后端漏了 message 时用兜底文案', () => {
    expect(parseErrorEnvelope({ error: { code: 'rate_limited' } })?.message).toBe(
      CODE_FALLBACK_MESSAGE.rate_limited,
    )
  })

  it('不是标准包络时返回 null', () => {
    expect(parseErrorEnvelope({ detail: 'nope' })).toBeNull()
    expect(parseErrorEnvelope('boom')).toBeNull()
    expect(parseErrorEnvelope(null)).toBeNull()
    expect(parseErrorEnvelope({ error: { message: 'no code' } })).toBeNull()
  })
})

describe('codeFromStatus（HTTP → 契约错误码兜底映射）', () => {
  it.each([
    [400, 'bad_request'],
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [409, 'email_taken'],
    [413, 'file_too_large'],
    [415, 'unsupported_file_type'],
    [422, 'unprocessable_upload'],
    [429, 'rate_limited'],
    [500, 'internal_error'],
    [503, 'internal_error'],
  ])('%i → %s', (status, expected) => {
    expect(codeFromStatus(status)).toBe(expected)
  })
})

describe('toApiError', () => {
  it('axios 响应错误 → 按 §4.1 包络产出 ApiError', () => {
    const error = {
      isAxiosError: true,
      response: { status: 404, data: { error: { code: 'not_found', message: '文档不存在' } } },
    }
    const api = toApiError(error)
    expect(isApiError(api)).toBe(true)
    expect(api.code).toBe('not_found')
    expect(api.status).toBe(404)
    expect(api.isNotFound).toBe(true)
  })

  it('响应体不是标准包络时按状态码兜底', () => {
    const api = toApiError({ isAxiosError: true, response: { status: 413, data: 'too big' } })
    expect(api.code).toBe('file_too_large')
    expect(api.message).toBe(CODE_FALLBACK_MESSAGE.file_too_large)
  })

  it('无响应的 axios 错误 → network_error', () => {
    expect(toApiError({ isAxiosError: true }).code).toBe('network_error')
  })

  it('AbortError → request_aborted（不是失败）', () => {
    expect(toApiError(new DOMException('x', 'AbortError')).code).toBe('request_aborted')
    expect(toApiError({ code: 'ERR_CANCELED' }).code).toBe('request_aborted')
  })

  it('已是 ApiError 时原样返回', () => {
    const original = new ApiError('quota_exceeded', '配额已满', 403)
    expect(toApiError(original)).toBe(original)
  })
})

describe('ApiError 语义判定（§7.1 分流依据）', () => {
  it('401 与 unauthorized / token_expired 归类为需要重新登录', () => {
    expect(new ApiError('token_expired', 'x', 401).isAuthError).toBe(true)
    expect(new ApiError('unauthorized', 'x').isAuthError).toBe(true)
    expect(new ApiError('forbidden', 'x', 403).isAuthError).toBe(false)
  })

  it('rate_limited / quota_exceeded 各自可判定', () => {
    expect(new ApiError('rate_limited', 'x', 429).isRateLimited).toBe(true)
    expect(new ApiError('quota_exceeded', 'x', 403).isQuotaExceeded).toBe(true)
  })

  it('可重试判定：网络 / 限流 / 5xx 可重试，参数错误不可重试', () => {
    expect(new ApiError('network_error', 'x').isRetryable).toBe(true)
    expect(new ApiError('rate_limited', 'x', 429).isRetryable).toBe(true)
    expect(new ApiError('internal_error', 'x', 500).isRetryable).toBe(true)
    expect(new ApiError('bad_request', 'x', 400).isRetryable).toBe(false)
  })
})

describe('describeError / errorMessage（§7.1 用户可见文案分流）', () => {
  it('unauthorized 类统一提示重新登录', () => {
    expect(describeError(new ApiError('token_expired', 'token 过期了', 401)).message).toBe(
      CODE_FALLBACK_MESSAGE.unauthorized,
    )
  })

  it('rate_limited 提示"操作过于频繁"', () => {
    expect(errorMessage(new ApiError('rate_limited', 'Too Many Requests', 429))).toBe(
      CODE_FALLBACK_MESSAGE.rate_limited,
    )
  })

  it('quota_exceeded 保留后端原始 message', () => {
    expect(errorMessage(new ApiError('quota_exceeded', '文档数已达 50 上限', 403))).toBe('文档数已达 50 上限')
  })

  it('其余错误直接用 message 原文', () => {
    expect(errorMessage(new ApiError('email_taken', '该邮箱已注册', 409))).toBe('该邮箱已注册')
    expect(describeError(new ApiError('bad_request', '密码至少 8 位', 400)).retryable).toBe(false)
  })
})
