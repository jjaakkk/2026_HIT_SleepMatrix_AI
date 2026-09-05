<script setup lang="ts">
/**
 * 左侧控制栏：数据源 / 回放 / 渲染 / 图层。
 * 无卡片外壳，分区标签 + 控件直排（Linear 式导航栏）。
 */
import { computed } from 'vue';
import UiSegmented from './ui/UiSegmented.vue';
import UiSwitch from './ui/UiSwitch.vue';
import UiSelect, { type SelectOption } from './ui/UiSelect.vue';
import Icon from './ui/Icon.vue';
import { SLEEP_POS_NAMES } from '../core/types';
import type { DemoAction, DemoPerson } from '../core/demo';
import type { HeatmapMode, ScaleMode } from '../render/heatmap';

const props = defineProps<{
  dataSource: 'demo' | 'simulated';
  sourceType: 'static' | 'dynamic';
  people: DemoPerson[];
  personIdx: number;
  person: DemoPerson | null;
  actionIdx: number;
  mode: HeatmapMode;
  scale: ScaleMode;
  showRegions: boolean;
  showSpine: boolean;
  showCalf: boolean;
  showDynLabels: boolean;
  /** 睡姿判定来源：记录标签 / 后端推理 */
  poseSource: 'label' | 'inference';
  /** 后端服务是否在线（离线时禁用 SVM 推理选项） */
  backendOnline: boolean;
}>();

const emit = defineEmits<{
  'update:dataSource': [v: 'demo' | 'simulated'];
  'update:sourceType': [v: 'static' | 'dynamic'];
  'update:personIdx': [v: number];
  'update:actionIdx': [v: number];
  'update:mode': [v: HeatmapMode];
  'update:scale': [v: ScaleMode];
  'update:showRegions': [v: boolean];
  'update:showSpine': [v: boolean];
  'update:showCalf': [v: boolean];
  'update:showDynLabels': [v: boolean];
  'update:poseSource': [v: 'label' | 'inference'];
}>();

function actionLabel(a: DemoAction): string {
  if (a.action === 0) return '空载记录 · 无人';
  return `${SLEEP_POS_NAMES[a.sleepPos] ?? ''} · 记录 ${a.action}`;
}

const personOptions = computed<SelectOption[]>(() =>
  props.people.map((p, i) => ({
    value: i,
    label: `${p.name} · ${p.height ?? '?'} cm / ${p.weight ?? '?'} kg`,
  })),
);

const actionOptions = computed<SelectOption[]>(() =>
  (props.person?.actions ?? []).map((a, i) => ({ value: i, label: actionLabel(a) })),
);

const dataSourceOptions = [
  { value: 'demo', label: '真实记录' },
  { value: 'simulated', label: '内置演示' },
];
const sourceOptions = [
  { value: 'static', label: '姿态动作' },
  { value: 'dynamic', label: '翻身过程' },
];
const modeOptions: { value: HeatmapMode; label: string; title?: string }[] = [
  { value: 'smooth', label: '标准', title: '标准压扩曲线' },
  { value: 'weak', label: '弱力可视化', title: '渲染压扩 γ=0.35，突出弱压力区域（可视化口径，非后端增强算法）' },
  { value: 'grid', label: '原始网格', title: '逐格原始读数' },
];
const scaleOptions: { value: ScaleMode; label: string; title?: string }[] = [
  { value: 'fixed250', label: '0–250', title: '固定量程 0–250' },
  { value: 'auto', label: '自动', title: '按当前帧峰值自适应' },
  { value: 'fixed500', label: '0–500', title: '固定量程 0–500' },
];
const poseSourceOptions = computed(() => [
  { value: 'label', label: '记录标签', title: '使用记录内睡姿标签（离线可用）' },
  {
    value: 'inference',
    label: 'SVM 推理',
    disabled: !props.backendOnline,
    title: props.backendOnline
      ? '调用后端 /api/posture/predict 逐帧推理'
      : '后端未连接，SVM 推理不可用',
  },
]);
</script>

