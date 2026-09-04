<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { FrameMetrics } from '../core/metrics.ts';
import { contactIndex } from '../core/metrics.ts';
import { niceTicks } from '../render/chart-scale.ts';

const props = defineProps<{
  /** 逐帧指标历史（回放顺序） */
  history: FrameMetrics[];
  /** 当前回放帧号（播放头） */
  frameIdx: number;
  /** 追加曲线（如选定区域的逐帧平均压力），主图左轴 */
  extraSeries?: { label: string; color: string; values: number[] }[];
}>();

/** 主图曲线（压力，单轴） */
const mainSeries = [
  { key: 'maxRaw', label: '最大压力', color: '#ff7a6b', value: (m: FrameMetrics) => m.maxRaw },
  { key: 'meanNet', label: '平均压力', color: '#2fd6b6', value: (m: FrameMetrics) => m.meanNet },
];
/** 接触面积（0-100%，独立小图，单轴） */
const contactSeries = {
  label: '接触面积 %',
  color: '#4da6ff',
  value: (m: FrameMetrics) => contactIndex(m),
};

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ x: number; y: number; idx: number; values: string[] } | null>(null);

const PAD = { left: 40, right: 12, top: 20, bottom: 20 };
/** 底部接触面积小图高度 */
const STRIP_H = 44;

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

  const n = props.history.length;
  if (n === 0) {
    ctx.fillStyle = '#64747f';
    ctx.font = '12px sans-serif';
    ctx.fillText('暂无数据', PAD.left + 8, PAD.top + 18);
    return;
  }

  const mainH = h - STRIP_H - 26; // 主图高度
  const plotW = w - PAD.left - PAD.right;
  const xOf = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * plotW;

  // ---- 主图（压力，单轴） ----
  let min = Infinity;
  let max = -Infinity;
  for (const m of props.history) {
    for (const s of mainSeries) {
      const v = s.value(m);
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  for (const es of props.extraSeries ?? []) {
    for (const v of es.values) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  const ticks = niceTicks(Math.min(min, 0), Math.max(max, 1), 5);
  const yOf = (v: number) =>
    PAD.top + mainH - ((v - ticks.min) / (ticks.max - ticks.min)) * mainH;

  ctx.font = '10px "IBM Plex Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (const t of ticks.ticks) {
    const y = yOf(t);
    ctx.strokeStyle = 'rgba(148,168,184,0.07)';
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(w - PAD.right, y);
    ctx.stroke();
    ctx.fillStyle = '#64747f';
    ctx.fillText(String(t), PAD.left - 6, y);
  }
  // x 轴帧号（最多 8 个刻度）
  const xStep = Math.max(1, Math.ceil(n / 8));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let i = 0; i < n; i += xStep) {
    ctx.fillStyle = '#64747f';
    ctx.fillText(String(i), xOf(i), PAD.top + mainH + 6);
  }

  for (const s of mainSeries) {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = xOf(i);
      const y = yOf(s.value(props.history[i]));
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  for (const es of props.extraSeries ?? []) {
    if (es.values.length === 0) continue;
    ctx.strokeStyle = es.color;
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    for (let i = 0; i < Math.min(es.values.length, n); i++) {
      const x = xOf(i);
      const y = yOf(es.values[i]);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // ---- 底部接触面积小图（0-100%，独立轴） ----
  const stripY = PAD.top + mainH + 22;
  const stripBottom = stripY + STRIP_H - 8;
  const cMin = 0;
  const cMax = 100;
  const cY = (v: number) => stripBottom - ((v - cMin) / (cMax - cMin)) * (STRIP_H - 8);
  ctx.font = '10px "IBM Plex Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#64747f';
  ctx.fillText('0', PAD.left - 6, stripBottom);
  ctx.fillText('100', PAD.left - 6, stripY);
  ctx.strokeStyle = 'rgba(148,168,184,0.07)';
  ctx.beginPath();
  ctx.moveTo(PAD.left, stripY);
  ctx.lineTo(w - PAD.right, stripY);
  ctx.stroke();
  ctx.strokeStyle = contactSeries.color;
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const x = xOf(i);
    const y = cY(contactSeries.value(props.history[i]));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // ---- 播放头 ----
  const cx = xOf(props.frameIdx);
  ctx.strokeStyle = 'rgba(233,240,245,0.85)';
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(cx, PAD.top);
  ctx.lineTo(cx, stripBottom);
  ctx.stroke();
  ctx.fillStyle = '#e9f0f5';
  ctx.beginPath();
  ctx.arc(cx, PAD.top - 2, 3.5, 0, Math.PI * 2);
  ctx.fill();

  // ---- 图例（主图曲线；接触面积图例画在小图旁） ----
  let lx = PAD.left;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.font = '11px sans-serif';
  const legendItems = [
    ...mainSeries.map((s) => ({ label: s.label, color: s.color, dashed: false })),
    ...(props.extraSeries ?? []).map((es) => ({ label: es.label, color: es.color, dashed: true })),
  ];
  for (const it of legendItems) {
    ctx.save();
    if (it.dashed) ctx.setLineDash([3, 2]);
    ctx.strokeStyle = it.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(lx, 5.5);
    ctx.lineTo(lx + 12, 5.5);
    ctx.stroke();
    ctx.restore();
    ctx.fillStyle = '#9fb0bc';
    ctx.fillText(it.label, lx + 16, 5.5);
    lx += 16 + ctx.measureText(it.label).width + 16;
  }
  // 接触面积图例（独立小图旁，右对齐）
  ctx.save();
  ctx.strokeStyle = contactSeries.color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(w - PAD.right - 12 - ctx.measureText(contactSeries.label).width - 8, stripY - 8);
  ctx.lineTo(w - PAD.right - ctx.measureText(contactSeries.label).width, stripY - 8);
  ctx.stroke();
  ctx.restore();
  ctx.textAlign = 'right';
  ctx.fillStyle = '#9fb0bc';
  ctx.fillText(contactSeries.label, w - PAD.right, stripY - 8);
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
    values: [
      ...mainSeries.map((s) => `${s.label} ${s.value(m).toFixed(1)}`),
      `${contactSeries.label} ${contactSeries.value(m).toFixed(1)}`,
    ],
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
      <div class="tt-title num">帧 {{ hover.idx }}</div>
      <div v-for="v in hover.values" :key="v" class="num">{{ v }}</div>
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
  background: var(--panel);
  border: 1px solid var(--border-strong);
  color: var(--text);
  font-size: 11px;
  padding: 6px 8px;
  border-radius: 6px;
  z-index: 10;
  line-height: 1.6;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
}
.tt-title {
  color: var(--text-2);
}
</style>
