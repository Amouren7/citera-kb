import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  evaluationsApi,
  toApiError,
  type ApiError,
  type EvalCompareResponse,
  type EvalDataset,
  type EvalItem,
  type EvalRunSummary,
  type RetrievalMode,
} from '@/api'

export const ALL_MODES: RetrievalMode[] = ['vector', 'keyword', 'hybrid']

export const MODE_LABEL: Record<RetrievalMode, string> = {
  vector: '向量检索',
  keyword: '关键词检索',
  hybrid: '混合检索（RRF）',
}

export interface MetricRow {
  runId: number
  mode: RetrievalMode
  label: string
  createdAt: string
  itemCount: number
  durationMs: number
  metrics: EvalRunSummary['metrics']
}

export const useEvaluationStore = defineStore('evaluation', () => {
  const datasets = ref<EvalDataset[]>([])
  const activeDatasetId = ref<number | null>(null)

  const items = ref<EvalItem[]>([])
  const itemsTotal = ref(0)
  const itemsPage = ref(1)
  const itemsPageSize = ref(10)

  const runs = ref<EvalRunSummary[]>([])
  const selectedRunIds = ref<number[]>([])
  const compare = ref<EvalCompareResponse | null>(null)

  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const running = ref(false)
  const error = ref<ApiError | null>(null)
  const runError = ref<ApiError | null>(null)

  const modes = ref<RetrievalMode[]>([...ALL_MODES])
  const topK = ref(5)

  const activeDataset = computed(
    () => datasets.value.find((dataset) => dataset.id === activeDatasetId.value) ?? null,
  )

  /** 对比图的数据行：同一模式只保留最新一次 run。 */
  const metricRows = computed<MetricRow[]>(() => {
    const byMode = new Map<RetrievalMode, MetricRow>()
    for (const run of compare.value?.runs ?? []) {
      const row: MetricRow = {
        runId: run.run_id,
        mode: run.mode,
        label: MODE_LABEL[run.mode] ?? run.mode,
        createdAt: run.created_at,
        itemCount: run.item_count,
        durationMs: run.duration_ms,
        metrics: run.metrics,
      }
      const existing = byMode.get(run.mode)
      if (!existing || Date.parse(run.created_at) >= Date.parse(existing.createdAt)) {
        byMode.set(run.mode, row)
      }
    }
    return ALL_MODES.filter((mode) => byMode.has(mode)).map((mode) => byMode.get(mode) as MetricRow)
  })

  /** 结论行：以 recall_at_3 为主指标找最优模式（用于"一眼看出 hybrid 更好"）。 */
  const bestMode = computed<MetricRow | null>(() => {
    const rows = metricRows.value
    if (rows.length === 0) return null
    return rows.reduce((best, row) =>
      row.metrics.recall_at_3 > best.metrics.recall_at_3 ||
      (row.metrics.recall_at_3 === best.metrics.recall_at_3 && row.metrics.mrr > best.metrics.mrr)
        ? row
        : best,
    )
  })

  const hybridGain = computed<number | null>(() => {
    const rows = metricRows.value
    if (rows.length < 2) return null
    const hybrid = rows.find((row) => row.mode === 'hybrid')
    if (!hybrid) return null
    const others = rows.filter((row) => row.mode !== 'hybrid')
    if (others.length === 0) return null
    const bestOther = Math.max(...others.map((row) => row.metrics.recall_at_3))
    return hybrid.metrics.recall_at_3 - bestOther
  })

  const itemsTotalPages = computed(() => Math.max(1, Math.ceil(itemsTotal.value / itemsPageSize.value)))

  async function fetchDatasets(): Promise<void> {
    try {
      datasets.value = await evaluationsApi.datasets()
      if (activeDatasetId.value === null && datasets.value.length > 0) {
        activeDatasetId.value = (datasets.value[0] as EvalDataset).id
      }
      error.value = null
    } catch (caught) {
      error.value = toApiError(caught)
      status.value = 'error'
    }
  }

  async function fetchItems(page = itemsPage.value): Promise<void> {
    if (activeDatasetId.value === null) return
    status.value = items.value.length === 0 ? 'loading' : status.value
    try {
      const result = await evaluationsApi.items(activeDatasetId.value, {
        page,
        page_size: itemsPageSize.value,
      })
      items.value = result.items
      itemsTotal.value = result.total
      itemsPage.value = result.page
      status.value = 'ready'
      error.value = null
    } catch (caught) {
      error.value = toApiError(caught)
      status.value = 'error'
    }
  }

  async function fetchRuns(): Promise<void> {
    try {
      const result = await evaluationsApi.runs({ page: 1, page_size: 30 })
      runs.value = result.items
    } catch (caught) {
      error.value = toApiError(caught)
    }
  }

  async function loadCompare(ids?: number[]): Promise<void> {
    const target = ids && ids.length > 0 ? ids : selectedRunIds.value
    try {
      compare.value = await evaluationsApi.compare(target)
      if (target.length === 0) {
        selectedRunIds.value = compare.value.runs.map((run) => run.run_id)
      }
      error.value = null
    } catch (caught) {
      error.value = toApiError(caught)
      compare.value = null
    }
  }

  /** 跑一次评测（同步接口，契约 §4.2）：跑完自动选中新 run 并载入对比。 */
  async function runEvaluation(): Promise<void> {
    if (activeDatasetId.value === null || running.value) return
    running.value = true
    runError.value = null
    try {
      const result = await evaluationsApi.run({
        dataset_id: activeDatasetId.value,
        modes: modes.value,
        top_k: topK.value,
      })
      const ids = result.runs.map((run) => run.run_id)
      await fetchRuns()
      selectedRunIds.value = ids
      await loadCompare(ids)
    } catch (caught) {
      runError.value = toApiError(caught)
    } finally {
      running.value = false
    }
  }

  function toggleRun(runId: number): void {
    const next = selectedRunIds.value.includes(runId)
      ? selectedRunIds.value.filter((id) => id !== runId)
      : [...selectedRunIds.value, runId]
    selectedRunIds.value = next
  }

  /** 只选中每个模式最近的一次 run。 */
  function selectLatestPerMode(): number[] {
    const picked = new Map<RetrievalMode, EvalRunSummary>()
    const ordered = [...runs.value].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    for (const run of ordered) {
      if (!picked.has(run.mode)) picked.set(run.mode, run)
    }
    const ids = ALL_MODES.map((mode) => picked.get(mode)?.run_id).filter(
      (id): id is number => typeof id === 'number',
    )
    selectedRunIds.value = ids
    return ids
  }

  async function bootstrap(): Promise<void> {
    await fetchDatasets()
    await Promise.all([fetchItems(1), fetchRuns()])
    const ids = selectLatestPerMode()
    await loadCompare(ids)
  }

  function setModes(next: RetrievalMode[]): void {
    modes.value = next.length > 0 ? next : [...ALL_MODES]
  }

  function $resetAll(): void {
    datasets.value = []
    activeDatasetId.value = null
    items.value = []
    itemsTotal.value = 0
    itemsPage.value = 1
    runs.value = []
    selectedRunIds.value = []
    compare.value = null
    status.value = 'idle'
    running.value = false
    error.value = null
    runError.value = null
  }

  return {
    datasets,
    activeDatasetId,
    activeDataset,
    items,
    itemsTotal,
    itemsPage,
    itemsPageSize,
    itemsTotalPages,
    runs,
    selectedRunIds,
    compare,
    status,
    running,
    error,
    runError,
    modes,
    topK,
    metricRows,
    bestMode,
    hybridGain,
    fetchDatasets,
    fetchItems,
    fetchRuns,
    loadCompare,
    runEvaluation,
    toggleRun,
    selectLatestPerMode,
    bootstrap,
    setModes,
    $resetAll,
  }
})
