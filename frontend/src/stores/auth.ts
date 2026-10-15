import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  authApi,
  clearToken,
  getToken,
  metaApi,
  setToken,
  toApiError,
  type ApiError,
  type AppMeta,
  type AuthResult,
  type User,
} from '@/api'

/** 认证与全局元信息（契约 §7.1：token 存 Pinia + localStorage 键 citera.token）。 */
export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(getToken())
  const meta = ref<AppMeta | null>(null)
  const metaError = ref<ApiError | null>(null)
  const initializing = ref(false)
  const bootstrapped = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  const isAdmin = computed(() => user.value?.role === 'admin')
  const displayName = computed(() => user.value?.display_name || user.value?.email || '未登录')
  const registrationOpen = computed(() => meta.value?.registration_open ?? true)

  function applySession(payload: AuthResult): User {
    token.value = payload.access_token
    setToken(payload.access_token)
    user.value = payload.user
    bootstrapped.value = true
    return payload.user
  }

  function clearSession(): void {
    token.value = null
    user.value = null
    clearToken()
  }

  async function login(email: string, password: string): Promise<User> {
    const payload = await authApi.login({ email: email.trim().toLowerCase(), password })
    return applySession(payload)
  }

  async function register(email: string, password: string, displayName: string): Promise<User> {
    const payload = await authApi.register({
      email: email.trim().toLowerCase(),
      password,
      display_name: displayName.trim(),
    })
    return applySession(payload)
  }

  function logout(): void {
    clearSession()
  }

  /** 冷启动：有 token 就拉一次 /auth/me，401 则清掉本地会话。 */
  async function bootstrap(): Promise<void> {
    if (bootstrapped.value || initializing.value) return
    initializing.value = true
    try {
      const stored = getToken()
      token.value = stored
      if (stored) {
        try {
          user.value = await authApi.me()
        } catch (error) {
          if (toApiError(error).isAuthError) clearSession()
        }
      }
    } finally {
      bootstrapped.value = true
      initializing.value = false
    }
  }

  async function loadMeta(): Promise<void> {
    if (meta.value) return
    try {
      meta.value = await metaApi.meta()
      metaError.value = null
    } catch (error) {
      metaError.value = toApiError(error)
    }
  }

  async function updateProfile(displayName: string): Promise<User> {
    const updated = await authApi.updateMe({ display_name: displayName })
    user.value = updated
    return updated
  }

  return {
    user,
    token,
    meta,
    metaError,
    initializing,
    bootstrapped,
    isAuthenticated,
    isAdmin,
    displayName,
    registrationOpen,
    applySession,
    clearSession,
    login,
    register,
    logout,
    bootstrap,
    loadMeta,
    updateProfile,
  }
})
