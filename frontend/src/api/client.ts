import axios, { type AxiosError, type AxiosInstance, type AxiosResponse } from 'axios'
import { describeError, toApiError } from './errors'
import { notifyError } from './notify'
import { clearToken, getToken } from './token'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 调用方自己渲染行内错误，不要再弹 toast */
    silent?: boolean
    /** 401 时不要触发"清 token + 跳登录"（登录/注册接口自身） */
    skipAuthRedirect?: boolean
  }
}

/** 契约 §4：VITE_API_BASE 为空时走同源（生产由 FastAPI 托管 dist）。 */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/+$/, '')
export const V1 = '/api/v1'

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export function authHeader(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

let unauthorizedHandler: (() => void) | null = null

/** main.ts 注入：清 token + 跳 /login（§7.1）。 */
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn
}

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE || undefined,
  timeout: 30000,
  headers: { Accept: 'application/json' },
})

http.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.set?.('Authorization', `Bearer ${token}`)
  return config
})

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: unknown) => {
    const api = toApiError(error)
    const config = axios.isAxiosError(error) ? (error as AxiosError).config : undefined

    if (api.isAuthError && !config?.skipAuthRedirect) {
      clearToken()
      unauthorizedHandler?.()
    }

    if (!config?.silent) {
      const described = describeError(api)
      notifyError({ code: described.code, message: described.message, status: api.status })
    }

    return Promise.reject(api)
  },
)

/** 统一取 data，调用方拿到的是契约里的响应体本身。 */
export async function unwrap<T>(request: Promise<AxiosResponse<T>>): Promise<T> {
  const response = await request
  return response.data
}
