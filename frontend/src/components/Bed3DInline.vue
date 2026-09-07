<script setup lang="ts">
/**
 * 嵌入式 3D 睡姿视图：持久展示在压力趋势面板位置（小尺寸画布），
 * 提供紧凑的睡姿切换/呼吸开关与全屏按钮。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Bed3DScene, type PostureId } from '../three/bed3d';
import { SLEEP_POS_NAMES } from '../core/types';
import Icon from './ui/Icon.vue';
import type { AirbagState } from '../core/airbag';

const props = withDefaults(
  defineProps<{
    frame: ArrayLike<number>;
    sleepPos: number;
    modelUrl?: string;
    airbagStates?: AirbagState[] | null;
  }>(),
  { modelUrl: '', airbagStates: null },
);

const emit = defineEmits<{ fullscreen: [] }>();

const canvasEl = ref<HTMLCanvasElement | null>(null);
const manual = ref<PostureId | null>(null);
const follow = ref(true);
const breathing = ref(true);

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

function pickPosture(id: PostureId) {
  manual.value = id;
  follow.value = false;
}
function toggleFollow() {
  follow.value = !follow.value;
  if (follow.value) manual.value = null;
}
function toggleBreathing() {
  breathing.value = !breathing.value;
  scene?.setBreathing(breathing.value);
}

onMounted(async () => {
  if (!canvasEl.value) return;
  scene = new Bed3DScene(canvasEl.value);
  scene.setFrame(props.frame);
  scene.setPosture(posture.value);
  scene.start();
  if (props.airbagStates) scene.setAirbagStates(props.airbagStates);
  const url = props.modelUrl || `${import.meta.env.BASE_URL}models/Soldier.glb`;
  try {
    await scene.loadBody(url);
  } catch {
    /* 模型缺失时仍展示床垫热力图与气囊 */
  }
});

watch(
  () => props.frame,
  (f) => scene?.setFrame(f),
);
watch(posture, (p) => scene?.setPosture(p));
watch(
  () => props.airbagStates,
  (s) => {
    if (s) scene?.setAirbagStates(s);
  },
  { immediate: true },
);
watch(
  () => props.sleepPos,
  () => {
    if (follow.value) manual.value = null;
  },
);

onBeforeUnmount(() => {
  scene?.dispose();
  scene = null;
});
</script>

<template>
  <div class="bed3d-inline">
    <div class="inline-bar">
      <div class="pose-chips" role="group" aria-label="睡姿选择">
        <button
          v-for="p in POSTURES"
          :key="p.id"
          type="button"
          class="chip"
          :class="{ on: posture === p.id }"
          :aria-pressed="posture === p.id"
          @click="pickPosture(p.id)"
        >
          {{ p.label }}
        </button>
        <button
          type="button"
          class="chip util"
          :class="{ on: follow }"
          :aria-pressed="follow"
          :title="follow ? '睡姿跟随当前回放记录' : '手动选择睡姿'"
          @click="toggleFollow"
        >
          跟随
        </button>
        <button
          type="button"
          class="chip util"
          :class="{ on: breathing }"
          :aria-pressed="breathing"
          title="呼吸起伏动画"
          @click="toggleBreathing"
        >
          呼吸
        </button>
      </div>
      <div class="inline-meta">
        <span class="pose-name">{{ SLEEP_POS_NAMES[posture] }}</span>
        <button
          type="button"
          class="fs"
          title="全屏查看 3D 视图"
          @click="emit('fullscreen')"
        >
          <Icon name="monitor" :size="12" />
          全屏
        </button>
      </div>
    </div>
    <div class="inline-canvas-wrap">
      <canvas ref="canvasEl" class="inline-canvas" />
    </div>
  </div>
</template>

<style scoped>
.bed3d-inline {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 6px;
}
.inline-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: none;
}
.pose-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 2px 8px;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-xs);
  font-size: var(--fs-2xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}
.chip:hover {
  border-color: var(--border-strong);
  color: var(--text-1);
}
.chip.on {
  color: var(--accent);
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}
.chip.util.on {
  color: #0f2a1d;
  background: var(--brand-from);
  border-color: var(--brand-from);
}
.inline-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.pose-name {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-2);
}
.fs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 2px 8px;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-xs);
  font-size: var(--fs-2xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.fs:hover {
  color: var(--accent);
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}
.inline-canvas-wrap {
  flex: 1;
  min-height: 0;
  border-radius: var(--r-sm);
  overflow: hidden;
  background: #0a1016;
  border: 1px solid var(--border-subtle);
}
.inline-canvas {
  display: block;
  width: 100%;
  height: 100%;
  outline: none;
}
</style>
