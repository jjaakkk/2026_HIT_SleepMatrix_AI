import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base './'：构建产物可在任意静态服务器/本地文件夹直接打开（答辩现场友好）
export default defineConfig({
  plugins: [vue()],
  base: './',
})
