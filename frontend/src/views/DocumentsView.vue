<script setup lang="ts">
/**
 * 文档库（契约 §7.1 /documents）：列表 + 上传 + 搜索筛选 + 状态徽标。
 * 三态齐全，处理中的文档会自动轮询到 ready（store 内实现）。
 */
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { errorMessage } from '@/api'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useIsCompact } from '@/composables/useMediaQuery'
import { useAuthStore } from '@/stores/auth'
import { useDocumentsStore } from '@/stores/documents'
import {
  formatBytes,
  formatCount,
  formatDateTime,
  formatRelative,
  sourceTypeLabel,
  truncate,
} from '@/utils/format'
import type { DocumentItem } from '@/api'

const store = useDocumentsStore()
const auth = useAuthStore()
const router = useRouter()
const isCompact = useIsCompact()

const ACCEPT = ['.txt', '.md', '.markdown', '.csv', '.log', '.json', '.pdf']
const ACCEPT_ATTR = ACCEPT.join(',')

/* -------------------------------- 查询 -------------------------------- */
const searchDraft = ref(store.query.q)
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(searchDraft, (value) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (store.query.q === value) return
    store.setQuery({ q: value })
    void store.fetchList()
  }, 320)
})

watch(
  () => store.query.q,
  (value) => {
    if (value !== searchDraft.value) searchDraft.value = value
  },
)

const statusOptions = [
  { value: '', label: '全部状态' },
  { value: 'ready', label: '已就绪' },
  { value: 'processing', label: '处理中' },
  { value: 'pending', label: '排队中' },
  { value: 'failed', label: '失败' },
]

const sortOptions = [
  { value: '-created_at', label: '最新优先' },
  { value: 'created_at', label: '最早优先' },
  { value: 'title', label: '标题排序' },
]

function applyFilter(patch: Record<string, unknown>): void {
  store.setQuery(patch)
  void store.fetchList()
}

function changePage(page: number): void {
  store.setQuery({ page })
  void store.fetchList()
}

/* -------------------------------- 上传 -------------------------------- */
const uploadOpen = ref(false)
const uploadMode = ref<'file' | 'paste'>('file')
const uploadForm = reactive({ title: '', rawText: '' })
const pickedFile = ref<File | null>(null)
const formError = ref('')
const dragging = ref(false)

const maxUploadMb = computed(() => auth.meta?.limits.max_upload_mb ?? 10)

function openUpload(mode: 'file' | 'paste'): void {
  uploadMode.value = mode
  uploadOpen.value = true
  formError.value = ''
  store.uploadError = null
}

function pickFile(file: File | null): void {
  formError.value = ''
  if (!file) {
    pickedFile.value = null
    return
  }
  const lower = file.name.toLowerCase()
  if (!ACCEPT.some((extension) => lower.endsWith(extension))) {
    formError.value = `不支持 ${file.name.split('.').pop() ?? ''} 类型，仅支持 ${ACCEPT.join(' ')}`
    pickedFile.value = null
    return
  }
  if (file.size > maxUploadMb.value * 1024 * 1024) {
    formError.value = `文件 ${formatBytes(file.size)} 超过 ${maxUploadMb.value} MB 上限`
    pickedFile.value = null
    return
  }
  pickedFile.value = file
  if (!uploadForm.title) uploadForm.title = file.name.replace(/\.[^.]+$/, '')
}

function onFileInput(event: Event): void {
  const input = event.target as HTMLInputElement
  pickFile(input.files?.[0] ?? null)
}

function onDrop(event: DragEvent): void {
  dragging.value = false
  pickFile(event.dataTransfer?.files?.[0] ?? null)
}

async function submitUpload(): Promise<void> {
  formError.value = ''
  if (uploadMode.value === 'file') {
    if (!pickedFile.value) {
      formError.value = '请先选择文件，或拖拽到虚线区域'
      return
    }
  } else {
    if (uploadForm.title.trim().length === 0) {
      formError.value = '请填写标题'
      return
    }
    if (uploadForm.rawText.trim().length === 0) {
      formError.value = '请粘贴正文内容'
      return
    }
  }

  const created = await store.upload(
    uploadMode.value === 'file'
      ? { file: pickedFile.value, title: uploadForm.title.trim() || undefined }
      : { title: uploadForm.title.trim(), rawText: uploadForm.rawText },
  )

  if (created) {
    ElMessage.success(`已提交《${created.title}》，正在后台切分与向量化`)
    uploadOpen.value = false
    pickedFile.value = null
    uploadForm.title = ''
    uploadForm.rawText = ''
    store.setQuery({ page: 1 })
  }
}

