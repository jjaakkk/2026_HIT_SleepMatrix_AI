<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import HeatmapCanvas from './components/HeatmapCanvas.vue';
import MetricCards from './components/MetricCards.vue';
import MetricsChart from './components/MetricsChart.vue';
import RegionRanking from './components/RegionRanking.vue';
import SleepPoseCard from './components/SleepPoseCard.vue';
import AirbagPanel from './components/AirbagPanel.vue';
import PoseTimeline from './components/PoseTimeline.vue';
import { turboColor } from './render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from './render/heatmap.ts';
import { SLEEP_POS_NAMES } from './core/types.ts';
import { computeMetrics, metricsHistory, isBedOccupied, poseDuration } from './core/metrics.ts';
import { parseRegion, parseSpine } from './core/parsers/annotations.ts';
import { regionStatsAll, regionMetrics, REGION_COLORS } from './core/region-stats.ts';
import { PlaybackController } from './core/playback.ts';
import { SimulatedAirbagSource } from './core/airbag.ts';
import { generateSimulatedDataset } from './core/simulate.ts';

interface DemoAction {
  action: number;
  sleepPos: number;
  region: string;
  spine: string;
  frames: number[][];
}
interface DemoPerson {
  name: string;
  height: number | null;
  weight: number | null;
  bg: number[];
  actions: DemoAction[];
}
interface DemoData {
  people: DemoPerson[];
  dynamic: { person: string; bg: number[]; frames: number[][]; labels: number[] };
}

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
const hoverCell = ref<{ row: number; col: number; value: number } | null>(null);

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

function actionLabel(a: DemoAction): string {
  if (a.action === 0) return '空载记录 · 无人';
  return `${SLEEP_POS_NAMES[a.sleepPos] ?? ''} · 记录 ${a.action}`;
}
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
const heatmapMaxHeight = computed(() => Math.max(260, viewportH.value - 450));

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
const hoverRegion = ref<number | null>(null);

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
  if (selectedRegion.value === null || !regions.value) return '#7a8794';
  const rg = regions.value[selectedRegion.value];
  return rg?.valid ? (REGION_COLORS[rg.name] ?? '#7a8794') : '#7a8794';
});

// 时钟（仪器面板元素）
const now = ref(new Date());
const clockText = computed(() => {
  const d = now.value;
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
});

// rAF 驱动
let rafId = 0;
let lastTs = 0;
let lastSec = 0;
function loop(ts: number) {
  if (lastTs > 0) {
    const dt = ts - lastTs;
    controller.value?.tick(dt);
    airbagSource.tick(dt);
  }
  lastTs = ts;
  if (ts - lastSec >= 1000) {
    lastSec = ts;
    now.value = new Date();
  }
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
function onSeek(e: Event) {
  const v = Number((e.target as HTMLInputElement).value);
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

const modeOptions: { value: HeatmapMode; label: string }[] = [
  { value: 'smooth', label: '标准' },
  { value: 'weak', label: '弱力增强' },
  { value: 'grid', label: '原始网格' },
];
const scaleOptions: { value: ScaleMode; label: string }[] = [
  { value: 'fixed250', label: '0–250' },
  { value: 'auto', label: '自动' },
  { value: 'fixed500', label: '0–500' },
];
const speedOptions = [0.5, 1, 2, 4];

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
  if (scale.value === 'auto') return `自动量程 · 峰值 ${metrics.value?.maxRaw ?? '-'}`;
  return '固定量程';
});
const legendCanvas = ref<HTMLCanvasElement | null>(null);

