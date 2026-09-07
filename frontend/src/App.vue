<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import SidebarControls from './components/SidebarControls.vue';
import Bed3DView from './components/Bed3DView.vue';
import Bed3DInline from './components/Bed3DInline.vue';
import HeatmapPanel from './components/HeatmapPanel.vue';
import Icon from './components/ui/Icon.vue';
import InsightPanel from './components/InsightPanel.vue';
import MetricsChart from './components/MetricsChart.vue';
import AirbagPanel from './components/AirbagPanel.vue';
import PoseTimeline from './components/PoseTimeline.vue';
import RegionRanking from './components/RegionRanking.vue';
import PanelCard from './components/ui/PanelCard.vue';
import { useScaleToFit } from './composables/useScaleToFit.ts';
import type { DemoData } from './core/demo';
import type { HeatmapMode, ScaleMode } from './render/heatmap.ts';
import { SLEEP_POS_NAMES } from './core/types.ts';
import { computeMetrics, metricsHistory, isBedOccupied, poseDuration } from './core/metrics.ts';
import { parseRegion, parseSpine } from './core/parsers/annotations.ts';
import { regionStatsAll, regionMetrics, REGION_COLORS } from './core/region-stats.ts';
import { PlaybackController } from './core/playback.ts';
import { SimulatedAirbagSource, type AirbagState } from './core/airbag.ts';
import { generateSimulatedDataset } from './core/simulate.ts';
import { useFrameInference } from './composables/useFrameInference.ts';
import { partitionRegionsToBodyRegions } from './core/frame-inference.ts';
import { SENSOR_BY_ID, mmToMatrixCell } from './core/airbag-layout.ts';

// 缩放适配：固定 1920×1080 设计空间，任意分辨率整体等比缩放（零滚动零溢出）
const { scale } = useScaleToFit();

const data = ref<DemoData | null>(null);
/** 数据模式：demo = 真实记录子集；simulated = 内置演示数据 */
const dataSource = ref<'demo' | 'simulated'>('demo');
const simulatedCache = ref<DemoData | null>(null);

function simulatedData(): DemoData {
  if (!simulatedCache.value) {
    simulatedCache.value = generateSimulatedDataset() as unknown as DemoData;
  }
  return simulatedCache.value;
}

async function loadData(): Promise<void> {
  const h = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
  if (h.get('data') === 'sim') dataSource.value = 'simulated';
  if (dataSource.value === 'simulated') {
    data.value = simulatedData();
    return;
  }
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/demo.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data.value = (await res.json()) as DemoData;
  } catch (e) {
    console.warn('[数据] demo.json 加载失败，自动切换内置演示数据：', e);
    dataSource.value = 'simulated';
    data.value = simulatedData();
  }
}

/**
 * #dataset= 直链参数：从后端拉取数据集真实帧作为「离线回放」数据源
 * （未接入设备时回放历史记录；回放帧同样逐帧送模型推理）。
 */
async function loadDatasetStream(filesParam: string): Promise<void> {
  const names = filesParam.split(',').map((s) => s.trim()).filter(Boolean);
  if (names.length === 0) return;
  const query = names.map((n) => `files=${encodeURIComponent(n)}`).join('&');
  try {
    const res = await fetch(`/api/dataset/stream?${query}`);
    if (!res.ok) {
      console.warn(`[数据] 数据集流加载失败（HTTP ${res.status}），继续使用内置演示数据`);
      return;
    }
    const dynamic = (await res.json()) as DemoData['dynamic'];
    // 保留 demo.json 的 people（静态姿态回放用），替换翻身过程帧源
    data.value = { people: data.value?.people ?? [], dynamic };
    dataSource.value = 'demo';
    sourceType.value = 'dynamic';
    personIdx.value = 0;
    actionIdx.value = 0;
    selectedRegion.value = null;
    inference.setDisplayMode('demo');
    rebuildController();
  } catch (e) {
    console.warn('[数据] 数据集流加载失败，继续使用内置演示数据：', e);
  }
}

