<script setup lang="ts">
/**
 * 管理台（契约 §7.1 /admin，仅 admin）：统计卡 + 用户表 + 设置表单。
 * 页面自己管局部状态，不新建 Pinia store。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, metaApi, toApiError, type AdminStats, type ApiError, type Health, type User, type UserRole } from '@/api'
import ErrorState from '@/components/ErrorState.vue'
import { formatCount, formatDateTime } from '@/utils/format'

const stats = ref<AdminStats | null>(null)
const statsError = ref<ApiError | null>(null)
const statsLoading = ref(true)

const users = ref<User[]>([])
const usersTotal = ref(0)
const usersPage = ref(1)
const usersPageSize = ref(10)
const usersQuery = ref('')
const usersError = ref<ApiError | null>(null)
const usersLoading = ref(true)
const savingUserId = ref<number | null>(null)

const health = ref<Health | null>(null)
const healthError = ref<ApiError | null>(null)

const settings = reactive({
  retrieval_mode: 'hybrid' as UserRole | string,
  top_k: 5,
  chunk_size: 800,
  chunk_overlap: 120,
  registration_open: true,
})
const settingsLoaded = ref(false)
const settingsError = ref<ApiError | null>(null)
const settingsSaving = ref(false)
const reseeding = ref(false)

const usersTotalPages = computed(() => Math.max(1, Math.ceil(usersTotal.value / usersPageSize.value)))

const statCells = computed(() => {
  const value = stats.value
  if (!value) return []
  return [
    { label: '用户', value: value.users, hint: '含管理员' },
    { label: '文档', value: value.documents, hint: `近 7 天 +${value.recent_7d.documents}` },
    { label: '片段', value: value.chunks, hint: '已向量化' },
    { label: '会话', value: value.conversations, hint: '未删除' },
    { label: '消息', value: value.messages, hint: `近 7 天 +${value.recent_7d.messages}` },
    { label: '评测运行', value: value.eval_runs, hint: '全部模式' },
  ]
})

async function loadStats(): Promise<void> {
  statsLoading.value = true
  try {
    stats.value = await adminApi.stats()
    statsError.value = null
  } catch (error) {
    statsError.value = toApiError(error)
  } finally {
    statsLoading.value = false
  }
}

async function loadUsers(page = usersPage.value): Promise<void> {
  usersLoading.value = true
  try {
    const result = await adminApi.users({
      page,
      page_size: usersPageSize.value,
      q: usersQuery.value.trim() || undefined,
    })
    users.value = result.items
    usersTotal.value = result.total
    usersPage.value = result.page
    usersError.value = null
  } catch (error) {
    usersError.value = toApiError(error)
  } finally {
    usersLoading.value = false
  }
}

async function loadSettings(): Promise<void> {
  try {
    const raw = await adminApi.settings()
    settings.retrieval_mode = String(raw.retrieval_mode ?? 'hybrid')
    settings.top_k = Number(raw.top_k ?? 5)
    settings.chunk_size = Number(raw.chunk_size ?? 800)
    settings.chunk_overlap = Number(raw.chunk_overlap ?? 120)
    settings.registration_open = Boolean(raw.registration_open ?? true)
    settingsLoaded.value = true
    settingsError.value = null
  } catch (error) {
    settingsError.value = toApiError(error)
  }
}

async function loadHealth(): Promise<void> {
  try {
    health.value = await metaApi.health()
    healthError.value = null
  } catch (error) {
    healthError.value = toApiError(error)
  }
}

async function patchUser(user: User, patch: { is_active?: boolean; role?: UserRole }): Promise<void> {
  savingUserId.value = user.id
  const snapshot = { ...user }
  try {
    const updated = await adminApi.updateUser(user.id, patch)
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) users.value[index] = { ...users.value[index], ...updated }
    ElMessage.success(`已更新 ${updated.email}`)
    void loadStats()
  } catch {
    // 回滚本地状态：接口失败时不能让界面显示"已改"
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) users.value[index] = { ...snapshot }
  } finally {
    savingUserId.value = null
  }
}

async function onToggleActive(user: User, value: boolean): Promise<void> {
  await patchUser(user, { is_active: value })
}

async function onRoleChange(user: User, value: string): Promise<void> {
  await patchUser(user, { role: value as UserRole })
}

async function saveSettings(): Promise<void> {
  settingsSaving.value = true
  try {
    const raw = await adminApi.saveSettings({
      retrieval_mode: settings.retrieval_mode,
      top_k: settings.top_k,
      chunk_size: settings.chunk_size,
      chunk_overlap: settings.chunk_overlap,
      registration_open: settings.registration_open,
    })
    settings.retrieval_mode = String(raw.retrieval_mode ?? settings.retrieval_mode)
    settings.top_k = Number(raw.top_k ?? settings.top_k)
    settings.chunk_size = Number(raw.chunk_size ?? settings.chunk_size)
    settings.chunk_overlap = Number(raw.chunk_overlap ?? settings.chunk_overlap)
    settings.registration_open = Boolean(raw.registration_open ?? settings.registration_open)
    ElMessage.success('设置已保存')
  } catch (error) {
    settingsError.value = toApiError(error)
  } finally {
    settingsSaving.value = false
  }
}

async function reseed(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '会重新灌入种子文档与评测数据集（幂等）。你手工上传的文档不会被删除，确认继续？',
      '重新灌种子数据',
      { confirmButtonText: '执行', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  reseeding.value = true
  try {
    await adminApi.reseed()
    ElMessage.success('种子数据已重新灌入')
    await Promise.all([loadStats(), loadUsers(1)])
  } catch (error) {
    statsError.value = toApiError(error)
  } finally {
    reseeding.value = false
  }
}

onMounted(() => {
  void Promise.all([loadStats(), loadUsers(1), loadSettings(), loadHealth()])
})
</script>

<template>
  <div class="admin">
    <header class="pagehead">
      <div class="stack stack--gap">
        <span class="micro">管理台</span>
        <h1 class="page-title">系统概览与设置</h1>
        <p class="lede">仅管理员可见。设置项写入 app_settings，检索参数与注册开关会立即影响所有用户的请求。</p>
      </div>
      <div class="row row--gap">
        <button class="btn" type="button" :disabled="reseeding" @click="reseed()">
          {{ reseeding ? '灌入中…' : '重新灌种子数据' }}
        </button>
        <button class="btn" type="button" @click="loadStats()">刷新统计</button>
      </div>
    </header>

    <!-- 统计 -->
    <ErrorState v-if="statsError" :error="statsError" title="统计加载失败" @retry="loadStats()" />

    <section v-else class="stats">
      <div v-if="statsLoading" class="stats__grid">
        <div v-for="index in 6" :key="index" class="stat">
          <span class="skel skel-line" style="width: 48px" />
          <span class="skel" style="width: 64px; height: 26px" />
        </div>
      </div>
      <div v-else class="stats__grid">
        <div v-for="cell in statCells" :key="cell.label" class="stat">
          <span class="micro">{{ cell.label }}</span>
          <strong class="num">{{ formatCount(cell.value) }}</strong>
          <span class="stat__hint num">{{ cell.hint }}</span>
        </div>
      </div>
    </section>

    <!-- 运行信息 -->
    <section class="runtime">
      <span class="micro">运行信息</span>
      <div v-if="health" class="runtime__items">
        <span class="badge">version {{ health.version }}</span>
        <span class="badge" :class="health.db === 'ok' ? 'badge--ok' : 'badge--err'">db {{ health.db }}</span>
        <span class="badge badge--accent">llm {{ health.llm_provider }}</span>
        <span class="badge">status {{ health.status }}</span>
      </div>
      <span v-else-if="healthError" class="dim">{{ healthError.message }}</span>
      <span v-else class="dim">检查中…</span>
    </section>

    <!-- 用户表 -->
    <section class="panel">
      <header class="panel__head">
        <span class="panel__title">用户</span>
        <div class="row row--gap">
          <input
            v-model="usersQuery"
            class="input users__search"
            type="search"
            placeholder="邮箱或昵称"
            @keyup.enter="loadUsers(1)"
          />
          <button class="btn btn--sm" type="button" @click="loadUsers(1)">搜索</button>
        </div>
      </header>

      <div v-if="usersLoading" class="panel__body">
        <span v-for="index in 5" :key="index" class="skel skel-line" style="width: 100%" />
      </div>

      <ErrorState
        v-else-if="usersError"
        :error="usersError"
        title="用户列表加载失败"
        @retry="loadUsers(usersPage)"
      />

      <div v-else-if="users.length === 0" class="panel__body">
        <p class="muted">没有匹配的用户。</p>
      </div>

      <div v-else class="tbl-wrap">
        <el-table :data="users" style="width: 100%">
          <el-table-column label="ID" width="64" align="right">
            <template #default="{ row }"><span class="num dim">{{ row.id }}</span></template>
          </el-table-column>
          <el-table-column label="邮箱" min-width="220">
            <template #default="{ row }"><span class="num">{{ row.email }}</span></template>
          </el-table-column>
          <el-table-column label="昵称" min-width="150">
            <template #default="{ row }">{{ row.display_name }}</template>
          </el-table-column>
          <el-table-column label="角色" width="140">
            <template #default="{ row }">
              <el-select
                :model-value="row.role"
                size="small"
                :disabled="savingUserId === row.id"
                @update:model-value="(value: string) => onRoleChange(row, value)"
              >
                <el-option label="user" value="user" />
                <el-option label="admin" value="admin" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="启用" width="96">
            <template #default="{ row }">
              <el-switch
                :model-value="row.is_active"
                :loading="savingUserId === row.id"
                @update:model-value="(value: boolean) => onToggleActive(row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="150">
            <template #default="{ row }"><span class="num dim">{{ formatDateTime(row.created_at) }}</span></template>
          </el-table-column>
        </el-table>
      </div>

      <div class="panel__body pager">
        <span class="micro num">共 {{ usersTotal }} 个用户 · 第 {{ usersPage }} / {{ usersTotalPages }} 页</span>
        <div class="row row--gap">
          <button class="btn btn--sm" type="button" :disabled="usersPage <= 1" @click="loadUsers(usersPage - 1)">上一页</button>
          <button
            class="btn btn--sm"
            type="button"
            :disabled="usersPage >= usersTotalPages"
            @click="loadUsers(usersPage + 1)"
          >
            下一页
          </button>
        </div>
      </div>
    </section>

    <!-- 设置 -->
    <section class="panel">
      <header class="panel__head">
        <span class="panel__title">检索与注册设置</span>
        <span class="micro">PUT /api/v1/admin/settings</span>
      </header>

      <ErrorState v-if="settingsError" :error="settingsError" title="设置操作失败" @retry="loadSettings()" />

      <div v-else-if="!settingsLoaded" class="panel__body">
        <span v-for="index in 4" :key="index" class="skel skel-line" style="width: 100%" />
      </div>

      <form v-else class="panel__body settings" @submit.prevent="saveSettings">
        <div class="settings__grid">
          <label class="field">
            <span class="field__label">retrieval_mode</span>
            <select v-model="settings.retrieval_mode" class="select">
              <option value="hybrid">hybrid（向量 + 关键词 RRF）</option>
              <option value="vector">vector（纯向量）</option>
              <option value="keyword">keyword（纯关键词）</option>
            </select>
            <span class="field__hint">新会话提问时的默认检索通道。</span>
          </label>

          <label class="field">
            <span class="field__label">top_k</span>
            <input v-model.number="settings.top_k" class="input num" type="number" min="1" max="50" />
            <span class="field__hint">每次检索返回的片段数。</span>
          </label>

          <label class="field">
            <span class="field__label">chunk_size</span>
            <input v-model.number="settings.chunk_size" class="input num" type="number" min="100" max="4000" />
            <span class="field__hint">切分目标字符数，影响新上传文档。</span>
          </label>

          <label class="field">
            <span class="field__label">chunk_overlap</span>
            <input v-model.number="settings.chunk_overlap" class="input num" type="number" min="0" max="1000" />
            <span class="field__hint">相邻片段的重叠字符数。</span>
          </label>
        </div>

        <label class="switchrow">
          <input v-model="settings.registration_open" type="checkbox" class="switchrow__box" />
          <span class="stack">
            <strong>开放注册</strong>
            <span class="field__hint">关闭后 /auth/register 返回 403，登录页的注册入口也会禁用。</span>
          </span>
        </label>

        <div class="row row--gap settings__actions">
          <button class="btn btn--primary" type="submit" :disabled="settingsSaving">
            {{ settingsSaving ? '保存中…' : '保存设置' }}
          </button>
          <button class="btn" type="button" @click="loadSettings()">放弃修改</button>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.admin {
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
  flex-wrap: wrap;
}

/* ------------------------------ 统计卡 ------------------------------ */
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
  font-size: var(--fs-26);
  font-weight: var(--fw-semi);
  line-height: 1.1;
}

.stat__hint {
  font-size: var(--fs-11);
  color: var(--c-ink-3);
}

/* ------------------------------ 运行信息 ------------------------------ */
.runtime {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--c-line);
  background: var(--c-sunken);
  flex-wrap: wrap;
}

.runtime__items {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
}

.runtime__items .badge {
  background: var(--c-surface);
}

/* -------------------------------- 表格 -------------------------------- */
.users__search {
  width: 200px;
  height: 28px;
  min-height: 28px;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  padding-top: var(--sp-3);
  flex-wrap: wrap;
}

/* -------------------------------- 设置 -------------------------------- */
.settings {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
}

.settings__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-4) var(--sp-5);
  max-width: 720px;
}

.switchrow {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  max-width: 720px;
  padding: var(--sp-3);
  border: 1px solid var(--c-line);
  background: var(--c-sunken);
  cursor: pointer;
}

.switchrow__box {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  accent-color: var(--c-accent);
}

.settings__actions {
  padding-top: var(--sp-1);
}

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
  .stats__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stat:nth-child(2n + 1) {
    border-left: none;
  }

  .stat:nth-child(n + 3) {
    border-top: 1px solid var(--c-line);
  }

  .settings__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .users__search {
    width: 140px;
  }
}
</style>
