<script setup lang="ts">
/**
 * 中央热力图面板：标题行 + 热力图 + 量程图例 + 传输控制。
 */
import { computed, onMounted, ref } from 'vue';
import HeatmapCanvas from './HeatmapCanvas.vue';
import UiSegmented from './ui/UiSegmented.vue';
import Icon from './ui/Icon.vue';
import { turboColor } from '../render/heatmap';
import type { HeatmapMode, ScaleMode } from '../render/heatmap';
import type { BodyRegion, SpinePoint } from '../core/types';

const props = defineProps<{
  frame: ArrayLike<number>;
  mode: HeatmapMode;
  scale: ScaleMode;
  maxHeight: number;
  regions: BodyRegion[] | null;
  spine: SpinePoint[] | null;
  showRegions: boolean;
  showSpine: boolean;
  showCalf: boolean;
  selectedRegion: number | null;
  sourceLabel: string;
  frameIdx: number;
  frameCount: number;
  playing: boolean;
  speed: number;
  /** 量程刻度（固定档）或 null（自动） */
  legendTicks: number[] | null;
  /** 图例说明文案 */
  legendCaption: string;
  /** 量程超限警告文案（null = 正常） */
  scaleWarning?: string | null;
}>();

const emit = defineEmits<{
  hover: [info: { row: number; col: number; value: number } | null];
  'region-hover': [index: number | null];
  'region-select': [index: number];
  'toggle-play': [];
  'step-prev': [];
  'step-next': [];
  seek: [index: number];
  speed: [v: number];
  'update:mode': [v: HeatmapMode];
  'update:scale': [v: ScaleMode];
}>();

const legendCanvas = ref<HTMLCanvasElement | null>(null);

