import { createApp } from 'vue'
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/inter/opsz.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import '@fontsource/noto-sans-sc/400.css'
import '@fontsource/noto-sans-sc/500.css'
import '@fontsource/noto-sans-sc/700.css'
import './style.css'
import App from './App.vue'

// 主题初始化：尊重系统偏好，允许用户覆盖（localStorage）
const saved = localStorage.getItem('sm-theme')
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
const initial = saved ?? (prefersDark ? 'dark' : 'light')
document.documentElement.dataset.theme = initial

createApp(App).mount('#app')
