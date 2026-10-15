import { http, unwrap, V1 } from './client'
import { cleanParams, normalizePaged, pickEntity } from './normalize'
import type { DocumentChunk, DocumentItem, DocumentStats, DocumentStatus, Paginated } from './types'

export type DocumentSort = 'created_at' | '-created_at' | 'title'

export interface DocumentListQuery {
  page?: number
  page_size?: number
  q?: string
  status?: DocumentStatus | ''
  sort?: DocumentSort
}

export interface ChunkListQuery {
  page?: number
  page_size?: number
}

export interface CreateDocumentInput {
  file?: File | null
  title?: string
  rawText?: string
}

export const documentsApi = {
  /** GET /api/v1/documents */
  async list(query: DocumentListQuery = {}): Promise<Paginated<DocumentItem>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/documents`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<DocumentItem>(raw, 'documents')
  },

  /** GET /api/v1/documents/stats —— 注意必须排在 /{id} 之前调用（路径更具体） */
  async stats(): Promise<DocumentStats> {
    const raw = await unwrap<DocumentStats>(http.get(`${V1}/documents/stats`, { silent: true }))
    return pickEntity<DocumentStats>(raw, 'stats')
  },

  /** GET /api/v1/documents/{id} */
  async get(id: number): Promise<DocumentItem> {
    const raw = await unwrap<unknown>(http.get(`${V1}/documents/${id}`, { silent: true }))
    return pickEntity<DocumentItem>(raw, 'document')
  },

  /** GET /api/v1/documents/{id}/chunks */
  async chunks(id: number, query: ChunkListQuery = {}): Promise<Paginated<DocumentChunk>> {
    const raw = await unwrap<unknown>(
      http.get(`${V1}/documents/${id}/chunks`, { params: cleanParams({ ...query }), silent: true }),
    )
    return normalizePaged<DocumentChunk>(raw, 'chunks')
  },

  /**
   * POST /api/v1/documents（multipart）
   * 契约：`file` 必填 或 `title`+`raw_text` 二选一。响应 201 `{document}`，status=pending。
   */
  async create(input: CreateDocumentInput, onProgress?: (percent: number) => void): Promise<DocumentItem> {
    const form = new FormData()
    if (input.file) form.append('file', input.file)
    if (input.title) form.append('title', input.title)
    if (input.rawText) form.append('raw_text', input.rawText)
    const raw = await unwrap<unknown>(
      http.post(`${V1}/documents`, form, {
        timeout: 120000,
        onUploadProgress: (event) => {
          if (!onProgress) return
          const total = event.total ?? 0
          if (total > 0) onProgress(Math.round((event.loaded / total) * 100))
        },
      }),
    )
    return pickEntity<DocumentItem>(raw, 'document')
  },

  /** PATCH /api/v1/documents/{id} */
  async rename(id: number, title: string): Promise<DocumentItem> {
    const raw = await unwrap<unknown>(http.patch(`${V1}/documents/${id}`, { title }))
    return pickEntity<DocumentItem>(raw, 'document')
  },

  /** DELETE /api/v1/documents/{id} → 204 */
  async remove(id: number): Promise<void> {
    await http.delete(`${V1}/documents/${id}`)
  },

  /** POST /api/v1/documents/{id}/reprocess → 202 */
  async reprocess(id: number): Promise<void> {
    await http.post(`${V1}/documents/${id}/reprocess`)
  },
}
