<script setup lang="ts">
/**
 * 应用外壳：左侧直角仪表盘导航轨（非 el-menu）+ 顶部 hairline 工具栏。
 * 导航用 mono 两位序号编号，与产品里"文档块 ord"的概念同构（DESIGN §6/§7）。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { metaApi, type Health } from '@/api'
import { useTheme } from '@/composables/useTheme'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { isDark, toggle } = useTheme()

interface NavItem {
  ord: string
  label: string
  name: string
  match: string
  adminOnly?: boolean
}

const allNav: NavItem[] = [
  { ord: '01', label: '问答', name: 'chat', match: '/chat' },
  { ord: '02', label: '文档库', name: 'documents', match: '/documents' },
  { ord: '03', label: '评测', name: 'evaluation', match: '/evaluation' },
  { ord: '04', label: '管理台', name: 'admin', match: '/admin', adminOnly: true },
]

const navItems = computed(() => allNav.filter((item) => !item.adminOnly || auth.isAdmin))

function isActive(item: NavItem): boolean {
  return route.path === item.match || route.path.startsWith(`${item.match}/`)
}

const crumb = computed(() => {
  const nav = allNav.find((item) => isActive(item))
  const title = typeof route.meta.title === 'string' ? route.meta.title : ''
  return nav ? `${nav.label} / ${title}` : title
})

const health = ref<Health | null>(null)
const healthDown = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

async function loadHealth(): Promise<void> {
  try {
    health.value = await metaApi.health()
    healthDown.value = false
  } catch {
    healthDown.value = true
  }
}

onMounted(() => {
  void loadHealth()
  void auth.loadMeta()
  timer = setInterval(() => void loadHealth(), 60_000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const healthLabel = computed(() => {
  if (healthDown.value) return 'API 不可达'
  if (!health.value) return '检查中'
  return `LLM ${health.value.llm_provider} · DB ${health.value.db}`
})

const healthTone = computed(() => {
  if (healthDown.value) return 'badge badge--err'
  if (!health.value) return 'badge'
  return health.value.db === 'ok' ? 'badge badge--ok' : 'badge badge--warn'
})

const nicknameDialog = ref(false)
const nicknameDraft = ref('')
const nicknameSaving = ref(false)

function openNickname(): void {
  nicknameDraft.value = auth.user?.display_name ?? ''
  nicknameDialog.value = true
}

async function saveNickname(): Promise<void> {
  const value = nicknameDraft.value.trim()
  if (value.length === 0) {
    ElMessage.warning('昵称不能为空')
    return
  }
  nicknameSaving.value = true
  try {
    await auth.updateProfile(value)
    ElMessage.success('昵称已更新')
    nicknameDialog.value = false
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '更新失败')
  } finally {
    nicknameSaving.value = false
  }
}

async function onUserCommand(command: string): Promise<void> {
  if (command === 'nickname') {
    openNickname()
    return
  }
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('退出后需要重新登录，确认退出？', '退出登录', {
        confirmButtonText: '退出',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
    auth.logout()
    void router.push({ name: 'login' })
  }
}
</script>

<template>
  <div class="shell">
    <aside class="rail">
      <RouterLink class="brand" :to="{ name: 'chat' }">
        <span class="brand__mark">C</span>
        <span class="brand__text">
          <strong>Citera</strong>
          <span class="micro">溯源知识库</span>
        </span>
      </RouterLink>

      <nav class="rail__nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          class="navitem"
          :class="{ 'is-active': isActive(item) }"
          :to="{ name: item.name }"
        >
          <span class="navitem__ord num">{{ item.ord }}</span>
          <span class="navitem__label">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="rail__foot">
        <button class="btn btn--quiet btn--block btn--sm" type="button" @click="toggle()">
          {{ isDark ? '浅色主题' : '深色主题' }}
        </button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar__left">
          <span class="micro topbar__brand">Citera</span>
          <span class="topbar__crumb">{{ crumb }}</span>
        </div>
        <div class="topbar__right">
          <span :class="healthTone" :title="healthLabel">
            <i class="dot" />
            <span class="num">{{ healthLabel }}</span>
          </span>
          <span class="micro topbar__version">v{{ auth.meta?.version ?? '0.1.0' }}</span>

          <el-dropdown trigger="click" @command="onUserCommand">
            <button class="userbtn" type="button">
              <span class="userbtn__name truncate">{{ auth.displayName }}</span>
              <span class="micro">{{ auth.isAdmin ? 'ADMIN' : 'USER' }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ auth.user?.email }}</el-dropdown-item>
                <el-dropdown-item command="nickname">修改昵称</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <slot />
      </main>
    </div>

    <el-dialog v-model="nicknameDialog" title="修改昵称" width="360px" append-to-body>
      <div class="field">
        <label class="field__label" for="nickname-input">显示名</label>
        <input id="nickname-input" v-model="nicknameDraft" class="input" maxlength="64" />
        <span class="field__hint">1 到 64 个字符，会显示在引用与评测记录旁。</span>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="nicknameDialog = false">取消</button>
        <button class="btn btn--primary" type="button" :disabled="nicknameSaving" @click="saveNickname()">
          {{ nicknameSaving ? '保存中' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: calc(var(--rail-w) + var(--rail-label-w)) 1fr;
  min-height: 100dvh;
  background: var(--c-paper);
}

/* ------------------------------- 导航轨 ------------------------------- */
.rail {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  padding: var(--sp-4) var(--sp-3);
  border-right: 1px solid var(--c-line);
  background: var(--c-surface);
  position: sticky;
  top: 0;
  height: 100dvh;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  border-bottom: none;
  color: var(--c-ink);
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  background: var(--c-accent);
  color: var(--c-accent-ink);
  font-family: var(--font-mono);
  font-size: var(--fs-16);
  font-weight: var(--fw-semi);
}

