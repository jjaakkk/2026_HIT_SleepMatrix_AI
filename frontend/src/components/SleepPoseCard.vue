<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  /** 状态名：仰卧/俯卧/左侧卧/右侧卧/离床·无人/在床/动态过程/推理标签 */
  pose: string;
  /** 持续帧数 */
  durationFrames: number;
  /** 回放基准帧率（时长 = 帧数 / fps） */
  fps: number;
  note?: string;
  /** 回放进行中（呼吸指示点） */
  live?: boolean;
  /** 睡姿判定来源 */
  source?: 'label' | 'inference';
  /** 推理置信度 0-1（仅 source=inference 时展示） */
  confidence?: number | null;
  /** 推理请求进行中 */
  predicting?: boolean;
}>();

const POSE_COLORS: Record<string, string> = {
  仰卧: '#3b82f6',
  俯卧: '#e6a23c',
  左侧卧: '#14b8a6',
  右侧卧: '#f4695f',
  离床: '#8b8f98',
  '离床 · 无人': '#8b8f98',
  在床: '#14b8a6',
  动态过程: '#0d7a6b',
};

const color = computed(() => POSE_COLORS[props.pose] ?? '#8b8f98');
const seconds = computed(() => (props.durationFrames / props.fps).toFixed(1));
const isEmpty = computed(() => props.pose === '离床' || props.pose === '离床 · 无人');
const confidencePct = computed(() =>
  props.confidence != null ? Math.round(Math.min(Math.max(props.confidence, 0), 1) * 100) : null,
);
</script>

<template>
  <div
    class="pose-card"
    :style="{ '--pose-color': color, borderColor: `color-mix(in srgb, ${color} 26%, transparent)` }"
  >
    <div class="tile" :aria-hidden="true">
      <svg class="icon" viewBox="0 0 64 64" :stroke="color" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <!-- 床 -->
        <rect
          x="8"
          y="46"
          width="48"
          height="9"
          rx="3"
          :stroke-dasharray="isEmpty ? '4 3.2' : 'none'"
          opacity="0.85"
        />
        <!-- 仰卧 / 俯卧 / 在床 -->
        <template v-if="pose === '仰卧' || pose === '俯卧' || pose === '在床'">
          <circle cx="32" cy="16" r="6.6" />
          <rect x="21" y="24.5" width="22" height="15" rx="7.5" />
          <rect x="26" y="39.5" width="4.4" height="8" rx="2.2" />
          <rect x="33.6" y="39.5" width="4.4" height="8" rx="2.2" />
        </template>
        <!-- 左侧卧 -->
        <template v-else-if="pose === '左侧卧'">
          <circle cx="21.5" cy="17.5" r="5.6" />
          <rect x="15.5" y="25" width="11" height="18" rx="5.5" />
          <rect x="17.5" y="43" width="7" height="6.5" rx="3.2" />
        </template>
        <!-- 右侧卧 -->
        <template v-else-if="pose === '右侧卧'">
          <circle cx="42.5" cy="17.5" r="5.6" />
          <rect x="37.5" y="25" width="11" height="18" rx="5.5" />
          <rect x="39.5" y="43" width="7" height="6.5" rx="3.2" />
        </template>
        <!-- 动态过程 -->
        <template v-else-if="pose === '动态过程'">
          <circle cx="16" cy="22" r="2.6" />
          <circle cx="32" cy="14" r="2.6" />
          <circle cx="48" cy="22" r="2.6" />
          <path d="M10 35.5 Q 32 44.5 54 35.5" stroke-dasharray="3.4 3.4" />
        </template>
      </svg>
    </div>

    <div class="body">
      <div class="name-row">
        <span class="pose-name">{{ pose }}</span>
        <span v-if="live && !isEmpty" class="live-dot" title="监测中" aria-hidden="true" />
        <span v-if="source === 'inference'" class="src-badge" :class="{ busy: predicting && confidencePct === null }">
          {{ predicting && confidencePct === null ? '推理中' : 'SVM 推理' }}
        </span>
      </div>
      <div class="duration num">
        持续 {{ durationFrames }} 帧 · {{ seconds }} 秒
      </div>
      <div v-if="source === 'inference'" class="conf-row">
        <span class="conf-track" aria-hidden="true">
          <span
            class="conf-fill"
            :style="{ width: (confidencePct ?? 0) + '%' }"
            :class="{ busy: predicting && confidencePct === null }"
          />
        </span>
        <span class="conf-val num">
          {{ confidencePct !== null ? `置信度 ${confidencePct}%` : '等待结果…' }}
        </span>
      </div>
      <div v-if="note" class="note">{{ note }}</div>
    </div>
  </div>
</template>

<style scoped>
.pose-card {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 14px 16px;
  border-radius: var(--r-sm);
  /* 嵌套规则：面板内不再嵌套带边框卡片 —— 用明度块表达层级 */
  border: none;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--pose-color) 7%, var(--surface-2)),
    var(--surface-2) 55%
  );
  transition: background-color var(--dur-base) var(--ease-out);
}
.pose-card:hover {
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--pose-color) 10%, var(--surface-hover)),
    var(--surface-hover) 55%
  );
}
.tile {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: var(--r-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--pose-color) 13%, var(--surface-1));
  border: 1px solid color-mix(in srgb, var(--pose-color) 22%, transparent);
}
.icon {
  width: 40px;
  height: 40px;
  display: block;
}
.body {
  min-width: 0;
  flex: 1;
}
.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pose-name {
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-1);
  line-height: 1.2;
}
.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-success);
  flex: none;
  animation: breathe 2s var(--ease-in-out) infinite;
}
@keyframes breathe {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.4;
    transform: scale(0.75);
  }
}
.duration {
  font-size: var(--fs-xs);
  color: var(--text-2);
  margin-top: 2px;
}
.src-badge {
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-strong);
  border-radius: var(--r-pill);
  padding: 1px 7px;
  white-space: nowrap;
  transition:
    color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}
.src-badge.busy {
  color: var(--text-3);
  background: var(--surface-3);
  border-color: var(--border);
  animation: busy-breathe 1.6s var(--ease-in-out) infinite;
}
@keyframes busy-breathe {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}
.conf-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
}
.conf-track {
  flex: 1;
  max-width: 84px;
  height: 4px;
  background: var(--surface-3);
  border-radius: 999px;
  overflow: hidden;
}
.conf-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width var(--dur-slow) var(--ease-out);
}
.conf-fill.busy {
  animation: conf-indeterminate 1.2s var(--ease-in-out) infinite;
}
@keyframes conf-indeterminate {
  0% {
    width: 12%;
    margin-left: 0;
  }
  50% {
    width: 46%;
  }
  100% {
    width: 12%;
    margin-left: 88%;
  }
}
.conf-val {
  font-size: 10.5px;
  color: var(--text-2);
  white-space: nowrap;
}
.note {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  margin-top: 2px;
  line-height: 1.45;
}
@media (prefers-reduced-motion: reduce) {
  .live-dot,
  .src-badge.busy,
  .conf-fill.busy {
    animation: none;
  }
}
</style>
