import { ref } from 'vue';

/** 明暗主题：html[data-theme] 驱动 CSS 变量，localStorage 记忆 */
export function useTheme() {
  const theme = ref<'light' | 'dark'>(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  );

  function setTheme(t: 'light' | 'dark') {
    theme.value = t;
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem('sm-theme', t);
    } catch {
      /* 隐私模式下静默失败 */
    }
  }

  function toggle() {
    setTheme(theme.value === 'dark' ? 'light' : 'dark');
  }

  return { theme, setTheme, toggle };
}
