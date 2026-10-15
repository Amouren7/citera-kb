import { describe, expect, it } from 'vitest'
import { cleanParams, normalizePaged, pickEntity } from '@/api/normalize'
import { clearToken, getStoredTheme, getToken, setStoredTheme, setToken, THEME_KEY, TOKEN_KEY } from '@/api/token'
import {
  documentStatusMeta,
  formatBytes,
  formatCount,
  formatMs,
  formatPercent,
  formatRelative,
  plainText,
  sourceTypeLabel,
  truncate,
} from '@/utils/format'

describe('响应包络宽容适配（契约 §4 少数端点未给精确包络）', () => {
  it('pickEntity 支持 {document:{...}} 与裸对象两种形状', () => {
    expect(pickEntity<{ id: number }>({ document: { id: 3 } }, 'document')).toEqual({ id: 3 })
    expect(pickEntity<{ id: number }>({ id: 3 }, 'document')).toEqual({ id: 3 })
  })

  it('normalizePaged 支持 items / 自定义键 / 裸数组三种形状', () => {
    expect(normalizePaged<number>({ items: [1, 2], total: 9, page: 2, page_size: 2 }, 'documents')).toEqual({
      items: [1, 2],
      total: 9,
      page: 2,
      page_size: 2,
    })
    expect(normalizePaged<number>({ documents: [1] }, 'documents').total).toBe(1)
    expect(normalizePaged<number>([1, 2, 3], 'documents').total).toBe(3)
  })

  it('normalizePaged 对无法识别的形状返回空列表而不是崩溃', () => {
    expect(normalizePaged<number>({ oops: true })).toEqual({ items: [], total: 0, page: 1, page_size: 0 })
    expect(normalizePaged<number>(null).items).toEqual([])
  })

  it('cleanParams 去掉 undefined / null / 空字符串，保留 0 与 false', () => {
    expect(cleanParams({ q: '', status: undefined, page: 1, top_k: 0, flag: false, note: null })).toEqual({
      page: 1,
      top_k: 0,
      flag: false,
    })
  })
})

describe('token 存取（契约 §7.1 键名 citera.token）', () => {
  it('setToken / getToken / clearToken 往返一致', () => {
    clearToken()
    expect(getToken()).toBeNull()
    setToken('abc.def')
    expect(getToken()).toBe('abc.def')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('abc.def')
    clearToken()
    expect(getToken()).toBeNull()
  })

  it('主题偏好独立存储，键名 citera.theme', () => {
    setStoredTheme('dark')
    expect(getStoredTheme()).toBe('dark')
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
    setStoredTheme('light')
    expect(getStoredTheme()).toBe('light')
  })
})

describe('展示层格式化', () => {
  it('formatBytes 按 B / KB / MB 分档', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.00 MB')
    expect(formatBytes(null)).toBe('—')
  })

  it('formatPercent 把 0–1 小数转成百分数', () => {
    expect(formatPercent(0.8333)).toBe('83.3%')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatPercent(undefined)).toBe('—')
  })

  it('formatMs 小于 1s 用毫秒，否则用秒', () => {
    expect(formatMs(58)).toBe('58 ms')
    expect(formatMs(1500)).toBe('1.50 s')
  })

  it('formatRelative 输出中文相对时间', () => {
    const now = Date.parse('2026-10-14T12:00:00Z')
    expect(formatRelative(new Date(now - 30_000).toISOString(), now)).toBe('刚刚')
    expect(formatRelative(new Date(now - 5 * 60_000).toISOString(), now)).toBe('5 分钟前')
    expect(formatRelative(new Date(now - 3 * 3600_000).toISOString(), now)).toBe('3 小时前')
    expect(formatRelative(new Date(now - 2 * 86400_000).toISOString(), now)).toBe('2 天前')
    expect(formatRelative(null, now)).toBe('—')
  })

  it('documentStatusMeta 给出中文标签与语义色调', () => {
    expect(documentStatusMeta('ready')).toEqual({ label: '已就绪', tone: 'ok' })
    expect(documentStatusMeta('processing').tone).toBe('warn')
    expect(documentStatusMeta('failed').tone).toBe('err')
  })

  it('sourceTypeLabel / truncate / formatCount 正常', () => {
    expect(sourceTypeLabel('upload')).toBe('上传')
    expect(sourceTypeLabel('paste')).toBe('粘贴')
    expect(sourceTypeLabel('seed')).toBe('种子')
    expect(truncate('abcdefghij', 4)).toBe('abcd…')
    expect(formatCount(12345)).toBe('12,345')
  })

  it('plainText 去掉 Markdown 标记与引用角标，用于标题摘要', () => {
    const text = plainText('### 结论\n\n- **整机**保修 12 个月[[c1]]\n\n| a | b |\n| - | - |')
    expect(text).not.toContain('#')
    expect(text).not.toContain('**')
    expect(text).not.toContain('[[c1]]')
    expect(text).toContain('整机保修 12 个月')
  })
})
