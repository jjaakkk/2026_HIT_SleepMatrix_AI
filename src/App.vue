<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import TopBar from './components/TopBar.vue';
import SidebarControls from './components/SidebarControls.vue';
import HeatmapPanel from './components/HeatmapPanel.vue';
import InsightPanel from './components/InsightPanel.vue';
import MetricsChart from './components/MetricsChart.vue';
import AirbagPanel from './components/AirbagPanel.vue';
import PoseTimeline from './components/PoseTimeline.vue';
import PanelCard from './components/ui/PanelCard.vue';
import type { DemoData } from './core/demo';
import type { HeatmapMode, ScaleMode } from './render/heatmap.ts';
import { SLEEP_POS_NAMES } from './core/types.ts';
import { computeMetrics, metricsHistory, isBedOccupied, poseDuration } from './core/metrics.ts';
import { parseRegion, parseSpine } from './core/parsers/annotations.ts';
import { regionStatsAll, regionMetrics, REGION_COLORS } from './core/region-stats.ts';
import { PlaybackController } from './core/playback.ts';
import { SimulatedAirbagSource } from './core/airbag.ts';
import { generateSimulatedDataset } from './core/simulate.ts';

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
const scale = ref<ScaleMode>('auto');
const hoverRegion = ref<number | null>(null);

const currentAction = computed(() => person.value?.actions[actionIdx.value] ?? null);
const frameCount = computed(() =>
  sourceType.value === 'dynamic'
    ? data.value?.dynamic.frames.length ?? 0
    : currentAction.value?.frames.length ?? 0,
);
const sleepPosName = computed(() =>
  sourceType.value === 'dynamic'
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
    if (sourceType.value === 'dynamic') return '动态过程';
    if (currentAction.value?.action === 0) return isBedOccupied(m) ? '在床' : '离床 · 无人';
    return SLEEP_POS_NAMES[currentAction.value?.sleepPos ?? -1] ?? '未知';
  }),
);
const poseDurationFrames = computed(() => poseDuration(poseKeys.value, frameIdx.value));

const sourceLabel = computed(() =>
  sourceType.value === 'dynamic'
    ? `${data.value?.dynamic.person ?? ''} · 翻身过程`
    : `${person.value?.name ?? ''} · ${sleepPosName.value}`,
);

// 回放引擎
const controller = ref<PlaybackController | null>(null);
const frameIdx = ref(0);
const speed = ref(1);
const playing = ref(false);

function rebuildController() {
  const frames =
    sourceType.value === 'dynamic'
      ? (data.value?.dynamic.frames ?? [])
      : (currentAction.value?.frames ?? []);
  controller.value = new PlaybackController(frames as ArrayLike<number>[], { fps: 10 });
  controller.value.onFrame = (i) => (frameIdx.value = i);
  controller.value.speed = speed.value;
  playing.value = false;
  frameIdx.value = 0;
}

const currentFrame = computed(
  () =>
    (sourceType.value === 'dynamic'
      ? data.value?.dynamic.frames[frameIdx.value]
      : currentAction.value?.frames[frameIdx.value]) ?? new Float32Array(0),
);

// 显示帧 = 扣除该人空载背景后的净压力（背景噪声在热力图上自然归零，"离床"画面即全黑）
const displayFrame = computed(() => {
  const raw = currentFrame.value;
  const bg = bgForMetrics.value;
  if (!bg) return raw;
  const out = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = Math.max(raw[i] - bg[i], 0);
  return out;
});

const metrics = computed(() => {
  if (!currentFrame.value.length || !person.value) return null;
  return computeMetrics(currentFrame.value, bgForMetrics.value, 20);
});

// 视口高度 → 热力图最大高度（保证底部曲线图可见）
const viewportH = ref(window.innerHeight);
const heatmapMaxHeight = computed(() => Math.max(240, viewportH.value - 480));

const framesList = computed<ArrayLike<number>[]>(() =>
  sourceType.value === 'dynamic'
    ? (data.value?.dynamic.frames ?? [])
    : (currentAction.value?.frames ?? []),
);
const bgForMetrics = computed<ArrayLike<number> | null>(() =>
  sourceType.value === 'dynamic' ? (data.value?.dynamic.bg ?? null) : (person.value?.bg ?? null),
);
const history = computed(() => metricsHistory(framesList.value, bgForMetrics.value, 20));

