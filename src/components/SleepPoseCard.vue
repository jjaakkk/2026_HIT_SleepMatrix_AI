<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  /** 状态名：仰卧/俯卧/左侧卧/右侧卧/离床·无人/在床/动态过程 */
  pose: string;
  /** 持续帧数 */
  durationFrames: number;
  /** 回放基准帧率（时长 = 帧数 / fps） */
  fps: number;
  note?: string;
}>();

const POSE_COLORS: Record<string, string> = {
  仰卧: '#4da6ff',
  俯卧: '#e6b84c',
  左侧卧: '#2fd6b6',
  右侧卧: '#ff7a6b',
  离床: '#7a8794',
  '离床 · 无人': '#7a8794',
  在床: '#2fd6b6',
  动态过程: '#2fd6b6',
};

const color = computed(() => POSE_COLORS[props.pose] ?? '#8B949E');
const seconds = computed(() => (props.durationFrames / props.fps).toFixed(1));

function stroke() {
  return { stroke: color.value, color: color.value };
}
</script>

<template>
  <div
    class="pose-card"
    :style="{
      borderColor: color,
      boxShadow: `inset 0 0 0 1px ${color}14, 0 0 18px ${color}22`,
    }"
  >
    <div class="lamp" :style="{ background: color, boxShadow: `0 0 12px ${color}90` }"></div>
    <svg class="icon" viewBox="0 0 64 64" :stroke="color" stroke-width="2" fill="none">
      <!-- 床 -->
      <rect x="8" y="46" width="48" height="10" rx="3" :stroke-dasharray="pose === '离床 · 无人' || pose === '离床' ? '4 3' : 'none'" />
      <!-- 仰卧 / 俯卧：对称身体 -->
      <template v-if="pose === '仰卧' || pose === '俯卧' || pose === '在床'">
        <circle cx="32" cy="16" r="7" />
        <rect x="20" y="24" width="24" height="16" rx="8" />
        <rect x="25" y="40" width="5" height="9" rx="2.5" />
        <rect x="34" y="40" width="5" height="9" rx="2.5" />
      </template>
      <!-- 左侧卧：窄身体偏左 -->
      <template v-else-if="pose === '左侧卧'">
        <circle cx="21" cy="17" r="6" />
        <rect x="15" y="25" width="12" height="19" rx="6" />
        <rect x="17" y="44" width="8" height="7" rx="4" />
      </template>
      <!-- 右侧卧：窄身体偏右 -->
      <template v-else-if="pose === '右侧卧'">
        <circle cx="43" cy="17" r="6" />
        <rect x="37" y="25" width="12" height="19" rx="6" />
        <rect x="39" y="44" width="8" height="7" rx="4" />
      </template>
      <!-- 离床：只有床 -->
      <template v-else-if="pose === '离床' || pose === '离床 · 无人'"></template>
      <!-- 动态过程：床 + 状态点 -->
      <template v-else>
        <circle cx="16" cy="22" r="3" fill="none" />
        <circle cx="32" cy="14" r="3" fill="none" />
        <circle cx="48" cy="22" r="3" fill="none" />
        <path d="M10 34 Q 32 44 54 34" stroke-dasharray="3 3" />
      </template>
    </svg>
    <div class="body">
      <div class="pose-name" :style="{ color }">{{ pose }}</div>
      <div class="duration num">持续 {{ durationFrames }} 帧 · {{ seconds }} 秒</div>
      <div v-if="note" class="note">{{ note }}</div>
    </div>
  </div>
</template>

<style scoped>
.pose-card {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid;
  border-radius: var(--r-card);
  padding: 9px 11px;
  margin-bottom: 10px;
  background: var(--panel-inset);
}
.lamp {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
  align-self: flex-start;
  margin-top: 6px;
}
.icon {
  width: 42px;
  height: 42px;
  flex: none;
}
.body {
  min-width: 0;
}
.pose-name {
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.01em;
}
.duration {
  font-size: 11.5px;
  color: var(--text-2);
  margin-top: 2px;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.note {
  font-size: 10px;
  color: var(--text-3);
  margin-top: 2px;
  line-height: 1.4;
}
</style>
