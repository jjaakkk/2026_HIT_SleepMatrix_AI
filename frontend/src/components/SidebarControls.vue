<script setup lang="ts">
/**
 * 左侧控制栏：品牌 + 数据源/回放/受测者/姿态/睡姿识别/图层/系统状态。
 * 无卡片外壳，分区标签 + 控件直排（Linear 式导航栏）。
 * 渲染/量程已移至热力图面板工具栏，本栏保持极简。
 */
import { computed } from 'vue';
import UiSegmented from './ui/UiSegmented.vue';
import UiSelect, { type SelectOption } from './ui/UiSelect.vue';
import Icon from './ui/Icon.vue';
import { SLEEP_POS_NAMES } from '../core/types';
import type { DemoAction, DemoPerson } from '../core/demo';
import type { DisplayMode } from '../composables/useFrameInference';

const props = defineProps<{
  dataSource: 'demo' | 'simulated';
  sourceType: 'static' | 'dynamic';
  people: DemoPerson[];
  personIdx: number;
  person: DemoPerson | null;
  actionIdx: number;
  showRegions: boolean;
  showSpine: boolean;
  showCalf: boolean;
  showDynLabels: boolean;
  /** 数据模式：推理接入（默认，模型驱动界面）| 数据展示（记录标签与标注） */
  displayMode: DisplayMode;
  backendOnline: boolean;
  backendState: 'checking' | 'online' | 'offline';
  modelAvailable: boolean;
  partitionModelAvailable: boolean;
  contractMismatch: boolean;
  simulated: boolean;
}>();

