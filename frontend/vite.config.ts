import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  define: {
    // sockjs-client 是 CommonJS 包，内部用到了 Node 的 `global` 变量，
    // 浏览器里没有这个全局对象，会直接抛 "ReferenceError: global is not defined"
    // 导致路由懒加载整个失败（页面白屏）。映射到 globalThis 即可。
    global: 'globalThis',
  },
  optimizeDeps: {
    // Monaco 是 CJS/ESM 混合的大包，预构建一次避免开发时反复按需编译导致页面卡顿
    include: ['monaco-editor'],
  },
  build: {
    rollupOptions: {
      output: {
        // Monaco Editor 体积约 2MB，单独分包，避免拖慢首屏加载。
        // 注意：Vite 8（rolldown）里 manualChunks 只接受函数形式，
        // 教程里的对象写法（{ 'monaco-editor': [...] }）在当前版本会报类型错误。
        manualChunks(id: string) {
          if (id.includes('monaco-editor')) return 'monaco-editor'
          return undefined
        },
      },
    },
  },
})