function selectDataSource(t: 'demo' | 'simulated'): void {
  if (dataSource.value === t) return;
  dataSource.value = t;
  const reset = () => {
    personIdx.value = 0;
    actionIdx.value = person.value?.actions.findIndex((a) => a.action !== 0) ?? 0;
    selectedRegion.value = null;
    rebuildController();
  };
  if (t === 'simulated') {
    data.value = simulatedData();
    reset();
  } else {
    data.value = null;
    loadData().then(reset);
  }
}

const personIdx = ref(0);
const person = computed(() => data.value?.people[personIdx.value] ?? null);
const sourceType = ref<'static' | 'dynamic'>('static');
const actionIdx = ref(0);
const mode = ref<HeatmapMode>('smooth');
const scaleMode = ref<ScaleMode>('auto');
const hoverRegion = ref<number | null>(null);

const currentAction = computed(() => person.value?.actions[actionIdx.value] ?? null);
// 离线回放模式：按侧栏回放选择（姿态动作/翻身过程）播放记录数据，帧同样送推理；
// 实时推理模式：帧源为设备接口（inference.deviceFrame），无输入时保持静止（黑屏）。
const effectiveDynamic = computed(() => sourceType.value === 'dynamic');
const frameCount = computed(() =>
  effectiveDynamic.value
    ? data.value?.dynamic.frames.length ?? 0
    : currentAction.value?.frames.length ?? 0,
);
const sleepPosName = computed(() =>
  effectiveDynamic.value
    ? '动态过程'
    : currentAction.value
      ? currentAction.value.action === 0
        ? metrics.value && !isBedOccupied(metrics.value)
          ? '离床 · 无人'
          : '在床'
        : (SLEEP_POS_NAMES[currentAction.value.sleepPos] ?? '未知')
      : '-',
);

// 睡姿状态持续时长（回放顺序内连续同状态帧数）
const poseKeys = computed(() =>
  history.value.map((m) => {
    if (effectiveDynamic.value) return '动态过程';
    if (currentAction.value?.action === 0) return isBedOccupied(m) ? '在床' : '离床 · 无人';
    return SLEEP_POS_NAMES[currentAction.value?.sleepPos ?? -1] ?? '未知';
  }),
);
const poseDurationFrames = computed(() => poseDuration(poseKeys.value, frameIdx.value));

const sourceLabel = computed(() => {
  if (inference.displayMode.value === 'inference') {
    return inference.deviceSource.value
      ? `设备流 · ${inference.deviceSource.value}`
      : '等待设备输入';
  }
  return sourceType.value === 'dynamic'
    ? `${data.value?.dynamic.person ?? ''} · 翻身过程`
    : `${person.value?.name ?? ''} · ${sleepPosName.value}`;
});

// 回放引擎
const controller = ref<PlaybackController | null>(null);
const frameIdx = ref(0);
const speed = ref(1);
const playing = ref(false);

function rebuildController() {
  if (inference.displayMode.value === 'inference') {
    // 实时推理：帧源为设备流，无回放控制器
    controller.value = null;
    frameIdx.value = 0;
    playing.value = false;
    return;
  }
  const frames = effectiveDynamic.value
    ? (data.value?.dynamic.frames ?? [])
    : (currentAction.value?.frames ?? []);
  if (frames.length === 0) {
    controller.value = null;
    frameIdx.value = 0;
    playing.value = false;
    return;
  }
  // 离线回放：停在末尾、手动播放（帧同样逐帧送推理）
  controller.value = new PlaybackController(frames as ArrayLike<number>[], {
    fps: 10,
    loop: false,
  });
  controller.value.onFrame = (i) => (frameIdx.value = i);
  controller.value.speed = speed.value;
  frameIdx.value = 0;
  playing.value = false;
}