function drawLegend() {
  const c = legendCanvas.value;
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth || 132;
  const h = c.clientHeight || 10;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }
  const ctx = c.getContext('2d')!;
  ctx.scale(dpr, dpr);
  for (let x = 0; x < w; x++) {
    const [r, g, b] = turboColor(x / (w - 1));
    ctx.fillStyle = `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
    ctx.fillRect(x, 0, 1, h);
  }
}

onMounted(drawLegend);

function onSeek(e: Event) {
  emit('seek', Number((e.target as HTMLInputElement).value));
}

/** 进度填充百分比（scrubber 轨道渐变） */
const fillPct = computed(() =>
  props.frameCount > 1 ? (props.frameIdx / (props.frameCount - 1)) * 100 : 0,
);

const MODE_LABELS: Record<HeatmapMode, string> = {
  smooth: '标准渲染',
  weak: '弱力可视化',
  grid: '原始网格',
};
const modeLabel = computed(() => MODE_LABELS[props.mode]);

const speedOptions = [
  { value: 0.5, label: '0.5×' },
  { value: 1, label: '1×' },
  { value: 2, label: '2×' },
  { value: 4, label: '4×' },
];

const modeOptions: { value: HeatmapMode; label: string; title?: string }[] = [
  { value: 'smooth', label: '标准', title: '标准压扩曲线' },
  { value: 'weak', label: '弱力', title: '渲染压扩 γ=0.35，突出弱压力区域（可视化口径）' },
  { value: 'grid', label: '网格', title: '逐格原始读数' },
];
const scaleOptions: { value: ScaleMode; label: string; title?: string }[] = [
  { value: 'fixed250', label: '0–250', title: '固定量程 0–250' },
  { value: 'auto', label: '自动', title: '按当前帧峰值自适应' },
  { value: 'fixed500', label: '0–500', title: '固定量程 0–500' },
];
</script>

<template>
  <section class="heatmap-panel">
    <header class="panel-head">
      <div class="src">
        <Icon name="activity" :size="13" class="src-icon" />
        <span class="src-label">{{ sourceLabel }}</span>
      </div>
      <div class="head-right">
        <span class="mode-chip">{{ modeLabel }}</span>
        <span class="frame-num num">{{ String(frameIdx).padStart(2, '0') }} / {{ frameCount - 1 }}</span>
      </div>
    </header>

    <div class="toolbar">
      <div class="tool-group" role="group" aria-label="渲染模式">
        <UiSegmented
          :model-value="mode"
          :options="modeOptions"
          size="sm"
          :equal="false"
          @update:model-value="emit('update:mode', $event as HeatmapMode)"
        />
      </div>
      <div class="tool-group" role="group" aria-label="压力量程">
        <UiSegmented
          :model-value="scale"
          :options="scaleOptions"
          size="sm"
          :equal="false"
          @update:model-value="emit('update:scale', $event as ScaleMode)"
        />
      </div>
    </div>

    <div class="canvas-zone">
      <HeatmapCanvas
        :frame="frame"
        :mode="mode"
        :scale="scale"
        :max-height="maxHeight"
        :regions="regions"
        :spine="spine"
        :show-regions="showRegions"
        :show-spine="showSpine"
        :show-calf="showCalf"
        :selected-region="selectedRegion"
        @hover="emit('hover', $event)"
        @region-hover="emit('region-hover', $event)"
        @region-select="emit('region-select', $event)"
      />
    </div>

    <div class="legend">
      <div class="legend-bar-wrap">
        <canvas ref="legendCanvas" class="legend-bar" aria-hidden="true" />
        <div v-if="legendTicks" class="legend-ticks num">
          <span v-for="t in legendTicks" :key="t">{{ t }}</span>
        </div>
      </div>
      <p class="legend-caption">
        <span v-if="legendTicks">固定量程</span>
        <template v-else>
          <span>自动量程</span>
          <span class="num peak">{{ legendCaption }}</span>
        </template>
      </p>
      <p v-if="scaleWarning" class="legend-warn">{{ scaleWarning }}</p>
      <p v-else class="legend-hint">悬停查看读数 · 点击区域联动曲线</p>
    </div>

    <div class="transport">
      <button class="ctl" type="button" title="上一帧" aria-label="上一帧" @click="emit('step-prev')">
        <Icon name="chevron-left" :size="15" />
      </button>
      <button
        class="ctl play"
        type="button"
        :class="{ on: playing }"
        :title="playing ? '暂停' : '播放'"
        :aria-label="playing ? '暂停' : '播放'"
        @click="emit('toggle-play')"
      >
        <Transition name="icon-swap" mode="out-in">
          <Icon v-if="playing" key="pause" name="pause" :size="15" />
          <Icon v-else key="play" name="play-fill" :size="15" filled />
        </Transition>
      </button>
      <button class="ctl" type="button" title="下一帧" aria-label="下一帧" @click="emit('step-next')">
        <Icon name="chevron-right" :size="15" />
      </button>
      <input
        class="scrub"
        type="range"
        :min="0"
        :max="Math.max(frameCount - 1, 0)"
        :value="frameIdx"
        :style="{ '--fill': fillPct + '%' }"
        aria-label="回放进度"
        @input="onSeek"
      />
      <div class="speed-seg">
        <UiSegmented
          :model-value="speed"
          :options="speedOptions"
          size="sm"
          :equal="false"
          aria-label="回放速度"
          @update:model-value="emit('speed', $event as number)"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.heatmap-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: 14px 16px 14px;
}

/* 标题行 */
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 10px;
  flex: none;
}
.src {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.src-icon {
  color: var(--accent);
  flex: none;
}
.src-label {
  font-size: var(--fs-sm);
  font-weight: 600;
  letter-spacing: 0.005em;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.head-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}
.mode-chip {
  font-size: var(--fs-2xs);
  color: var(--text-2);
  border: 1px solid var(--border);
  background: var(--surface-2);
  border-radius: var(--r-pill);
  padding: 2px 9px;
  white-space: nowrap;
}
.frame-num {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--text-2);
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* 工具栏：渲染 + 量程（自侧栏移入，贴近操作对象） */
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding-bottom: 10px;
}
.tool-group :deep(.seg) {
  width: auto;
}

/* 画布区 */
.canvas-zone {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px 0;
}

/* 图例行 */
.legend {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  padding-top: 12px;
  flex: none;
}
.legend-bar-wrap {
  flex: none;
  width: 132px;
}
.legend-bar {
  width: 132px;
  height: 10px;
  display: block;
  border-radius: 3px;
  border: 1px solid var(--border);
}
.legend-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-3);
  margin-top: 4px;
  letter-spacing: -0.01em;
}
.legend-caption {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
  padding-bottom: 1px;
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.legend-caption .peak {
  color: var(--text-2);
  font-size: var(--fs-xs);
}
.legend-hint {
  margin-left: auto;
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
  padding-bottom: 1px;
  opacity: 0.9;
}
.legend-warn {
  margin-left: auto;
  font-size: var(--fs-2xs);
  color: var(--c-warning);
  white-space: nowrap;
  padding-bottom: 1px;
}

/* 传输控制 */
.transport {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-top: 12px;
  flex: none;
}
.ctl {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex: none;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  cursor: pointer;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}
.ctl:hover {
  color: var(--text-1);
  border-color: var(--border-strong);
  background: var(--surface-1);
}
.ctl:active {
  transform: scale(0.92);
}
.ctl.play {
  width: 36px;
  height: 36px;
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-contrast);
}
.ctl.play:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  color: var(--accent-contrast);
  transform: translateY(-1px);
}
.ctl.play:active {
  transform: scale(0.94);
}
.ctl.play.on {
  animation: play-ring 1.8s var(--ease-out) infinite;
}
@keyframes play-ring {
  0% {
    box-shadow: 0 0 0 0 var(--accent-ring);
  }
  70% {
    box-shadow: 0 0 0 9px transparent;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
  }
}
.icon-swap-enter-active,
.icon-swap-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-spring);
}
.icon-swap-enter-from {
  opacity: 0;
  transform: scale(0.7);
}
.icon-swap-leave-to {
  opacity: 0;
  transform: scale(0.7);
}

.scrub {
  flex: 1;
  min-width: 60px;
  height: 20px;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  cursor: pointer;
}
.scrub::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(
    to right,
    var(--accent) 0%,
    var(--accent) var(--fill, 0%),
    var(--surface-3) var(--fill, 0%),
    var(--surface-3) 100%
  );
  border: 1px solid var(--border-subtle);
}
.scrub::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 13px;
  height: 13px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--surface-1);
  border: 2.5px solid var(--accent);
  box-shadow: var(--shadow-float);
  transition:
    transform var(--dur-fast) var(--ease-spring),
    box-shadow var(--dur-fast) var(--ease-out);
}
.scrub:hover::-webkit-slider-thumb {
  transform: scale(1.15);
  box-shadow: 0 0 0 4px var(--accent-ring);
}
.scrub:active::-webkit-slider-thumb {
  transform: scale(1.05);
  box-shadow: 0 0 0 6px var(--accent-ring);
}
.scrub::-moz-range-track {
  height: 4px;
  border-radius: 999px;
  background: var(--surface-3);
}
.scrub::-moz-range-progress {
  height: 4px;
  border-radius: 999px;
  background: var(--accent);
}
.scrub::-moz-range-thumb {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--surface-1);
  border: 2.5px solid var(--accent);
}

.speed-seg {
  flex: none;
}
.speed-seg :deep(.seg) {
  width: auto;
}

@media (prefers-reduced-motion: reduce) {
  .ctl.play.on {
    animation: none;
  }
}
</style>
