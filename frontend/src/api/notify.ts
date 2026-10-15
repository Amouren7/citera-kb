/**
 * 错误提示的可插拔出口：api 层不直接依赖 UI 库（main.ts 注入 ElMessage）。
 * 便于单测与替换。
 */

export interface ErrorNotice {
  code: string
  message: string
  status: number
}

export type ErrorNotifier = (notice: ErrorNotice) => void

let notifier: ErrorNotifier | null = null

export function setErrorNotifier(fn: ErrorNotifier | null): void {
  notifier = fn
}

export function notifyError(notice: ErrorNotice): void {
  if (notifier) notifier(notice)
}