const currentFrame = computed(
  () =>
    (inference.displayMode.value === 'inference'
      ? (inference.deviceFrame.value ?? new Float32Array(0))
      : effectiveDynamic.value
        ? data.value?.dynamic.frames[frameIdx.value]
        : currentAction.value?.frames[frameIdx.value]) ?? new Float32Array(0),
);

// 显示帧 = 模型弱区增强矩阵优先（两种模式均可用），否则回退原始帧；
// 离线回放额外扣除该人空载背景后的净压力（背景噪声在热力图上自然归零）
const displayFrame = computed(() => {
  const src =
    inference.enhancedFrame.value ??
    (inference.displayMode.value === 'inference'
      ? inference.deviceFrame.value ?? new Float32Array(0)
      : currentFrame.value);
  if (inference.displayMode.value === 'inference' || !src.length) return src;
  const bg = bgForMetrics.value;
  if (!bg) return src;
  const out = new Float32Array(src.length);
  for (let i = 0; i < src.length; i++) out[i] = Math.max(src[i] - bg[i], 0);
  return out;
});

const metrics = computed(() => {
  if (!currentFrame.value.length) return null;
  const bg = inference.displayMode.value === 'inference' ? null : bgForMetrics.value;
  return computeMetrics(currentFrame.value, bg, 20);
});

// 设计空间内热力图最大高度（1920×1080 常量：内容行 758 - 面板镶边 ~150）
const heatmapMaxHeight = 608;

const framesList = computed<ArrayLike<number>[]>(() => {
  if (inference.displayMode.value === 'inference') {
    const f = inference.deviceFrame.value;
    return f && f.length ? [f] : [];
  }
  return effectiveDynamic.value
    ? (data.value?.dynamic.frames ?? [])
    : (currentAction.value?.frames ?? []);
});
const bgForMetrics = computed<ArrayLike<number> | null>(() =>
  inference.displayMode.value === 'inference'
    ? null
    : effectiveDynamic.value
      ? (data.value?.dynamic.bg ?? null)
      : (person.value?.bg ?? null),
);
const history = computed(() => metricsHistory(framesList.value, bgForMetrics.value, 20));

// 区域：模型分区结果优先（两种模式均接推理）；不可用时回放模式回退记录标注
const regions = computed(() => {
  if (inference.partition.value) {
    return partitionRegionsToBodyRegions(inference.partition.value);
  }
  if (inference.displayMode.value === 'inference') return null;
  return sourceType.value === 'static' && currentAction.value?.region
    ? parseRegion(currentAction.value.region)
    : null;
});
/** 分区掩码覆盖层（模型输出，两种模式可用） */
const partitionMask = computed(() =>
  inference.partition.value ? inference.partition.value.mask : null,
);
/** 区域来源：inference（模型分区）| annotation（记录标注）| null（无区域） */
const regionSource = computed<'inference' | 'annotation' | null>(() => {
  if (!regions.value) return null;
  return inference.partitionAvailable.value ? 'inference' : 'annotation';
});
// 脊柱参考线：记录标注，仅在离线回放模式使用
const spine = computed(() =>
  inference.displayMode.value === 'demo' &&
  sourceType.value === 'static' &&
  currentAction.value?.spine
    ? parseSpine(currentAction.value.spine)
    : null,
);

const showRegions = ref(true);
const showSpine = ref(true);
const showCalf = ref(false);
const showDynLabels = ref(false);
const selectedRegion = ref<number | null>(null);

// 3D 睡姿演示叠加层
const show3D = ref(false);
/** 中下方面板视图：3D 演示持久展示，压力曲线按按钮切换 */
const viewMode = ref<'3d' | 'chart'>('3d');
// 3D 人体姿势：模型推理结果优先（两种模式），否则用记录标签
const sleepPos3d = computed(() => {
  if (inference.prediction.value) {
    const id = inference.prediction.value.label_id;
    if (id >= 0 && id <= 3) return id as 0 | 1 | 2 | 3;
  }
  const p = currentAction.value?.sleepPos;
  return typeof p === 'number' && p >= 0 && p <= 3 ? p : 0;
});

