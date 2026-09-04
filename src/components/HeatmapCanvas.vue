<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue';
import { renderHeatmap, pickCell, computeFrameMax } from '../render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from '../render/heatmap.ts';
import { COLS, ROWS } from '../core/types.ts';

const props = defineProps<{
  frame: ArrayLike<number>;
  mode: HeatmapMode;
  scale: ScaleMode;
}>();

const emit = defineEmits<{ hover: [info: { row: number; col: number; value: number } | null] }>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ row: number; col: number; value: number; x: number; y: number } | null>(null);

const cssWidth = ref(0);
const cssHeight = computed(() => (cssWidth.value * ROWS) / COLS);

const frameMax = computed(() => computeFrameMax(props.frame));

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

onMounted(() => {
  const wrap = canvasRef.value?.parentElement;
  if (wrap) cssWidth.value = wrap.clientWidth;
  draw();
});

watch(() => [props.frame, props.mode, props.scale, cssWidth.value], draw);
</script>

<template>
  <div class="heatmap-wrap" @mousemove="onMove" @mouseleave="onLeave">
    <canvas ref="canvasRef" :style="{ width: cssWidth + 'px', height: cssHeight + 'px' }" />
    <div v-if="hover" class="tooltip" :style="{ left: hover.x + 12 + 'px', top: hover.y - 10 + 'px' }">
      (行{{ hover.row }}, 列{{ hover.col }}) = {{ hover.value.toFixed(0) }}
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
