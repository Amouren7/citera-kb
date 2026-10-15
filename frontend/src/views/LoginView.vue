<script setup lang="ts">
/**
 * 登录 / 注册同页（契约 §7.1）。视觉：右侧直角表单，左侧宣言 + 可点的引用角标演示
 * （记忆点 3，DESIGN §6）——没有居中白卡、没有插图、没有渐变。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { errorMessage, type Citation } from '@/api'
import CitationPopover from '@/components/CitationPopover.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

type Mode = 'login' | 'register'
const mode = ref<Mode>('login')

const form = reactive({ email: '', password: '', displayName: '' })
const touched = reactive({ email: false, password: false, displayName: false })
const submitting = ref(false)
const submitError = ref('')

const redirect = computed(() => {
  const value = route.query.redirect
  return typeof value === 'string' && value.startsWith('/') ? value : '/chat'
})

const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()))
const passwordValid = computed(() => form.password.length >= 8 && /[A-Za-z]/.test(form.password) && /\d/.test(form.password))
const displayNameValid = computed(() => {
  const length = form.displayName.trim().length
  return length >= 1 && length <= 64
})

const emailError = computed(() => (touched.email && !emailValid.value ? '请输入有效的邮箱地址' : ''))
const passwordError = computed(() => {
  if (!touched.password) return ''
  if (form.password.length < 8) return '密码至少 8 位'
  if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) return '密码需同时包含字母与数字'
  return ''
})
const displayNameError = computed(() =>
  touched.displayName && !displayNameValid.value ? '昵称需为 1 到 64 个字符' : '',
)

const canSubmit = computed(() => {
  const base = emailValid.value && passwordValid.value
  return mode.value === 'login' ? base : base && displayNameValid.value
})

onMounted(() => {
  void auth.loadMeta()
})

watch(mode, () => {
  submitError.value = ''
  touched.email = false
  touched.password = false
  touched.displayName = false
})

async function submit(): Promise<void> {
  touched.email = true
  touched.password = true
  touched.displayName = true
  submitError.value = ''
  if (!canSubmit.value || submitting.value) return

  submitting.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.email, form.password)
    } else {
      await auth.register(form.email, form.password, form.displayName)
    }
    await router.replace(redirect.value)
  } catch (error) {
    submitError.value = errorMessage(error)
  } finally {
    submitting.value = false
  }
}

function useDemo(kind: 'demo' | 'admin'): void {
  mode.value = 'login'
  form.email = kind === 'demo' ? 'demo@citera.dev' : 'admin@citera.dev'
  form.password = kind === 'demo' ? 'demo1234' : 'admin1234'
  touched.email = false
  touched.password = false
  submitError.value = ''
}

/* ---- 引用角标演示：直接复用产品里的来源卡组件 ---- */
const demoCitation: Citation = {
  chunk_id: 7,
  document_id: 2,
  document_title: '产品保修条款',
  ord: 3,
  heading: '三、保修期限',
  snippet:
    '整机保修期为自签收之日起 12 个月。主板、显示屏等核心部件保修期为 24 个月；电池、充电器等易损耗配件保修期为 6 个月。',
  score: 0.92,
  retrieval: 'hybrid',
  rank: 1,
}
const demoOpen = ref(false)
const demoAnchor = ref<DOMRect | null>(null)

function toggleDemo(event: MouseEvent): void {
  const element = event.currentTarget as HTMLElement
  if (demoOpen.value) {
    demoOpen.value = false
    return
  }
  demoAnchor.value = element.getBoundingClientRect()
  demoOpen.value = true
}
</script>

