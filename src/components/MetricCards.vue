<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import type { FrameMetrics } from '../core/metrics.ts';
import { contactIndex } from '../core/metrics.ts';

const props = defineProps<{
  metrics: FrameMetrics | null;
  history: FrameMetrics[];
}>();

interface CardDef {
  key: string;
  label: string;
  unit: string;
  color: string;
  value: (m: FrameMetrics) => number;
  fmt: (v: number) => string;
  note?: string;
}

const cards: CardDef[] = [
  {
    key: 'maxRaw',
    label: '最大压力',
    unit: '传感器读数',
    color: '#ff7a1a',
    value: (m) => m.maxRaw,
    fmt: (v) => v.toFixed(0),
  },
  {
    key: 'maxNet',
    label: '净最大压力',
    unit: '扣空载后',
    color: '#ff3b30',
    value: (m) => m.maxNet,
    fmt: (v) => v.toFixed(0),
  },
  {
    key: 'meanNet',
    label: '平均压力',
    unit: '有效接触点均值',
    color: '#39c5cf',
    value: (m) => m.meanNet,
    fmt: (v) => v.toFixed(1),
  },
  {
    key: 'contact',
    label: '接触面积 / 有效点数',
    unit: '占 1056 点的 %',
    color: '#a29bfe',
    value: (m) => contactIndex(m),
    fmt: (v) => v.toFixed(1),
    note: '指数为候选定义，待确认',
  },
];

const canvasRefs = ref<Record<string, HTMLCanvasElement | null>>({});

function setRef(key: string) {
  return (el: unknown) => {
    (canvasRefs.value as Record<string, HTMLCanvasElement | null>)[key] = el as HTMLCanvasElement | null;
  };
}

function drawSparkline(key: string) {
  const c = canvasRefs.value[key];
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  c.width = w * dpr;
  c.height = h * dpr;
  const ctx = c.getContext('2d')!;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const series = props.history.map((m) => cards.find((x) => x.key === key)!.value(m));
  if (series.length < 2) return;
  const n = Math.min(series.length, 60);
  const slice = series.slice(-n);
  if (slice.length < 2) return;
  const min = Math.min(...slice);
  const max = Math.max(...slice);
  const range = max - min || 1;
  const color = cards.find((x) => x.key === key)!.color;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  slice.forEach((v, i) => {
    const x = (i / (n - 1)) * w;
    const y = h - 2 - ((v - min) / range) * (h - 4);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

onMounted(() => {
  for (const c of cards) drawSparkline(c.key);
});
watch(() => props.history, () => {
  for (const c of cards) drawSparkline(c.key);
});
</script>

<template>
  <div class="cards">
    <div v-for="c in cards" :key="c.key" class="card">
      <div class="card-head">
        <span class="dot" :style="{ background: c.color }"></span>
        <span class="label">{{ c.label }}</span>
      </div>
      <div class="value" :style="{ color: c.color }">
        {{ metrics ? c.fmt(c.value(metrics)) : '—' }}
      </div>
      <div class="unit">{{ c.unit }}</div>
      <canvas :ref="setRef(c.key)" class="spark"></canvas>
      <div v-if="c.note" class="note">{{ c.note }}</div>
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 9px;
  min-width: 0;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.value {
  font-size: 19px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.unit {
  font-size: 10.5px;
  color: var(--text-secondary);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spark {
  width: 100%;
  height: 14px;
  margin-top: 3px;
  display: block;
}
.note {
  font-size: 10px;
  color: var(--text-secondary);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
