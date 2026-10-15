import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  conversationsApi,
  streamChatMessage,
  toApiError,
  type ApiError,
  type Citation,
  type Conversation,
  type Message,
  type RetrievalMode,
  type SseMetaPayload,
  type SseErrorPayload,
} from '@/api'

export interface ChatOptions {
  topK: number
  retrievalMode: RetrievalMode
  documentIds: number[]
  /** 本地偏好：无 documentIds 时是否启用混合检索（仅透传给后端） */
  useHybrid: boolean
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<Conversation[]>([])
  const conversationsStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const listError = ref<ApiError | null>(null)

  const activeId = ref<number | null>(null)
  const messages = ref<Message[]>([])
  const messagesStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const detailError = ref<ApiError | null>(null)

  const streaming = ref(false)
  const streamText = ref('')
  const streamCitations = ref<Citation[]>([])
  const streamElapsedMs = ref<number | null>(null)
  const streamMeta = ref<SseMetaPayload | null>(null)
  const streamError = ref<SseErrorPayload | null>(null)
  const sendError = ref<ApiError | null>(null)

  const options = ref<ChatOptions>({ topK: 5, retrievalMode: 'hybrid', documentIds: [], useHybrid: true })

  let controller: AbortController | null = null

  const activeConversation = computed(
    () => conversations.value.find((conversation) => conversation.id === activeId.value) ?? null,
  )
  const hasCitations = computed(() => streamCitations.value.length > 0)
  const sortedConversations = computed(() =>
    [...conversations.value].sort(
      (a, b) => Date.parse(b.last_message_at ?? b.updated_at) - Date.parse(a.last_message_at ?? a.updated_at),
    ),
  )

  async function fetchConversations(): Promise<void> {
    conversationsStatus.value = conversations.value.length === 0 ? 'loading' : conversationsStatus.value
    try {
      const page = await conversationsApi.list({ page: 1, page_size: 50 })
      conversations.value = page.items
      conversationsStatus.value = 'ready'
      listError.value = null
    } catch (caught) {
      listError.value = toApiError(caught)
      conversationsStatus.value = 'error'
    }
  }

  async function createConversation(title?: string): Promise<Conversation> {
    const created = await conversationsApi.create(title)
    conversations.value = [created, ...conversations.value.filter((item) => item.id !== created.id)]
    return created
  }

  async function openConversation(id: number): Promise<void> {
    activeId.value = id
    messagesStatus.value = 'loading'
    detailError.value = null
    streamText.value = ''
    streamCitations.value = []
    streamMeta.value = null
    streamError.value = null
    try {
      const conversation = await conversationsApi.get(id)
      messages.value = [...(conversation.messages ?? [])]
      messagesStatus.value = 'ready'
      const index = conversations.value.findIndex((item) => item.id === id)
      if (index >= 0) {
        conversations.value[index] = { ...conversations.value[index], ...conversation }
      } else {
        conversations.value.unshift(conversation)
      }
    } catch (caught) {
      detailError.value = toApiError(caught)
      messagesStatus.value = 'error'
      messages.value = []
    }
  }

  async function renameConversation(id: number, title: string): Promise<boolean> {
    try {
      const updated = await conversationsApi.rename(id, title)
      const index = conversations.value.findIndex((item) => item.id === id)
      if (index >= 0) conversations.value[index] = { ...conversations.value[index], ...updated }
      return true
    } catch (caught) {
      listError.value = toApiError(caught)
      return false
    }
  }

  async function removeConversation(id: number): Promise<boolean> {
    try {
      await conversationsApi.remove(id)
      conversations.value = conversations.value.filter((item) => item.id !== id)
      if (activeId.value === id) {
        activeId.value = null
        messages.value = []
        messagesStatus.value = 'idle'
      }
      return true
    } catch (caught) {
      listError.value = toApiError(caught)
      return false
    }
  }

  function startNewConversation(): void {
    activeId.value = null
    messages.value = []
    messagesStatus.value = 'idle'
    streamText.value = ''
    streamCitations.value = []
    streamMeta.value = null
    streamError.value = null
    detailError.value = null
  }

