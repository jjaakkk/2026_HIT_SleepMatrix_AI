<script setup lang="ts">
import { computed } from 'vue';
import type { RegionMetrics } from '../core/region-stats.ts';
import Icon from './ui/Icon.vue';

const props = defineProps<{
  stats: RegionMetrics[];
  selected: number | null;
  hovered: number | null;
}>();

const emit = defineEmits<{ select: [index: number] }>();

const maxMean = computed(() => Math.max(props.stats[0]?.meanNet ?? 1, 1));
</script>

<template>
  <div class="ranking">
    <div v-if="stats.length === 0" class="empty">
      <Icon name="info" :size="13" />
      <span>当前记录无区域标注</span>
    </div>
    <button
      v-for="(s, i) in stats"
      :key="s.name"
      class="row"
      :class="{ selected: selected === s.index, hovered: hovered === s.index }"
      :style="{ '--i': i, '--row-color': s.color }"
      :title="`峰值 ${s.maxNet.toFixed(0)} · 有效点 ${s.activePoints} · 净压和 ${s.sumNet.toFixed(0)}`"
      @click="emit('select', s.index)"
    >
      <span class="rank num">{{ String(i + 1).padStart(2, '0') }}</span>
      <span class="name">
        <span class="dot" aria-hidden="true" />
        {{ s.name }}
        <Icon v-if="selected === s.index" name="check" :size="12" class="check" />
      </span>
      <span class="bar" aria-hidden="true">
        <span class="fill" :style="{ width: (s.meanNet / maxMean) * 100 + '%' }" />
      </span>
      <span class="val num">{{ s.meanNet.toFixed(0) }}</span>
    </button>
  </div>
</template>

<style scoped>
.ranking {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.empty {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-xs);
  color: var(--text-3);
  padding: 10px 2px;
}
.empty .icon {
  opacity: 0.7;
}
.row {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 44px 32px;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 4px 9px 4px 6px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-sm);
  cursor: pointer;
  color: var(--text-1);
  text-align: left;
  position: relative;
  animation: row-in 420ms var(--ease-out) both;
  animation-delay: calc(var(--i) * 40ms + 160ms);
  transition:
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}
@keyframes row-in {
  from {
    opacity: 0;
    transform: translateX(8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
.row:hover {
  border-color: var(--border-strong);
  background: var(--surface-2);
}
.row.selected {
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}
.row.hovered:not(.selected) {
  border-color: var(--border-strong);
  background: var(--surface-2);
}
.rank {
  font-size: 10px;
  color: var(--text-3);
  text-align: right;
  letter-spacing: 0.02em;
}
.name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-xs);
  white-space: nowrap;
  overflow: hidden;
  min-width: 0;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 2.5px;
  background: var(--row-color);
  flex: none;
  transition: transform var(--dur-fast) var(--ease-spring);
}
.row:hover .dot {
  transform: scale(1.25);
}
.check {
  color: var(--accent);
  flex: none;
  animation: check-in var(--dur-base) var(--ease-spring);
}
@keyframes check-in {
  from {
    opacity: 0;
    transform: scale(0.5);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
.bar {
  height: 5px;
  background: var(--surface-3);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--row-color);
  opacity: 0.85;
  transition: width var(--dur-slow) var(--ease-out);
}
.row.selected .fill {
  opacity: 1;
}
.val {
  font-size: var(--fs-xs);
  font-weight: 600;
  text-align: right;
  letter-spacing: -0.01em;
}
@media (prefers-reduced-motion: reduce) {
  .row {
    animation: none;
  }
}
</style>
