import { http, unwrap } from './client'
import { pickEntity } from './normalize'
import type { AppMeta, Health } from './types'

export const metaApi = {
  /** GET /api/health —— 注意不在 /api/v1 前缀下（契约 §4） */
  async health(): Promise<Health> {
    const raw = await unwrap<Health>(http.get('/api/health', { silent: true, timeout: 8000 }))
    return raw
  },

  /** GET /api/v1/meta */
  async meta(): Promise<AppMeta> {
    const raw = await unwrap<AppMeta>(http.get('/api/v1/meta', { silent: true }))
    return pickEntity<AppMeta>(raw, 'meta')
  },
}
