/**
 * 契约 §4 里少数端点只写了"详情/分页"而未给出精确包络（例如 GET /documents/{id}）。
 * 这里做**宽容适配**：两种常见形状（`{document}` / 直接对象、`{items}` / 数组）都能吃下，
 * 避免前端因为包络差异而与后端联调时炸掉。字段名一律不猜，只处理包络层。
 */

import type { Paginated } from './types'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

/** 从 `{document: {...}}` 或 `{...}` 中取出实体。 */
export function pickEntity<T>(raw: unknown, key: string): T {
  if (isRecord(raw) && key in raw && raw[key] !== undefined && raw[key] !== null) {
    return raw[key] as T
  }
  return raw as T
}

/**
 * 归一化分页响应：支持 `{items,total,page,page_size}`、`{<key>:[...]}`、裸数组。
 */
export function normalizePaged<T>(raw: unknown, ...arrayKeys: string[]): Paginated<T> {
  if (Array.isArray(raw)) {
    return { items: raw as T[], total: raw.length, page: 1, page_size: raw.length }
  }
  if (isRecord(raw)) {
    for (const key of [...arrayKeys, 'items']) {
      const value = raw[key]
      if (Array.isArray(value)) {
        const items = value as T[]
        return {
          items,
          total: asNumber(raw.total, items.length),
          page: asNumber(raw.page, 1),
          page_size: asNumber(raw.page_size, items.length),
        }
      }
    }
  }
  return { items: [], total: 0, page: 1, page_size: 0 }
}

/** 去掉 undefined / 空字符串的查询参数，避免 `?q=` 这种无效查询。 */
export function cleanParams(query: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    result[key] = value
  }
  return result
}
