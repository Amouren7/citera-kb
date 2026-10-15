/** 断点判断（与 DESIGN-frontend §7 的 640/768/1024/1280 对齐）。 */

import { onScopeDispose, ref, type Ref } from 'vue'

export function useMediaQuery(query: string): Ref<boolean> {
  const matches = ref(false)
  if (typeof window === 'undefined' || !window.matchMedia) return matches

  const mql = window.matchMedia(query)
  matches.value = mql.matches
  const handler = (event: MediaQueryListEvent) => {
    matches.value = event.matches
  }
  mql.addEventListener('change', handler)
  onScopeDispose(() => mql.removeEventListener('change', handler))
  return matches
}

export function useIsCompact(): Ref<boolean> {
  return useMediaQuery('(max-width: 768px)')
}