  /**
   * 发送提问（契约 §7.2 + §4.2 流式）：
   * 无会话则先建会话 → 乐观插入用户消息 → fetch+ReadableStream 流式 → done 后落库到本地列表。
   */
  async function send(content: string): Promise<void> {
    const text = content.trim()
    if (!text || streaming.value) return

    sendError.value = null
    let conversationId = activeId.value
    try {
      if (!conversationId) {
        const created = await createConversation()
        conversationId = created.id
        activeId.value = created.id
      }
    } catch (caught) {
      sendError.value = toApiError(caught)
      return
    }

    streamText.value = ''
    streamCitations.value = []
    streamElapsedMs.value = null
    streamMeta.value = null
    streamError.value = null

    const optimistic: Message = {
      id: -Date.now(),
      conversation_id: conversationId,
      role: 'user',
      content: text,
      citations: [],
      latency_ms: null,
      created_at: new Date().toISOString(),
    }
    messages.value = [...messages.value, optimistic]
    messagesStatus.value = 'ready'
    streaming.value = true
    controller = new AbortController()

    let finalized = false
    const finalize = (payload: {
      id: number
      content: string
      citations: Citation[]
      latencyMs: number | null
    }): void => {
      finalized = true
      messages.value = [
        ...messages.value,
        {
          id: payload.id,
          conversation_id: conversationId as number,
          role: 'assistant',
          content: payload.content,
          citations: payload.citations,
          latency_ms: payload.latencyMs,
          created_at: new Date().toISOString(),
        },
      ]
    }

    try {
      await streamChatMessage(
        conversationId,
        {
          content: text,
          top_k: options.value.topK,
          retrieval_mode: options.value.retrievalMode,
          document_ids: options.value.documentIds.length > 0 ? options.value.documentIds : undefined,
        },
        {
          signal: controller.signal,
          onMeta: (meta) => {
            streamMeta.value = meta
            const index = messages.value.findIndex((message) => message.id === optimistic.id)
            if (index >= 0) {
              messages.value[index] = { ...messages.value[index], id: meta.user_message_id }
            }
          },
          onRetrieval: (payload) => {
            streamCitations.value = payload.chunks
            streamElapsedMs.value = payload.elapsed_ms
          },
          onDelta: (payload) => {
            streamText.value += payload.text
          },
          onDone: (payload) => {
            finalize({
              id: payload.assistant_message_id,
              content: streamText.value,
              citations: streamCitations.value,
              latencyMs: payload.latency_ms,
            })
          },
          onError: (payload) => {
            streamError.value = payload
          },
        },
      )
    } catch (caught) {
      const api = toApiError(caught)
      if (api.code !== 'request_aborted') sendError.value = api
    } finally {
      // 中断或异常但已有部分文本：保留为一条"已中断"的回答
      if (!finalized && streamText.value.length > 0) {
        finalize({
          id: -Date.now(),
          content: streamText.value,
          citations: streamCitations.value,
          latencyMs: null,
        })
      }
      streaming.value = false
      controller = null
      streamText.value = ''
      // 首条消息后标题会变成前 30 字，刷新列表让左侧同步
      void fetchConversations()
    }
  }

  /** "停止生成"（契约 §7.2.2）：中断 fetch 流。 */
  function stop(): void {
    controller?.abort()
  }

  function setOptions(patch: Partial<ChatOptions>): void {
    options.value = { ...options.value, ...patch }
  }

  function $resetAll(): void {
    stop()
    conversations.value = []
    conversationsStatus.value = 'idle'
    listError.value = null
    activeId.value = null
    messages.value = []
    messagesStatus.value = 'idle'
    detailError.value = null
    streamText.value = ''
    streamCitations.value = []
    streamElapsedMs.value = null
    streamMeta.value = null
    streamError.value = null
    sendError.value = null
  }

  return {
    conversations,
    sortedConversations,
    conversationsStatus,
    listError,
    activeId,
    activeConversation,
    messages,
    messagesStatus,
    detailError,
    streaming,
    streamText,
    streamCitations,
    streamElapsedMs,
    streamMeta,
    streamError,
    sendError,
    options,
    hasCitations,
    fetchConversations,
    createConversation,
    openConversation,
    renameConversation,
    removeConversation,
    startNewConversation,
    send,
    stop,
    setOptions,
    $resetAll,
  }
})
