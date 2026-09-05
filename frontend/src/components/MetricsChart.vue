<script setup lang="ts">
/**
 * 压力趋势图（v4.1 重设计）：
 * 单一语义轴 —— 只画「净压力」（扣除空载基线），两条同口径曲线：
 *   平均净压力（主视觉，面积+线） + 最大净压力（细线）
 * 选定区域的平均压力以虚线叠加（同一口径）。
 * 原则：同单位同口径的指标才共享一个轴；接触面积等异口径指标不进此图
 * （其趋势在指标卡 sparkline 中呈现），杜绝"几合一"的混轴混淆。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { FrameMetrics } from '../core/metrics.ts';
import { niceTicks } from '../render/chart-scale.ts';
import Icon from './ui/Icon.vue';

const props = defineProps<{
  /** 逐帧指标历史（回放顺序） */
  history: FrameMetrics[];
  /** 当前回放帧号（播放头） */
  frameIdx: number;
  /** 追加曲线（选定区域逐帧平均净压力），虚线叠加 */
  extraSeries?: { label: string; color: string; values: number[] }[];
}>();

/** 主图曲线：统一「净压力」口径（颜色取自语义令牌） */
const mainSeries = [
  {
    key: 'meanNet',
    label: '平均净压力',
    varName: '--accent',
    fallback: '#0d7a6b',
    value: (m: FrameMetrics) => m.meanNet,
  },
  {
    key: 'maxNet',
    label: '最大净压力',
    varName: '--c-coral',
    fallback: '#f4695f',
    value: (m: FrameMetrics) => m.maxNet,
  },
];

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ x: number; y: number; idx: number; values: { label: string; color: string; v: string }[] } | null>(null);

const PAD = { left: 44, right: 14, top: 14, bottom: 24 };

/* 运行时解析 CSS 语义色 */
function cssColor(hexFallback: string, varName: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return raw || hexFallback;
}
function alpha(hex: string, a: number): string {
  if (/^#[0-9a-f]{6}$/i.test(hex)) {
    return `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(
      hex.slice(5, 7),
      16,
    )},${a})`;
  }
  return hex;
}
function resolveSeriesColor(s: { varName: string; fallback: string }): string {
  return cssColor(s.fallback, s.varName);
}

