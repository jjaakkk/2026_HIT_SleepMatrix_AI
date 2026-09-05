<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import type { FrameMetrics } from '../core/metrics.ts';
import { contactIndex } from '../core/metrics.ts';
import { useTweenNumber } from '../composables/useTweenNumber';

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
  decimals: number;
  note?: string;
}

const cards: CardDef[] = [
  {
    key: 'maxRaw',
    label: '最大压力',
    unit: '原始读数',
    color: 'var(--c-coral)',
    value: (m) => m.maxRaw,
    decimals: 0,
    note: '当前帧全部 1056 点中的最大原始读数',
  },
  {
    key: 'maxNet',
    label: '净最大压力',
    unit: '扣除空载',
    color: 'var(--c-amber)',
    value: (m) => m.maxNet,
    decimals: 0,
    note: '扣减空载背景后的最大净压力',
  },
  {
    key: 'meanNet',
    label: '平均压力',
    unit: '接触点均值',
    color: 'var(--accent)',
    value: (m) => m.meanNet,
    decimals: 1,
    note: '有效接触点的平均净压力',
  },
  {
    key: 'contact',
    label: '接触面积',
    unit: '1056 点占比',
    color: 'var(--c-blue)',
    value: (m) => contactIndex(m),
    decimals: 1,
    note: '净压超过阈值的点占比（自定义口径）',
  },
];

// 数值滚动显示（四个指标分别 tween）
const displays = cards.map((c) => ({
  key: c.key,
  display: useTweenNumber(() => {
    const m = props.metrics;
    return m ? c.value(m) : null;
  }, { decimals: c.decimals }),
}));

const canvasRefs = ref<Record<string, HTMLCanvasElement | null>>({});

function setRef(key: string) {
  return (el: unknown) => {
    (canvasRefs.value as Record<string, HTMLCanvasElement | null>)[key] = el as HTMLCanvasElement | null;
  };
}

function hexWithAlpha(colorVar: string, alpha: number): string {
  // canvas 无法直接使用 CSS 变量，运行时取计算值并附加透明度
  const el = document.documentElement;
  const raw = getComputedStyle(el).getPropertyValue(colorVar.replace('var(', '').replace(')', '')).trim();
  if (/^#[0-9a-f]{6}$/i.test(raw)) {
    const r = parseInt(raw.slice(1, 3), 16);
    const g = parseInt(raw.slice(3, 5), 16);
    const b = parseInt(raw.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return raw;
}

function drawSparkline(key: string) {
  const c = canvasRefs.value[key];
  if (!c) return;
  const def = cards.find((x) => x.key === key)!;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (w === 0 || h === 0) return;
  c.width = w * dpr;
  c.height = h * dpr;
  const ctx = c.getContext('2d')!;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const series = props.history.map((m) => def.value(m));
  if (series.length < 2) return;
  const n = Math.min(series.length, 60);
  const slice = series.slice(-n);
  let min = Infinity;
  let max = -Infinity;
  for (const v of slice) {
    if (v < min) min = v;
    if (v > max) max = v;
  }
  const range = max - min || 1;
  const pad = 2.5;
  const color = hexWithAlpha(def.color, 1);
  const pts = slice.map((v, i) => ({
    x: (i / (n - 1)) * w,
    y: h - pad - ((v - min) / range) * (h - pad * 2),
  }));

  // 渐变面积填充
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, hexWithAlpha(def.color, 0.22));
  grad.addColorStop(1, hexWithAlpha(def.color, 0));
  ctx.beginPath();
  ctx.moveTo(pts[0].x, h);
  for (const p of pts) ctx.lineTo(p.x, p.y);
  ctx.lineTo(pts[pts.length - 1].x, h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 折线
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.4;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    if (i === 0) ctx.moveTo(pts[i].x, pts[i].y);
    else ctx.lineTo(pts[i].x, pts[i].y);
  }
  ctx.stroke();

  // 末端点
  const last = pts[pts.length - 1];
  ctx.beginPath();
  ctx.arc(last.x, last.y, 2.2, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(last.x, last.y, 4.4, 0, Math.PI * 2);
  ctx.strokeStyle = hexWithAlpha(def.color, 0.25);
  ctx.lineWidth = 1;
  ctx.stroke();
}

const historyKey = computed(() => props.history.length);
onMounted(() => {
  for (const c of cards) drawSparkline(c.key);
});
watch(historyKey, () => {
  requestAnimationFrame(() => {
    for (const c of cards) drawSparkline(c.key);
  });
});
</script>

<template>
  <div class="cards">
    <div
      v-for="(c, i) in cards"
      :key="c.key"
      class="card"
      :style="{ '--i': i, '--card-color': c.color }"
      :title="c.note"
    >
      <div class="card-head">
        <span class="dot" aria-hidden="true" />
        <span class="label">{{ c.label }}</span>
        <span class="unit">{{ c.unit }}</span>
      </div>
      <div class="value num">{{ displays.find((d) => d.key === c.key)?.display ?? '—' }}</div>
      <canvas :ref="setRef(c.key)" class="spark" aria-hidden="true" />
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}
.card {
  background: var(--surface-2);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  padding: 11px 12px 9px;
  min-width: 0;
  animation: card-in 460ms var(--ease-out) both;
  animation-delay: calc(var(--i) * 50ms + 120ms);
  transition:
    border-color var(--dur-base) var(--ease-out),
    background-color var(--dur-base) var(--ease-out);
}
/* 悬停只提亮表面（共识规则：不位移、不加投影） */
.card:hover {
  border-color: var(--border-strong);
  background: var(--surface-hover);
}
@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
  min-width: 0;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--card-color);
  flex: none;
}
.label {
  font-size: var(--fs-2xs);
  font-weight: 500;
  color: var(--text-2);
  white-space: nowrap;
}
.unit {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 40%;
}
.value {
  font-size: var(--fs-num);
  font-weight: 600;
  line-height: 1.15;
  color: var(--text-1);
  letter-spacing: -0.02em;
  font-family: var(--font-ui);
  font-variant-numeric: tabular-nums;
}
.spark {
  width: 100%;
  height: 20px;
  margin-top: 5px;
  display: block;
}
@media (prefers-reduced-motion: reduce) {
  .card {
    animation: none;
  }
}
</style>
