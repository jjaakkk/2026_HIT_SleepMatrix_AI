<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue';
import type { FrameMetrics } from '../core/metrics.ts';
import { contactIndex } from '../core/metrics.ts';
import { niceTicks } from '../render/chart-scale.ts';

const props = defineProps<{
  /** 逐帧指标历史（回放顺序） */
  history: FrameMetrics[];
  /** 当前回放帧号（播放头） */
  frameIdx: number;
  /** 追加曲线（如选定区域的逐帧平均压力），左轴 */
  extraSeries?: { label: string; color: string; values: number[] }[];
}>();

interface SeriesDef {
  key: string;
  label: string;
  color: string;
  axis: 'left' | 'right';
  value: (m: FrameMetrics) => number;
}

const series: SeriesDef[] = [
  { key: 'maxRaw', label: '最大压力', color: '#ff7a1a', axis: 'left', value: (m) => m.maxRaw },
  { key: 'meanNet', label: '平均压力', color: '#39c5cf', axis: 'left', value: (m) => m.meanNet },
  { key: 'contact', label: '接触面积 %', color: '#a29bfe', axis: 'right', value: (m) => contactIndex(m) },
];

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ x: number; y: number; idx: number; values: string[] } | null>(null);

const PAD = { left: 44, right: 44, top: 26, bottom: 26 };

function draw() {
  const c = canvasRef.value;
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== w * dpr || c.height !== h * dpr) {
    c.width = w * dpr;
    c.height = h * dpr;
  }
  const ctx = c.getContext('2d')!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const plotW = w - PAD.left - PAD.right;
  const plotH = h - PAD.top - PAD.bottom;
  const n = props.history.length;
  if (n === 0) {
    ctx.fillStyle = '#8b949e';
    ctx.font = '12px sans-serif';
    ctx.fillText('暂无数据', PAD.left + 8, PAD.top + 20);
    return;
  }

  // 数据范围
  let lMin = Infinity, lMax = -Infinity, rMin = Infinity, rMax = -Infinity;
  for (const m of props.history) {
    for (const s of series) {
      const v = s.value(m);
      if (s.axis === 'left') {
        if (v < lMin) lMin = v;
        if (v > lMax) lMax = v;
      } else {
        if (v < rMin) rMin = v;
        if (v > rMax) rMax = v;
      }
    }
  }
  for (const es of props.extraSeries ?? []) {
    for (const v of es.values) {
      if (v < lMin) lMin = v;
      if (v > lMax) lMax = v;
    }
  }
  const lTicks = niceTicks(Math.min(lMin, 0), Math.max(lMax, 1), 5);
  const rTicks = niceTicks(Math.min(rMin, 0), Math.max(rMax, 1), 5);

  const xOf = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * plotW;
  const yOf = (v: number, t: ReturnType<typeof niceTicks>) =>
    PAD.top + plotH - ((v - t.min) / (t.max - t.min)) * plotH;

  // 网格与刻度
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (const t of lTicks.ticks) {
    const y = yOf(t, lTicks);
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(w - PAD.right, y);
    ctx.stroke();
    ctx.fillStyle = '#8b949e';
    ctx.fillText(String(t), PAD.left - 6, y);
  }
  ctx.textAlign = 'left';
  for (const t of rTicks.ticks) {
    const y = yOf(t, rTicks);
    ctx.fillStyle = '#8b949e';
    ctx.fillText(String(t), w - PAD.right + 6, y);
  }
  // x 轴帧号（最多 8 个刻度）
  const xStep = Math.max(1, Math.ceil(n / 8));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let i = 0; i < n; i += xStep) {
    ctx.fillStyle = '#8b949e';
    ctx.fillText(String(i), xOf(i), PAD.top + plotH + 6);
  }

  // 曲线
  for (const s of series) {
    const ticks = s.axis === 'left' ? lTicks : rTicks;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = xOf(i);
      const y = yOf(s.value(props.history[i]), ticks);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  // 追加曲线（如选定区域）
  for (const es of props.extraSeries ?? []) {
    if (es.values.length === 0) continue;
    ctx.strokeStyle = es.color;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    for (let i = 0; i < Math.min(es.values.length, n); i++) {
      const x = xOf(i);
      const y = yOf(es.values[i], lTicks);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 播放头
  const cx = xOf(props.frameIdx);
  ctx.strokeStyle = 'rgba(230,237,243,0.85)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(cx, PAD.top);
  ctx.lineTo(cx, PAD.top + plotH);
  ctx.stroke();
  ctx.fillStyle = '#e6edf3';
  ctx.beginPath();
  ctx.arc(cx, PAD.top - 2, 4, 0, Math.PI * 2);
  ctx.fill();

  // 图例
  let lx = PAD.left;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  const allSeries = [...series];
  const extra = props.extraSeries ?? [];
  for (const s of allSeries) {
    ctx.fillStyle = s.color;
    ctx.fillRect(lx, 4, 10, 3);
    ctx.fillStyle = '#8b949e';
    ctx.fillText(s.label, lx + 14, 5.5);
    lx += 14 + ctx.measureText(s.label).width + 14;
  }
  for (const es of extra) {
    ctx.save();
    ctx.setLineDash([3, 2]);
    ctx.strokeStyle = es.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(lx, 5.5);
    ctx.lineTo(lx + 10, 5.5);
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = '#8b949e';
    ctx.fillText(es.label, lx + 14, 5.5);
    lx += 14 + ctx.measureText(es.label).width + 14;
  }
}

function onMove(e: MouseEvent) {
  const c = canvasRef.value;
  if (!c) return;
  const rect = c.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const plotW = rect.width - PAD.left - PAD.right;
  const n = props.history.length;
  if (n === 0 || x < PAD.left || x > rect.width - PAD.right) {
    hover.value = null;
    return;
  }
  const idx = Math.min(Math.max(Math.round(((x - PAD.left) / plotW) * (n - 1)), 0), n - 1);
  const m = props.history[idx];
  hover.value = {
    x,
    y,
    idx,
    values: series.map((s) => `${s.label} ${s.value(m).toFixed(1)}`),
  };
}
function onLeave() {
  hover.value = null;
}

onMounted(() => {
  draw();
  window.addEventListener('resize', draw);
});
onBeforeUnmount(() => window.removeEventListener('resize', draw));
watch(() => [props.history, props.frameIdx], draw);
</script>

<template>
  <div class="chart-wrap" @mousemove="onMove" @mouseleave="onLeave">
    <canvas ref="canvasRef" class="chart"></canvas>
    <div v-if="hover" class="tooltip" :style="{ left: hover.x + 10 + 'px', top: hover.y + 10 + 'px' }">
      <div class="tt-title">帧 {{ hover.idx }}</div>
      <div v-for="v in hover.values" :key="v">{{ v }}</div>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 150px;
}
.chart {
  width: 100%;
  height: 100%;
  display: block;
}
.tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(22, 27, 34, 0.96);
  border: 1px solid #30363d;
  color: #e6edf3;
  font-size: 11px;
  padding: 6px 8px;
  border-radius: 4px;
  z-index: 10;
  line-height: 1.5;
}
.tt-title {
  color: #8b949e;
}
</style>
