<script setup lang="ts">
/**
 * 文档详情（契约 §7.1 /documents/:id）：块预览分页 + 状态。
 * 支持 ?chunk=N 定位（回答里的「打开原文」就是跳到这里）。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ErrorState from '@/components/ErrorState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useDocumentsStore } from '@/stores/documents'
import { formatBytes, formatCount, formatDateTime, sourceTypeLabel } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const store = useDocumentsStore()

const documentId = computed(() => Number(route.params.id))
const focusedOrd = ref<number | null>(null)
const jumping = ref('')
const listRef = ref<HTMLElement | null>(null)

const metaEntries = computed(() => {
  const meta = store.detail?.meta ?? {}
  return Object.entries(meta).filter(([, value]) => value !== null && value !== undefined)
})

const chunkTotalPages = computed(() =>
  Math.max(1, Math.ceil(store.chunkTotal / store.chunkPageSize)),
)

const isProcessing = computed(
  () => store.detail?.status === 'pending' || store.detail?.status === 'processing',
)

async function load(): Promise<void> {
  const id = documentId.value
  if (!Number.isFinite(id)) return
  await store.fetchDetail(id)

  const queryChunk = Number(route.query.chunk)
  focusedOrd.value = Number.isFinite(queryChunk) && queryChunk > 0 ? queryChunk : null
  store.setChunkFocus(focusedOrd.value)

  const page =
    focusedOrd.value && focusedOrd.value > store.chunkPageSize
      ? Math.max(1, Math.ceil(focusedOrd.value / store.chunkPageSize))
      : 1
  await store.fetchChunks(id, page)
  if (isProcessing.value) store.startPolling()
  await scrollToFocus()
}

async function scrollToFocus(): Promise<void> {
  if (!focusedOrd.value) return
  await nextTick()
  const target = listRef.value?.querySelector<HTMLElement>(`[data-ord="${focusedOrd.value}"]`)
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function goChunkPage(page: number): Promise<void> {
  if (page < 1 || page > chunkTotalPages.value) return
  await store.fetchChunks(documentId.value, page)
}

async function jumpToOrd(): Promise<void> {
  const ord = Number(jumping.value)
  if (!Number.isFinite(ord) || ord < 1) {
    ElMessage.warning('请输入大于 0 的块序号')
    return
  }
  focusedOrd.value = ord
  store.setChunkFocus(ord)
  await goChunkPage(Math.max(1, Math.ceil(ord / store.chunkPageSize)))
  await scrollToFocus()
}

async function reprocess(): Promise<void> {
  const ok = await store.reprocess(documentId.value)
  if (ok) ElMessage.success('已重新提交切分与向量化，处理完成后自动刷新')
}

async function rename(): Promise<void> {
  const title = window.prompt('新的标题', store.detail?.title ?? '')
  if (title === null) return
  const trimmed = title.trim()
  if (!trimmed) {
    ElMessage.warning('标题不能为空')
    return
  }
  const ok = await store.rename(documentId.value, trimmed)
  if (ok) ElMessage.success('标题已更新')
}

watch(
  () => route.params.id,
  () => {
    void load()
  },
  { immediate: true },
)

// 处理完成后把焦点块所在页刷新一次，保证刚生成的块可见
watch(
  () => store.detail?.status,
  (status, previous) => {
    if (previous && previous !== 'ready' && status === 'ready') {
      void store.fetchChunks(documentId.value, store.chunkPage)
    }
  },
)

onUnmounted(() => {
  store.stopPolling()
  store.setChunkFocus(null)
})

function backToList(): void {
  void router.push({ name: 'documents' })
}
</script>

<template>
  <div class="detail">
    <nav class="crumbs">
      <button class="crumbs__back" type="button" @click="backToList">← 返回文档库</button>
      <span class="micro">文档 / 第 {{ documentId }} 号</span>
    </nav>

    <!-- 加载骨架 -->
    <div v-if="store.detailStatus === 'loading'" class="stack stack--gap">
      <span class="skel" style="width: 280px; height: 26px" />
      <span class="skel skel-line" style="width: 60%" />
      <span class="skel" style="width: 100%; height: 220px" />
    </div>

    <ErrorState
      v-else-if="store.detailStatus === 'error'"
      :error="store.detailError"
      title="文档加载失败"
      @retry="load()"
    />

    <template v-else-if="store.detail">
      <header class="head">
        <div class="stack stack--gap">
          <div class="row row--gap">
            <StatusBadge :status="store.detail.status" />
            <span class="badge">{{ sourceTypeLabel(store.detail.source_type) }}</span>
            <span v-if="store.detail.filename" class="badge">{{ store.detail.filename }}</span>
          </div>
          <h1 class="page-title head__title">{{ store.detail.title }}</h1>
          <p class="head__meta num">
            {{ formatCount(store.detail.chunk_count) }} 块 · {{ formatCount(store.detail.char_count) }} 字符 ·
            {{ formatBytes(store.detail.size_bytes) }} · 更新于 {{ formatDateTime(store.detail.updated_at) }}
          </p>
        </div>
        <div class="row row--gap head__actions">
          <button class="btn" type="button" @click="rename()">重命名</button>
          <button class="btn" type="button" :disabled="isProcessing" @click="reprocess()">重新切分</button>
          <RouterLink
            class="btn btn--primary"
            :to="{ name: 'chat', query: { doc: String(store.detail.id) } }"
          >
            对它提问
          </RouterLink>
        </div>
      </header>

      <!-- 处理中 / 失败 -->
      <section v-if="isProcessing" class="notice notice--warn">
        <i class="dot dot--pulse" />
        <div class="stack stack--gap">
          <strong>正在后台切分与向量化</strong>
          <span class="muted">
            此页每 2.5 秒自动刷新一次；完成后片段会出现在下方，并可以被检索命中。
          </span>
        </div>
      </section>

      <section v-else-if="store.detail.status === 'failed'" class="notice notice--err">
        <div class="stack stack--gap grow">
          <span class="errbox__code">unprocessable_upload</span>
          <strong>解析失败</strong>
          <span class="muted">{{ store.detail.error_message || '文档内容无法解析' }}</span>
        </div>
        <button class="btn" type="button" @click="reprocess()">重试解析</button>
      </section>

      <!-- 切分参数快照 -->
      <section class="metastrip">
        <span class="micro">切分参数快照</span>
        <div class="metastrip__items">
          <span v-for="[key, value] in metaEntries" :key="key" class="badge">
            {{ key }}: {{ value }}
          </span>
          <span v-if="metaEntries.length === 0" class="dim">meta 为空</span>
        </div>
      </section>

      <!-- 块列表 -->
      <section class="chunks" aria-label="文档片段">
        <header class="chunks__head">
          <div class="stack stack--gap">
            <span class="micro">片段预览</span>
            <h2 class="section-title">共 {{ store.chunkTotal }} 块</h2>
          </div>
          <div class="row row--gap">
            <input
              v-model="jumping"
              class="input chunks__jump"
              type="number"
              min="1"
              placeholder="块序号"
              @keyup.enter="jumpToOrd()"
            />
            <button class="btn btn--sm" type="button" @click="jumpToOrd()">跳转</button>
          </div>
        </header>

        <div v-if="store.chunkStatus === 'loading'" class="stack stack--gap">
          <span v-for="index in 4" :key="index" class="skel" style="width: 100%; height: 92px" />
        </div>

        <ErrorState
          v-else-if="store.chunkStatus === 'error'"
          :error="store.chunkError"
          title="片段加载失败"
          @retry="goChunkPage(store.chunkPage)"
        />

        <div v-else-if="store.chunks.length === 0" class="notice">
          <strong>还没有片段</strong>
          <span class="muted">这份文档可能正在排队处理，或内容为空。</span>
        </div>

        <ol v-else ref="listRef" class="chunklist">
          <li
            v-for="chunk in store.chunks"
            :key="chunk.id"
            class="chunk"
            :class="{ 'is-focused': focusedOrd === chunk.ord }"
            :data-ord="chunk.ord"
          >
            <div class="chunk__head">
              <span class="chunk__ord num">#{{ chunk.ord }}</span>
              <strong class="chunk__heading">{{ chunk.heading ?? '无章节标题' }}</strong>
              <span class="badge num">{{ chunk.token_estimate }} tok</span>
              <span class="badge" :class="chunk.has_embedding ? 'badge--ok' : 'badge--warn'">
                {{ chunk.has_embedding ? '已向量化' : '未向量化' }}
              </span>
            </div>
            <p class="chunk__content">{{ chunk.content }}</p>
          </li>
        </ol>

        <div v-if="store.chunkTotal > 0" class="pager">
          <span class="micro num">
            第 {{ store.chunkPage }} / {{ chunkTotalPages }} 页 · 每页 {{ store.chunkPageSize }} 块
          </span>
          <div class="row row--gap">
            <button class="btn btn--sm" type="button" :disabled="store.chunkPage <= 1" @click="goChunkPage(store.chunkPage - 1)">
              上一页
            </button>
            <button
              class="btn btn--sm"
              type="button"
              :disabled="store.chunkPage >= chunkTotalPages"
              @click="goChunkPage(store.chunkPage + 1)"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  max-width: var(--shell-max);
}

.crumbs {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.crumbs__back {
  border: 0;
  background: transparent;
  padding: 0;
  color: var(--c-accent);
  font-size: var(--fs-13);
  cursor: pointer;
}

.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-5);
  padding-bottom: var(--sp-4);
  border-bottom: 1px solid var(--c-line);
}

.head__title {
  font-size: var(--fs-26);
}

.head__meta {
  font-size: var(--fs-12);
  color: var(--c-ink-3);
}

.head__actions {
  flex: none;
}

a.btn {
  border-bottom: 1px solid var(--c-line-2);
}

.notice {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.notice--warn {
  border-left: 3px solid var(--c-warn);
  background: var(--c-warn-wash);
}

.notice--err {
  border-left: 3px solid var(--c-err);
  background: var(--c-err-wash);
}

.notice--err .muted {
  color: var(--c-err);
}

.metastrip {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  background: var(--c-sunken);
}

.metastrip__items {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.metastrip__items .badge {
  background: var(--c-surface);
}

.chunks {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.chunks__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-4);
}

.chunks__jump {
  width: 110px;
}

.chunklist {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.chunk {
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  border-left: 2px solid var(--c-line-2);
  background: var(--c-surface);
  transition: border-color var(--dur-2) var(--ease), background var(--dur-2) var(--ease);
}

.chunk.is-focused {
  border-left-color: var(--c-accent);
  background: var(--c-accent-wash);
}

.chunk__head {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex-wrap: wrap;
  margin-bottom: var(--sp-2);
}

.chunk__ord {
  font-size: var(--fs-12);
  font-weight: var(--fw-medium);
  color: var(--c-accent);
  min-width: 34px;
}

.chunk__heading {
  font-size: var(--fs-14);
  font-weight: var(--fw-semi);
}

.chunk__content {
  font-size: var(--fs-14);
  line-height: 1.85;
  color: var(--c-ink-2);
  white-space: pre-wrap;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

@media (max-width: 768px) {
  .head {
    flex-direction: column;
    align-items: flex-start;
  }

  .head__actions {
    flex-wrap: wrap;
  }

  .chunks__head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
