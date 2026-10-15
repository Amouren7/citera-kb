import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { citeraMockPlugin } from './mock/index.ts'

// 契约 §4：前端唯一出入是 src/api/**，基址由 VITE_API_BASE 决定。
// 本地开发默认 VITE_API_BASE=''（同源），由 mock 中间件接管 /api/*，因此不依赖后端进程。
// 后端就绪后把 .env.development 改成 VITE_API_BASE=http://localhost:8000 且 VITE_MOCK=false。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [vue(), citeraMockPlugin({ enabled: env.VITE_MOCK !== 'false' })],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      strictPort: true,
    },
    preview: {
      port: 4173,
      strictPort: true,
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      chunkSizeWarningLimit: 1400,
      // 注意：Vite 8 默认压缩器（oxc）在压缩阶段会把参数声明与函数体里的同名标识符改写错位，
      // 例如 `(perRun) => perRun.run_id` 被压成 `(perRun) => per_run.run_id`。
      // 根因是模板内联表达式里的箭头函数参数被改写（见 EvaluationView.vue 的 cellMap 注释），
      // 已在源码层面规避：模板里不再写这类闭包，改为 setup 里预摊平成 Map。
      // 因此这里保持默认压缩器即可，不需要换 terser/esbuild。
      rollupOptions: {
        output: {
          // Vite 8 / Rollup 5 只接受函数形式
          manualChunks(id: string) {
            if (id.includes('node_modules/echarts') || id.includes('node_modules\\echarts')) return 'echarts'
            if (id.includes('node_modules/element-plus') || id.includes('node_modules\\element-plus')) return 'element'
            return undefined
          },
        },
      },
    },
  }
})
