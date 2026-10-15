import { http, unwrap, V1 } from './client'
import { pickEntity } from './normalize'
import type { AuthResult, User } from './types'

export interface RegisterPayload {
  email: string
  password: string
  display_name: string
}

export interface LoginPayload {
  email: string
  password: string
}

/** 契约 §4.2 认证：登录/注册接口自身不触发 401 跳转，错误交给页面行内展示。 */
export const authApi = {
  async login(payload: LoginPayload): Promise<AuthResult> {
    const raw = await unwrap<AuthResult>(http.post(`${V1}/auth/login`, payload, { skipAuthRedirect: true, silent: true }))
    return pickEntity<AuthResult>(raw, 'auth')
  },

  async register(payload: RegisterPayload): Promise<AuthResult> {
    const raw = await unwrap<AuthResult>(
      http.post(`${V1}/auth/register`, payload, { skipAuthRedirect: true, silent: true }),
    )
    return pickEntity<AuthResult>(raw, 'auth')
  },

  async me(): Promise<User> {
    const raw = await unwrap<unknown>(http.get(`${V1}/auth/me`, { silent: true }))
    return pickEntity<User>(raw, 'user')
  },

  async updateMe(payload: { display_name?: string }): Promise<User> {
    const raw = await unwrap<unknown>(http.patch(`${V1}/auth/me`, payload))
    return pickEntity<User>(raw, 'user')
  },
}