// 气囊模拟源（真实设备就绪后换成实现同一接口的适配器）
const airbagSource = new SimulatedAirbagSource();
const airbagStates = ref<AirbagState[]>(airbagSource.getStates());
airbagSource.subscribe(() => {
  airbagStates.value = airbagSource.getStates();
});

// 布置图传感器叠加层与点击联动（默认关闭，部位区域默认显示）
const showSensors = ref(false);
const selectedSensor = ref<number | null>(null);
const sensorCurve = computed(() => {
  if (selectedSensor.value === null) return [];
  const s = SENSOR_BY_ID[selectedSensor.value];
  if (!s) return [];
  const cell = mmToMatrixCell(s.xMm, s.yMm);
  const idx = cell.row * 24 + cell.col;
  const bg = bgForMetrics.value;
  return framesList.value.map((f) =>
    Math.max((f[idx] ?? 0) - (bg?.[idx] ?? 0), 0),
  );
});
const extraSeries = computed(() => {
  if (selectedSensor.value !== null && sensorCurve.value.length) {
    const s = SENSOR_BY_ID[selectedSensor.value];
    return [
      {
        label: `传感器 ${selectedSensor.value} 净压`,
        color: s ? (s.region === 'green' ? '#3FB950' : s.region === 'yellow' ? '#D29922' : '#F85149') : '#8b8f98',
        values: sensorCurve.value,
      },
    ];
  }
  if (selectedRegion.value !== null && regionCurve.value.length) {
    return [
      {
        label: `${selectedRegionName.value}平均压力`,
        color: selectedRegionColor.value,
        values: regionCurve.value,
      },
    ];
  }
  return [];
});

function onAirbagPreset(name: string) {
  if (name === '腰部支撑增强') {
    showRegions.value = true;
    selectedRegion.value = 2;
  }
}

const regionStats = computed(() => {
  if (!regions.value || !currentFrame.value.length) return [];
  return regionStatsAll(currentFrame.value, bgForMetrics.value, regions.value, 20);
});

const regionCurve = computed(() => {
  if (selectedRegion.value === null || !regions.value) return [];
  const rg = regions.value[selectedRegion.value];
  if (!rg?.valid) return [];
  const bg = bgForMetrics.value;
  return framesList.value.map((f) => regionMetrics(f, bg, rg, 20).meanNet);
});
const selectedRegionName = computed(() => {
  if (selectedRegion.value === null || !regions.value) return '';
  const rg = regions.value[selectedRegion.value];
  return rg?.valid ? rg.name : '';
});
const selectedRegionColor = computed(() => {
  if (selectedRegion.value === null || !regions.value) return '#8b8f98';
  const rg = regions.value[selectedRegion.value];
  return rg?.valid ? (REGION_COLORS[rg.name] ?? '#8b8f98') : '#8b8f98';
});

// 单帧聚合推理（架构：通过 HTTP API 获取算法结果；两种模式均接推理，模型不可用时回退记录数据）
const inference = useFrameInference();
const displayPose = computed(() => {
  if (inference.prediction.value) {
    return inference.prediction.value.label_zh;
  }
  if (inference.displayMode.value === 'inference') {
    return inference.streamIdle.value ? '等待设备输入' : sleepPosName.value;
  }
  return sleepPosName.value;
});
const poseNote = computed(() => {
  if (inference.prediction.value) {
    return `${inference.postureModelAvailable.value ? '模型推理' : '推理'} · POST /api/frame/analyze`;
  }
  if (inference.displayMode.value === 'inference') {
    if (inference.streamIdle.value) return '未检测到设备输入 · 保持静止';
    if (inference.backend.value === 'offline') return '后端离线 · 等待重连';
    return '等待模型推理结果';
  }
  return sourceType.value === 'dynamic'
    ? '翻身过程 · 记录标签（无模型结果时）'
    : currentAction.value?.action === 0
      ? '空载记录 · 判定为离床'
      : '记录标签（无模型结果时）';
});

