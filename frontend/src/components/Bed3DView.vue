<script setup lang="ts">
/**
 * 3D 睡姿演示：全屏叠加层。
 * - 床垫热力图与当前回放帧实时联动（displayFrame，净压力）。
 * - 睡姿默认跟随当前记录（sleepPos），可手动切换四种睡姿。
 * - 人体模型：Cesium RiggedFigure（CC BY 4.0）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import Icon from './ui/Icon.vue';
import { Bed3DScene, type PostureId } from '../three/bed3d';
import { SLEEP_POS_NAMES } from '../core/types';

const props = withDefaults(
  defineProps<{
    /** 当前显示帧（1056 净压力值，行优先） */
    frame: ArrayLike<number>;
    /** 当前记录的睡姿 label id（0-3） */
    sleepPos: number;
    /** 帧来源说明（显示在标题副行） */
    sourceLabel?: string;
    modelUrl?: string;
  }>(),
  { sourceLabel: '', modelUrl: '' },
);

const emit = defineEmits<{ close: [] }>();

const canvasEl = ref<HTMLCanvasElement | null>(null);
const manual = ref<PostureId | null>(null);
const follow = ref(true);
const breathing = ref(true);
const loadError = ref<string | null>(null);

let scene: Bed3DScene | null = null;

const POSTURES: { id: PostureId; label: string }[] = [
  { id: 0, label: '仰卧' },
  { id: 1, label: '俯卧' },
  { id: 2, label: '左侧卧' },
  { id: 3, label: '右侧卧' },
];

const posture = computed<PostureId>(() => {
  if (manual.value !== null) return manual.value;
  const p = props.sleepPos;
  return p >= 0 && p <= 3 ? (p as PostureId) : 0;
});

function pickPosture(id: PostureId): void {
  manual.value = id;
  follow.value = false;
}
function toggleFollow(): void {
  follow.value = !follow.value;
  if (follow.value) manual.value = null;
}
function toggleBreathing(): void {
  breathing.value = !breathing.value;
  scene?.setBreathing(breathing.value);
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close');
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown);
  if (!canvasEl.value) return;
  try {
    scene = new Bed3DScene(canvasEl.value);
  } catch (e) {
    loadError.value = `当前环境无法创建 WebGL 上下文（${e instanceof Error ? e.message : String(e)}）`;
    return;
  }
  (window as unknown as Record<string, unknown>).__bed3dDebug = () =>
    scene?.debugInfo() ?? null;
  (window as unknown as Record<string, unknown>).__bed3dScene = scene;
  scene.setFrame(props.frame);
  scene.setPosture(posture.value);
  scene.start();
  const url = props.modelUrl || `${import.meta.env.BASE_URL}models/Soldier.glb`;
  try {
    await scene.loadBody(url);
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e);
  }
});

watch(
  () => props.frame,
  (f) => scene?.setFrame(f),
);
watch(posture, (p) => scene?.setPosture(p));
watch(
  () => props.sleepPos,
  () => {
    // 跟随模式下切记录时同步睡姿
    if (follow.value) manual.value = null;
  },
);

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
  scene?.dispose();
  scene = null;
});
</script>

<template>
  <div class="bed3d" role="dialog" aria-label="三维睡姿演示">
    <header class="bed3d-bar">
      <div class="bed3d-title">
        <Icon name="cube" :size="15" />
        <div class="bed3d-title-text">
          <span class="title">三维睡姿演示</span>
          <span class="sub" v-if="sourceLabel">{{ sourceLabel }}</span>
          <span class="sub" v-else>人体模型 · Cesium RiggedFigure（CC BY 4.0）</span>
        </div>
      </div>

      <div class="pose-switch" role="group" aria-label="睡姿选择">
        <button
          v-for="p in POSTURES"
          :key="p.id"
          type="button"
          class="pose-chip"
          :class="{ on: posture === p.id }"
          :aria-pressed="posture === p.id"
          @click="pickPosture(p.id)"
        >
          {{ p.label }}
        </button>
        <button
          type="button"
          class="pose-chip util"
          :class="{ on: follow }"
          :aria-pressed="follow"
          :title="follow ? '睡姿跟随当前回放记录' : '手动选择睡姿'"
          @click="toggleFollow"
        >
          <Icon name="radio" :size="12" />
          跟随回放
        </button>
        <button
          type="button"
          class="pose-chip util"
          :class="{ on: breathing }"
          :aria-pressed="breathing"
          title="呼吸起伏动画"
          @click="toggleBreathing"
        >
          <Icon name="wind" :size="12" />
          呼吸
        </button>
      </div>

      <button type="button" class="close" title="关闭（Esc）" @click="emit('close')">
        <Icon name="x" :size="16" />
      </button>
    </header>

    <div class="bed3d-canvas-wrap">
      <canvas ref="canvasEl" class="bed3d-canvas" />
      <p v-if="loadError" class="bed3d-error">
        人体模型加载失败：{{ loadError }}（床垫热力图仍可正常查看）
      </p>
      <div class="bed3d-hint">
        <span>拖拽旋转</span>
        <span>滚轮缩放</span>
        <span>右键平移</span>
        <span>Esc 关闭</span>
      </div>
      <div class="bed3d-credit">
        {{ SLEEP_POS_NAMES[posture] }} · 床垫热力图 = 当前帧净压力 · 气囊条带 = 布置示意
      </div>
    </div>
  </div>
</template>

<style scoped>
.bed3d {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  background: rgba(5, 9, 14, 0.94);
  backdrop-filter: blur(6px);
  animation: bed3d-in 220ms var(--ease-out) both;
}
@keyframes bed3d-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.bed3d-bar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(13, 20, 28, 0.6);
}
.bed3d-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-1);
  min-width: 0;
}
.bed3d-title-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.bed3d-title .title {
  font-size: var(--fs-md);
  font-weight: 600;
  letter-spacing: 0.01em;
}
.bed3d-title .sub {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pose-switch {
  display: flex;
  gap: 6px;
  margin-left: auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.pose-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 5px 12px;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: var(--fs-xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}
.pose-chip:hover {
  border-color: var(--border-strong);
  color: var(--text-1);
}
.pose-chip.on {
  color: var(--accent);
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}
.pose-chip.util.on {
  color: #0f2a1d;
  background: var(--brand-from);
  border-color: var(--brand-from);
}

.close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--surface-2);
  color: var(--text-2);
  cursor: pointer;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}
.close:hover {
  color: var(--text-1);
  border-color: var(--border-strong);
}

.bed3d-canvas-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}
.bed3d-canvas {
  display: block;
  width: 100%;
  height: 100%;
  outline: none;
}
.bed3d-error {
  position: absolute;
  left: 50%;
  top: 16px;
  transform: translateX(-50%);
  max-width: 80%;
  padding: 8px 14px;
  border-radius: var(--r-sm);
  background: rgba(120, 40, 20, 0.85);
  color: #ffd9c9;
  font-size: var(--fs-xs);
}
.bed3d-hint {
  position: absolute;
  right: 16px;
  bottom: 14px;
  display: flex;
  gap: 10px;
  font-size: var(--fs-2xs);
  color: var(--text-3);
}
.bed3d-hint span + span::before {
  content: '·';
  margin-right: 10px;
  opacity: 0.5;
}
.bed3d-credit {
  position: absolute;
  left: 16px;
  bottom: 14px;
  font-size: var(--fs-2xs);
  color: var(--text-3);
}
</style>
