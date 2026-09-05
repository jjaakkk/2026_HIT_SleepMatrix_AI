import { createApp } from 'vue'
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/inter/opsz.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
// MiSans（小米，免费商用）——与 Inter 几何气质匹配的中文字体；
// cn-font-split 按 unicode-range 切块，浏览器按需加载。字重已重映射为 400/500/600。
import './assets/fonts/misans/MiSans-400.css'
import './assets/fonts/misans/MiSans-500.css'
import './assets/fonts/misans/MiSans-600.css'
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')
