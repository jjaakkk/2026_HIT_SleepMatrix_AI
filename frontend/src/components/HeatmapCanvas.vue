<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, computed } from 'vue';
import { renderHeatmap, pickCell, computeFrameMax, turboColor } from '../render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from '../render/heatmap.ts';
import { COLS, ROWS, type BodyRegion, type SpinePoint } from '../core/types.ts';
import { REGION_COLORS } from '../core/region-stats.ts';
import {
  AIRBAG_RECTS,
  AIRBAG_SENSORS,
  AIRBAG_ID_TO_COLOR,
  REGION_COLORS as AIRBAG_REGION_COLORS,
  mmToMatrixCell,
  type AirbagSensor,
} from '../core/airbag-layout.ts';
import type { AirbagState } from '../core/airbag.ts';

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
  /** 身体分区推理掩码（44×24，1肩 2背 3腰 4臀 5大腿；推理接入模式） */
  partitionMask?: number[][] | null;
  /** 布置图传感器叠加层开关 */
  showSensors?: boolean;
  /** 气囊实时状态（模拟源）：充气 → 对应传感器点增强（支撑效果模拟联动） */
  airbagStates?: AirbagState[] | null;
  /** 选中传感器（外部联动曲线） */
  selectedSensor?: number | null;
}>();