.brand__text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
  min-width: 0;
}

.brand__text strong {
  font-size: var(--fs-16);
  letter-spacing: -0.01em;
}

.rail__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.navitem {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-2);
  border: none;
  border-left: 2px solid transparent;
  color: var(--c-ink-2);
  transition: background var(--dur-1) var(--ease), color var(--dur-1) var(--ease);
}

.navitem:hover {
  background: var(--c-sunken);
  color: var(--c-ink);
}

.navitem.is-active {
  border-left-color: var(--c-accent);
  background: var(--c-accent-wash);
  color: var(--c-accent);
}

.navitem__ord {
  font-size: var(--fs-11);
  letter-spacing: var(--tracking-micro);
  color: currentColor;
  opacity: 0.75;
}

.navitem__label {
  font-size: var(--fs-13);
  font-weight: var(--fw-medium);
}

.rail__foot {
  margin-top: auto;
}

/* -------------------------------- 主区 -------------------------------- */
.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
  height: var(--topbar-h);
  padding: 0 var(--sp-5);
  border-bottom: 1px solid var(--c-line);
  background: var(--c-surface);
  position: sticky;
  top: 0;
  z-index: 20;
}

.topbar__left {
  display: flex;
  align-items: baseline;
  gap: var(--sp-3);
  min-width: 0;
}

.topbar__brand {
  color: var(--c-accent);
}

.topbar__crumb {
  font-size: var(--fs-13);
  color: var(--c-ink-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar__right {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.topbar__version {
  white-space: nowrap;
}

.userbtn {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  max-width: 190px;
  padding: 2px var(--sp-2);
  border: 1px solid var(--c-line);
  background: var(--c-surface);
  cursor: pointer;
  transition: background var(--dur-1) var(--ease);
}

.userbtn:hover {
  background: var(--c-sunken);
}

.userbtn__name {
  font-size: var(--fs-13);
  max-width: 170px;
}

.content {
  flex: 1 1 auto;
  min-width: 0;
  padding: var(--sp-5);
}

/* ------------------------------ 响应式 ------------------------------ */
@media (max-width: 768px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr auto;
  }

  .rail {
    order: 2;
    position: sticky;
    bottom: 0;
    top: auto;
    height: auto;
    flex-direction: row;
    align-items: center;
    gap: var(--sp-2);
    padding: var(--sp-1) var(--sp-2);
    border-right: none;
    border-top: 1px solid var(--c-line);
    z-index: 30;
  }

  .brand,
  .rail__foot {
    display: none;
  }

  .rail__nav {
    flex-direction: row;
    flex: 1 1 auto;
    justify-content: space-between;
  }

  .navitem {
    flex-direction: column;
    align-items: center;
    gap: 1px;
    flex: 1 1 0;
    padding: var(--sp-1);
    border-left: none;
    border-top: 2px solid transparent;
  }

  .navitem.is-active {
    border-left-color: transparent;
    border-top-color: var(--c-accent);
  }

  .main {
    order: 1;
  }

  .topbar {
    height: auto;
    padding: var(--sp-2) var(--sp-3);
    gap: var(--sp-2);
  }

  .topbar__version {
    display: none;
  }

  .content {
    padding: var(--sp-3);
  }
}
</style>
