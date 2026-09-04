<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  /** 动态文件内的 0/1/2 睡姿标签（官方：忽视，仅作参考展示） */
  labels: number[];
  frameIdx: number;
}>();

const emit = defineEmits<{ seek: [index: number] }>();

const POS_COLORS: Record<number, string> = {
  0: '#4da6ff', // 仰卧
  1: '#e6b84c', // 俯卧
  2: '#2fd6b6', // 左侧卧
  3: '#ff7a6b', // 右侧卧
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
      color: POS_COLORS[props.labels[i]] ?? '#8b949e',
      label: POS_NAMES[props.labels[i]] ?? '?',
    });
    i = j;
  }
  return out;
});

const n = computed(() => Math.max(props.labels.length, 1));

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
  <div class="pose-timeline" @click="onClick">
    <div
      v-for="(s, i) in segments"
      :key="i"
      class="seg"
      :style="segStyle(s)"
      :title="`${s.label}（文件内标签，仅供参考）`"
    ></div>
    <div class="cursor" :style="{ left: (frameIdx / n) * 100 + '%' }"></div>
  </div>
</template>

<style scoped>
.pose-timeline {
  position: relative;
  height: 14px;
  background: #21262d;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  margin-bottom: 6px;
}
.seg {
  position: absolute;
  top: 0;
  bottom: 0;
  opacity: 0.75;
}
.cursor {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  background: #e6edf3;
  z-index: 2;
}
</style>
