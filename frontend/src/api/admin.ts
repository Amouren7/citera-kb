import { http, unwrap, V1 } from './client'
import { cleanParams, normalizePaged, pickEntity } from './normalize'
import type { AdminStats, Paginated, User, UserRole } from './types'

export const adminApi = {
  /** GET /api/v1/admin/stats */
  async stats(): Promise<AdminStats> {
    const raw = await unwrap<AdminStats>(http.get(`${V1}/admin/stats`, { silent: true }))
    return pickEntity<AdminStats>(raw, 'stats')
  },

  /** GET /api/v1/admin/users */
  async users(query: { page?: number; page_size?: number; q?: string } = {}): Promise<Paginated<User>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/admin/users`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<User>(raw, 'users')
  },

  /** PATCH /api/v1/admin/users/{id} */
  async updateUser(id: number, payload: { is_active?: boolean; role?: UserRole }): Promise<User> {
    const raw = await unwrap<unknown>(http.patch(`${V1}/admin/users/${id}`, payload))
    return pickEntity<User>(raw, 'user')
  },

  /** GET /api/v1/admin/settings → `{settings:{key:value}}` */
  async settings(): Promise<Record<string, unknown>> {
    const raw = await unwrap<unknown>(http.get(`${V1}/admin/settings`, { silent: true }))
    return pickEntity<Record<string, unknown>>(raw, 'settings')
  },

  /** PUT /api/v1/admin/settings（只接受白名单键） */
  async saveSettings(settings: Record<string, unknown>): Promise<Record<string, unknown>> {
    const raw = await unwrap<unknown>(http.put(`${V1}/admin/settings`, { settings }))
    return pickEntity<Record<string, unknown>>(raw, 'settings')
  },

  /** POST /api/v1/admin/reseed（幂等） */
  async reseed(): Promise<void> {
    await http.post(`${V1}/admin/reseed`, {}, { timeout: 120000 })
  },
}