const emit = defineEmits<{
  hover: [info: { row: number; col: number; value: number } | null];
  'region-hover': [index: number | null];
  'region-select': [index: number];
  'sensor-select': [id: number];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const hover = ref<{ row: number; col: number; value: number; x: number; y: number } | null>(null);
const hoverRegion = ref<number | null>(null);
const hoverSensor = ref<AirbagSensor | null>(null);

const cssWidth = ref(0);
const cssHeight = computed(() => (cssWidth.value * ROWS) / COLS);

const frameMax = computed(() => computeFrameMax(props.frame));

/** 悬浮格对应的 turbo 色（工具提示色块） */
const hoverColor = computed(() => {
  if (!hover.value) return '#888';
  const m = frameMax.value || 1;
  const t = Math.min(Math.max(hover.value.value / m, 0), 1);
  const [r, g, b] = turboColor(t);
  return `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
});

// ---------------------------------------------------------------------------
// 布置图传感器叠加层（60 点：mm 坐标 → 44×24 矩阵格心 → px）
// ---------------------------------------------------------------------------

const sensorPx = computed(() => {
  if (!props.showSensors || cssWidth.value === 0) return [];
  const pressureById = new Map<string, number>();
  for (const s of props.airbagStates ?? []) pressureById.set(s.zoneId, s.pressure);
  return AIRBAG_SENSORS.map((s) => {
    const cell = mmToMatrixCell(s.xMm, s.yMm);
    const px = ((cell.col + 0.5) / COLS) * cssWidth.value;
    const py = ((cell.row + 0.5) / ROWS) * cssHeight.value;
    const pressure = pressureById.get(s.airbagId) ?? 0;
    const boost = pressure / 100; // 0..1：气囊充气 → 传感器点增强（模拟支撑效果）
    return {
      sensor: s,
      x: px,
      y: py,
      color: AIRBAG_REGION_COLORS[s.region],
      r: 4 + boost * 2.4,
      boost,
      value: props.frame[cell.row * COLS + cell.col] ?? 0,
      active: hoverSensor.value?.id === s.id || props.selectedSensor === s.id,
    };
  });
});

/** 气囊矩形叠加层（mm 精确投影，比例与布置图一致） */
const airbagRectsPx = computed(() => {
  if (!props.showSensors || cssWidth.value === 0) return [];
  return AIRBAG_RECTS.map((r) => ({
    id: r.id,
    color: AIRBAG_ID_TO_COLOR[r.id] ?? '#888888',
    x: (r.x1 / 1800) * cssWidth.value,
    y: (r.y1 / 2000) * cssHeight.value,
    w: ((r.x2 - r.x1) / 1800) * cssWidth.value,
    h: ((r.y2 - r.y1) / 2000) * cssHeight.value,
  }));
});

// 区域矩形（px 坐标；覆盖到 x2/y2 格含）
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

// 分区掩码类色（class_id 1..5 → 肩/背/腰/臀/大腿，与 REGION_COLORS 对齐）
const PARTITION_CLASS_COLORS: Record<number, string> = {
  1: REGION_COLORS['肩部'],
  2: REGION_COLORS['背部'],
  3: REGION_COLORS['腰部'],
  4: REGION_COLORS['臀部'],
  5: REGION_COLORS['大腿部'],
};

/** 分区掩码覆盖层（推理接入模式：非零像素按类别着色，半透明叠加于热力图） */
interface MaskCell {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
}
const partitionMaskCells = computed<MaskCell[]>(() => {
  if (!props.partitionMask || !props.showRegions || cssWidth.value === 0) return [];
  const cw = cssWidth.value / COLS;
  const ch = cssHeight.value / ROWS;
  const cells: MaskCell[] = [];
  for (let r = 0; r < ROWS; r++) {
    const row: number[] | undefined = props.partitionMask[r];
    if (!row) continue;
    for (let c = 0; c < COLS; c++) {
      const cls = row[c] ?? 0;
      const color = PARTITION_CLASS_COLORS[cls];
      if (!color) continue;
      cells.push({ x: c * cw, y: r * ch, w: cw + 0.6, h: ch + 0.6, color });
    }
  }
  return cells;
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
  // 传感器命中检测（优先展示传感器提示）
  let hitSensor: AirbagSensor | null = null;
  if (props.showSensors) {
    let best = Infinity;
    for (const s of AIRBAG_SENSORS) {
      const c = mmToMatrixCell(s.xMm, s.yMm);
      const sx = ((c.col + 0.5) / COLS) * cssWidth.value;
      const sy = ((c.row + 0.5) / ROWS) * cssHeight.value;
      const d = Math.hypot(px - sx, py - sy);
      if (d < 12 && d < best) {
        best = d;
        hitSensor = s;
      }
    }
  }
  hoverSensor.value = hitSensor;
  if (!hitSensor) emit('hover', cell);
}

function onLeave() {
  hover.value = null;
  hoverSensor.value = null;
  emit('hover', null);
}
function onSensorClick(id: number) {
  emit('sensor-select', id);
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

const hoverSensorPx = computed(() =>
  hoverSensor.value
    ? sensorPx.value.find((s) => s.sensor.id === hoverSensor.value!.id) ?? null
    : null,
);
function measureBase(): HTMLElement | null {
  const wrap = canvasRef.value?.parentElement;
  return wrap?.parentElement ?? null;
}

onMounted(() => {
  const zone = measureBase();
  if (zone) {
    const w = zone.clientWidth;
    const h = props.maxHeight ?? Infinity;
    cssWidth.value = Math.min(w, (h * COLS) / ROWS);
  }
  draw();
  window.addEventListener('resize', onResize);
});

function onResize() {
  const zone = measureBase();
  if (zone) {
    const w = zone.clientWidth;
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
      v-if="regionRects.length || spinePx.length || partitionMaskCells.length"
      class="overlay"
      :width="cssWidth"
      :height="cssHeight"
    >
      <g v-if="partitionMaskCells.length" class="partition-mask" pointer-events="none">
        <rect
          v-for="(cell, i) in partitionMaskCells"
          :key="i"
          :x="cell.x"
          :y="cell.y"
          :width="cell.w"
          :height="cell.h"
          :fill="cell.color"
          fill-opacity="0.22"
          stroke="rgba(13,17,23,0.35)"
          stroke-width="0.5"
        />
      </g>
      <g v-if="spinePx.length && spinePath" class="spine">
        <path
          :d="spinePath"
          fill="none"
          stroke="rgba(238,243,248,0.9)"
          stroke-width="1.3"
          stroke-dasharray="5 3.5"
          stroke-linecap="round"
        />
        <circle
          v-for="(p, i) in spinePx"
          :key="i"
          :cx="p.x"
          :cy="p.y"
          r="3.4"
          fill="#eef3f8"
          stroke="rgba(13,17,23,0.85)"
          stroke-width="1"
        />
      </g>
      <g
        v-for="rect in regionRects"
        :key="`${rect.index}-${rect.active}`"
        class="region"
        :class="{ active: rect.active }"
        @mouseenter="onRegionEnter(rect.index)"
        @mouseleave="onRegionLeave"
        @click.stop="onRegionClick(rect.index)"
      >
        <rect
          :x="rect.x + 1.5"
          :y="rect.y + 1.5"
          :width="Math.max(rect.w - 3, 2)"
          :height="Math.max(rect.h - 3, 2)"
          :rx="6"
          :fill="rect.color"
          :fill-opacity="rect.active ? 0.26 : 0.1"
          :stroke="rect.active ? '#ffffff' : rect.color"
          :stroke-width="rect.active ? 2.2 : 1.3"
          :stroke-opacity="rect.active ? 1 : 0.75"
        />
        <rect
          :x="rect.x + 5"
          :y="rect.y + 5"
          :width="(rect.name.length * 12 + 16)"
          :height="17"
          :rx="5.5"
          :fill="rect.active ? rect.color : 'rgba(13,17,23,0.78)'"
          :stroke="rect.active ? '#ffffff' : rect.color"
          :stroke-width="1.1"
        />
        <text
          :x="rect.x + 5 + (rect.name.length * 12 + 16) / 2"
          :y="rect.y + 5 + 11.8"
          :fill="rect.active ? 'rgba(13,17,23,0.92)' : rect.color"
          font-size="10.5"
          font-weight="700"
          text-anchor="middle"
          pointer-events="none"
        >
          {{ rect.name }}
        </text>
      </g>
      <g v-if="airbagRectsPx.length" class="airbag-rects" pointer-events="none">
        <g v-for="r in airbagRectsPx" :key="r.id">
          <rect
            :x="r.x"
            :y="r.y"
            :width="r.w"
            :height="r.h"
            :rx="4"
            :fill="r.color"
            fill-opacity="0.1"
            :stroke="r.color"
            stroke-opacity="0.55"
            stroke-width="1.1"
          />
          <text
            :x="r.x + r.w / 2"
            :y="r.y + r.h / 2 + 3.5"
            :fill="r.color"
            font-size="9.5"
            font-weight="700"
            text-anchor="middle"
            opacity="0.95"
          >
            {{ r.id }}
          </text>
        </g>
      </g>
      <g v-if="sensorPx.length" class="sensors">
        <g
          v-for="s in sensorPx"
          :key="s.sensor.id"
          class="sensor"
          :class="{ active: s.active, boosted: s.boost > 0.5 }"
          @click.stop="onSensorClick(s.sensor.id)"
        >
          <circle
            v-if="s.boost > 0.5"
            :cx="s.x"
            :cy="s.y"
            :r="s.r + 4.5"
            :fill="s.color"
            fill-opacity="0.16"
            pointer-events="none"
          />
          <circle
            :cx="s.x"
            :cy="s.y"
            :r="s.r"
            :fill="s.active ? '#ffffff' : s.color"
            :fill-opacity="s.active ? 0.95 : 0.75"
            :stroke="s.active ? s.color : 'rgba(10,14,20,0.9)'"
            :stroke-width="s.active ? 2.4 : 1.2"
          />
        </g>
      </g>
      <g v-if="hover && hoverRegion === null && !hoverSensor" class="crosshair" pointer-events="none">
        <line
          :x1="hover.x"
          :y1="0"
          :x2="hover.x"
          :y2="cssHeight"
          stroke="rgba(255,255,255,0.28)"
          stroke-width="1"
        />
        <line
          :x1="0"
          :y1="hover.y"
          :x2="cssWidth"
          :y2="hover.y"
          stroke="rgba(255,255,255,0.28)"
          stroke-width="1"
        />
      </g>
    </svg>
    <Transition name="tip">
      <div
        v-if="hoverSensor && hoverSensorPx"
        class="tooltip sensor-tip"
        :style="{
          left: Math.min(hoverSensorPx.x + 14, cssWidth - 200) + 'px',
          top: Math.max(hoverSensorPx.y - 40, 8) + 'px',
        }"
      >
        <span
          class="swatch"
          :style="{ background: AIRBAG_REGION_COLORS[hoverSensor.region] }"
          aria-hidden="true"
        />
        <span class="tt-main num">传感器 {{ hoverSensor.id }} · 气囊 {{ hoverSensor.airbagId }}</span>
        <span class="tt-sub num">净压 {{ hoverSensorPx.value.toFixed(0) }}</span>
      </div>
    </Transition>
    <Transition name="tip">
      <div
        v-if="hover && hoverRegion === null && !hoverSensor"
        class="tooltip"
        :style="{ left: Math.min(hover.x + 14, cssWidth - 150) + 'px', top: Math.max(hover.y - 42, 8) + 'px' }"
      >
        <span class="swatch" :style="{ background: hoverColor }" aria-hidden="true" />
        <span class="tt-main num">净压 {{ hover.value.toFixed(0) }}</span>
        <span class="tt-sub num">行 {{ hover.row }} · 列 {{ hover.col }}</span>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.heatmap-wrap {
  position: relative;
  /* 收缩包裹画布实际尺寸：深色底只存在于热力图之下，不留黑块 */
  width: fit-content;
  max-width: 100%;
  margin: 0 auto;
  border-radius: var(--r-md);
  overflow: hidden;
  background: #0c0f15;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.05),
    inset 0 1px 8px rgba(0, 0, 0, 0.35),
    var(--shadow-float);
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
.sensor {
  cursor: pointer;
}
.sensor circle {
  transition:
    r var(--dur-base) var(--ease-out),
    fill-opacity var(--dur-base) var(--ease-out);
}
.sensor.active circle {
  filter: drop-shadow(0 0 4px rgba(255, 255, 255, 0.55));
}
.sensor-tip .tt-main {
  color: #ffffff;
}
.spine {
  animation: spine-in 640ms var(--ease-out);
}
@keyframes spine-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.region rect {
  transition:
    fill-opacity var(--dur-base) var(--ease-out),
    stroke-opacity var(--dur-base) var(--ease-out);
}
.region.active > rect:first-child {
  animation: region-pop var(--dur-slow) var(--ease-out);
}
@keyframes region-pop {
  0% {
    fill-opacity: 0.42;
  }
  100% {
    fill-opacity: 0.26;
  }
}
.crosshair {
  animation: none;
}
.tooltip {
  position: absolute;
  pointer-events: none;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 9px;
  background: rgba(13, 17, 23, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 7px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.4);
  color: #eef3f8;
  font-size: 11px;
  white-space: nowrap;
  z-index: 10;
  backdrop-filter: blur(4px);
}
.swatch {
  width: 8px;
  height: 8px;
  border-radius: 2.5px;
  flex: none;
}
.tt-main {
  font-weight: 600;
  letter-spacing: 0;
}
.tt-sub {
  color: rgba(238, 243, 248, 0.62);
  font-size: 11px;
}
.tip-enter-active,
.tip-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}
.tip-enter-from,
.tip-leave-to {
  opacity: 0;
  transform: translateY(3px);
}
@media (prefers-reduced-motion: reduce) {
  .spine {
    animation: none;
  }
}
</style>