function draw() {
  const c = canvasRef.value;
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (w === 0 || h === 0) return;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext('2d')!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const grid = cssColor('rgba(120,125,140,0.12)', '--border');
  const tick = cssColor('#757575', '--text-3');
  const playhead = cssColor('#171717', '--text-1');
  const meanColor = resolveSeriesColor(mainSeries[0]);
  const maxColor = resolveSeriesColor(mainSeries[1]);

  const n = props.history.length;
  if (n === 0) {
    ctx.fillStyle = tick;
    ctx.font = '13px "IBM Plex Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('暂无数据', w / 2, h / 2 - 6);
    return;
  }

  const plotW = w - PAD.left - PAD.right;
  const plotH = h - PAD.top - PAD.bottom;
  const xOf = (i: number) => PAD.left + (i / Math.max(n - 1, 1)) * plotW;

  // 单轴量程：仅净压力系列 + 区域叠加（同口径）
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
  const yOf = (v: number) => PAD.top + plotH - ((v - ticks.min) / (ticks.max - ticks.min)) * plotH;

  // 网格 + Y 轴刻度
  ctx.font = '11px "IBM Plex Mono", monospace';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (const t of ticks.ticks) {
    const y = yOf(t);
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(PAD.left, y);
    ctx.lineTo(w - PAD.right, y);
    ctx.stroke();
    ctx.fillStyle = tick;
    ctx.fillText(String(t), PAD.left - 8, y);
  }
  // X 轴帧号（最多 8 个刻度）
  const xStep = Math.max(1, Math.ceil(n / 8));
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let i = 0; i < n; i += xStep) {
    ctx.fillStyle = tick;
    ctx.fillText(String(i), xOf(i), PAD.top + plotH + 8);
  }

  function strokeSeries(values: number[], color: string, width: number, dashed: boolean, fill: boolean) {
    const pts = values.map((v, i) => ({ x: xOf(i), y: yOf(v) }));
    if (pts.length < 2) return;
    if (fill) {
      const grad = ctx.createLinearGradient(0, PAD.top, 0, PAD.top + plotH);
      grad.addColorStop(0, alpha(color, 0.15));
      grad.addColorStop(1, alpha(color, 0));
      ctx.beginPath();
      ctx.moveTo(pts[0].x, PAD.top + plotH);
      for (const p of pts) ctx.lineTo(p.x, p.y);
      ctx.lineTo(pts[pts.length - 1].x, PAD.top + plotH);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();
    }
    ctx.save();
    if (dashed) ctx.setLineDash([5, 4]);
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    for (let i = 0; i < pts.length; i++) {
      if (i === 0) ctx.moveTo(pts[i].x, pts[i].y);
      else ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.stroke();
    ctx.restore();
  }

  // 平均净压力（面积主视觉）→ 最大净压力（细线）→ 区域叠加（虚线）
  strokeSeries(props.history.map(mainSeries[0].value), meanColor, 1.8, false, true);
  strokeSeries(props.history.map(mainSeries[1].value), maxColor, 1.4, false, false);
  for (const es of props.extraSeries ?? []) {
    if (es.values.length === 0) continue;
    strokeSeries(es.values.slice(0, n), es.color, 2, true, false);
  }

  // 播放头
  const cx = xOf(Math.min(Math.max(props.frameIdx, 0), n - 1));
  ctx.strokeStyle = alpha(playhead, 0.55);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(cx, PAD.top);
  ctx.lineTo(cx, PAD.top + plotH);
  ctx.stroke();
  ctx.fillStyle = playhead;
  ctx.beginPath();
  ctx.arc(cx, PAD.top - 2, 3.4, 0, Math.PI * 2);
  ctx.fill();
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
  const rows = [
    ...mainSeries.map((s) => ({ label: s.label, color: resolveSeriesColor(s), v: s.value(m).toFixed(1) })),
    ...(props.extraSeries ?? []).map((es) => ({
      label: es.label,
      color: es.color,
      v: (es.values[Math.min(idx, es.values.length - 1)] ?? 0).toFixed(1),
    })),
  ];
  hover.value = { x, y, idx, values: rows };
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

const legendItems = computed(() => [
  ...mainSeries.map((s) => ({ label: s.label, varName: s.varName, dashed: false })),
  ...(props.extraSeries ?? []).map((es) => ({ label: es.label, varName: undefined, rawColor: es.color, dashed: true })),
]);

function legendSwatchStyle(it: { varName?: string; rawColor?: string; dashed: boolean }) {
  const color = it.varName ? `var(${it.varName})` : it.rawColor;
  return {
    background: it.dashed
      ? `repeating-linear-gradient(90deg, ${color} 0 5px, transparent 5px 9px)`
      : color,
  };
}

/** 悬浮提示定位：跟随指针，纵向夹紧避免溢出 */
function tooltipStyle(h: { x: number; y: number }) {
  return { left: h.x + 12 + 'px', top: Math.min(h.y + 12, 130) + 'px' };
}
</script>

<template>
  <div class="chart-root">
    <div class="legend">
      <span v-for="it in legendItems" :key="it.label" class="legend-item">
        <span class="legend-swatch" :style="legendSwatchStyle(it)" aria-hidden="true" />
        {{ it.label }}
      </span>
      <span class="legend-unit">单位 · 净压力（扣除空载）</span>
    </div>
    <div class="chart-wrap" @mousemove="onMove" @mouseleave="onLeave">
      <canvas ref="canvasRef" class="chart" />
      <div v-if="hover && hover.values.length" class="tooltip" :style="tooltipStyle(hover)">
        <div class="tt-title num">帧 {{ hover.idx }}</div>
        <div v-for="v in hover.values" :key="v.label" class="tt-row">
          <span class="tt-dot" :style="{ background: v.color }" aria-hidden="true" />
          <span class="tt-label">{{ v.label }}</span>
          <span class="tt-val num">{{ v.v }}</span>
        </div>
      </div>
      <div v-if="history.length === 0" class="empty">
        <Icon name="activity" :size="16" />
        <span>暂无数据</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chart-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.legend {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding-bottom: 8px;
  flex: none;
  flex-wrap: wrap;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-2xs);
  color: var(--text-2);
  white-space: nowrap;
}
.legend-swatch {
  width: 14px;
  height: 3px;
  border-radius: 999px;
  display: inline-block;
}
.legend-unit {
  margin-left: auto;
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
}
.chart-wrap {
  position: relative;
  flex: 1;
  min-height: 110px;
}
.chart {
  width: 100%;
  height: 100%;
  display: block;
}
.tooltip {
  position: absolute;
  pointer-events: none;
  background: var(--surface-1);
  border: 1px solid var(--border);
  color: var(--text-1);
  font-size: var(--fs-2xs);
  padding: 7px 10px;
  border-radius: var(--r-sm);
  z-index: 10;
  line-height: 1.7;
  box-shadow: var(--shadow-pop);
  min-width: 132px;
}
.tt-title {
  color: var(--text-3);
  margin-bottom: 3px;
  font-size: 11px;
  letter-spacing: 0.03em;
}
.tt-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tt-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.tt-label {
  flex: 1;
  color: var(--text-2);
}
.tt-val {
  color: var(--text-1);
  font-weight: 600;
}
.empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-3);
  font-size: var(--fs-xs);
  pointer-events: none;
}
</style>
