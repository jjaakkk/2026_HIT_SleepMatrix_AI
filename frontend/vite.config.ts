import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base './'：构建产物可在任意静态服务器/本地文件夹直接打开（答辩现场友好）
//
// /api 代理 → 后端算法服务（backend/app.py，默认 127.0.0.1:5000）。
// 后端未启动时前端优雅降级为本地记录标签 + 内置契约。
// 生产环境可通过 VITE_API_BASE 指向真实 API 地址。
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:5000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [vue()],
  base: './',
  server: { proxy: apiProxy },
  preview: { proxy: apiProxy },
})