<template>
  <div class="auth">
    <!-- 左：宣言 + 引用演示 -->
    <section class="auth__left">
      <header class="auth__brand">
        <span class="auth__mark">C</span>
        <div class="stack">
          <strong>Citera</strong>
          <span class="micro">溯源知识库</span>
        </div>
      </header>

      <h1 class="auth__title">
        把散落的资料<br />变成<em>能点回原文</em>的回答
      </h1>

      <p class="auth__lede">
        做 AI 应用最怕答了没法核实。所以这个系统把「引用可溯源」当第一目标：每条回答都标出它依据的文档、章节与块序号，点一下就能回原文核对。
      </p>

      <div class="auth__demo">
        <span class="micro">试试这个角标</span>
        <p class="auth__demotext">
          整机保修期为自签收之日起 12 个月。<button class="cite" type="button" @click="toggleDemo">1</button>
        </p>
        <CitationPopover
          v-if="demoOpen"
          :citation="demoCitation"
          :index="1"
          :anchor="demoAnchor"
          :show-link="false"
          @close="demoOpen = false"
        />
      </div>

      <ul class="auth__facts">
        <li><span class="mono">01</span> 混合检索（向量 + 关键词，RRF 融合）</li>
        <li><span class="mono">02</span> 流式回答逐句挂引用角标</li>
        <li><span class="mono">03</span> 离线可用：无模型 Key 时由检索结果受控合成</li>
      </ul>
    </section>

    <!-- 右：表单 -->
    <section class="auth__right">
      <div class="auth__panel">
        <div class="authtabs" role="tablist">
          <button
            class="authtab"
            :class="{ 'is-active': mode === 'login' }"
            type="button"
            role="tab"
            :aria-selected="mode === 'login'"
            @click="mode = 'login'"
          >
            登录
          </button>
          <button
            class="authtab"
            :class="{ 'is-active': mode === 'register' }"
            type="button"
            role="tab"
            :aria-selected="mode === 'register'"
            :disabled="!auth.registrationOpen"
            @click="mode = 'register'"
          >
            注册
          </button>
        </div>

        <form class="auth__form" novalidate @submit.prevent="submit">
          <div v-if="mode === 'register'" class="field">
            <label class="field__label" for="auth-name">昵称</label>
            <input
              id="auth-name"
              v-model="form.displayName"
              class="input"
              autocomplete="nickname"
              maxlength="64"
              :aria-invalid="Boolean(displayNameError)"
              @blur="touched.displayName = true"
            />
            <span v-if="displayNameError" class="field__error">{{ displayNameError }}</span>
            <span v-else class="field__hint">会显示在引用与评测记录旁</span>
          </div>

          <div class="field">
            <label class="field__label" for="auth-email">邮箱</label>
            <input
              id="auth-email"
              v-model="form.email"
              class="input"
              type="email"
              autocomplete="email"
              :aria-invalid="Boolean(emailError)"
              @blur="touched.email = true"
            />
            <span v-if="emailError" class="field__error">{{ emailError }}</span>
          </div>

          <div class="field">
            <label class="field__label" for="auth-password">密码</label>
            <input
              id="auth-password"
              v-model="form.password"
              class="input"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              :aria-invalid="Boolean(passwordError)"
              @blur="touched.password = true"
            />
            <span v-if="passwordError" class="field__error">{{ passwordError }}</span>
            <span v-else-if="mode === 'register'" class="field__hint">至少 8 位，且同时包含字母与数字</span>
          </div>

          <div v-if="submitError" class="errbox" role="alert">
            <div class="stack stack--gap grow">
              <span class="errbox__code">登录失败</span>
              <span>{{ submitError }}</span>
            </div>
          </div>

          <button class="btn btn--primary btn--lg btn--block" type="submit" :disabled="submitting">
            {{ submitting ? '处理中…' : mode === 'login' ? '登录' : '创建账号并登录' }}
          </button>

          <p class="auth__switch">
            <template v-if="mode === 'login'">还没有账号？<button class="linklike" type="button" :disabled="!auth.registrationOpen" @click="mode = 'register'">注册一个</button></template>
            <template v-else>已有账号？<button class="linklike" type="button" @click="mode = 'login'">去登录</button></template>
          </p>
        </form>

        <div class="auth__demo-accounts">
          <span class="micro">演示账号（点一下自动填入）</span>
          <div class="row row--gap">
            <button class="btn btn--sm" type="button" @click="useDemo('demo')">演示用户 demo@citera.dev</button>
            <button class="btn btn--sm" type="button" @click="useDemo('admin')">管理员 admin@citera.dev</button>
          </div>
          <p v-if="!auth.registrationOpen" class="field__hint">当前未开放注册（registration_open=false）。</p>
        </div>
      </div>

      <p class="auth__foot micro">
        <RouterLink to="/chat">继续前往问答</RouterLink>
      </p>
    </section>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: 1.15fr 0.85fr;
  min-height: 100dvh;
  background: var(--c-paper);
}

