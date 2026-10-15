/**
 * token 的唯一读写点。契约 §7.1：token 存 Pinia + localStorage（键名 citera.token）。
 * 放在 api 层是为了让 axios 拦截器不依赖 Pinia（避免循环依赖），Pinia store 只做镜像。
 */

export const TOKEN_KEY = 'citera.token'
export const THEME_KEY = 'citera.theme'

function storage(): Storage | null {
  try {
    if (typeof localStorage === 'undefined') return null
    return localStorage
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null
}

export function setToken(token: string): void {
  storage()?.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  storage()?.removeItem(TOKEN_KEY)
}

export function getStoredTheme(): 'light' | 'dark' | null {
  const value = storage()?.getItem(THEME_KEY)
  return value === 'light' || value === 'dark' ? value : null
}

export function setStoredTheme(theme: 'light' | 'dark'): void {
  storage()?.setItem(THEME_KEY, theme)
}
