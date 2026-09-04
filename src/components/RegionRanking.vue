<script setup lang="ts">
import { computed } from 'vue';
import type { RegionMetrics } from '../core/region-stats.ts';

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
    <div v-if="stats.length === 0" class="empty">当前用户无区域标注</div>
    <button
      v-for="s in stats"
      :key="s.name"
      class="row"
      :class="{ selected: selected === s.index, hovered: hovered === s.index }"
      @click="emit('select', s.index)"
    >
      <span class="name">
        <span class="dot" :style="{ background: s.color }"></span>
        {{ s.name }}
      </span>
      <span class="bar">
        <span class="fill" :style="{ width: (s.meanNet / maxMean) * 100 + '%', background: s.color }"></span>
      </span>
      <span class="val">{{ s.meanNet.toFixed(0) }}</span>
      <span class="meta">峰值{{ s.maxNet.toFixed(0) }} · {{ s.activePoints }}点</span>
    </button>
  </div>
</template>

<style scoped>
.ranking {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
.row {
  display: grid;
  grid-template-columns: 62px 1fr 34px;
  align-items: center;
  gap: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  cursor: pointer;
  color: var(--text);
  text-align: left;
  position: relative;
}
.row.selected {
  border-color: var(--accent);
}
.row.hovered:not(.selected) {
  border-color: #57606a;
}
.name {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}
.bar {
  height: 6px;
  background: #21262d;
  border-radius: 3px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width 0.25s ease;
}
.val {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.meta {
  grid-column: 2 / 4;
  font-size: 10px;
  color: var(--text-secondary);
}
</style>