// rAF 驱动
let rafId = 0;
let lastTs = 0;
function loop(ts: number) {
  if (lastTs > 0) {
    const dt = ts - lastTs;
    controller.value?.tick(dt);
    airbagSource.tick(dt);
  }
  lastTs = ts;
  playing.value = controller.value?.isPlaying ?? false;
  rafId = requestAnimationFrame(loop);
}
onMounted(() => (rafId = requestAnimationFrame(loop)));
onBeforeUnmount(() => cancelAnimationFrame(rafId));

function togglePlay() {
  controller.value?.toggle();
}
function stepPrev() {
  controller.value?.step(-1);
}
function stepNext() {
  controller.value?.step(1);
}
function onSeek(v: number) {
  controller.value?.seek(v);
}
function setSpeed(v: number) {
  speed.value = v;
  if (controller.value) controller.value.speed = v;
}

function selectAction(i: number) {
  actionIdx.value = i;
  rebuildController();
}
function selectPerson(i: number) {
  personIdx.value = i;
  actionIdx.value = 0;
  rebuildController();
}
function selectSource(t: 'static' | 'dynamic') {
  sourceType.value = t;
  rebuildController();
}
function onRegionSelect(i: number) {
  selectedRegion.value = i;
  selectedSensor.value = null;
}
function onSensorSelect(id: number) {
  selectedSensor.value = id;
  selectedRegion.value = null;
}

// URL hash 状态（便于直链演示）
function applyHash() {
  const h = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
  // 模式解析放在最前：随后的 rebuildController/autoplay 基于最终模式执行
  if (h.get('pose') === 'svm') inference.setDisplayMode('inference');
  if (h.get('pose') === 'label') inference.setDisplayMode('demo');
  const dmRaw = h.get('display');
  if (dmRaw === 'inference' || dmRaw === 'demo') {
    inference.setDisplayMode(dmRaw);
  } else if (h.get('type') || h.get('person') || h.get('action') || h.get('calf') || h.get('region')) {
    // 带回放参数的演示直链隐含「离线回放」模式；无参数默认「实时推理」
    inference.setDisplayMode('demo');
  }
  if (h.get('type') === 'dynamic') sourceType.value = 'dynamic';
  const pn = h.get('person');
  if (pn && data.value) {
    const pi = data.value.people.findIndex((p) => p.name === pn);
    if (pi >= 0) personIdx.value = pi;
  }
  const aRaw = h.get('action');
  if (aRaw !== null && person.value) {
    const a = Number(aRaw);
    if (!Number.isNaN(a)) {
      const idx = person.value.actions.findIndex((x) => x.action === a);
      if (idx >= 0) actionIdx.value = idx;
    }
  }
  if (h.get('mode') === 'grid' || h.get('mode') === 'weak') mode.value = h.get('mode') as HeatmapMode;
  if (h.get('scale') === 'auto' || h.get('scale') === 'fixed500')
    scaleMode.value = h.get('scale') as ScaleMode;
  if (h.get('calf') === '1') showCalf.value = true;
  if (h.get('dynlabels') === '1') showDynLabels.value = true;
  const rgRaw = h.get('region');
  if (rgRaw !== null) {
    const rg = Number(rgRaw);
    if (!Number.isNaN(rg) && rg >= 0 && rg <= 5) selectedRegion.value = rg;
  }
  rebuildController();
  const fRaw = h.get('frame');
  if (fRaw !== null) {
    const f = Number(fRaw);
    if (!Number.isNaN(f)) controller.value?.seek(f);
  }
  if (h.get('autoplay') === '1') {
    // 延迟到模式切换 watcher 的 rebuildController 之后，避免播放状态被重置
    window.setTimeout(() => controller.value?.play(), 0);
  }
}