/* ------------------------------ 行操作 ------------------------------ */
const renameOpen = ref(false)
const renameTarget = ref<DocumentItem | null>(null)
const renameDraft = ref('')
const renameSaving = ref(false)

function openRename(document: DocumentItem): void {
  renameTarget.value = document
  renameDraft.value = document.title
  renameOpen.value = true
}

async function submitRename(): Promise<void> {
  const target = renameTarget.value
  const title = renameDraft.value.trim()
  if (!target || title.length === 0) {
    ElMessage.warning('标题不能为空')
    return
  }
  renameSaving.value = true
  try {
    const ok = await store.rename(target.id, title)
    if (ok) {
      ElMessage.success('标题已更新')
      renameOpen.value = false
    }
  } finally {
    renameSaving.value = false
  }
}

async function confirmRemove(document: DocumentItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除后《${truncate(document.title, 24)}》及其 ${document.chunk_count} 个片段将不再出现在检索结果中，确认删除？`,
      '删除文档',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const ok = await store.remove(document.id)
  if (ok) ElMessage.success('已删除')
}

async function reprocess(document: DocumentItem): Promise<void> {
  const ok = await store.reprocess(document.id)
  if (ok) ElMessage.success('已重新提交切分与向量化')
}

function openDocument(document: DocumentItem): void {
  void router.push({ name: 'document-detail', params: { id: document.id } })
}

function rowClass({ row }: { row: DocumentItem }): string {
  return store.lastUploaded?.id === row.id ? 'is-fresh' : ''
}

/* ------------------------------ 生命周期 ------------------------------ */
onMounted(() => {
  void store.refresh()
})

onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer)
  store.stopPolling()
})

const canReset = computed(
  () => store.query.q !== '' || store.query.status !== '' || store.query.sort !== '-created_at',
)
</script>

<template>
  <div class="docs">
    <header class="pagehead">
      <div class="stack stack--gap">
        <span class="micro">文档库</span>
        <h1 class="page-title">资料与切分结果</h1>
        <p class="lede">
          上传的文本会被切成片段并向量化；每条回答引用的就是这里的片段，所以块序号可以直接核对。
        </p>
      </div>
      <div class="row row--gap pagehead__actions">
        <button class="btn" type="button" @click="openUpload('paste')">粘贴文本</button>
        <button class="btn btn--primary" type="button" @click="openUpload('file')">上传文件</button>
      </div>
    </header>

    <!-- 统计条 -->
    <section class="stats" aria-label="文档统计">
      <div v-if="store.stats" class="stats__grid">
        <div class="stat">
          <span class="micro">文档总数</span>
          <strong class="num">{{ formatCount(store.stats.total) }}</strong>
        </div>
        <div class="stat">
          <span class="micro">已就绪</span>
          <strong class="num stat--ok">{{ formatCount(store.stats.ready) }}</strong>
        </div>
        <div class="stat">
          <span class="micro">处理中</span>
          <strong class="num stat--warn">{{ formatCount(store.stats.processing) }}</strong>
        </div>
        <div class="stat">
          <span class="micro">失败</span>
          <strong class="num stat--err">{{ formatCount(store.stats.failed) }}</strong>
        </div>
        <div class="stat">
          <span class="micro">片段总数</span>
          <strong class="num">{{ formatCount(store.stats.chunk_total) }}</strong>
        </div>
        <div class="stat">
          <span class="micro">字符总数</span>
          <strong class="num">{{ formatCount(store.stats.char_total) }}</strong>
        </div>
      </div>
      <div v-else class="stats__grid">
        <div v-for="index in 6" :key="index" class="stat">
          <span class="skel skel-line" style="width: 56px" />
          <span class="skel" style="width: 40px; height: 22px" />
        </div>
      </div>
    </section>

    <!-- 工具条 -->
    <section class="toolbar">
      <div class="field toolbar__search">
        <label class="field__label" for="doc-search">搜索</label>
        <input
          id="doc-search"
          v-model="searchDraft"
          class="input"
          type="search"
          placeholder="标题、文件名或片段正文"
        />
      </div>
      <div class="field">
        <label class="field__label" for="doc-status">状态</label>
        <select
          id="doc-status"
          class="select"
          :value="store.query.status"
          @change="applyFilter({ status: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="option in statusOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="field">
        <label class="field__label" for="doc-sort">排序</label>
        <select
          id="doc-sort"
          class="select"
          :value="store.query.sort"
          @change="applyFilter({ sort: ($event.target as HTMLSelectElement).value })"
        >
          <option v-for="option in sortOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>
      <div class="toolbar__actions">
        <button v-if="canReset" class="btn btn--quiet" type="button" @click="store.resetQuery(); store.fetchList()">
          重置
        </button>
        <button class="btn" type="button" @click="store.refresh()">刷新</button>
      </div>
    </section>

    <!-- 错误 -->
    <ErrorState
      v-if="store.status === 'error'"
      :error="store.error"
      title="文档列表加载失败"
      @retry="store.fetchList()"
    />

    <!-- 加载骨架 -->
    <div v-else-if="store.status === 'loading'" class="tbl-wrap">
      <div v-for="index in 6" :key="index" class="rowskel">
        <span class="skel skel-line" style="width: 28%" />
        <span class="skel skel-line" style="width: 12%" />
        <span class="skel skel-line" style="width: 10%" />
        <span class="skel skel-line" style="width: 32%" />
      </div>
    </div>

    <!-- 空态 -->
    <EmptyState
      v-else-if="store.isEmpty"
      :title="canReset ? '没有匹配的文档' : '文档库还是空的'"
      :hint="
        canReset
          ? '换个关键词或把状态筛选改回全部试试。'
          : '上传一份 PDF / Markdown / TXT，或直接粘贴一段规则文本，几秒后就能对它提问。'
      "
      :action-label="canReset ? '' : '上传第一份文档'"
      :secondary-label="canReset ? '清空筛选条件' : '粘贴文本'"
      @action="openUpload('file')"
      @secondary="canReset ? (store.resetQuery(), store.fetchList()) : openUpload('paste')"
    />

    <!-- 列表 -->
    <template v-else>
      <div v-if="!isCompact" class="tbl-wrap">
        <el-table :data="store.items" :row-class-name="rowClass" style="width: 100%" @row-click="openDocument">
          <el-table-column label="标题" min-width="240">
            <template #default="{ row }">
              <div class="cell-title">
                <RouterLink
                  class="cell-title__link"
                  :to="{ name: 'document-detail', params: { id: row.id } }"
                  @click.stop
                >
                  {{ row.title }}
                </RouterLink>
                <span class="micro">{{ sourceTypeLabel(row.source_type) }}<template v-if="row.filename"> · {{ row.filename }}</template></span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="128">
            <template #default="{ row }">
              <StatusBadge :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="片段" width="86" align="right">
            <template #default="{ row }"><span class="num">{{ formatCount(row.chunk_count) }}</span></template>
          </el-table-column>
          <el-table-column label="字符" width="96" align="right">
            <template #default="{ row }"><span class="num">{{ formatCount(row.char_count) }}</span></template>
          </el-table-column>
          <el-table-column label="大小" width="96" align="right">
            <template #default="{ row }"><span class="num">{{ formatBytes(row.size_bytes) }}</span></template>
          </el-table-column>
          <el-table-column label="更新时间" width="140">
            <template #default="{ row }"><span class="num dim">{{ formatDateTime(row.updated_at) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="230" align="right">
            <template #default="{ row }">
              <div class="rowactions" @click.stop>
                <button class="btn btn--sm" type="button" @click="openDocument(row)">查看块</button>
                <button class="btn btn--sm" type="button" @click="openRename(row)">重命名</button>
                <button class="btn btn--sm" type="button" @click="reprocess(row)">重跑</button>
                <button class="btn btn--sm btn--danger" type="button" @click="confirmRemove(row)">删除</button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 窄屏：卡片列 -->
      <ul v-else class="cards">
        <li v-for="row in store.items" :key="row.id" class="carditem">
          <div class="row row--between row--gap">
            <RouterLink class="carditem__title" :to="{ name: 'document-detail', params: { id: row.id } }">
              {{ row.title }}
            </RouterLink>
            <StatusBadge :status="row.status" />
          </div>
          <div class="carditem__meta num">
            {{ sourceTypeLabel(row.source_type) }} · {{ formatCount(row.chunk_count) }} 块 · {{ formatBytes(row.size_bytes) }} ·
            {{ formatRelative(row.updated_at) }}
          </div>
          <p v-if="row.error_message" class="carditem__err">{{ row.error_message }}</p>
          <div class="row row--gap">
            <button class="btn btn--sm" type="button" @click="openDocument(row)">查看块</button>
            <button class="btn btn--sm" type="button" @click="openRename(row)">重命名</button>
            <button class="btn btn--sm" type="button" @click="reprocess(row)">重跑</button>
            <button class="btn btn--sm btn--danger" type="button" @click="confirmRemove(row)">删除</button>
          </div>
        </li>
      </ul>

      <div class="pager">
        <span class="micro num">共 {{ store.total }} 条 · 第 {{ store.query.page }} / {{ store.totalPages }} 页</span>
        <div class="row row--gap">
          <button class="btn btn--sm" type="button" :disabled="store.query.page <= 1" @click="changePage(store.query.page - 1)">
            上一页
          </button>
          <button
            class="btn btn--sm"
            type="button"
            :disabled="store.query.page >= store.totalPages"
            @click="changePage(store.query.page + 1)"
          >
            下一页
          </button>
        </div>
      </div>
    </template>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadOpen" :title="uploadMode === 'file' ? '上传文件' : '粘贴文本'" width="560px">
      <div class="uploadtabs">
        <button
          class="authtab"
          :class="{ 'is-active': uploadMode === 'file' }"
          type="button"
          @click="uploadMode = 'file'"
        >
          文件上传
        </button>
        <button
          class="authtab"
          :class="{ 'is-active': uploadMode === 'paste' }"
          type="button"
          @click="uploadMode = 'paste'"
        >
          粘贴文本
        </button>
      </div>

      <div v-if="uploadMode === 'file'" class="stack stack--gap">
        <label
          class="dropzone"
          :class="{ 'is-dragging': dragging }"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
        >
          <input class="sr-only" type="file" :accept="ACCEPT_ATTR" @change="onFileInput" />
          <span class="micro">拖拽文件到这里，或点击选择</span>
          <strong>{{ pickedFile ? pickedFile.name : '未选择文件' }}</strong>
          <span class="field__hint">
            支持 {{ ACCEPT.join(' ') }}，单个文件不超过 {{ maxUploadMb }} MB；PDF 走文本抽取。
          </span>
        </label>
        <div class="field">
          <label class="field__label" for="up-title">标题（可选）</label>
          <input id="up-title" v-model="uploadForm.title" class="input" maxlength="255" placeholder="默认取文件名" />
        </div>
      </div>

      <div v-else class="stack stack--gap">
        <div class="field">
          <label class="field__label" for="paste-title">标题</label>
          <input id="paste-title" v-model="uploadForm.title" class="input" maxlength="255" placeholder="例如：售后规则补充说明" />
        </div>
        <div class="field">
          <label class="field__label" for="paste-body">正文</label>
          <textarea
            id="paste-body"
            v-model="uploadForm.rawText"
            class="textarea"
            rows="9"
            placeholder="直接粘贴 Markdown / 纯文本，建议带上小标题，切分时会作为 heading 记录。"
          />
          <span class="field__hint num">{{ uploadForm.rawText.length }} 字符</span>
        </div>
      </div>

      <div v-if="store.uploading" class="progress">
        <div class="progress__bar" :style="{ width: `${store.uploadProgress}%` }" />
        <span class="micro num">上传中 {{ store.uploadProgress }}%</span>
      </div>

      <div v-if="formError || store.uploadError" class="errbox" role="alert">
        <div class="stack stack--gap grow">
          <span class="errbox__code">上传失败</span>
          <span>{{ formError || errorMessage(store.uploadError) }}</span>
        </div>
      </div>

      <template #footer>
        <button class="btn" type="button" @click="uploadOpen = false">取消</button>
        <button class="btn btn--primary" type="button" :disabled="store.uploading" @click="submitUpload">
          {{ store.uploading ? '上传中…' : '提交并切分' }}
        </button>
      </template>
    </el-dialog>

    <!-- 重命名弹窗 -->
    <el-dialog v-model="renameOpen" title="重命名文档" width="420px">
      <div class="field">
        <label class="field__label" for="rename-input">标题</label>
        <input id="rename-input" v-model="renameDraft" class="input" maxlength="255" />
      </div>
      <template #footer>
        <button class="btn" type="button" @click="renameOpen = false">取消</button>
        <button class="btn btn--primary" type="button" :disabled="renameSaving" @click="submitRename">
          {{ renameSaving ? '保存中' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.docs {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  max-width: var(--shell-max);
}

.pagehead {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--sp-5);
}

.pagehead__actions {
  flex: none;
}

/* ------------------------------ 统计条 ------------------------------ */
.stats {
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.stats__grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.stat {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
  padding: var(--sp-3) var(--sp-4);
}

.stat + .stat {
  border-left: 1px solid var(--c-line);
}

.stat strong {
  font-size: var(--fs-20);
  font-weight: var(--fw-semi);
}

.stat--ok {
  color: var(--c-ok);
}

.stat--warn {
  color: var(--c-warn);
}

.stat--err {
  color: var(--c-err);
}

/* ------------------------------ 工具条 ------------------------------ */
.toolbar {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.toolbar__search {
  flex: 1 1 260px;
  max-width: 380px;
}

.toolbar__actions {
  display: flex;
  gap: var(--sp-2);
  margin-left: auto;
}

/* ------------------------------- 列表 ------------------------------- */
.cell-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.cell-title__link {
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
  color: var(--c-ink);
  border-bottom: none;
}

.cell-title__link:hover {
  color: var(--c-accent);
}

.rowactions {
  display: flex;
  gap: var(--sp-1);
  justify-content: flex-end;
}

:deep(.el-table .is-fresh) {
  background: var(--c-accent-wash);
}

.rowskel {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
}

.rowskel + .rowskel {
  border-top: 1px solid var(--c-line);
}

.cards {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}

.carditem {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
}

.carditem__title {
  font-size: var(--fs-14);
  font-weight: var(--fw-medium);
  color: var(--c-ink);
  border-bottom: none;
}

.carditem__meta {
  font-size: var(--fs-11);
  color: var(--c-ink-3);
}

.carditem__err {
  font-size: var(--fs-12);
  color: var(--c-err);
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}

/* ------------------------------ 弹窗内 ------------------------------ */
.uploadtabs {
  display: flex;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
  border-bottom: 1px solid var(--c-line);
}

.authtab {
  padding: var(--sp-2) 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--c-ink-3);
  font-size: var(--fs-13);
  cursor: pointer;
}

.authtab.is-active {
  color: var(--c-ink);
  border-bottom-color: var(--c-accent);
}

.dropzone {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  align-items: flex-start;
  padding: var(--sp-6) var(--sp-5);
  border: 1px dashed var(--c-line-2);
  background: var(--c-sunken);
  cursor: pointer;
  transition: border-color var(--dur-1) var(--ease), background var(--dur-1) var(--ease);
}

.dropzone:hover,
.dropzone.is-dragging {
  border-color: var(--c-accent);
  background: var(--c-accent-wash);
}

.dropzone strong {
  font-size: var(--fs-14);
}

.progress {
  position: relative;
  margin-top: var(--sp-3);
  height: 22px;
  border: 1px solid var(--c-line);
  background: var(--c-sunken);
  display: flex;
  align-items: center;
  padding: 0 var(--sp-2);
}

.progress__bar {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--c-accent-wash);
  transition: width var(--dur-2) var(--ease);
}

.progress .micro {
  position: relative;
}

/* ------------------------------ 响应式 ------------------------------ */
@media (max-width: 1024px) {
  .stats__grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .stat:nth-child(3n + 1) {
    border-left: none;
  }

  .stat:nth-child(n + 4) {
    border-top: 1px solid var(--c-line);
  }
}

@media (max-width: 768px) {
  .pagehead {
    flex-direction: column;
    align-items: flex-start;
  }

  .stats__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stat:nth-child(3n + 1) {
    border-left: none;
  }

  .stat:nth-child(2n + 1) {
    border-left: none;
  }

  .stat:nth-child(n + 3) {
    border-top: 1px solid var(--c-line);
  }

  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar__search {
    max-width: none;
  }

  .toolbar__actions {
    margin-left: 0;
  }
}
</style>
