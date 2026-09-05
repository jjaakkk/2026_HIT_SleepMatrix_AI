<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  /** 动态文件内的 0/1/2 睡姿标签（官方：忽视，仅作参考展示） */
  labels: number[];
  frameIdx: number;
}>();

const emit = defineEmits<{ seek: [index: number] }>();

const POS_COLORS: Record<number, string> = {
  0: '#3b82f6', // 仰卧
  1: '#e6a23c', // 俯卧
  2: '#14b8a6', // 左侧卧
  3: '#f4695f', // 右侧卧
};

const POS_NAMES: Record<number, string> = { 0: '仰卧', 1: '俯卧', 2: '左侧卧', 3: '右侧卧' };

interface Segment {
  start: number;
  end: number;
  color: string;
  label: string;
}

const segments = computed<Segment[]>(() => {
  const out: Segment[] = [];
  let i = 0;
  while (i < props.labels.length) {
    let j = i + 1;
    while (j < props.labels.length && props.labels[j] === props.labels[i]) j++;
    out.push({
      start: i,
      end: j - 1,
      color: POS_COLORS[props.labels[i]] ?? '#8b8f98',
      label: POS_NAMES[props.labels[i]] ?? '?',
    });
    i = j;
  }
  return out;
});

const n = computed(() => Math.max(props.labels.length, 1));
const cursorPct = computed(() => (props.frameIdx / n.value) * 100);

function segStyle(s: Segment) {
  const left = (s.start / n.value) * 100;
  const w = ((s.end - s.start + 1) / n.value) * 100;
  return { left: left + '%', width: w + '%', background: s.color };
}

function onClick(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement;
  const rect = el.getBoundingClientRect();
  const ratio = (e.clientX - rect.left) / rect.width;
  emit('seek', Math.round(ratio * (n.value - 1)));
}
</script>

<template>
  <div class="pose-tl" role="group" aria-label="睡姿参考标签（文件内标签，仅供参考）">
    <div class="track" @click="onClick">
      <div
        v-for="(s, i) in segments"
        :key="i"
        class="seg"
        :style="segStyle(s)"
        :title="`${s.label}（文件内标签，仅供参考）`"
      />
      <div class="cursor" :style="{ left: cursorPct + '%' }" aria-hidden="true" />
    </div>
    <div class="cap">
      <span class="cap-label">睡姿参考标签</span>
      <span class="cap-note">文件自带 · 仅供参考</span>
    </div>
  </div>
</template>

<style scoped>
.pose-tl {
  flex: none;
  margin-bottom: 2px;
}
.track {
  position: relative;
  height: 16px;
  background: var(--surface-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-xs);
  overflow: hidden;
  cursor: pointer;
  transition: border-color var(--dur-fast) var(--ease-out);
}
.track:hover {
  border-color: var(--border-strong);
}
.seg {
  position: absolute;
  top: 0;
  bottom: 0;
  opacity: 0.82;
  transition: opacity var(--dur-fast) var(--ease-out);
}
.track:hover .seg {
  opacity: 0.95;
}
.cursor {
  position: absolute;
  top: -1px;
  bottom: -1px;
  width: 2px;
  background: var(--text-1);
  border-radius: 1px;
  z-index: 2;
  transition: left var(--dur-fast) linear;
}
.cursor::before {
  content: '';
  position: absolute;
  top: -1px;
  left: 50%;
  transform: translateX(-50%);
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-1);
}
.cap {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
}
.cap-label {
  color: var(--text-2);
}
.cap-note {
  color: var(--text-3);
}
</style>