const legendTicks = computed<number[] | null>(() => {
  if (scaleMode.value === 'fixed250') return [0, 50, 100, 150, 200, 250];
  if (scaleMode.value === 'fixed500') return [0, 100, 200, 300, 400, 500];
  return null;
});
const legendCaption = computed(() => {
  const m = metrics.value;
  return m ? `峰值 ${Math.round(m.maxRaw)}` : '峰值 —';
});
const scaleWarning = computed(() =>
  scaleMode.value !== 'auto' &&
  metrics.value &&
  metrics.value.maxRaw > (scaleMode.value === 'fixed250' ? 250 : 500)
    ? '峰值超出量程 · 顶部已截断'
    : null,
);

onMounted(async () => {
  void inference.probe();
  await loadData();
  const hash = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
  const dsFiles = hash.get('dataset');
  if (dsFiles) {
    await loadDatasetStream(dsFiles);
  }
  if (person.value) {
    const i = person.value.actions.findIndex((a) => a.action !== 0);
    if (i >= 0) actionIdx.value = i;
  }
  applyHash();
});

watch(() => frameCount.value, (n) => {
  if (frameIdx.value >= n) frameIdx.value = n - 1;
});
watch([sourceType, actionIdx, personIdx], () => {
  selectedRegion.value = null;
  selectedSensor.value = null;
});
// 模式切换：重建帧源（实时推理 → 动态序列循环自动播放；离线回放 → 所选记录）
watch(
  () => inference.displayMode.value,
  () => {
    selectedRegion.value = null;
    selectedSensor.value = null;
    rebuildController();
  },
);

// 推理触发：帧号 / 数据模式 / 后端状态变化时队列化当前帧（组合式函数内部节流 + latest-wins）
watch(
  [frameIdx, () => inference.displayMode.value, () => inference.backend.value],
  () => inference.queueAnalyze(currentFrame.value),
);
</script>

