/**
 * mock 的检索/回答引擎。
 * 目标不是复刻后端算法，而是让前端的每一处渲染都有**可信的真实数据形状**：
 *  - 混合检索按契约 §5.1 的 RRF 融合（k=60）实现，`retrieval` 记首次召回通道、`rank` 记融合名次
 *  - echo 模式的受控合成按契约 §5.3 生成，含固定说明行与逐句 `[[cN]]` 标注
 */

import type { Citation, RetrievalMode } from '../src/api/types.ts'
import type { MockChunk, MockStore } from './state.ts'

const RRF_K = 60

/** 中文按字符 unigram + bigram，英文/数字按词切。 */
export function tokenize(text: string): string[] {
  const lower = text.toLowerCase()
  const tokens = new Set<string>()
  const words = lower.match(/[a-z0-9]+/g) ?? []
  for (const word of words) tokens.add(word)
  const cjk = lower.replace(/[^\u4e00-\u9fa5]/g, '')
  for (let i = 0; i < cjk.length; i += 1) {
    tokens.add(cjk[i] as string)
    if (i + 1 < cjk.length) tokens.add(cjk.slice(i, i + 2))
  }
  return [...tokens]
}

/** 确定性伪随机：同一输入永远同一结果，便于复现与截图比对。 */
function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

function jitter(seed: number): number {
  return ((seed % 997) / 997) * 0.06
}

interface Scored {
  chunk: MockChunk
  score: number
}

function bigrams(tokens: string[]): string[] {
  return tokens.filter((token) => token.length === 2)
}

/** 关键词通道：命中 bigram/词的比例（模拟 ts_rank_cd + pg_trgm 兜底）。 */
function keywordScores(chunks: MockChunk[], tokens: string[]): Scored[] {
  const grams = bigrams(tokens)
  const singles = tokens.filter((token) => token.length === 1)
  return chunks
    .map((chunk) => {
      const content = chunk.content.toLowerCase()
      const gramHits = grams.filter((gram) => content.includes(gram)).length
      const singleHits = singles.filter((token) => content.includes(token)).length
      const norm = grams.length || 1
      const exact = gramHits / norm
      const loose = singles.length ? singleHits / singles.length / 6 : 0
      return { chunk, score: exact * 0.92 + loose }
    })
    .filter((item) => item.score > 0.005)
}

/** 向量通道：字面重合度打底 + 确定性微扰（模拟语义召回比字面更"模糊"）。 */
function vectorScores(chunks: MockChunk[], tokens: string[]): Scored[] {
  return chunks.map((chunk) => {
    const content = chunk.content.toLowerCase()
    const hits = tokens.filter((token) => content.includes(token)).length
    const base = hits / Math.max(tokens.length, 1)
    const noise = jitter(hash(`${chunk.id}:${tokens.join('')}`))
    return { chunk, score: base * 0.85 + noise }
  })
}

function rankOf(list: Scored[]): Map<number, number> {
  const map = new Map<number, number>()
  list.forEach((item, index) => map.set(item.chunk.id, index + 1))
  return map
}

function takeTop(list: Scored[], size: number): Scored[] {
  return [...list].sort((a, b) => b.score - a.score || a.chunk.id - b.chunk.id).slice(0, size)
}

export interface RetrievalResult {
  citations: Citation[]
  chunks: MockChunk[]
  elapsed_ms: number
}

/**
 * 契约 §5.1：每路各取 top_k*4 候选 → RRF 融合 → 取 top_k。
 * `retrieval` = 首次召回的通道；`rank` = 融合后名次。
 * 单通道模式直接用该通道的名次与分数。
 */