// 区域与脊柱标注
const regions = computed(() =>
  sourceType.value === 'static' && currentAction.value?.region
    ? parseRegion(currentAction.value.region)
    : null,
);
const spine = computed(() =>
  sourceType.value === 'static' && currentAction.value?.spine
    ? parseSpine(currentAction.value.spine)
    : null,
);

const showRegions = ref(true);
const showSpine = ref(true);
const showCalf = ref(false);
const showDynLabels = ref(false);
const selectedRegion = ref<number | null>(null);

// 气囊模拟源（真实设备就绪后换成实现同一接口的适配器）
const airbagSource = new SimulatedAirbagSource();

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

// URL hash 状态（便于直链演示）
function applyHash() {
  const h = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
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
  if (h.get('scale') === 'auto' || h.get('scale') === 'fixed500') scale.value = h.get('scale') as ScaleMode;
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
  if (h.get('autoplay') === '1') controller.value?.play();
}

const legendTicks = computed<number[] | null>(() => {
  if (scale.value === 'fixed250') return [0, 50, 100, 150, 200, 250];
  if (scale.value === 'fixed500') return [0, 100, 200, 300, 400, 500];
  return null;
});
const legendCaption = computed(() => {
  const m = metrics.value;
  return m ? `峰值 ${Math.round(m.maxRaw)}` : '峰值 —';
});
const scaleWarning = computed(() =>
  scale.value !== 'auto' && metrics.value && metrics.value.maxRaw > (scale.value === 'fixed250' ? 250 : 500)
    ? '峰值超出量程 · 顶部已截断'
    : null,
);

onMounted(async () => {
  window.addEventListener('resize', () => (viewportH.value = window.innerHeight));
  await loadData();
  if (person.value) {
    const i = person.value.actions.findIndex((a) => a.action !== 0);
    if (i >= 0) actionIdx.value = i;
  }
  applyHash();
});

watch(() => frameCount.value, (n) => {
  if (frameIdx.value >= n) frameIdx.value = n - 1;
});
watch([sourceType, actionIdx, personIdx], () => (selectedRegion.value = null));
</script>

<template>
  <div class="shell">
    <TopBar :playing="playing" :simulated="dataSource === 'simulated'" />

    <Transition name="page" mode="out-in">
      <div v-if="data" key="app" class="stage">
        <main class="content">
          <aside class="col-left">
            <SidebarControls
              :data-source="dataSource"
              :source-type="sourceType"
              :people="data.people"
              :person-idx="personIdx"
              :person="person"
              :action-idx="actionIdx"
              :mode="mode"
              :scale="scale"
              :show-regions="showRegions"
              :show-spine="showSpine"
              :show-calf="showCalf"
              :show-dyn-labels="showDynLabels"
              @update:data-source="selectDataSource"
              @update:source-type="selectSource"
              @update:person-idx="selectPerson"
              @update:action-idx="selectAction"
              @update:mode="mode = $event"
              @update:scale="scale = $event"
              @update:show-regions="showRegions = $event"
              @update:show-spine="showSpine = $event"
              @update:show-calf="showCalf = $event"
              @update:show-dyn-labels="showDynLabels = $event"
            />
          </aside>

          <section class="col-center">
            <HeatmapPanel
              :frame="displayFrame"
              :mode="mode"
              :scale="scale"
              :max-height="heatmapMaxHeight"
              :regions="regions"
              :spine="spine"
              :show-regions="showRegions"
              :show-spine="showSpine"
              :show-calf="showCalf"
              :selected-region="selectedRegion"
              :source-label="sourceLabel"
              :frame-idx="frameIdx"
              :frame-count="frameCount"
              :playing="playing"
              :speed="speed"
              :legend-ticks="legendTicks"
              :legend-caption="legendCaption"
              :scale-warning="scaleWarning"
              @region-hover="hoverRegion = $event"
              @region-select="selectedRegion = $event"
              @toggle-play="togglePlay"
              @step-prev="stepPrev"
              @step-next="stepNext"
              @seek="onSeek"
              @speed="setSpeed"
            />
          </section>

          <aside class="col-right">
            <InsightPanel
              :pose="sleepPosName"
              :duration-frames="poseDurationFrames"
              :pose-note="
                sourceType === 'dynamic'
                  ? '翻身过程 · 未使用文件内标签'
                  : currentAction?.action === 0
                    ? '空载记录 · 判定为离床'
                    : undefined
              "
              :playing="playing"
              :metrics="metrics"
              :history="history"
              :region-stats="regionStats"
              :selected-region="selectedRegion"
              :hover-region="hoverRegion"
              @select-region="selectedRegion = $event"
            />
          </aside>
        </main>

        <section class="bottom">
          <PanelCard class="chart-panel" flush title="压力趋势" icon="activity">
            <div class="chart-inner">
              <PoseTimeline
                v-if="sourceType === 'dynamic' && showDynLabels && data"
                :labels="data.dynamic.labels"
                :frame-idx="frameIdx"
                @seek="(i) => controller?.seek(i)"
              />
              <MetricsChart
                :history="history"
                :frame-idx="frameIdx"
                :extra-series="
                  selectedRegion !== null && regionCurve.length
                    ? [{ label: `${selectedRegionName}平均压力`, color: selectedRegionColor, values: regionCurve }]
                    : []
                "
              />
            </div>
          </PanelCard>
          <AirbagPanel :source="airbagSource" @preset="onAirbagPreset" />
        </section>
      </div>

      <div v-else key="loading" class="loading" role="status" aria-label="正在加载数据">
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
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(1200px 500px at 50% -180px, var(--accent-soft) 0%, transparent 60%),
    var(--bg);
}