const emit = defineEmits<{
  'update:dataSource': [v: 'demo' | 'simulated'];
  'update:sourceType': [v: 'static' | 'dynamic'];
  'update:personIdx': [v: number];
  'update:actionIdx': [v: number];
  'update:showRegions': [v: boolean];
  'update:showSpine': [v: boolean];
  'update:showCalf': [v: boolean];
  'update:showDynLabels': [v: boolean];
  'update:displayMode': [v: DisplayMode];
  open3d: [];
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
const displayModeOptions = computed(() => [
  {
    value: 'inference',
    label: '推理接入',
    disabled: !props.backendOnline,
    title: props.backendOnline
      ? '调用后端 /api/frame/analyze 逐帧分析（睡姿 + 身体分区 + 弱区增强），结果驱动热力图、区域与 3D 模型'
      : '后端未连接 · 已按数据展示兜底，重连后自动恢复推理',
  },
  {
    value: 'demo',
    label: '数据展示',
    title: '使用记录内睡姿标签与部位标注渲染（离线可用）',
  },
]);

interface LayerDef {
  key: 'showRegions' | 'showSpine' | 'showCalf' | 'showDynLabels';
  icon: string;
  label: string;
  title: string;
  visible: boolean;
}
const layers = computed<LayerDef[]>(() => [
  {
    key: 'showRegions',
    icon: 'target',
    label: '部位区域',
    title:
      props.displayMode === 'inference'
        ? '身体分区模型输出（/api/frame/analyze）'
        : '24 区域标注',
    visible: true,
  },
  {
    key: 'showSpine',
    icon: 'activity',
    label: '脊柱参考线',
    title: '5 点拟合（记录标注）',
    visible: props.displayMode === 'demo',
  },
  {
    key: 'showCalf',
    icon: 'layers',
    label: '小腿区域',
    title: '3 人已标注（记录标注）',
    visible: props.displayMode === 'demo',
  },
  {
    key: 'showDynLabels',
    icon: 'clock',
    label: '原始标签',
    title: '文件自带 · 仅供参考',
    visible: props.sourceType === 'dynamic',
  },
]);

function layerValue(key: LayerDef['key']): boolean {
  return props[key];
}
function toggleLayer(key: LayerDef['key']) {
  const v = !props[key];
  if (key === 'showRegions') emit('update:showRegions', v);
  else if (key === 'showSpine') emit('update:showSpine', v);
  else if (key === 'showCalf') emit('update:showCalf', v);
  else emit('update:showDynLabels', v);
}
</script>

<template>
  <nav class="rail" aria-label="数据与控制">
    <div class="brand">
      <div class="mark" aria-hidden="true">
        <svg viewBox="0 0 28 28" fill="none">
          <defs>
            <linearGradient id="sm-brand-side" x1="4" y1="3" x2="24" y2="26" gradientUnits="userSpaceOnUse">
              <stop stop-color="var(--brand-from)" />
              <stop offset="1" stop-color="var(--brand-to)" />
            </linearGradient>
          </defs>
          <rect width="28" height="28" rx="8" fill="url(#sm-brand-side)" />
          <path
            d="M7.5 14.2c1.1-1.5 2-1.5 3.1 0s2 1.5 3.1 0 2-1.5 3.1 0 2 1.5 3.1 0"
            stroke="#fff"
            stroke-width="1.7"
            stroke-linecap="round"
            opacity="0.95"
          />
        </svg>
      </div>
      <div class="brand-text">
        <span class="name">SleepMatrix</span>
        <span class="sub">睡眠压力监测台</span>
      </div>
    </div>

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
      <h4 class="group-title"><Icon name="sparkles" :size="11" />数据模式</h4>
      <UiSegmented
        :model-value="displayMode"
        :options="displayModeOptions"
        size="sm"
        aria-label="数据模式（推理接入 / 数据展示）"
        @update:model-value="emit('update:displayMode', $event as 'inference' | 'demo')"
      />
    </section>

    <section class="group">
      <h4 class="group-title"><Icon name="eye" :size="11" />图层</h4>
      <div class="layer-grid">
        <button
          v-for="l in layers.filter((x) => x.visible)"
          :key="l.key"
          type="button"
          class="layer-chip"
          :class="{ on: layerValue(l.key) }"
          :aria-pressed="layerValue(l.key)"
          :title="l.title"
          @click="toggleLayer(l.key)"
        >
          <Icon :name="l.icon" :size="12" />
          <span>{{ l.label }}</span>
        </button>
      </div>
    </section>

    <section class="group">
      <h4 class="group-title"><Icon name="cube" :size="11" />三维演示</h4>
      <button type="button" class="d3-open" title="打开全屏 3D 睡姿视图（人体模型 + 床垫热力图）" @click="emit('open3d')">
        <Icon name="cube" :size="13" />
        <span>打开 3D 睡姿视图</span>
      </button>
    </section>

    <section class="group status">
      <h4 class="group-title"><Icon name="radio" :size="11" />系统状态</h4>
      <ul class="status-list">
        <li v-if="contractMismatch" class="status-row warn" title="后端契约版本与前端基线不一致，已保持本地映射">
          <i class="dot" />契约版本不一致
        </li>
        <li
          v-else
          class="status-row"
          :class="backendState === 'online' ? 'ok' : 'mute'"
          :title="
            backendState === 'online'
              ? modelAvailable
                ? '算法服务已连接 · 睡姿模型就绪'
                : '算法服务已连接 · 睡姿模型缺失（已回退记录标签）'
              : backendState === 'offline'
                ? '后端未连接 · 推理接入模式自动回退数据展示'
                : '检测后端 /api/health …'
          "
        >
          <i class="dot" />
          {{ backendState === 'online' ? '算法服务在线' : backendState === 'offline' ? '算法服务未连接' : '算法服务检测中' }}
        </li>
        <li
          v-if="backendState === 'online'"
          class="status-row"
          :class="partitionModelAvailable ? 'ok' : 'warn'"
          :title="
            partitionModelAvailable
              ? '身体分区模型就绪 · 热力图区域与掩码由模型输出'
              : '身体分区模型缺失 · 区域回退记录标注'
          "
        >
          <i class="dot" />
          {{ partitionModelAvailable ? '分区模型就绪' : '分区模型缺失' }}
        </li>
        <li
          v-if="displayMode === 'inference' && backendState !== 'online'"
          class="status-row warn"
          title="推理接入模式 · 后端重连后自动恢复逐帧分析"
        >
          <i class="dot" />等待后端 · 数据展示兜底
        </li>
        <li v-if="simulated" class="status-row warn" title="使用内置模拟数据">
          <i class="dot" />演示模式 · 内置数据
        </li>
        <li class="status-row mute" title="条带布局依据布置图编号；压力数据为回放，不受模拟气囊影响">
          <i class="dot" />气囊 · 模拟信号
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
  padding: 2px 2px 8px 0;
  height: 100%;
  overflow-y: auto;
  min-height: 0;
}

/* 品牌行 */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 2px 10px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 2px;
}
.mark {
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 8px;
  box-shadow: var(--shadow-float);
}
.mark svg {
  width: 100%;
  height: 100%;
  display: block;
}
.brand-text {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}
.name {
  font-size: var(--fs-lg);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  font-size: var(--fs-2xs);
  color: var(--text-3);
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

/* 图层：紧凑芯片格（2 列） */
.layer-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px;
}
.layer-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 27px;
  padding: 4px 8px;
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
.layer-chip:hover {
  border-color: var(--border-strong);
  color: var(--text-1);
}
.layer-chip.on {
  color: var(--accent);
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}

/* 3D 视图入口 */
.d3-open {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 30px;
  padding: 5px 10px;
  background: linear-gradient(135deg, var(--brand-from), var(--brand-to));
  color: #f2fbf6;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  font-size: var(--fs-xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    filter var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}
.d3-open:hover {
  filter: brightness(1.08);
  box-shadow: var(--shadow-float);
}

/* 系统状态 */
.status {
  margin-top: auto;
  padding-top: 2px;
}
.status-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-2xs);
  color: var(--text-2);
  padding: 2px 2px;
}
.status-row .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-slate);
  flex: none;
}
.status-row.ok .dot {
  background: var(--c-success);
}
.status-row.warn {
  color: var(--c-warning);
}
.status-row.warn .dot {
  background: var(--c-amber);
}
.status-row.mute .dot {
  background: var(--c-slate);
}
</style>
