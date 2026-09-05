<script setup lang="ts">
/**
 * 顶栏：品牌 + 系统状态 + 时钟 + 主题切换。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue';
import Icon from './ui/Icon.vue';
import UiBadge from './ui/UiBadge.vue';
import { useTheme } from '../composables/useTheme';

const props = defineProps<{
  /** 回放进行中（LIVE 脉冲） */
  playing: boolean;
  /** 使用内置模拟数据 */
  simulated: boolean;
}>();

const { theme, toggle } = useTheme();

const now = ref(new Date());
let timer = 0;
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => window.clearInterval(timer));

function clockText(): string {
  const d = now.value;
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
}
</script>

<template>
  <header class="topbar">
    <div class="left">
      <div class="mark" aria-hidden="true">
        <svg viewBox="0 0 28 28" fill="none">
          <defs>
            <linearGradient id="sm-brand" x1="4" y1="3" x2="24" y2="26" gradientUnits="userSpaceOnUse">
              <stop stop-color="var(--brand-from)" />
              <stop offset="1" stop-color="var(--brand-to)" />
            </linearGradient>
          </defs>
          <rect width="28" height="28" rx="8" fill="url(#sm-brand)" />
          <path
            d="M7.5 14.2c1.1-1.5 2-1.5 3.1 0s2 1.5 3.1 0 2-1.5 3.1 0 2 1.5 3.1 0"
            stroke="#fff"
            stroke-width="1.7"
            stroke-linecap="round"
            opacity="0.95"
          />
        </svg>
      </div>
      <div class="brand">
        <span class="name">SleepMatrix</span>
        <span class="sub">睡眠压力监测台</span>
      </div>
    </div>

    <div class="status">
      <UiBadge :pulse="playing" :variant="playing ? 'accent' : 'neutral'">
        {{ playing ? '正在回放' : '数据回放 · 历史记录' }}
      </UiBadge>
      <UiBadge v-if="simulated" variant="warning">演示模式 · 内置数据</UiBadge>
      <UiBadge variant="warning">气囊 · 模拟信号</UiBadge>
    </div>

    <div class="right">
      <span class="clock num" role="timer" aria-label="当前时间">{{ clockText() }}</span>
      <span class="divider" aria-hidden="true" />
      <button
        type="button"
        class="theme-btn"
        :aria-label="theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
        :title="theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
        @click="toggle"
      >
        <Transition name="theme-swap" mode="out-in">
          <Icon v-if="theme === 'dark'" key="sun" name="sun" :size="15" />
          <Icon v-else key="moon" name="moon" :size="15" />
        </Transition>
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 58px;
  padding: 0 20px;
  background: var(--surface-1);
  border-bottom: 1px solid var(--border-subtle);
  flex: none;
  position: relative;
  z-index: var(--z-sticky);
}
.left {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}
.mark {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  box-shadow: var(--shadow-sm);
  transition: transform var(--dur-base) var(--ease-spring);
}
.mark:hover {
  transform: scale(1.05);
}
.mark svg {
  width: 100%;
  height: 100%;
  display: block;
}
.brand {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}
.name {
  font-size: var(--fs-lg);
  font-weight: 650;
  letter-spacing: -0.015em;
  color: var(--text-1);
}
.sub {
  font-size: var(--fs-2xs);
  color: var(--text-3);
}
.status {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}
.clock {
  font-size: var(--fs-sm);
  color: var(--text-2);
  letter-spacing: 0.02em;
  font-weight: 500;
}
.divider {
  width: 1px;
  height: 18px;
  background: var(--border);
}
.theme-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-2);
  color: var(--text-2);
  cursor: pointer;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}
.theme-btn:hover {
  color: var(--text-1);
  border-color: var(--border-strong);
  background: var(--surface-1);
}
.theme-btn:active {
  transform: scale(0.94);
}
.theme-swap-enter-active,
.theme-swap-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-spring);
}
.theme-swap-enter-from {
  opacity: 0;
  transform: rotate(-60deg) scale(0.6);
}
.theme-swap-leave-to {
  opacity: 0;
  transform: rotate(60deg) scale(0.6);
}

@media (max-width: 860px) {
  .status {
    display: none;
  }
}
</style>
