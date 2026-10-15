import { http, unwrap, V1 } from './client'
import { cleanParams, normalizePaged, pickEntity } from './normalize'
import type { AskRequest, AskResponse, Conversation, Paginated } from './types'

export interface ConversationListQuery {
  page?: number
  page_size?: number
}

export const conversationsApi = {
  /** GET /api/v1/conversations */
  async list(query: ConversationListQuery = {}): Promise<Paginated<Conversation>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/conversations`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<Conversation>(raw, 'conversations')
  },

  /** POST /api/v1/conversations → 201 `{conversation}` */
  async create(title?: string): Promise<Conversation> {
    const body = title ? { title } : {}
    const raw = await unwrap<unknown>(http.post(`${V1}/conversations`, body))
    return pickEntity<Conversation>(raw, 'conversation')
  },

  /** GET /api/v1/conversations/{id}（含 messages，按 created_at 升序） */
  async get(id: number): Promise<Conversation> {
    const raw = await unwrap<unknown>(http.get(`${V1}/conversations/${id}`, { silent: true }))
    return pickEntity<Conversation>(raw, 'conversation')
  },

  /** PATCH /api/v1/conversations/{id} */
  async rename(id: number, title: string): Promise<Conversation> {
    const raw = await unwrap<unknown>(http.patch(`${V1}/conversations/${id}`, { title }))
    return pickEntity<Conversation>(raw, 'conversation')
  },

  /** DELETE /api/v1/conversations/{id} → 204 */
  async remove(id: number): Promise<void> {
    await http.delete(`${V1}/conversations/${id}`)
  },

  /** POST /api/v1/conversations/{id}/messages（非流式，stream=false） */
  async ask(id: number, body: AskRequest): Promise<AskResponse> {
    const raw = await unwrap<unknown>(
      http.post(`${V1}/conversations/${id}/messages`, { ...body, stream: false }, { timeout: 120000, silent: true }),
    )
    return raw as AskResponse
  },
}
