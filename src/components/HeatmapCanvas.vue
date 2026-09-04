<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, computed } from 'vue';
import { renderHeatmap, pickCell, computeFrameMax } from '../render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from '../render/heatmap.ts';
import { COLS, ROWS, type BodyRegion, type SpinePoint } from '../core/types.ts';
import { REGION_COLORS } from '../core/region-stats.ts';

const props = defineProps<{
  frame: ArrayLike<number>;
  mode: HeatmapMode;
  scale: ScaleMode;
  /** 画布最大高度（CSS px，用于保证底部曲线图可见） */
  maxHeight?: number;
  /** 身体部位区域（null = 无标注不画） */
  regions?: BodyRegion[] | null;
  /** 脊柱点（null = 无标注不画） */
  spine?: SpinePoint[] | null;
  showRegions?: boolean;
  showSpine?: boolean;
  /** 小腿部仅在 SAI/dgs/gzy 有标注，默认不显示 */
  showCalf?: boolean;
  selectedRegion?: number | null;
}>();

const emit = defineEmits<{
  hover: [info: { row: number; col: number; value: number } | null];
  'region-hover': [index: number | null];
  'region-select': [index: number];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ row: number; col: number; value: number; x: number; y: number } | null>(null);
const hoverRegion = ref<number | null>(null);

const cssWidth = ref(0);
const cssHeight = computed(() => (cssWidth.value * ROWS) / COLS);

const frameMax = computed(() => computeFrameMax(props.frame));

// 区域矩形（px 坐标；列 x → px = x*W/COLS，行 y → px = y*H/ROWS，覆盖到 x2/y2 格含）
const regionRects = computed(() => {
  if (!props.regions || !props.showRegions || cssWidth.value === 0) return [];
  return props.regions
    .map((r, index) => ({ r, index }))
    .filter(({ r, index }) => r.valid && (index < 5 || props.showCalf))
    .map(({ r, index }) => {
      const x = (r.x1 / COLS) * cssWidth.value;
      const y = (r.y1 / ROWS) * cssHeight.value;
      const w = ((r.x2 - r.x1 + 1) / COLS) * cssWidth.value;
      const h = ((r.y2 - r.y1 + 1) / ROWS) * cssHeight.value;
      return {
        index,
        name: r.name,
        color: REGION_COLORS[r.name] ?? '#8b949e',
        x,
        y,
        w,
        h,
        active: hoverRegion.value === index || props.selectedRegion === index,
      };
    });
});

const spinePx = computed(() => {
  if (!props.spine || !props.showSpine || cssWidth.value === 0) return [];
  return props.spine.map((p) => ({
    x: ((p.x + 0.5) / COLS) * cssWidth.value,
    y: ((p.y + 0.5) / ROWS) * cssHeight.value,
  }));
});
const spinePath = computed(() =>
  spinePx.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '),
);

function draw() {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  // 平滑模式做 2× 超采样（浏览器缩放时平滑下采样），消除格心插值的阶梯感
  const ss = props.mode === 'grid' ? 1 : 2;
  const w = Math.round(cssWidth.value * dpr * ss);
  const h = Math.round(((cssWidth.value * ROWS) / COLS) * dpr * ss);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const ctx = canvas.getContext('2d')!;
  renderHeatmap(ctx, props.frame, { mode: props.mode, scale: props.scale, width: w, height: h });
}

function onMove(e: MouseEvent) {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const px = e.clientX - rect.left;
  const py = e.clientY - rect.top;
  const cell = pickCell(px, py, rect.width, rect.height, props.frame);
  hover.value = { ...cell, x: px, y: py };
  emit('hover', cell);
}

function onLeave() {
  hover.value = null;
  emit('hover', null);
}
function onRegionEnter(i: number) {
  hoverRegion.value = i;
  emit('region-hover', i);
}
function onRegionLeave() {
  hoverRegion.value = null;
  emit('region-hover', null);
}
function onRegionClick(i: number) {
  emit('region-select', i);
}

onMounted(() => {
  const wrap = canvasRef.value?.parentElement;
  if (wrap) {
    const w = wrap.clientWidth;
    const h = props.maxHeight ?? Infinity;
    cssWidth.value = Math.min(w, (h * COLS) / ROWS);
  }
  draw();
  window.addEventListener('resize', onResize);
});

function onResize() {
  const wrap = canvasRef.value?.parentElement;
  if (wrap) {
    const w = wrap.clientWidth;
    const h = props.maxHeight ?? Infinity;
    cssWidth.value = Math.min(w, (h * COLS) / ROWS);
  }
  draw();
}

watch(() => [props.frame, props.mode, props.scale, props.maxHeight, cssWidth.value], draw);

onBeforeUnmount(() => window.removeEventListener('resize', onResize));
</script>

<template>
  <div class="heatmap-wrap" @mousemove="onMove" @mouseleave="onLeave">
    <canvas ref="canvasRef" :style="{ width: cssWidth + 'px', height: cssHeight + 'px' }" />
    <svg
      v-if="regionRects.length || spinePx.length"
      class="overlay"
      :width="cssWidth"
      :height="cssHeight"
    >
      <g v-if="spinePx.length && spinePath">
        <path :d="spinePath" fill="none" stroke="#e6edf3" stroke-width="1.2" stroke-dasharray="4 3" opacity="0.85" />
        <circle v-for="(p, i) in spinePx" :key="i" :cx="p.x" :cy="p.y" r="3.5" fill="#e6edf3" opacity="0.95" />
      </g>
      <g
        v-for="rect in regionRects"
        :key="rect.index"
        class="region"
        :class="{ active: rect.active }"
        @mouseenter="onRegionEnter(rect.index)"
        @mouseleave="onRegionLeave"
        @click.stop="onRegionClick(rect.index)"
      >
        <rect
          :x="rect.x"
          :y="rect.y"
          :width="rect.w"
          :height="rect.h"
          :fill="rect.color"
          :fill-opacity="rect.active ? 0.3 : 0.08"
          :stroke="rect.active ? '#ffffff' : rect.color"
          :stroke-width="rect.active ? 3 : 1.2"
        />
        <text
          :x="rect.x + 4"
          :y="rect.y + 13"
          :fill="rect.active ? '#ffffff' : rect.color"
          font-size="11"
          font-weight="700"
          stroke="#0d1117"
          stroke-width="3"
          paint-order="stroke"
          pointer-events="none"
        >
          {{ rect.name }}
        </text>
      </g>
    </svg>
    <div v-if="hover && hoverRegion === null" class="tooltip" :style="{ left: hover.x + 12 + 'px', top: hover.y - 10 + 'px' }">
      (行{{ hover.row }}, 列{{ hover.col }}) 净压 = {{ hover.value.toFixed(0) }}
    </div>
  </div>
</template>

<style scoped>
.heatmap-wrap {
  position: relative;
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  background: #0a0e14;
}
canvas {
  display: block;
  cursor: crosshair;
}
.overlay {
  position: absolute;
  top: 0;
  left: 0;
}
.region {
  cursor: pointer;
}
.tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(22, 27, 34, 0.95);
  border: 1px solid #30363d;
  color: #e6edf3;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
  z-index: 10;
}
</style>