export function retrieve(
  store: MockStore,
  query: string,
  mode: RetrievalMode,
  topK: number,
  documentIds?: number[],
): RetrievalResult {
  const scope = store.chunks.filter(
    (chunk) => !documentIds || documentIds.length === 0 || documentIds.includes(chunk.document_id),
  )
  const tokens = tokenize(query)
  const candidateLimit = Math.max(topK * 4, topK)

  const vectorList = takeTop(vectorScores(scope, tokens), candidateLimit)
  const keywordList = takeTop(keywordScores(scope, tokens), candidateLimit)
  const vectorRanks = rankOf(vectorList)
  const keywordRanks = rankOf(keywordList)

  const docTitle = (chunk: MockChunk) =>
    store.documents.find((doc) => doc.id === chunk.document_id)?.title ?? '未知文档'

  const toCitation = (chunk: MockChunk, score: number, retrieval: RetrievalMode, rank: number): Citation => ({
    chunk_id: chunk.id,
    document_id: chunk.document_id,
    document_title: docTitle(chunk),
    ord: chunk.ord,
    heading: chunk.heading,
    snippet: chunk.content.slice(0, 160),
    score: Math.round(Math.min(0.99, Math.max(0.05, score)) * 100) / 100,
    retrieval,
    rank,
  })

  if (mode === 'vector' || mode === 'keyword') {
    const list = mode === 'vector' ? vectorList : keywordList
    const top = takeTop(list, topK)
    return {
      citations: top.map((item, index) => toCitation(item.chunk, normalize(item.score, list), mode, index + 1)),
      chunks: top.map((item) => item.chunk),
      elapsed_ms: mode === 'vector' ? 38 + (hash(query) % 12) : 9 + (hash(query) % 6),
    }
  }

  // 混合：RRF 融合
  const fused = new Map<number, { chunk: MockChunk; score: number; first: RetrievalMode }>()
  for (const item of vectorList) {
    const rank = vectorRanks.get(item.chunk.id) as number
    fused.set(item.chunk.id, { chunk: item.chunk, score: 1 / (RRF_K + rank), first: 'vector' })
  }
  for (const item of keywordList) {
    const rank = keywordRanks.get(item.chunk.id) as number
    const existing = fused.get(item.chunk.id)
    if (existing) existing.score += 1 / (RRF_K + rank)
    else fused.set(item.chunk.id, { chunk: item.chunk, score: 1 / (RRF_K + rank), first: 'keyword' })
  }

  const ordered = [...fused.values()].sort((a, b) => b.score - a.score || a.chunk.id - b.chunk.id).slice(0, topK)
  const maxScore = ordered[0]?.score || 1
  return {
    citations: ordered.map((entry, index) =>
      toCitation(entry.chunk, 0.62 + (entry.score / maxScore) * 0.36, entry.first, index + 1),
    ),
    chunks: ordered.map((entry) => entry.chunk),
    elapsed_ms: 47 + (hash(query) % 20),
  }
}

function normalize(score: number, list: Scored[]): number {
  const max = list[0]?.score ?? 1
  const min = list[list.length - 1]?.score ?? 0
  if (max === min) return 0.72
  return 0.42 + ((score - min) / (max - min)) * 0.5
}

const DISCLAIMER = '（演示模式：未配置模型，以下内容由检索结果受控合成，非模型生成）'

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[。！？；])/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 4)
}

/**
 * 契约 §5.3 echo 模式：从检索块中挑与问题重合度最高的句子，
 * 按块顺序组织，每句句尾挂 `[[cN]]`；资料不足时明确说不知道。
 */
export function synthesizeAnswer(question: string, citations: Citation[], chunks: MockChunk[]): string {
  if (citations.length === 0) {
    return `${DISCLAIMER}\n\n### 结论\n\n- 现有资料不足以回答这个问题，未检索到相关片段。请先上传相关文档，或换一种问法。`
  }

  const tokens = tokenize(question)
  const bullets: string[] = []
  const used = new Set<string>()

  chunks.forEach((chunk, index) => {
    const ref = index + 1
    for (const sentence of splitSentences(chunk.content)) {
      if (bullets.length >= 4) break
      const hits = tokens.filter((token) => sentence.toLowerCase().includes(token)).length
      if (hits < 2 || used.has(sentence)) continue
      used.add(sentence)
      bullets.push(`- ${sentence} [[c${ref}]]`)
    }
  })

  if (bullets.length === 0) {
    const first = chunks[0] as MockChunk
    bullets.push(`- ${splitSentences(first.content)[0] ?? first.content.slice(0, 80)} [[c1]]`)
  }

  const top = citations[0] as Citation
  const table = citations
    .slice(0, 5)
    .map(
      (citation) =>
        `| ${citation.rank} | ${citation.document_title} | ${citation.heading ?? '（无标题）'} | 块 ${citation.ord} | ${citation.score.toFixed(2)} |`,
    )
    .join('\n')

  return [
    DISCLAIMER,
    '',
    '### 结论',
    '',
    ...bullets,
    '',
    '**依据片段**',
    '',
    `> ${top.snippet}`,
    '',
    '| 名次 | 文档 | 章节 | 片段 | 相关度 |',
    '| --- | --- | --- | --- | --- |',
    table,
    '',
    `共命中 ${citations.length} 个片段，检索通道 ${top.retrieval}，融合名次 ${top.rank}。`,
  ].join('\n')
}
