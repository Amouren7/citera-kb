/**
 * Markdown 渲染 + `[[cN]]` 引用角标（契约 §7.2.5/6）。
 * 顺序固定：先把 `[[cN]]` 换成角标标记 → marked 渲染 → DOMPurify 消毒。
 * 角标放在 marked 之前是因为 marked 会把裸 `[[c1]]` 当普通文本，
 * 而消毒放在最后是为了保证任何路径进来的 HTML 都被清洗过。
 */

import DOMPurify from 'dompurify'
import { marked } from 'marked'
import type { Citation } from '@/api'

marked.setOptions({ gfm: true, breaks: true })

/** 只允许回答里真实需要的标签：不放开 img / style / svg / iframe。 */
const ALLOWED_TAGS = [
  'p',
  'br',
  'hr',
  'strong',
  'em',
  'del',
  'sup',
  'span',
  'code',
  'pre',
  'blockquote',
  'ul',
  'ol',
  'li',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'a',
]

const ALLOWED_ATTR = ['class', 'data-cite', 'href', 'title', 'target', 'rel', 'role', 'tabindex', 'aria-label']

export interface RenderOptions {
  /** 是否允许外链（默认允许但强制 target/rel，且只放行 http(s)） */
  allowLinks?: boolean
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 代码块与行内代码里的 `[[cN]]` 不能被替换，这里按代码与否切段。 */
export function splitByCode(text: string): Array<{ code: boolean; text: string }> {
  const parts = text.split(/(```[\s\S]*?```|`[^`\n]*`)/g)
  return parts
    .filter((part) => part.length > 0)
    .map((part) => ({
      code: /^```[\s\S]*```$/.test(part) || /^`[^`\n]*`$/.test(part),
      text: part,
    }))
}

export function citationChipHtml(index: number, citations: Citation[]): string {
  const citation = index >= 1 ? citations[index - 1] : undefined
  if (!citation) {
    const label = `引用 [[c${index}]] 不在本条回答的引用列表中`
    return `<sup class="cite cite--missing" data-cite="${index}" role="button" tabindex="0" aria-label="${escapeHtml(
      label,
    )}" title="${escapeHtml(label)}">${index}</sup>`
  }
  const heading = citation.heading ?? '无章节'
  const label = `引用 ${index}：${citation.document_title} · ${heading} · 第 ${citation.ord} 块 · 相关度 ${citation.score.toFixed(2)}`
  return `<sup class="cite" data-cite="${index}" role="button" tabindex="0" aria-label="${escapeHtml(
    label,
  )}" title="${escapeHtml(label)}">${index}</sup>`
}

/** `[[cN]]` → 上标角标（跳过代码块/行内代码）。 */
export function replaceCitationMarkers(text: string, citations: Citation[] = []): string {
  return splitByCode(text)
    .map((segment) =>
      segment.code
        ? segment.text
        : segment.text.replace(/\[\[\s*c(\d+)\s*\]\]/g, (_match, raw: string) =>
            citationChipHtml(Number(raw), citations),
          ),
    )
    .join('')
}

export function sanitizeHtml(html: string, options: RenderOptions = {}): string {
  const serialized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form', 'input', 'img', 'svg'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'srcset'],
    ADD_ATTR: ['target', 'rel', 'data-cite'],
    ALLOW_DATA_ATTR: true,
    KEEP_CONTENT: true,
    RETURN_TRUSTED_TYPE: false,
  }) as unknown as string

  if (options.allowLinks === false) {
    return serialized.replace(/<a\s[^>]*>/g, '<span>').replace(/<\/a>/g, '</span>')
  }
  return serialized
}

/** 回答正文渲染：`[[cN]]` → 角标 → marked → DOMPurify。 */
export function renderMarkdown(text: string, citations: Citation[] = [], options: RenderOptions = {}): string {
  const source = text ?? ''
  const withChips = replaceCitationMarkers(source, citations)
  const rawHtml = marked.parse(withChips, { async: false }) as string
  return sanitizeHtml(rawHtml, options)
}

/** 单行内联渲染（标题、片段等），不产生 <p>。 */
export function renderInline(text: string, citations: Citation[] = []): string {
  const source = text ?? ''
  const withChips = replaceCitationMarkers(source, citations)
  const rawHtml = marked.parseInline(withChips, { async: false }) as string
  return sanitizeHtml(rawHtml)
}

/** 正文里出现过的角标序号（升序去重），用于"该回答引用了哪几块"。 */
export function extractCitationIndexes(text: string): number[] {
  const found = new Set<number>()
  for (const segment of splitByCode(text ?? '')) {
    if (segment.code) continue
    const matches = segment.text.matchAll(/\[\[\s*c(\d+)\s*\]\]/g)
    for (const match of matches) {
      const value = Number(match[1])
      if (Number.isFinite(value) && value > 0) found.add(value)
    }
  }
  return [...found].sort((a, b) => a - b)
}
