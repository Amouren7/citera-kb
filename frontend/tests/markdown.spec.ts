import { describe, expect, it } from 'vitest'
import type { Citation } from '@/api'
import {
  extractCitationIndexes,
  renderInline,
  renderMarkdown,
  replaceCitationMarkers,
  sanitizeHtml,
  splitByCode,
} from '@/utils/markdown'

const citations: Citation[] = [
  {
    chunk_id: 7,
    document_id: 2,
    document_title: '产品保修条款',
    ord: 3,
    heading: '三、保修期限',
    snippet: '整机保修期为自签收之日起 12 个月。',
    score: 0.83,
    retrieval: 'hybrid',
    rank: 1,
  },
  {
    chunk_id: 6,
    document_id: 2,
    document_title: '产品保修条款',
    ord: 2,
    heading: '二、保修凭证',
    snippet: '需提供订单编号或电子发票。',
    score: 0.71,
    retrieval: 'keyword',
    rank: 2,
  },
]

describe('[[cN]] 引用角标（契约 §7.2.5）', () => {
  it('把 [[c1]] 换成带上标类与 data-cite 的角标', () => {
    const html = replaceCitationMarkers('整机保修 12 个月。[[c1]]', citations)
    expect(html).toContain('class="cite"')
    expect(html).toContain('data-cite="1"')
    expect(html).toContain('aria-label="引用 1：产品保修条款 · 三、保修期限 · 第 3 块 · 相关度 0.83"')
  })

  it('容忍 [[c 1 ]] 里的空格', () => {
    expect(replaceCitationMarkers('答案[[ c2 ]]', citations)).toContain('data-cite="2"')
  })

  it('超出 citations 长度的角标降级为 cite--missing 而不是消失', () => {
    const html = replaceCitationMarkers('答案[[c9]]', citations)
    expect(html).toContain('cite--missing')
    expect(html).toContain('不在本条回答的引用列表中')
  })

  it('代码块与行内代码里的 [[c1]] 不被替换', () => {
    const fenced = '说明：\n\n```\n[[c1]]\n```\n\n正文[[c1]]'
    const html = replaceCitationMarkers(fenced, citations)
    expect(html.match(/data-cite="1"/g)).toHaveLength(1)
    expect(html).toContain('```')
    expect(replaceCitationMarkers('`[[c1]]` 与 [[c1]]', citations).match(/data-cite/g)).toHaveLength(1)
  })

  it('renderMarkdown 同时产出角标与正常 Markdown 结构', () => {
    const html = renderMarkdown('### 结论\n\n- 整机保修 12 个月[[c1]]\n', citations)
    expect(html).toContain('<h3')
    expect(html).toContain('<ul>')
    expect(html).toContain('data-cite="1"')
  })

  it('extractCitationIndexes 去重升序，且跳过代码块', () => {
    expect(extractCitationIndexes('a[[c2]]b[[c1]]c[[c2]]\n```\n[[c7]]\n```')).toEqual([1, 2])
  })

  it('renderInline 不产生段落标签', () => {
    const html = renderInline('**保修** 12 个月[[c1]]', citations)
    expect(html).not.toContain('<p>')
    expect(html).toContain('<strong>')
  })

  it('splitByCode 正确切分围栏与行内代码', () => {
    const segments = splitByCode('a `b` c\n```\nd\n```\ne')
    expect(segments.filter((segment) => segment.code)).toHaveLength(2)
  })
})

describe('DOMPurify 消毒（契约 §7.2.6）', () => {
  it('剔除 script / iframe / img / 内联事件与 style', () => {
    const dirty =
      '<p onclick="alert(1)" style="color:red">ok</p><script>alert(1)</script><iframe src="x"></iframe><img src=x onerror="alert(1)">'
    const clean = sanitizeHtml(dirty)
    expect(clean).not.toContain('<script')
    expect(clean).not.toContain('<iframe')
    expect(clean).not.toContain('<img')
    expect(clean).not.toContain('onclick')
    expect(clean).not.toContain('style=')
    expect(clean).toContain('ok')
  })

  it('保留表格、代码块与角标属性', () => {
    const clean = sanitizeHtml('<table><tr><td>a</td></tr></table><pre><code>x</code></pre><sup class="cite" data-cite="1" role="button" tabindex="0">1</sup>')
    expect(clean).toContain('<table>')
    expect(clean).toContain('<pre>')
    expect(clean).toContain('data-cite="1"')
  })

  it('renderMarkdown 走完整个链路后恶意 HTML 仍被清除', () => {
    const html = renderMarkdown('正常文本[[c1]]\n\n<script>steal()</script>\n\n<a href="javascript:alert(1)">x</a>', citations)
    expect(html).not.toContain('<script')
    expect(html).not.toContain('javascript:')
    expect(html).toContain('data-cite="1"')
  })
})