<template>
  <div class="viewport">
    <div class="stage" :style="{ transform: `scale(${scale})` }">
      <Transition name="page" mode="out-in">
        <div v-if="data" key="app" class="shell">
          <main class="content">
            <aside class="col-left">
              <SidebarControls
                :data-source="dataSource"
                :source-type="sourceType"
                :people="data.people"
                :person-idx="personIdx"
                :person="person"
                :action-idx="actionIdx"
                :show-regions="showRegions"
                :show-spine="showSpine"
                :show-calf="showCalf"
                :show-dyn-labels="showDynLabels"
                :display-mode="inference.displayMode.value"
                :backend-online="inference.backend.value === 'online'"
                :backend-state="inference.backend.value"
                :model-available="inference.postureModelAvailable.value"
                :partition-model-available="inference.partitionModelAvailable.value"
                :contract-mismatch="inference.contractMismatch.value"
                :simulated="dataSource === 'simulated'"
                :stream-idle="inference.streamIdle.value"
                :device-source="inference.deviceSource.value"
                @update:data-source="selectDataSource"
                @update:source-type="selectSource"
                @update:person-idx="selectPerson"
                @update:action-idx="selectAction"
                @update:show-regions="showRegions = $event"
                @update:show-spine="showSpine = $event"
                @update:show-calf="showCalf = $event"
                @update:show-dyn-labels="showDynLabels = $event"
                @update:display-mode="inference.setDisplayMode($event)"
                @open-3d="show3D = true"
              />
            </aside>

            <section class="col-center">
              <HeatmapPanel
                :frame="displayFrame"
                :mode="mode"
                :scale="scaleMode"
                :max-height="heatmapMaxHeight"
                :regions="regions"
                :spine="spine"
                :show-regions="showRegions"
                :show-spine="showSpine"
                :show-calf="showCalf"
                :selected-region="selectedRegion"
                :partition-mask="partitionMask"
                :region-source="regionSource"
                :source-label="sourceLabel"
                :frame-idx="frameIdx"
                :frame-count="frameCount"
                :playing="playing"
                :speed="speed"
                :legend-ticks="legendTicks"
                :legend-caption="legendCaption"
                :scale-warning="scaleWarning"
                :show-sensors="showSensors"
                :airbag-states="airbagStates"
                :selected-sensor="selectedSensor"
                @update:mode="mode = $event"
                @update:scale="scaleMode = $event"
                @update:show-sensors="showSensors = $event"
                @region-hover="hoverRegion = $event"
                @region-select="onRegionSelect"
                @sensor-select="onSensorSelect"
                @toggle-play="togglePlay"
                @step-prev="stepPrev"
                @step-next="stepNext"
                @seek="onSeek"
                @speed="setSpeed"
              />
              <PanelCard
                class="chart-panel"
                flush
                :title="viewMode === '3d' ? '三维睡姿演示' : '压力趋势'"
                :subtitle="viewMode === '3d' ? '人体模型 · 床垫热力图 · 气囊布置（实时联动）' : '净压力 · 扣除空载基线'"
                :icon="viewMode === '3d' ? 'cube' : 'activity'"
              >
                <div class="chart-inner">
                  <div class="view-switch" role="group" aria-label="视图切换">
                    <button
                      type="button"
                      class="vs-btn"
                      :class="{ on: viewMode === '3d' }"
                      :aria-pressed="viewMode === '3d'"
                      title="持久展示 3D 睡姿视图"
                      @click="viewMode = '3d'"
                    >
                      <Icon name="cube" :size="12" />
                      3D 视图
                    </button>
                    <button
                      type="button"
                      class="vs-btn"
                      :class="{ on: viewMode === 'chart' }"
                      :aria-pressed="viewMode === 'chart'"
                      title="压力趋势折线图"
                      @click="viewMode = 'chart'"
                    >
                      <Icon name="activity" :size="12" />
                      压力曲线
                    </button>
                  </div>
                  <Bed3DInline
                    v-if="viewMode === '3d'"
                    :frame="displayFrame"
                    :sleep-pos="sleepPos3d"
                    :airbag-states="airbagStates"
                    @fullscreen="show3D = true"
                  />
                  <template v-else>
                    <PoseTimeline
                      v-if="sourceType === 'dynamic' && showDynLabels && data"
                      :labels="data.dynamic.labels"
                      :frame-idx="frameIdx"
                      @seek="(i) => controller?.seek(i)"
                    />
                    <MetricsChart
                      :history="history"
                      :frame-idx="frameIdx"
                      :extra-series="extraSeries"
                    />
                  </template>
                </div>
              </PanelCard>
            </section>

            <aside class="col-right">
              <InsightPanel
                :pose="displayPose"
                :duration-frames="poseDurationFrames"
                :pose-note="poseNote"
                :playing="playing"
                :pose-source="inference.prediction.value ? 'inference' : 'label'"
                :confidence="inference.prediction.value?.confidence ?? null"
                :predicting="inference.analyzing.value"
                :metrics="metrics"
                :history="history"
              />
            </aside>
          </main>

          <section class="bottom">
            <AirbagPanel :source="airbagSource" @preset="onAirbagPreset" />
            <PanelCard class="ranking-panel" flush title="部位受力" subtitle="按平均净压排序" icon="bar-chart">
              <div class="ranking-inner">
                <RegionRanking
                  :stats="regionStats"
                  :selected="selectedRegion"
                  :hovered="hoverRegion"
                  @select="selectedRegion = $event"
                />
              </div>
            </PanelCard>
          </section>
        </div>

        <div v-else key="loading" class="shell loading" role="status" aria-label="正在加载数据">
          <svg class="loading-mark" viewBox="0 0 44 44" fill="none" aria-hidden="true">
            <defs>
              <linearGradient id="sm-loading" x1="4" y1="3" x2="40" y2="41" gradientUnits="userSpaceOnUse">
                <stop stop-color="var(--brand-from)" />
                <stop offset="1" stop-color="var(--brand-to)" />
              </linearGradient>
            </defs>
            <rect width="44" height="44" rx="12" fill="url(#sm-loading)" />
            <path
              d="M12 21.5c1.6-2.2 3-2.2 4.6 0s3 2.2 4.6 0 3-2.2 4.6 0 3 2.2 4.6 0"
              stroke="#fff"
              stroke-width="2.2"
              stroke-linecap="round"
            />
          </svg>
          <p class="loading-text">正在加载监测数据…</p>
        </div>
      </Transition>

      <Bed3DView
        v-if="show3D"
        :frame="displayFrame"
        :sleep-pos="sleepPos3d"
        :source-label="sourceLabel"
        :airbag-states="airbagStates"
        @close="show3D = false"
      />
    </div>
  </div>
