import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ElementPlus, { ElMessage } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { setErrorNotifier, setUnauthorizedHandler } from '@/api'
import { initTheme } from '@/composables/useTheme'
import router from '@/router'
import App from '@/App.vue'

import 'element-plus/dist/index.css'
import '@/styles/base.css'
import '@/styles/element-overrides.css'

initTheme()

// 契约 §7.1：错误统一用 ElMessage 提示（文案分流在 src/api/errors.ts 里做）
setErrorNotifier(({ message }) => {
  ElMessage({ type: 'error', message, duration: 4200, grouping: true, showClose: true })
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 契约 §7.1：401（unauthorized / token_expired）→ 清 token 跳 /login?redirect=
setUnauthorizedHandler(() => {
  const current = router.currentRoute.value
  if (current.name === 'login') return
  ElMessage.closeAll()
  void router.replace({ name: 'login', query: { redirect: current.fullPath } })
})

app.mount('#app')
