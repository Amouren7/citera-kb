/** 主题：默认跟随系统，用户显式切换后持久化到 localStorage（键 citera.theme）。 */

import { computed, ref } from 'vue'
import { getStoredTheme, setStoredTheme } from '@/api'

export type ThemeMode = 'light' | 'dark'

const mode = ref<ThemeMode>(resolveInitialMode())
let mediaBound = false

function resolveInitialMode(): ThemeMode {
  const stored = getStoredTheme()
  if (stored) return stored
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function apply(next: ThemeMode): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = next
  document.documentElement.style.colorScheme = next
}

export function initTheme(): void {
  apply(mode.value)
  if (mediaBound || typeof window === 'undefined' || !window.matchMedia) return
  mediaBound = true
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  query.addEventListener('change', (event) => {
    if (getStoredTheme()) return // 用户已显式选择，不再跟随系统
    mode.value = event.matches ? 'dark' : 'light'
    apply(mode.value)
  })
}

export function useTheme() {
  const isDark = computed(() => mode.value === 'dark')

  function setMode(next: ThemeMode): void {
    mode.value = next
    setStoredTheme(next)
    apply(next)
  }

  function toggle(): void {
    setMode(mode.value === 'dark' ? 'light' : 'dark')
  }

  return { mode, isDark, setMode, toggle }
}