<template>
  <nav class="rail" aria-label="数据与控制">
    <section class="group">
      <h4 class="group-title"><Icon name="database" :size="11" />数据源</h4>
      <UiSegmented
        :model-value="dataSource"
        :options="dataSourceOptions"
        size="sm"
        aria-label="数据源"
        @update:model-value="emit('update:dataSource', $event as 'demo' | 'simulated')"
      />
    </section>

    <section class="group">
      <h4 class="group-title"><Icon name="history" :size="11" />回放</h4>
      <UiSegmented
        :model-value="sourceType"
        :options="sourceOptions"
        size="sm"
        aria-label="回放类型"
        @update:model-value="emit('update:sourceType', $event as 'static' | 'dynamic')"
      />
    </section>

    <template v-if="sourceType === 'static'">
      <section class="group">
        <h4 class="group-title"><Icon name="user" :size="11" />受测者</h4>
        <UiSelect
          :model-value="personIdx"
          :options="personOptions"
          icon="user"
          aria-label="选择受测者"
          @update:model-value="emit('update:personIdx', $event as number)"
        />
      </section>
      <section class="group">
        <h4 class="group-title"><Icon name="body" :size="11" />姿态记录</h4>
        <UiSelect
          :model-value="actionIdx"
          :options="actionOptions"
          icon="body"
          aria-label="选择姿态记录"
          @update:model-value="emit('update:actionIdx', $event as number)"
        />
      </section>
    </template>

    <section class="group">
      <h4 class="group-title"><Icon name="body" :size="11" />睡姿识别</h4>
      <UiSegmented
        :model-value="poseSource"
        :options="poseSourceOptions"
        size="sm"
        aria-label="睡姿判定来源"
        @update:model-value="emit('update:poseSource', $event as 'label' | 'inference')"
      />
      <p class="foot">
        <template v-if="poseSource === 'inference'">后端逐帧推理 · 结果与置信度来自算法服务</template>
        <template v-else>记录内标签 · 离线可用；接后端后可选 SVM 推理</template>
      </p>
    </section>

    <section class="group">
      <h4 class="group-title"><Icon name="layers" :size="11" />渲染</h4>
      <UiSegmented
        :model-value="mode"
        :options="modeOptions"
        size="sm"
        aria-label="渲染模式"
        @update:model-value="emit('update:mode', $event as HeatmapMode)"
      />
      <div class="gap-8" />
      <UiSegmented
        :model-value="scale"
        :options="scaleOptions"
        size="sm"
        aria-label="压力量程"
        @update:model-value="emit('update:scale', $event as ScaleMode)"
      />
    </section>

    <section class="group">
      <h4 class="group-title"><Icon name="eye" :size="11" />图层</h4>
      <ul class="layers">
        <li>
          <label class="row">
            <span class="txt">
              部位区域
              <span class="hint">24 区域标注</span>
            </span>
            <UiSwitch
              :model-value="showRegions"
              @update:model-value="emit('update:showRegions', $event)"
            />
          </label>
        </li>
        <li>
          <label class="row">
            <span class="txt">
              脊柱参考线
              <span class="hint">5 点拟合</span>
            </span>
            <UiSwitch :model-value="showSpine" @update:model-value="emit('update:showSpine', $event)" />
          </label>
        </li>
        <li>
          <label class="row">
            <span class="txt">
              小腿区域
              <span class="hint">3 人已标注</span>
            </span>
            <UiSwitch :model-value="showCalf" @update:model-value="emit('update:showCalf', $event)" />
          </label>
        </li>
        <li v-if="sourceType === 'dynamic'">
          <label class="row">
            <span class="txt">
              原始参考标签
              <span class="hint">文件自带</span>
            </span>
            <UiSwitch
              :model-value="showDynLabels"
              @update:model-value="emit('update:showDynLabels', $event)"
            />
          </label>
        </li>
      </ul>
    </section>
  </nav>
</template>

<style scoped>
.rail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px 8px 0;
  overflow-y: auto;
  min-height: 0;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-2xs);
  font-weight: 600;
  letter-spacing: 0.07em;
  color: var(--text-3);
  padding-left: 2px;
}
.group-title .icon {
  opacity: 0.9;
}
.gap-8 {
  height: 8px;
}
.layers {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px 7px 2px;
  border-radius: var(--r-sm);
  cursor: pointer;
  transition: background-color var(--dur-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}
.row:hover {
  background: var(--surface-2);
}
.txt {
  font-size: var(--fs-xs);
  color: var(--text-1);
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}
.hint {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  white-space: nowrap;
}
.foot {
  font-size: 10.5px;
  color: var(--text-3);
  line-height: 1.5;
  padding: 0 2px;
}
</style>
