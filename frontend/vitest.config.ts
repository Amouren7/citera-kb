import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    // 用 jsdom 而不是 happy-dom：happy-dom 默认禁用 iframe 页面加载，
    // DOMPurify 3.x 在初始化沙箱文档时抛错后会**退化成原样返回**，
    // 于是"消毒"测试会假绿。jsdom 下 DOMPurify 走正常路径，测的才是真行为。
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    globals: true,
    restoreMocks: true,
    unstubGlobals: true,
    reporters: ['default'],
  },
})