onMounted(async () => {
  window.addEventListener('resize', () => (viewportH.value = window.innerHeight));
  await loadData();
  if (person.value) {
    const i = person.value.actions.findIndex((a) => a.action !== 0);
    if (i >= 0) actionIdx.value = i;
  }
  applyHash();
  const c = legendCanvas.value;
  if (c) {
    c.width = 256;
    c.height = 14;
    const ctx = c.getContext('2d')!;
    for (let x = 0; x < 256; x++) {
      const [r, g, b] = turboColor(x / 255);
      ctx.fillStyle = `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
      ctx.fillRect(x, 0, 1, 14);
    }
  }
});

watch(() => frameCount.value, (n) => {
  if (frameIdx.value >= n) frameIdx.value = n - 1;
});
watch([sourceType, actionIdx, personIdx], () => (selectedRegion.value = null));
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <svg class="logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="3" width="20" height="18" rx="3" />
          <path d="M4 12h3l1.5-4 3 8 3-6 1.5 2H20" />
        </svg>
        <div class="brand-text">
          <span class="brand-name">SleepMatrix</span>
          <span class="brand-sub">睡眠压力监测台</span>
        </div>
      </div>
      <div class="topbar-right">
        <span class="pill live"><i class="dot" :class="{ pulse: playing }"></i>数据回放 · 历史记录</span>
        <span v-if="dataSource === 'simulated'" class="pill warn"><i class="dot"></i>演示模式 · 内置数据</span>
        <span class="pill warn"><i class="dot"></i>气囊 · 模拟信号</span>
        <span class="clock num">{{ clockText }}</span>
      </div>
    </header>

    <main class="content">
      <aside class="panel left">
        <h2>数据</h2>
        <div class="field">
          <span class="label">模式</span>
          <div class="seg">
            <button :class="{ active: dataSource === 'demo' }" @click="selectDataSource('demo')">真实记录</button>
            <button :class="{ active: dataSource === 'simulated' }" @click="selectDataSource('simulated')">内置演示</button>
          </div>
        </div>
        <div class="field">
          <span class="label">回放</span>
          <div class="seg">
            <button :class="{ active: sourceType === 'static' }" @click="selectSource('static')">姿态动作</button>
            <button :class="{ active: sourceType === 'dynamic' }" @click="selectSource('dynamic')">翻身过程</button>
          </div>
        </div>
        <template v-if="sourceType === 'static'">
          <label class="field">
            <span class="label">受测者</span>
            <select :value="personIdx" @change="selectPerson(Number(($event.target as HTMLSelectElement).value))">
              <option v-for="(p, i) in data?.people" :key="p.name" :value="i">
                {{ p.name }} · {{ p.height ?? '?' }} cm / {{ p.weight ?? '?' }} kg
              </option>
            </select>
          </label>
          <label class="field">
            <span class="label">姿态</span>
            <select :value="actionIdx" @change="selectAction(Number(($event.target as HTMLSelectElement).value))">
              <option v-for="(a, i) in person?.actions" :key="a.action" :value="i">
                {{ actionLabel(a) }}
              </option>
            </select>
          </label>
        </template>
        <div class="field">
          <span class="label">渲染</span>
          <div class="seg">
            <button v-for="m in modeOptions" :key="m.value" :class="{ active: mode === m.value }" @click="mode = m.value">
              {{ m.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <span class="label">量程</span>
          <div class="seg">
            <button v-for="s in scaleOptions" :key="s.value" :class="{ active: scale === s.value }" @click="scale = s.value">
              {{ s.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <span class="label">图层</span>
          <div class="checks">
            <label><input type="checkbox" v-model="showRegions" /> 部位区域</label>
            <label><input type="checkbox" v-model="showSpine" /> 脊柱参考线</label>
            <label><input type="checkbox" v-model="showCalf" /> 小腿区域<span class="tiny">3 人已标注</span></label>
            <label v-if="sourceType === 'dynamic'">
              <input type="checkbox" v-model="showDynLabels" /> 原始参考标签<span class="tiny">文件自带</span>
            </label>
          </div>
        </div>
        <div class="legend">
          <canvas ref="legendCanvas" class="legend-canvas"></canvas>
          <div v-if="legendTicks" class="legend-ticks num">
            <span v-for="t in legendTicks" :key="t">{{ t }}</span>
          </div>
          <div v-else class="legend-caption">
            <span>自动量程 · 峰值</span>
            <span class="num">{{ metrics ? Math.round(metrics.maxRaw) : '-' }}</span>
          </div>
        </div>
      </aside>

      <section class="center">
        <div class="heatmap-panel">
          <div class="heatmap-title">
            <span class="src">{{ sourceLabel }}</span>
            <span class="title-right">
              <span v-if="hoverCell" class="hover-tag num">
                {{ hoverCell.row }},{{ hoverCell.col }} · 净压 {{ hoverCell.value }}
              </span>
              <span class="frame-tag num">{{ String(frameIdx).padStart(2, '0') }} / {{ frameCount - 1 }}</span>
            </span>
          </div>
          <HeatmapCanvas
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
            @hover="hoverCell = $event"
            @region-hover="hoverRegion = $event"
            @region-select="selectedRegion = $event"
          />
          <div class="controls">
            <button class="ctl" title="上一帧" aria-label="上一帧" @click="stepPrev">
              <svg viewBox="0 0 16 16" fill="currentColor"><path d="M10.5 3.5 6 8l4.5 4.5" /></svg>
            </button>
            <button class="ctl play" :title="playing ? '暂停' : '播放'" :aria-label="playing ? '暂停' : '播放'" @click="togglePlay">
              <svg v-if="playing" viewBox="0 0 16 16" fill="currentColor"><rect x="4" y="3" width="2.6" height="10" rx="1" /><rect x="9.4" y="3" width="2.6" height="10" rx="1" /></svg>
              <svg v-else viewBox="0 0 16 16" fill="currentColor"><path d="M5 3.8v8.4a.5.5 0 0 0 .76.43l6.9-4.2a.5.5 0 0 0 0-.86L5.76 3.37A.5.5 0 0 0 5 3.8Z" /></svg>
            </button>
            <button class="ctl" title="下一帧" aria-label="下一帧" @click="stepNext">
              <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 3.5 10 8l-4.5 4.5" /></svg>
            </button>
            <input
              class="progress"
              type="range"
              :min="0"
              :max="frameCount - 1"
              :value="frameIdx"
              aria-label="回放进度"
              @input="onSeek"
            />
            <div class="speed-seg">
              <button
                v-for="s in speedOptions"
                :key="s"
                :class="{ active: speed === s }"
                @click="setSpeed(s)"
              >
                {{ s }}×
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside class="panel right">
        <h2>睡姿</h2>
        <SleepPoseCard
          :pose="sleepPosName"
          :duration-frames="poseDurationFrames"
          :fps="10"
          :note="sourceType === 'dynamic' ? '翻身过程 · 未使用文件内标签' : currentAction?.action === 0 ? '空载记录 · 判定为离床' : undefined"
        />
        <h2>压力指标</h2>
        <MetricCards :metrics="metrics" :history="history" />
        <h2 class="mt">部位受力<span class="sub">按平均净压排序</span></h2>
        <RegionRanking :stats="regionStats" :selected="selectedRegion" :hovered="hoverRegion" @select="selectedRegion = $event" />
        <p class="hint">读数与热力图均为扣除空载后的净压力</p>
        <p
          v-if="scale !== 'auto' && metrics && metrics.maxRaw > (scale === 'fixed250' ? 250 : 500)"
          class="warn"
        >
          峰值超出量程 · 顶部已截断
        </p>
      </aside>
    </main>

    <section class="bottom">
      <div class="chart-panel">
        <h2>压力趋势</h2>
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
      <div class="airbag-panel panel">
        <AirbagPanel :source="airbagSource" @preset="onAirbagPreset" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* ---------- 顶栏 ---------- */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, var(--bg-elev), var(--panel));
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo {
  width: 30px;
  height: 30px;
  color: var(--accent);
}
.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}
.brand-name {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.brand-sub {
  font-size: 11px;
  color: var(--text-2);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  padding: 3px 10px;
}
.pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex: none;
}
.pill .dot.pulse {
  animation: pulse 1.6s ease-in-out infinite;
}
.pill.warn .dot {
  background: var(--c-amber);
}
.clock {
  font-size: 14px;
  color: var(--text);
  letter-spacing: 0.04em;
  margin-left: 4px;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
@media (prefers-reduced-motion: reduce) {
  .pill .dot.pulse { animation: none; }
}

/* ---------- 三栏主体 ---------- */
.content {
  flex: 1;
  display: grid;
  grid-template-columns: 236px 1fr 264px;
  grid-template-rows: minmax(0, 1fr);
  gap: 14px;
  padding: 14px 20px;
  min-height: 0;
  overflow: hidden;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-panel);
  padding: 14px 16px 22px;
  overflow: auto;
  min-height: 0;
}
.panel h2 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}
.panel h2.mt {
  margin-top: 16px;
}
.field {
  display: block;
  margin-bottom: 12px;
}
.field .label {
  display: block;
  font-size: 11.5px;
  color: var(--text-3);
  margin-bottom: 6px;
}
select {
  width: 100%;
  appearance: none;
  background: var(--panel-inset);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  padding: 7px 26px 7px 10px;
  font-size: 12.5px;
  font-family: var(--font-ui);
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' fill='none' stroke='%239fb0bc' stroke-width='1.4' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}
select:hover {
  border-color: var(--border-strong);
}
.seg {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
.seg button {
  flex: 1;
  min-width: 52px;
  background: var(--panel-inset);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  padding: 5px 6px;
  font-size: 12px;
  font-family: var(--font-ui);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.seg button:hover {
  color: var(--text);
  border-color: var(--border-strong);
}
.seg button.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.checks {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12.5px;
  color: var(--text);
}
.checks label {
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
}
.checks input {
  accent-color: var(--accent);
  width: 14px;
  height: 14px;
}
.tiny {
  font-size: 10.5px;
  color: var(--text-3);
}
.sub {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-3);
  margin-left: 6px;
  letter-spacing: 0;
}
.legend-canvas {
  width: 100%;
  height: 12px;
  border-radius: 3px;
  image-rendering: pixelated;
  border: 1px solid var(--border);
}
.legend-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 10.5px;
  color: var(--text-3);
  margin-top: 4px;
}
.legend-caption {
  font-size: 11px;
  color: var(--text-3);
  margin-top: 4px;
  text-align: center;
}

/* ---------- 中央热力图（仪器面板） ---------- */
.center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  overflow: auto;
}
.heatmap-panel {
  width: 100%;
  max-width: 640px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-panel);
  padding: 12px 14px 14px;
}
.heatmap-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 10px;
}
.src {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.title-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hover-tag {
  font-size: 11.5px;
  color: var(--accent);
}
.frame-tag {
  font-size: 11.5px;
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 8px;
}
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.ctl {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--panel-inset);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  width: 32px;
  height: 30px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.ctl svg {
  width: 15px;
  height: 15px;
}
.ctl:hover {
  border-color: var(--border-strong);
  background: var(--bg-elev);
}
.ctl.play {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.progress {
  flex: 1;
  accent-color: var(--accent);
}
.speed-seg {
  display: flex;
  gap: 4px;
}
.speed-seg button {
  background: var(--panel-inset);
  color: var(--text-3);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  padding: 3px 8px;
  font-size: 11.5px;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.speed-seg button:hover {
  color: var(--text-2);
  border-color: var(--border-strong);
}
.speed-seg button.active {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}

/* ---------- 右栏 ---------- */
.hint {
  margin-top: 12px;
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.5;
}
.warn {
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--c-amber);
  line-height: 1.5;
}

/* ---------- 底部：趋势 + 气囊 ---------- */
.bottom {
  display: flex;
  gap: 14px;
  margin: 0 20px 14px;
  min-height: 0;
}
.chart-panel {
  flex: 1;
  min-width: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-panel);
  padding: 10px 16px 12px;
  height: 218px;
  display: flex;
  flex-direction: column;
}
.chart-panel h2 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.chart-panel :deep(.chart-wrap) {
  flex: 1;
}
.airbag-panel {
  width: 396px;
  flex: none;
  height: 218px;
}
</style>