</template>

<style scoped>
/* 视口：整屏画布；stage 为固定 1920×1080 设计空间，等比缩放居中 */
.viewport {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.stage {
  width: 1920px;
  height: 1080px;
  flex: none;
  transform-origin: center center;
  will-change: transform;
}

.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 16px 20px 0;
  background:
    radial-gradient(1200px 500px at 50% -180px, var(--accent-soft) 0%, transparent 60%),
    var(--bg);
}

/* ---------- 主体三栏 ---------- */
.content {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr) 300px;
  gap: 16px;
}
.col-left {
  min-height: 0;
  animation: enter-y 420ms var(--ease-out) 40ms both;
}
/* 中部双面板：热力图 + 压力趋势 */
.col-center {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(380px, 0.9fr) minmax(320px, 1.1fr);
  gap: 16px;
  animation: enter-y 420ms var(--ease-out) 80ms both;
}
.col-right {
  min-height: 0;
  animation: enter-y 420ms var(--ease-out) 120ms both;
}

@keyframes enter-y {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ---------- 底部：气囊 + 部位排行 ---------- */
.bottom {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  padding: 12px 0 14px;
  height: 280px;
  min-height: 0;
  flex: none;
  animation: enter-y 420ms var(--ease-out) 160ms both;
}
.chart-panel {
  min-width: 0;
  height: 100%;
}
.chart-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 12px 16px 14px;
}
.chart-inner :deep(.chart-root) {
  flex: 1;
  min-height: 0;
}
.chart-inner :deep(.bed3d-inline) {
  flex: 1;
  min-height: 0;
}

/* 视图切换（3D 持久 / 压力曲线） */
.view-switch {
  display: flex;
  gap: 5px;
  flex: none;
  padding-bottom: 8px;
}
.vs-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 24px;
  padding: 2px 10px;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: var(--fs-2xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out);
}
.vs-btn:hover {
  border-color: var(--border-strong);
  color: var(--text-1);
}
.vs-btn.on {
  color: var(--accent);
  border-color: var(--accent-soft-strong);
  background: var(--accent-soft);
}
.ranking-panel {
  min-width: 0;
  height: 100%;
}
.ranking-inner {
  height: 100%;
  min-height: 0;
  padding: 10px 14px 14px;
}

/* ---------- 加载态 ---------- */
.loading {
  align-items: center;
  justify-content: center;
  gap: 18px;
}
.loading-mark {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  box-shadow: var(--shadow-float);
  animation: breathe 2.2s var(--ease-in-out) infinite;
}
@keyframes breathe {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(0.94);
    opacity: 0.82;
  }
}
.loading-text {
  font-size: var(--fs-sm);
  color: var(--text-3);
  letter-spacing: 0.03em;
}

/* ---------- 页面过渡 ---------- */
.page-enter-active,
.page-leave-active {
  transition:
    opacity var(--dur-page) var(--ease-out),
    transform var(--dur-page) var(--ease-out);
}
.page-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.998);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.998);
}

@media (prefers-reduced-motion: reduce) {
  .col-left,
  .col-center,
  .col-right,
  .bottom,
  .loading-mark {
    animation: none;
  }
}
</style>
