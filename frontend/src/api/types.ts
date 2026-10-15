/**
 * 契约 §4 的 TypeScript 映射。字段一律以 docs/CONTRACT.md 为准，不得自行发明。
 */

export type UserRole = 'user' | 'admin'
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type SourceType = 'upload' | 'paste' | 'seed'
export type RetrievalMode = 'vector' | 'keyword' | 'hybrid'
export type MessageRole = 'user' | 'assistant'

export interface User {
  id: number
  email: string
  display_name: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface AuthResult {
  user: User
  access_token: string
  token_type: 'bearer'
}

export interface MeResponse {
  user: User
}

export interface Health {
  status: string
  version: string
  db: 'ok' | 'error'
  llm_provider: 'echo' | 'openai'
}

export interface RateLimits {
  max_upload_mb: number
  max_documents: number
  max_conversations: number
}

export interface AppMeta {
  app_name: string
  version: string
  registration_open: boolean
  limits: RateLimits
}

export interface DocumentItem {
  id: number
  title: string
  source_type: SourceType
  filename: string | null
  mime_type: string | null
  size_bytes: number
  status: DocumentStatus
  error_message: string | null
  chunk_count: number
  char_count: number
  meta: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface DocumentStats {
  total: number
  ready: number
  processing: number
  failed: number
  chunk_total: number
  char_total: number
  by_status: Array<{ status: DocumentStatus; count: number }>
}

export interface DocumentChunk {
  id: number
  ord: number
  heading: string | null
  content: string
  token_estimate: number
  has_embedding: boolean
}

export interface Citation {
  chunk_id: number
  document_id: number
  document_title: string
  ord: number
  heading: string | null
  snippet: string
  score: number
  retrieval: RetrievalMode
  rank: number
}

export interface Message {
  id: number
  conversation_id: number
  role: MessageRole
  content: string
  citations: Citation[]
  latency_ms: number | null
  created_at: string
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count?: number
  last_message_at?: string | null
  messages?: Message[]
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AskRequest {
  content: string
  top_k?: number
  retrieval_mode?: RetrievalMode
  document_ids?: number[]
}

export interface AskResponse {
  user_message: Message
  assistant_message: Message
}

/* ------------------------------- SSE 事件 ------------------------------- */

export interface SseMetaPayload {
  conversation_id: number
  user_message_id: number
  assistant_message_id: number
  retrieval_mode: RetrievalMode
  top_k: number
}

export interface SseRetrievalPayload {
  chunks: Citation[]
  elapsed_ms: number
}

export interface SseDeltaPayload {
  text: string
}

export interface SseDonePayload {
  assistant_message_id: number
  finish_reason: string
  latency_ms: number
  usage: { prompt_chars: number; completion_chars: number }
}

export interface SseErrorPayload {
  code: string
  message: string
}

/* -------------------------------- 评测 -------------------------------- */

export interface EvalDataset {
  id: number
  name: string
  description: string
  is_seed: boolean
  created_at: string
  item_count?: number
}

export interface EvalItem {
  id: number
  dataset_id: number
  question: string
  gold_chunk_ids: number[]
  gold_document_titles: string[]
  tags: string[]
  created_at: string
}

export interface EvalMetrics {
  recall_at_1: number
  recall_at_3: number
  recall_at_5: number
  recall_at_10: number
  mrr: number
  hit_rate: number
  avg_latency_ms: number
  item_count: number
}

export interface EvalRunSummary {
  run_id: number
  mode: RetrievalMode
  metrics: EvalMetrics
  item_count: number
  duration_ms: number
  created_at: string
}

export interface EvalRunResult {
  run_id: number
  mode: RetrievalMode
  metrics: EvalMetrics
}

export interface EvalRunResponse {
  runs: EvalRunResult[]
}

export interface EvalCompareItem {
  item_id: number
  question: string
  per_run: Array<{ run_id: number; rank: number | null; hit: boolean }>
}

export interface EvalCompareResponse {
  runs: EvalRunSummary[]
  items: EvalCompareItem[]
}

/* -------------------------------- 管理 -------------------------------- */

export interface AdminStats {
  users: number
  documents: number
  chunks: number
  conversations: number
  messages: number
  eval_runs: number
  recent_7d: { documents: number; messages: number }
}

export interface AppSettings {
  retrieval_mode: RetrievalMode
  top_k: number
  chunk_size: number
  chunk_overlap: number
  registration_open: boolean
}

export interface SettingsResponse {
  settings: Record<string, unknown>
}
