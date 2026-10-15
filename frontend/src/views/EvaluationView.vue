<script setup lang="ts">
/**
 * 检索评测（契约 §7.3）：三模式指标对比柱状图 + 逐题命中排名表。
 * 图必须一眼看出 hybrid 优于纯向量，所以主指标锁 recall@3 并在结论行给出差值。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { ElMessage } from 'element-plus'
import type { EvalCompareItem, RetrievalMode } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import { useTheme } from '@/composables/useTheme'
import { ALL_MODES, MODE_LABEL, useEvaluationStore } from '@/stores/evaluation'
import { formatDateTime, formatMs, formatPercent } from '@/utils/format'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const store = useEvaluationStore()
const { mode: themeMode } = useTheme()

const chartEl = ref<HTMLElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let observer: ResizeObserver | null = null

const METRIC_SERIES: Array<{ key: keyof typeof METRIC_KEYS; label: string }> = [
  { key: 'recall_at_1', label: 'recall@1' },
  { key: 'recall_at_3', label: 'recall@3' },
  { key: 'recall_at_5', label: 'recall@5' },
  { key: 'hit_rate', label: 'hit_rate' },
  { key: 'mrr', label: 'MRR' },
]
const METRIC_KEYS = {
  recall_at_1: 'recall_at_1',
  recall_at_3: 'recall_at_3',
  recall_at_5: 'recall_at_5',
  hit_rate: 'hit_rate',
  mrr: 'mrr',
} as const

const modeDraft = ref<RetrievalMode[]>([...ALL_MODES])

function palette(): { ramp: string[]; ink: string; ink2: string; line: string; surface: string } {
  return themeMode.value === 'dark'
    ? {
        ramp: ['#7C8CFF', '#98A5FF', '#B4BEFF', '#CCD3FF', '#E4E8FF'],
        ink: '#E7E9EE',
        ink2: '#A2A9B4',
        line: '#24282F',
        surface: '#15181D',
      }
    : {
        ramp: ['#3340D8', '#4E5ADF', '#6B75E7', '#8A92EE', '#A9AFF4'],
        ink: '#14161A',
        ink2: '#4A4F58',
        line: '#DCDEDB',
        surface: '#FFFFFF',
      }
}

function buildOption(): Record<string, unknown> {
  const colors = palette()
  const rows = store.metricRows
  return {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 16, top: 32, bottom: 56, containLabel: false },
    textStyle: {
      fontFamily:
        'system-ui, -apple-system, "Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", sans-serif',
      color: colors.ink,
    },
    legend: {
      bottom: 4,
      left: 'left',
      icon: 'rect',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
      textStyle: { color: colors.ink2, fontSize: 11 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: colors.surface,
      borderColor: colors.line,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { color: colors.ink, fontSize: 12 },
      valueFormatter: (value: number) => `${Number(value).toFixed(1)}%`,
    },
    xAxis: {
      type: 'category',
      data: rows.map((row) => row.label),
      axisLine: { lineStyle: { color: colors.line } },
      axisTick: { show: false },
      axisLabel: { color: colors.ink, fontSize: 12, margin: 12 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      name: '百分比',
      nameTextStyle: { color: colors.ink2, fontSize: 11, align: 'right' },
      axisLabel: { color: colors.ink2, fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: colors.line, type: 'solid' } },
    },
    series: METRIC_SERIES.map((metric, index) => ({
      name: metric.label,
      type: 'bar',
      barMaxWidth: 22,
      barGap: '18%',
      itemStyle: { color: colors.ramp[index] ?? colors.ramp[0], borderRadius: 0 },
      data: rows.map((row) => Number((row.metrics[metric.key] * 100).toFixed(1))),
      label: {
        show: index === 1,
        position: 'top',
        color: colors.ink,
        fontSize: 11,
        formatter: '{c}%',
      },
      emphasis: { focus: 'series' },
    })),
  }
}

function renderChart(): void {
  const el = chartEl.value
  if (!el) return
  // ⚠️ 必须重新取实例：运行评测/翻页时 store.status 会短暂变为 loading，
  // 根模板的 v-else 分支被销毁重建，图表容器是**新元素**；旧实例随之被 ECharts 自动 dispose。
  // 若继续持有旧引用并对已销毁实例 setOption，画布会永久空白（端到端走查实测到的现象：
  // 首屏图表 76,217 个非空像素 → 点「运行评测」后 canvas 消失、零像素）。
  const existing = echarts.getInstanceByDom(el)
  if (existing !== chart) {
    chart = existing ?? echarts.init(el, undefined, { renderer: 'canvas' })
  }
  chart.setOption(buildOption(), true)
  chart.resize()
}

const itemsByRun = computed(() => {
  const runs = store.compare?.runs ?? []
  return runs.map((run) => ({
    runId: run.run_id,
    mode: run.mode,
    label: MODE_LABEL[run.mode] ?? run.mode,
  }))
})

const cellMap = computed(() => {
  // 逐题命中矩阵：在 setup 里预先摊平成 Map，模板只做 O(1) 取值。
  // ⚠️ 不在模板内联表达式里写箭头函数：Vue SFC 编译器在 inline 模式下会把
  // `item.per_run.find((perRun) => perRun.run_id === runId)` 改写成
  // `item.per_run.find((perRun) => per_run.run_id === runId)` —— 参数声明保留 perRun、
  // 函数体被写成 per_run，运行时报 `ReferenceError: per_run is not defined`，
  // 整张逐题表渲染失败。tsc 与 vitest 都发现不了（源码本身合法），
  // 只有浏览器端到端走查能抓到。顺带把"每格一次 find"的 O(n) 扫描降成 O(1)。
  const map = new Map<string, { rank: number | null; hit: boolean }>()
  for (const item of store.compare?.items ?? []) {
    for (const entry of item.per_run ?? []) {
      map.set(`${item.item_id}:${entry.run_id}`, { rank: entry.rank, hit: entry.hit })
    }
  }
  return map
})

function cellOf(itemId: number, runId: number): { rank: number | null; hit: boolean } {
  return cellMap.value.get(`${itemId}:${runId}`) ?? { rank: null, hit: false }
}

const conclusion = computed(() => {
  const best = store.bestMode
  if (!best) return ''
  const gain = store.hybridGain
  if (gain === null) {
    return `当前只有 ${best.label} 的结果，recall@3 为 ${formatPercent(best.metrics.recall_at_3)}。`
  }
  if (gain > 0) {
    return `${best.label} 在主指标 recall@3 上领先其它模式 ${(gain * 100).toFixed(1)} 个百分点。`
  }
  if (gain === 0) {
    return `${best.label} 与其它模式在主指标 recall@3 上持平。`
  }
  return `本次运行里混合检索未跑赢单通道（差 ${(Math.abs(gain) * 100).toFixed(1)} 个百分点），可以调大 top_k 或更换评测集再看。`
})

async function run(): Promise<void> {
  store.setModes(modeDraft.value)
  await store.runEvaluation()
}

async function toggleRun(runId: number): Promise<void> {
  store.toggleRun(runId)
  await store.loadCompare()
}

async function latestPerMode(): Promise<void> {
  const ids = store.selectLatestPerMode()
  await store.loadCompare(ids)
}

onMounted(async () => {
  await store.bootstrap()
  renderChart()
  if (chartEl.value && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => chart?.resize())
    observer.observe(chartEl.value)
  }
})

watch(() => store.metricRows, () => nextTick(() => renderChart()), { deep: true })
watch(themeMode, () => nextTick(() => renderChart()))
// 容器被重建时（status 在 loading/ready 之间切换）也要重画，否则画布永久空白
watch(chartEl, (el) => {
  if (el) nextTick(() => renderChart())
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  chart?.dispose()
  chart = null
})

watch(
  () => store.runError,
  (error) => {
    if (error) ElMessage.error(error.message)
  },
)
</script>

<template>
  <div class="eval">
    <header class="pagehead">
      <div class="stack stack--gap">
        <span class="micro">检索评测</span>
        <h1 class="page-title">三种检索模式的口径对比</h1>
        <p class="lede">
          同一个评测集、同一批 gold 片段，只换检索通道。指标全是 0–1 小数，命中定义是该题的 gold 块出现在返回的前
          top_k 条里。
        </p>
      </div>
    </header>

    <!-- 控制条 -->
    <section class="controls">
      <label class="field">
        <span class="field__label">数据集</span>
        <el-select
          :model-value="store.activeDatasetId ?? undefined"
          placeholder="选择数据集"
          style="width: 260px"
          @update:model-value="(value: number) => { store.activeDatasetId = value; store.fetchItems(1); store.selectLatestPerMode(); store.loadCompare() }"
        >
          <el-option
            v-for="dataset in store.datasets"
            :key="dataset.id"
            :label="`${dataset.name}（${dataset.item_count ?? 0} 题）`"
            :value="dataset.id"
          />
        </el-select>
      </label>

      <div class="field">
        <span class="field__label">对比模式</span>
        <el-checkbox-group v-model="modeDraft" size="small">
          <el-checkbox v-for="mode in ALL_MODES" :key="mode" :value="mode" :label="mode">
            {{ MODE_LABEL[mode] }}
          </el-checkbox>
        </el-checkbox-group>
      </div>

      <label class="field">
        <span class="field__label">top_k</span>
        <el-input-number v-model="store.topK" :min="1" :max="10" size="small" controls-position="right" />
      </label>

      <div class="controls__run">
        <button class="btn btn--primary btn--lg" type="button" :disabled="store.running" @click="run()">
          {{ store.running ? '评测进行中…' : '运行评测' }}
        </button>
      </div>
    </section>

    <ErrorState
      v-if="store.status === 'error'"
      :error="store.error"
      title="评测数据加载失败"
      @retry="store.bootstrap()"
    />

    <ErrorState v-if="store.runError" :error="store.runError" title="评测运行失败" @retry="run()" />

    <div v-if="store.running" class="notice">
      <i class="dot dot--pulse" />
      <div class="stack stack--gap">
        <strong>正在执行评测</strong>
        <span class="muted">
          同步接口，会依次跑 {{ modeDraft.length }} 个模式 × {{ store.activeDataset?.item_count ?? '—' }} 题，通常几秒内完成。
        </span>
      </div>
    </div>

    <EmptyState
      v-else-if="store.status === 'ready' && store.datasets.length === 0"
      title="还没有评测数据集"
      hint="后端初始化时会灌入一个 ≥12 题的种子评测集，先执行 python -m app.db.init_db。"
    />

    <template v-else>
      <!-- 图表 -->
      <section class="panel">
        <header class="panel__head">
          <span class="panel__title">指标对比</span>
          <span class="micro">
            运行
            {{ store.metricRows.map((row) => `#${row.runId}`).join(' / ') || '—' }}
          </span>
        </header>
        <div v-if="store.metricRows.length === 0" class="panel__body">
          <span v-if="store.status === 'loading'" class="skel" style="display: block; width: 100%; height: 260px" />
          <p v-else class="muted">还没有可对比的 run，点「运行评测」生成一次。</p>
        </div>
        <div v-else ref="chartEl" class="chart" />
        <div v-if="store.metricRows.length > 0" class="latency">
          <span class="micro">平均单题检索耗时</span>
          <div class="latency__items">
            <span v-for="row in store.metricRows" :key="row.runId" class="badge">
              {{ row.label }} {{ formatMs(row.metrics.avg_latency_ms) }}
            </span>
          </div>
        </div>
      </section>

      <!-- 结论 -->
      <section v-if="conclusion" class="conclusion">
        <span class="micro">结论</span>
        <p>{{ conclusion }}</p>
      </section>

      <!-- 逐题排名 -->
      <section class="panel">
        <header class="panel__head">
          <span class="panel__title">逐题命中排名</span>
          <span class="micro num">共 {{ store.itemsTotal }} 题 · 第 {{ store.itemsPage }} / {{ store.itemsTotalPages }} 页</span>
        </header>

        <div v-if="store.status === 'loading'" class="panel__body">
          <span v-for="index in 6" :key="index" class="skel skel-line" style="width: 100%" />
        </div>

        <div v-else-if="itemsByRun.length === 0" class="panel__body">
          <p class="muted">没有可对比的 run。</p>
        </div>

        <div v-else class="tbl-wrap">
          <el-table :data="store.compare?.items ?? []" style="width: 100%">
            <el-table-column label="题目" min-width="300">
              <template #default="{ row }">
                <span class="qcell">{{ row.question }}</span>
              </template>
            </el-table-column>
            <el-table-column
              v-for="run in itemsByRun"
              :key="run.runId"
              :label="`${run.label} #${run.runId}`"
              width="180"
            >
              <template #default="{ row }">
                <span v-if="cellOf(row.item_id, run.runId).hit" class="badge badge--ok num">
                  命中 #{{ cellOf(row.item_id, run.runId).rank }}
                </span>
                <span v-else class="badge num"><i class="dot" /> 未命中</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="panel__body pager">
          <button
            class="btn btn--sm"
            type="button"
            :disabled="store.itemsPage <= 1"
            @click="store.fetchItems(store.itemsPage - 1)"
          >
            上一页
          </button>
          <button
            class="btn btn--sm"
            type="button"
            :disabled="store.itemsPage >= store.itemsTotalPages"
            @click="store.fetchItems(store.itemsPage + 1)"
          >
            下一页
          </button>
        </div>
      </section>

      <!-- 历史 run -->
      <section class="panel">
        <header class="panel__head">
          <span class="panel__title">历史运行</span>
          <button class="btn btn--sm" type="button" @click="latestPerMode()">只选各模式最新一次</button>
        </header>
        <ul class="runs">
          <li v-for="entry in store.runs" :key="entry.run_id" class="runrow" :class="{ 'is-selected': store.selectedRunIds.includes(entry.run_id) }">
            <button class="runrow__main" type="button" @click="toggleRun(entry.run_id)">
              <span class="runrow__id num">#{{ entry.run_id }}</span>
              <span class="runrow__mode">{{ MODE_LABEL[entry.mode] ?? entry.mode }}</span>
              <span class="runrow__metric num">recall@3 {{ formatPercent(entry.metrics.recall_at_3) }}</span>
              <span class="runrow__metric num">MRR {{ entry.metrics.mrr.toFixed(3) }}</span>
              <span class="runrow__metric num">{{ entry.item_count }} 题</span>
              <span class="runrow__metric num">{{ formatMs(entry.duration_ms) }}</span>
              <span class="runrow__time num">{{ formatDateTime(entry.created_at) }}</span>
            </button>
          </li>
          <li v-if="store.runs.length === 0" class="panel__body muted">还没有历史运行记录。</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.eval {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  max-width: var(--shell-max);
}

.pagehead {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.controls {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-5);
  flex-wrap: wrap;
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.controls__run {
  margin-left: auto;
}

.chart {
  width: 100%;
  height: 320px;
  padding: var(--sp-2) var(--sp-3) 0;
}

.latency {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-4) var(--sp-3);
  border-top: 1px solid var(--c-line);
  flex-wrap: wrap;
}

.latency__items {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.conclusion {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  border-left: 2px solid var(--c-accent);
  background: var(--c-accent-wash);
}

.conclusion p {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
}

.qcell {
  font-size: var(--fs-13);
}

.pager {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding-top: var(--sp-3);
}

.runs {
  display: flex;
  flex-direction: column;
  max-height: 340px;
  overflow-y: auto;
}

.runrow {
  border-left: 2px solid transparent;
}

.runrow + .runrow {
  border-top: 1px solid var(--c-line);
}

.runrow.is-selected {
  border-left-color: var(--c-accent);
  background: var(--c-accent-wash);
}

.runrow__main {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  width: 100%;
  padding: var(--sp-2) var(--sp-4);
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: var(--fs-12);
  flex-wrap: wrap;
}

.runrow__main:hover {
  background: var(--c-sunken);
}

.runrow.is-selected .runrow__main:hover {
  background: transparent;
}

.runrow__id {
  color: var(--c-accent);
  min-width: 42px;
}

.runrow__mode {
  min-width: 130px;
  font-weight: var(--fw-medium);
}

.runrow__metric {
  color: var(--c-ink-2);
}

.runrow__time {
  margin-left: auto;
  color: var(--c-ink-3);
}

@media (max-width: 768px) {
  .controls {
    flex-direction: column;
    align-items: stretch;
  }

  .controls__run {
    margin-left: 0;
  }

  .chart {
    height: 260px;
  }

  .runrow__time {
    margin-left: 0;
  }
}
</style>
