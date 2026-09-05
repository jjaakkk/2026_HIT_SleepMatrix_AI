<script setup lang="ts">
/**
 * 面板容器：统一的表面 + 可选标题行（图标 + 标题 + 副标题 + 动作区）。
 */
import Icon from './Icon.vue';

withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    icon?: string;
    /** 无内边距（内容自控） */
    flush?: boolean;
    /** 无外边框（融入背景，仅标题行） */
    borderless?: boolean;
  }>(),
  { title: undefined, subtitle: undefined, icon: undefined, flush: false, borderless: false },
);
</script>

<template>
  <section class="panel" :class="{ flush, borderless }">
    <header v-if="title || $slots.actions" class="head">
      <div class="head-main">
        <Icon v-if="icon" :name="icon" :size="13" class="head-icon" />
        <h3 class="head-title">{{ title }}</h3>
        <span v-if="subtitle" class="head-sub">{{ subtitle }}</span>
      </div>
      <div v-if="$slots.actions" class="head-actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="body"><slot /></div>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--surface-1);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-xs);
}
.panel.borderless {
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 13px 16px 0;
}
.head-main {
  display: flex;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}
.head-icon {
  color: var(--text-3);
  align-self: center;
}
.head-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--text-1);
  white-space: nowrap;
}
.head-sub {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}
.body {
  flex: 1;
  min-height: 0;
  padding: 12px 16px 16px;
}
.flush .body {
  padding: 0;
}
</style>
