/**
 * 前端唯一出入层（契约 §1）。
 * 页面/store 只允许从这里 import，不得直接使用 axios 或 fetch。
 */

export { API_BASE, apiUrl, authHeader, http, setUnauthorizedHandler, unwrap, V1 } from './client'
export {
  ApiError,
  CODE_FALLBACK_MESSAGE,
  codeFromStatus,
  describeError,
  ERROR_CODES,
  errorMessage,
  isApiError,
  parseErrorEnvelope,
  toApiError,
} from './errors'
export type { ApiErrorCode, ApiErrorPayload } from './errors'
export { setErrorNotifier, notifyError } from './notify'
export type { ErrorNotice, ErrorNotifier } from './notify'
export { clearToken, getStoredTheme, getToken, setStoredTheme, setToken, THEME_KEY, TOKEN_KEY } from './token'
export { cleanParams, normalizePaged, pickEntity } from './normalize'

export { authApi } from './auth'
export type { LoginPayload, RegisterPayload } from './auth'
export { documentsApi } from './documents'
export type { ChunkListQuery, CreateDocumentInput, DocumentListQuery, DocumentSort } from './documents'
export { conversationsApi } from './conversations'
export type { ConversationListQuery } from './conversations'
export { evaluationsApi } from './evaluations'
export type { RunEvaluationInput } from './evaluations'
export { adminApi } from './admin'
export { metaApi } from './meta'

export { dispatchFrame, isAbortError, SseParser, streamChatMessage } from './sse'
export type { SseFrame, SseHandlers, StreamChatOptions } from './sse'

export type * from './types'
