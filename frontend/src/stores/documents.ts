import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  documentsApi,
  toApiError,
  type ApiError,
  type DocumentChunk,
  type DocumentItem,
  type DocumentStats,
  type DocumentStatus,
  type Paginated,
} from '@/api'
import type { DocumentSort } from '@/api'

export interface DocumentQuery {
  q: string
  status: DocumentStatus | ''
  sort: DocumentSort
  page: number
  pageSize: number
}

const POLL_INTERVAL = 2500
const POLL_LIMIT = 60

export const useDocumentsStore = defineStore('documents', () => {
  const items = ref<DocumentItem[]>([])
  const total = ref(0)
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const error = ref<ApiError | null>(null)

  const stats = ref<DocumentStats | null>(null)
  const statsError = ref<ApiError | null>(null)

  const query = ref<DocumentQuery>({ q: '', status: '', sort: '-created_at', page: 1, pageSize: 10 })

  const uploading = ref(false)
  const uploadProgress = ref(0)
  const uploadError = ref<ApiError | null>(null)
  const lastUploaded = ref<DocumentItem | null>(null)

  const detail = ref<DocumentItem | null>(null)
  const detailStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const detailError = ref<ApiError | null>(null)

  const chunks = ref<DocumentChunk[]>([])
  const chunkTotal = ref(0)
  const chunkPage = ref(1)
  const chunkPageSize = ref(10)
  const chunkStatus = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const chunkError = ref<ApiError | null>(null)
  const chunkFocusOrd = ref<number | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let pollTicks = 0

  const hasUnsettled = computed(() =>
    items.value.some((item) => item.status === 'pending' || item.status === 'processing'),
  )
  const isEmpty = computed(() => status.value === 'ready' && items.value.length === 0)
  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / query.value.pageSize)))

  async function fetchList(): Promise<void> {
    status.value = items.value.length === 0 ? 'loading' : status.value
    try {
      const page: Paginated<DocumentItem> = await documentsApi.list({
        page: query.value.page,
        page_size: query.value.pageSize,
        q: query.value.q,
        status: query.value.status,
        sort: query.value.sort,
      })
      items.value = page.items
      total.value = page.total
      status.value = 'ready'
      error.value = null
    } catch (caught) {
      error.value = toApiError(caught)
      status.value = 'error'
    }
  }

  async function fetchStats(): Promise<void> {
    try {
      stats.value = await documentsApi.stats()
      statsError.value = null
    } catch (caught) {
      statsError.value = toApiError(caught)
    }
  }

  async function refresh(): Promise<void> {
    await Promise.all([fetchList(), fetchStats()])
    syncPolling()
  }

  function setQuery(patch: Partial<DocumentQuery>): void {
    const next = { ...query.value, ...patch }
    if (patch.q !== undefined || patch.status !== undefined || patch.sort !== undefined) {
      next.page = 1
    }
    query.value = next
  }

  function resetQuery(): void {
    query.value = { q: '', status: '', sort: '-created_at', page: 1, pageSize: 10 }
  }

  async function upload(input: {
    file?: File | null
    title?: string
    rawText?: string
  }): Promise<DocumentItem | null> {
    uploading.value = true
    uploadProgress.value = 0
    uploadError.value = null
    try {
      const created = await documentsApi.create(input, (percent) => {
        uploadProgress.value = percent
      })
      lastUploaded.value = created
      await refresh()
      startPolling()
      return created
    } catch (caught) {
      uploadError.value = toApiError(caught)
      return null
    } finally {
      uploading.value = false
      uploadProgress.value = 0
    }
  }

  async function rename(id: number, title: string): Promise<boolean> {
    try {
      const updated = await documentsApi.rename(id, title)
      const index = items.value.findIndex((item) => item.id === id)
      if (index >= 0) items.value[index] = updated
      if (detail.value?.id === id) detail.value = updated
      return true
    } catch (caught) {
      error.value = toApiError(caught)
      return false
    }
  }

  async function remove(id: number): Promise<boolean> {
    try {
      await documentsApi.remove(id)
      items.value = items.value.filter((item) => item.id !== id)
      total.value = Math.max(0, total.value - 1)
      await fetchStats()
      return true
    } catch (caught) {
      error.value = toApiError(caught)
      return false
    }
  }

  async function reprocess(id: number): Promise<boolean> {
    try {
      await documentsApi.reprocess(id)
      const index = items.value.findIndex((item) => item.id === id)
      if (index >= 0) {
        items.value[index] = { ...items.value[index], status: 'processing' } as DocumentItem
      }
      if (detail.value?.id === id) detail.value = { ...detail.value, status: 'processing' }
      startPolling()
      return true
    } catch (caught) {
      error.value = toApiError(caught)
      return false
    }
  }

  async function fetchDetail(id: number): Promise<void> {
    detailStatus.value = 'loading'
    detailError.value = null
    try {
      detail.value = await documentsApi.get(id)
      detailStatus.value = 'ready'
    } catch (caught) {
      detailError.value = toApiError(caught)
      detailStatus.value = 'error'
      detail.value = null
    }
  }

  async function fetchChunks(id: number, page = chunkPage.value): Promise<void> {
    chunkStatus.value = chunks.value.length === 0 ? 'loading' : chunkStatus.value
    try {
      const result = await documentsApi.chunks(id, { page, page_size: chunkPageSize.value })
      chunks.value = result.items
      chunkTotal.value = result.total
      chunkPage.value = result.page
      chunkStatus.value = 'ready'
      chunkError.value = null
    } catch (caught) {
      chunkError.value = toApiError(caught)
      chunkStatus.value = 'error'
    }
  }

  /** 文档详情页轮询：处理中 → 自动刷新状态与块列表。 */
  function startPolling(): void {
    if (pollTimer || typeof window === 'undefined') return
    pollTicks = 0
    pollTimer = setInterval(() => {
      pollTicks += 1
      void tick()
      if (pollTicks >= POLL_LIMIT) stopPolling()
    }, POLL_INTERVAL)
  }

  async function tick(): Promise<void> {
    const current: DocumentItem | null = detail.value
    if (current && (current.status === 'pending' || current.status === 'processing')) {
      await fetchDetail(current.id)
      // 重新读取，避免 TS 沿用上面那段的字面量收窄
      const refreshed: DocumentItem | null = detail.value
      if (refreshed?.status === 'ready') {
        await fetchChunks(refreshed.id, 1)
        await fetchStats()
      }
    }
    if (hasUnsettled.value) {
      await fetchList()
      await fetchStats()
    } else {
      stopPolling()
    }
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function syncPolling(): void {
    if (hasUnsettled.value) startPolling()
    else stopPolling()
  }

  function setChunkFocus(ord: number | null): void {
    chunkFocusOrd.value = ord
  }

  function $resetAll(): void {
    stopPolling()
    items.value = []
    total.value = 0
    status.value = 'idle'
    error.value = null
    stats.value = null
    statsError.value = null
    detail.value = null
    detailStatus.value = 'idle'
    detailError.value = null
    chunks.value = []
    chunkTotal.value = 0
    chunkPage.value = 1
    chunkStatus.value = 'idle'
    chunkError.value = null
    resetQuery()
  }

  return {
    items,
    total,
    status,
    error,
    stats,
    statsError,
    query,
    uploading,
    uploadProgress,
    uploadError,
    lastUploaded,
    detail,
    detailStatus,
    detailError,
    chunks,
    chunkTotal,
    chunkPage,
    chunkPageSize,
    chunkStatus,
    chunkError,
    chunkFocusOrd,
    hasUnsettled,
    isEmpty,
    totalPages,
    fetchList,
    fetchStats,
    refresh,
    setQuery,
    resetQuery,
    upload,
    rename,
    remove,
    reprocess,
    fetchDetail,
    fetchChunks,
    startPolling,
    stopPolling,
    setChunkFocus,
    $resetAll,
  }
})
