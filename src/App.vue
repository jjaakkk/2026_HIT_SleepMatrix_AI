<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import HeatmapCanvas from './components/HeatmapCanvas.vue';
import MetricCards from './components/MetricCards.vue';
import MetricsChart from './components/MetricsChart.vue';
import RegionRanking from './components/RegionRanking.vue';
import SleepPoseCard from './components/SleepPoseCard.vue';
import { turboColor } from './render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from './render/heatmap.ts';
import { SLEEP_POS_NAMES } from './core/types.ts';
import { computeMetrics, metricsHistory, isBedOccupied, poseDuration } from './core/metrics.ts';
import { parseRegion, parseSpine } from './core/parsers/annotations.ts';
import { regionStatsAll, regionMetrics, REGION_COLORS } from './core/region-stats.ts';
import { PlaybackController } from './core/playback.ts';

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
  if (a.action === 0) return '空载（无人）';
  return `Action ${a.action} · ${SLEEP_POS_NAMES[a.sleepPos] ?? ''}`;
}
const sourceLabel = computed(() =>
  sourceType.value === 'dynamic'
    ? `${data.value?.dynamic.person ?? ''} · 动态过程`
    : `${person.value?.name ?? ''} · Action ${currentAction.value?.action ?? '-'} · ${sleepPosName.value}`,
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

// 视口高度 → 热力图最大高度（保证底部曲线图在 900px 高视口内也可见）
const viewportH = ref(window.innerHeight);
const heatmapMaxHeight = computed(() => Math.max(260, viewportH.value - 450));

// 当前数据源的全部帧 + 对应空载背景（动态帧用 wzh 自己的背景）
const framesList = computed<ArrayLike<number>[]>(() =>
  sourceType.value === 'dynamic'
    ? (data.value?.dynamic.frames ?? [])
    : (currentAction.value?.frames ?? []),
);
const bgForMetrics = computed<ArrayLike<number> | null>(() =>
  sourceType.value === 'dynamic' ? (data.value?.dynamic.bg ?? null) : (person.value?.bg ?? null),
);
// 逐帧指标历史（回放顺序），用于指标卡 sparkline 与时间曲线
const history = computed(() => metricsHistory(framesList.value, bgForMetrics.value, 20));

// 区域与脊柱标注（当前动作；同一动作内标注基本恒定）
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
const selectedRegion = ref<number | null>(null);
const hoverRegion = ref<number | null>(null);

// 当前帧区域统计（按平均净压力降序）
const regionStats = computed(() => {
  if (!regions.value || !currentFrame.value.length) return [];
  return regionStatsAll(currentFrame.value, bgForMetrics.value, regions.value, 20);
});

// 选定区域的逐帧平均压力曲线
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
  if (selectedRegion.value === null || !regions.value) return '#8b949e';
  const rg = regions.value[selectedRegion.value];
  return rg?.valid ? (REGION_COLORS[rg.name] ?? '#8b949e') : '#8b949e';
});

