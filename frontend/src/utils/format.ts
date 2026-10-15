/** 展示层格式化。全部纯函数，便于单测。 */

import type { DocumentStatus } from '@/api'

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function formatDate(iso: string | null | undefined): string {
  const full = formatDateTime(iso)
  return full === '—' ? full : full.slice(0, 10)
}

export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—'
  const time = new Date(iso).getTime()
  if (Number.isNaN(time)) return '—'
  const diff = now - time
  if (diff < 0) return formatDate(iso)
  const minute = 60_000
  if (diff < minute) return '刚刚'
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < 24 * 60 * minute) return `${Math.floor(diff / (60 * minute))} 小时前`
  if (diff < 30 * 24 * 60 * minute) return `${Math.floor(diff / (24 * 60 * minute))} 天前`
  return formatDate(iso)
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('zh-CN')
}

/** 0–1 的小数 → 百分数，保留一位（契约 §4 metrics 全是 0–1 小数）。 */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(2)} s`
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(2)
}

export interface StatusMeta {
  label: string
  tone: 'ok' | 'warn' | 'err' | 'neutral'
}

export function documentStatusMeta(status: DocumentStatus | string): StatusMeta {
  switch (status) {
    case 'ready':
      return { label: '已就绪', tone: 'ok' }
    case 'processing':
      return { label: '处理中', tone: 'warn' }
    case 'pending':
      return { label: '排队中', tone: 'warn' }
    case 'failed':
      return { label: '失败', tone: 'err' }
    default:
      return { label: status || '未知', tone: 'neutral' }
  }
}

export function sourceTypeLabel(sourceType: string): string {
  switch (sourceType) {
    case 'upload':
      return '上传'
    case 'paste':
      return '粘贴'
    case 'seed':
      return '种子'
    default:
      return sourceType
  }
}

export function truncate(text: string, max = 80): string {
  if (!text) return ''
  return text.length <= max ? text : `${text.slice(0, max)}…`
}

/** 去掉 Markdown 标记，用于标题、摘要等纯文本位置。 */
export function plainText(markdown: string): string {
  return markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}>\s?/gm, '')
    .replace(/\*\*([^*]*)\*\*/g, '$1')
    .replace(/\*([^*]*)\*/g, '$1')
    .replace(/\[\[c\d+\]\]/g, '')
    .replace(/\|/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
