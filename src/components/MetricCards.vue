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
    unit: '原始读数',
    color: '#ff7a6b',
    value: (m) => m.maxRaw,
    fmt: (v) => v.toFixed(0),
  },
  {
    key: 'maxNet',
    label: '净最大压力',
    unit: '扣除空载',
    color: '#e6b84c',
    value: (m) => m.maxNet,
    fmt: (v) => v.toFixed(0),
  },
  {
    key: 'meanNet',
    label: '平均压力',
    unit: '接触点均值',
    color: '#2fd6b6',
    value: (m) => m.meanNet,
    fmt: (v) => v.toFixed(1),
  },
  {
    key: 'contact',
    label: '接触面积',
    unit: '1056 点占比 · 自定义口径',
    color: '#4da6ff',
    value: (m) => contactIndex(m),
    fmt: (v) => v.toFixed(1),
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
  ctx.lineWidth = 1.4;
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
    <div v-for="c in cards" :key="c.key" class="card" :style="{ borderTopColor: c.color }">
      <div class="card-head">
        <span class="label">{{ c.label }}</span>
      </div>
      <div class="value num" :style="{ color: c.color }">
        {{ metrics ? c.fmt(c.value(metrics)) : '—' }}
      </div>
      <div class="unit" :title="c.unit">{{ c.unit }}</div>
      <canvas :ref="setRef(c.key)" class="spark"></canvas>
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.card {
  background: var(--panel-inset);
  border: 1px solid var(--border);
  border-top: 2px solid var(--border);
  border-radius: var(--r-card);
  padding: 8px 10px 7px;
  min-width: 0;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 3px;
}
.label {
  font-size: 12px;
  color: var(--text-2);
}
.value {
  font-size: 21px;
  font-weight: 600;
  line-height: 1.1;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.unit {
  font-size: 10px;
  color: var(--text-3);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spark {
  width: 100%;
  height: 15px;
  margin-top: 4px;
  display: block;
  opacity: 0.85;
}
</style>