// rAF 驱动
let rafId = 0;
let lastTs = 0;
function loop(ts: number) {
  if (lastTs > 0) controller.value?.tick(ts - lastTs);
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

// URL hash 状态（便于截图/演示直链）：#type=dynamic&person=wzh&action=2&frame=10&mode=grid&scale=auto
function applyHash() {
  const h = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
  if (h.get('type') === 'dynamic') sourceType.value = 'dynamic';
  const pn = h.get('person');
  if (pn && data.value) {
    const pi = data.value.people.findIndex((p) => p.name === pn);
    if (pi >= 0) personIdx.value = pi;
  }
  const a = Number(h.get('action'));
  if (!Number.isNaN(a) && person.value) {
    const idx = person.value.actions.findIndex((x) => x.action === a);
    if (idx >= 0) actionIdx.value = idx;
  }
  if (h.get('mode') === 'grid' || h.get('mode') === 'weak') mode.value = h.get('mode') as HeatmapMode;
  if (h.get('scale') === 'auto' || h.get('scale') === 'fixed500') scale.value = h.get('scale') as ScaleMode;
  if (h.get('calf') === '1') showCalf.value = true;
  const rgRaw = h.get('region');
  if (rgRaw !== null) {
    const rg = Number(rgRaw);
    if (!Number.isNaN(rg) && rg >= 0 && rg <= 5) selectedRegion.value = rg;
  }
  rebuildController();
  const f = Number(h.get('frame'));
  if (!Number.isNaN(f)) controller.value?.seek(f);
  if (h.get('autoplay') === '1') controller.value?.play();
}

const legendCanvas = ref<HTMLCanvasElement | null>(null);

onMounted(async () => {
  window.addEventListener('resize', () => (viewportH.value = window.innerHeight));
  const res = await fetch(`${import.meta.env.BASE_URL}data/demo.json`);
  data.value = (await res.json()) as DemoData;
  applyHash();
  // 图例渐变色（turbo，0-250）
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

const phases = [
  { id: 1, name: '读取数据', done: true },
  { id: 2, name: '静态热力图', done: true },
  { id: 3, name: '帧动画', done: true },
  { id: 4, name: '实时指标与曲线', done: true },
  { id: 5, name: '区域分析', done: true },
  { id: 6, name: '完整大屏 UI', done: true },
  { id: 7, name: '气囊模块', done: false },
  { id: 8, name: '最终 Demo', done: false },
];
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <h1>智能床垫实时监测系统</h1>
      <div class="badges">
        <span class="badge replay">● 回放 · 本地历史数据</span>
        <span class="badge">v0.6.0 · Phase 6</span>
      </div>
    </header>

    <main class="content">
      <aside class="panel left">
        <h2>数据源</h2>
        <div class="field">
          <span>类型</span>
          <div class="seg">
            <button :class="{ active: sourceType === 'static' }" @click="selectSource('static')">静态动作</button>
            <button :class="{ active: sourceType === 'dynamic' }" @click="selectSource('dynamic')">动态过程</button>
          </div>
        </div>
        <template v-if="sourceType === 'static'">
          <label class="field">
            <span>用户</span>
            <select :value="personIdx" @change="selectPerson(Number(($event.target as HTMLSelectElement).value))">
              <option v-for="(p, i) in data?.people" :key="p.name" :value="i">
                {{ p.name }}（{{ p.height ?? '?' }}cm / {{ p.weight ?? '?' }}kg）
              </option>
            </select>
          </label>
          <label class="field">
            <span>动作</span>
            <select :value="actionIdx" @change="selectAction(Number(($event.target as HTMLSelectElement).value))">
              <option v-for="(a, i) in person?.actions" :key="a.action" :value="i">
                {{ actionLabel(a) }}
              </option>
            </select>
          </label>
        </template>
        <div class="field">
          <span>显示模式</span>
          <div class="seg">
            <button v-for="m in modeOptions" :key="m.value" :class="{ active: mode === m.value }" @click="mode = m.value">
              {{ m.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <span>量程</span>
          <div class="seg">
            <button v-for="s in scaleOptions" :key="s.value" :class="{ active: scale === s.value }" @click="scale = s.value">
              {{ s.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <span>标注叠加</span>
          <div class="checks">
            <label><input type="checkbox" v-model="showRegions" /> 区域框</label>
            <label><input type="checkbox" v-model="showSpine" /> 脊柱线</label>
            <label><input type="checkbox" v-model="showCalf" /> 小腿部<span class="tiny">(仅3人有标注)</span></label>
          </div>
        </div>
        <div class="legend">
          <canvas ref="legendCanvas" class="legend-canvas"></canvas>
          <div class="legend-ticks">
            <span>0</span><span>50</span><span>100</span><span>150</span><span>200</span><span>250</span>
          </div>
        </div>
      </aside>

      <section class="center">
        <div class="heatmap-panel">
          <div class="heatmap-title">
            <span>{{ sourceLabel }}</span>
            <span class="title-right">
              <span v-if="hoverCell" class="hover-tag">
                ({{ hoverCell.row }}, {{ hoverCell.col }}) 净压 = {{ hoverCell.value }}
              </span>
              <span class="frame-tag">第 {{ frameIdx }} 帧</span>
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
            <button class="ctl" title="上一帧" @click="stepPrev">⏮</button>
            <button class="ctl play" :title="playing ? '暂停' : '播放'" @click="togglePlay">
              {{ playing ? 'Ⅱ' : '▶' }}
            </button>
            <button class="ctl" title="下一帧" @click="stepNext">⏭</button>
            <input
              class="progress"
              type="range"
              :min="0"
              :max="frameCount - 1"
              :value="frameIdx"
              @input="onSeek"
            />
            <span class="frame-num">{{ frameIdx }} / {{ frameCount - 1 }}</span>
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
        <h2>睡眠状态</h2>
        <SleepPoseCard
          :pose="sleepPosName"
          :duration-frames="poseDurationFrames"
          :fps="10"
          :note="sourceType === 'dynamic' ? '动态过程：文件内 0/1/2 标签行按官方说明忽略' : currentAction?.action === 0 ? '空载帧：扣背景后有效接触点 < 50 判定为离床（自研启发式）' : undefined"
        />
        <h2>实时压力指标</h2>
        <MetricCards :metrics="metrics" :history="history" />
        <h2 style="margin-top: 18px">区域压力排行<span class="sub">（平均净压力）</span></h2>
        <RegionRanking :stats="regionStats" :selected="selectedRegion" :hovered="hoverRegion" @select="selectedRegion = $event" />
        <p class="hint">
          热力图与读数均为扣除空载背景后的净压力；回放基准 10 fps（采集帧率约 2.3 fps）；行 0 = 头端，列 12 = 中线。
        </p>
        <p
          v-if="scale !== 'auto' && metrics && metrics.maxRaw > (scale === 'fixed250' ? 250 : 500)"
          class="warn"
        >
          ⚠ 帧最大压力 {{ metrics.maxRaw }} 超出当前量程，峰值区被削顶显示
        </p>
      </aside>
    </main>

    <section class="chart-panel">
      <h2>压力指标趋势（随回放实时更新）</h2>
      <MetricsChart
        :history="history"
        :frame-idx="frameIdx"
        :extra-series="
          selectedRegion !== null && regionCurve.length
            ? [{ label: `${selectedRegionName}平均压力`, color: selectedRegionColor, values: regionCurve }]
            : []
        "
      />
    </section>

    <footer class="footer">
      <span v-for="p in phases" :key="p.id" class="phase" :class="{ done: p.done }">P{{ p.id }} {{ p.name }}</span>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
}
.topbar h1 {
  font-size: 20px;
  font-weight: 600;
}
.badges {
  display: flex;
  gap: 10px;
}
.badge {
  font-size: 13px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
}
.badge.replay {
  color: var(--accent);
  border-color: var(--accent);
}
.content {
  flex: 1;
  display: grid;
  grid-template-columns: 240px 1fr 260px;
  grid-template-rows: minmax(0, 1fr);
  gap: 16px;
  padding: 16px 20px;
  min-height: 0;
  overflow: hidden;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px 20px;
  overflow: auto;
  min-height: 0;
}
.panel h2 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.field {
  display: block;
  margin-bottom: 14px;
}
.field > span {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
select {
  width: 100%;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.seg {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.seg button {
  flex: 1;
  min-width: 56px;
  background: var(--bg);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 6px;
  font-size: 12px;
  cursor: pointer;
}
.seg button.active {
  color: var(--accent);
  border-color: var(--accent);
}
.checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text);
}
.checks label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.checks input {
  accent-color: var(--accent);
}
.tiny {
  font-size: 10px;
  color: var(--text-secondary);
}
.sub {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-secondary);
  margin-left: 6px;
}
.legend-canvas {
  width: 100%;
  height: 14px;
  border-radius: 4px;
  image-rendering: pixelated;
}
.legend-ticks {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}
.center {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
  overflow: auto;
}
.heatmap-panel {
  width: 100%;
  max-width: 620px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
}
.heatmap-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text);
  margin-bottom: 10px;
}
.frame-tag {
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 8px;
}
.title-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hover-tag {
  font-size: 12px;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.ctl {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  width: 34px;
  height: 30px;
  cursor: pointer;
  font-size: 14px;
}
.ctl.play {
  border-color: var(--accent);
  color: var(--accent);
}
.progress {
  flex: 1;
  accent-color: var(--accent);
}
.frame-num {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
  min-width: 56px;
  text-align: right;
}
.speed-seg {
  display: flex;
  gap: 4px;
}
.speed-seg button {
  background: var(--bg);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.speed-seg button.active {
  color: var(--accent);
  border-color: var(--accent);
}
.info {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}
.info > div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.info dt {
  color: var(--text-secondary);
}
.info dd {
  font-variant-numeric: tabular-nums;
}
.hint {
  margin-top: 14px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.warn {
  margin-top: 10px;
  font-size: 12px;
  color: #d29922;
  line-height: 1.6;
}
.footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  font-size: 11px;
}
.chart-panel {
  margin: 0 20px 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 16px;
  height: 220px;
  display: flex;
  flex-direction: column;
}
.chart-panel h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.chart-panel :deep(.chart-wrap) {
  flex: 1;
}
.phase {
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
}
.phase.done {
  color: var(--accent);
  border-color: var(--accent);
}
</style>
