<script setup lang="ts">
/**
 * 状态徽章：圆点 + 文本。用于顶栏系统状态（数据源/信号/演示模式）。
 */
withDefaults(
  defineProps<{
    variant?: 'neutral' | 'accent' | 'warning' | 'danger' | 'success';
    dot?: boolean;
    /** 呼吸脉冲（进行中状态） */
    pulse?: boolean;
  }>(),
  { variant: 'neutral', dot: true, pulse: false },
);
</script>

<template>
  <span class="badge" :class="[`b-${variant}`, { pulse }]">
    <i v-if="dot" class="dot" aria-hidden="true" />
    <span class="txt"><slot /></span>
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3.5px 10px;
  border-radius: var(--r-pill);
  border: 1px solid var(--border);
  background: var(--surface-2);
  font-size: var(--fs-xs);
  line-height: 1.5;
  color: var(--text-2);
  white-space: nowrap;
  user-select: none;
  transition: border-color var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-slate);
  flex: none;
}
.b-accent {
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
  color: var(--accent);
}
.b-accent .dot {
  background: var(--accent);
}
.b-warning {
  border-color: var(--c-warning-soft);
  background: var(--c-warning-soft);
  color: var(--c-warning);
}
.b-warning .dot {
  background: var(--c-amber);
}
.b-danger {
  border-color: var(--c-danger-soft);
  background: var(--c-danger-soft);
  color: var(--c-danger);
}
.b-danger .dot {
  background: var(--c-coral);
}
.b-success {
  border-color: var(--c-success-soft);
  background: var(--c-success-soft);
  color: var(--c-success);
}
.b-success .dot {
  background: var(--c-success);
}
.dot.pulse {
  animation: badge-pulse 1.8s var(--ease-in-out) infinite;
}
@keyframes badge-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.35;
    transform: scale(0.82);
  }
}
@media (prefers-reduced-motion: reduce) {
  .dot.pulse {
    animation: none;
  }
}
</style>