/* ------------------------------- 左侧 ------------------------------- */
.auth__left {
  display: flex;
  flex-direction: column;
  gap: var(--sp-6);
  padding: var(--sp-9) var(--sp-8);
  border-right: 1px solid var(--c-line);
  background: var(--c-surface);
}

.auth__brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.auth__mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  background: var(--c-accent);
  color: var(--c-accent-ink);
  font-family: var(--font-mono);
  font-size: var(--fs-16);
  font-weight: var(--fw-semi);
}

.auth__brand strong {
  font-size: var(--fs-16);
}

.auth__title {
  font-size: var(--fs-46);
  line-height: 1.12;
  letter-spacing: -0.03em;
  font-weight: var(--fw-semi);
  max-width: 18ch;
}

.auth__title em {
  font-style: normal;
  color: var(--c-accent);
  box-shadow: inset 0 -0.22em 0 var(--c-accent-wash);
}

.auth__lede {
  max-width: 46ch;
  color: var(--c-ink-2);
  font-size: var(--fs-14);
  line-height: 1.8;
}

.auth__demo {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-4);
  border: 1px solid var(--c-line);
  border-left: 2px solid var(--c-accent);
  background: var(--c-sunken);
  max-width: 46ch;
}

.auth__demotext {
  font-size: var(--fs-14);
  line-height: 1.8;
}

.auth__facts {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin-top: auto;
  color: var(--c-ink-2);
  font-size: var(--fs-13);
}

.auth__facts li {
  display: flex;
  gap: var(--sp-3);
}

.auth__facts .mono {
  color: var(--c-accent);
  font-size: var(--fs-11);
}

/* ------------------------------- 右侧 ------------------------------- */
.auth__right {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--sp-5);
  padding: var(--sp-8) var(--sp-7);
}

.auth__panel {
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  max-width: 380px;
  width: 100%;
}

.authtabs {
  display: flex;
  border-bottom: 1px solid var(--c-line);
}

.authtab {
  flex: 1 1 0;
  padding: var(--sp-2) 0;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--c-ink-3);
  font-size: var(--fs-14);
  cursor: pointer;
  transition: color var(--dur-1) var(--ease), border-color var(--dur-1) var(--ease);
}

.authtab:hover:not(:disabled) {
  color: var(--c-ink);
}

.authtab.is-active {
  color: var(--c-ink);
  border-bottom-color: var(--c-accent);
  font-weight: var(--fw-medium);
}

.authtab:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.auth__form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.auth__switch {
  font-size: var(--fs-13);
  color: var(--c-ink-2);
}

.linklike {
  border: 0;
  background: none;
  padding: 0;
  color: var(--c-accent);
  cursor: pointer;
  font-size: inherit;
  border-bottom: 1px solid var(--c-accent-line);
}

.linklike:disabled {
  color: var(--c-ink-3);
  border-bottom-color: var(--c-line-2);
  cursor: not-allowed;
}

.auth__demo-accounts {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding-top: var(--sp-4);
  border-top: 1px solid var(--c-line);
}

.auth__demo-accounts .row {
  flex-wrap: wrap;
}

.auth__foot {
  text-align: center;
}

/* ------------------------------ 响应式 ------------------------------ */
@media (max-width: 1024px) {
  .auth {
    grid-template-columns: 1fr;
  }

  .auth__left {
    border-right: none;
    border-bottom: 1px solid var(--c-line);
    padding: var(--sp-7) var(--sp-5);
    gap: var(--sp-5);
  }

  .auth__title {
    font-size: var(--fs-34);
  }

  .auth__facts {
    margin-top: var(--sp-2);
  }

  .auth__right {
    padding: var(--sp-6) var(--sp-5) var(--sp-8);
  }

  .auth__panel {
    max-width: none;
  }
}
</style>