.stage {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* ---------- 主体三栏 ---------- */
.content {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 246px minmax(0, 1fr) 302px;
  gap: 16px;
  padding: 16px 20px 0;
}
.col-left {
  min-height: 0;
  overflow-y: auto;
  animation: enter-y 520ms var(--ease-out) 60ms both;
}
.col-center {
  min-height: 0;
  display: flex;
  justify-content: center;
  animation: enter-y 560ms var(--ease-out) 120ms both;
}
.col-center :deep(.heatmap-panel) {
  width: min(100%, 520px);
}
.col-right {
  min-height: 0;
  animation: enter-y 520ms var(--ease-out) 180ms both;
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

/* ---------- 底部：趋势 + 气囊 ---------- */
.bottom {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 430px;
  gap: 16px;
  padding: 14px 20px 20px;
  height: 244px;
  min-height: 0;
  flex: none;
  animation: enter-y 520ms var(--ease-out) 240ms both;
}
.chart-panel {
  min-width: 0;
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

/* ---------- 加载态 ---------- */
.loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
}
.loading-mark {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  box-shadow: var(--shadow-md);
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

/* ---------- 响应式 ---------- */
@media (max-width: 1440px) {
  .content {
    grid-template-columns: 224px minmax(0, 1fr) 278px;
  }
  .bottom {
    grid-template-columns: minmax(0, 1fr) 396px;
  }
}
@media (max-width: 1220px) {
  .shell {
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }
  .stage {
    min-height: 0;
  }
  .content {
    grid-template-columns: 1fr;
    grid-auto-rows: auto;
    padding: 16px 16px 0;
  }
  .col-left {
    overflow: visible;
    animation-delay: 60ms;
  }
  .col-left :deep(.rail) {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 14px 20px;
  }
  .col-left :deep(.rail .group) {
    flex: 1 1 220px;
    min-width: 200px;
  }
  .col-center {
    animation-delay: 120ms;
    min-height: 420px;
  }
  .col-center :deep(.heatmap-panel) {
    width: 100%;
    max-width: 560px;
  }
  .col-right {
    animation-delay: 180ms;
    min-height: 420px;
  }
  .bottom {
    grid-template-columns: 1fr;
    height: auto;
    grid-auto-rows: 232px auto;
    padding: 14px 16px 20px;
    animation-delay: 240ms;
  }
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
