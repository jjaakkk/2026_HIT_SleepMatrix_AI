<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import HeatmapCanvas from './components/HeatmapCanvas.vue';
import { turboColor } from './render/heatmap.ts';
import type { HeatmapMode, ScaleMode } from './render/heatmap.ts';
import { SLEEP_POS_NAMES } from './core/types.ts';
import { computeMetrics } from './core/metrics.ts';

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
  dynamic: { person: string; frames: number[][]; labels: number[] };
}

const data = ref<DemoData | null>(null);
const person = ref<DemoPerson | null>(null);
const actionIdx = ref(0);
const frameIdx = ref(0);
const mode = ref<HeatmapMode>('smooth');
const scale = ref<ScaleMode>('fixed250');
const hoverCell = ref<{ row: number; col: number; value: number } | null>(null);

const currentAction = computed(() => person.value?.actions[actionIdx.value] ?? null);
const frameCount = computed(() => currentAction.value?.frames.length ?? 0);
const currentFrame = computed(() => currentAction.value?.frames[frameIdx.value] ?? new Float32Array(0));
const sleepPosName = computed(() =>
  currentAction.value ? SLEEP_POS_NAMES[currentAction.value.sleepPos] ?? '未知' : '-',
);
const metrics = computed(() => {
  if (!currentFrame.value.length || !person.value) return null;
  return computeMetrics(currentFrame.value, person.value.bg, 20);
});

const modeOptions: { value: HeatmapMode; label: string }[] = [
  { value: 'smooth', label: '标准' },
  { value: 'weak', label: '弱力增强' },
  { value: 'grid', label: '原始网格' },
];
const scaleOptions: { value: ScaleMode; label: string }[] = [
  { value: 'fixed250', label: '固定 0–250' },
  { value: 'auto', label: '自动' },
  { value: 'fixed500', label: '固定 0–500' },
];

function selectAction(i: number) {
  actionIdx.value = i;
  frameIdx.value = 0;
}

onMounted(async () => {
  const res = await fetch(`${import.meta.env.BASE_URL}data/demo.json`);
  data.value = (await res.json()) as DemoData;
  person.value = data.value.people[0] ?? null;
});

watch(actionIdx, () => (frameIdx.value = 0));
watch(() => frameCount.value, (n) => {
  if (frameIdx.value >= n) frameIdx.value = n - 1;
});

// 图例渐变色（turbo，0-250）
const legendCanvas = ref<HTMLCanvasElement | null>(null);
onMounted(() => {
  const c = legendCanvas.value;
  if (!c) return;
  c.width = 256;
  c.height = 14;
  const ctx = c.getContext('2d')!;
  for (let x = 0; x < 256; x++) {
    const [r, g, b] = turboColor(x / 255);
    ctx.fillStyle = `rgb(${Math.round(r * 255)},${Math.round(g * 255)},${Math.round(b * 255)})`;
    ctx.fillRect(x, 0, 1, 14);
  }
});

const phases = [
  { id: 1, name: '读取数据（txt/json 解析 + 标注 + 指标）', done: true },
  { id: 2, name: '静态热力图（Canvas + turbo 色带）', done: true },
  { id: 3, name: '帧动画（回放引擎）', done: false },
  { id: 4, name: '实时指标卡与曲线', done: false },
  { id: 5, name: '区域分析叠加', done: false },
  { id: 6, name: '完整大屏 UI', done: false },
  { id: 7, name: '气囊模块（模拟 + 预留接口）', done: false },
  { id: 8, name: '最终 Demo', done: false },
];
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <h1>智能床垫实时监测系统</h1>
      <div class="badges">
        <span class="badge replay">● 回放 · 本地历史数据</span>
        <span class="badge">v0.2.0 · Phase 2</span>
      </div>
    </header>

    <main class="content">
      <aside class="panel left">
        <h2>数据源</h2>
        <label class="field">
          <span>用户</span>
          <select :value="person?.name" disabled>
            <option>{{ person?.name }}</option>
          </select>
        </label>
        <label class="field">
          <span>动作</span>
          <select :value="actionIdx" @change="selectAction(Number(($event.target as HTMLSelectElement).value))">
            <option v-for="(a, i) in person?.actions" :key="a.action" :value="i">
              Action {{ a.action }} · {{ SLEEP_POS_NAMES[a.sleepPos] }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>帧号 {{ frameIdx }} / {{ frameCount - 1 }}</span>
          <input type="range" :min="0" :max="frameCount - 1" v-model.number="frameIdx" />
        </label>
        <div class="field">
          <span>显示模式</span>
          <div class="seg">
            <button
              v-for="m in modeOptions"
              :key="m.value"
              :class="{ active: mode === m.value }"
              @click="mode = m.value"
            >
              {{ m.label }}
            </button>
          </div>
        </div>
        <div class="field">
          <span>量程</span>
          <div class="seg">
            <button
              v-for="s in scaleOptions"
              :key="s.value"
              :class="{ active: scale === s.value }"
              @click="scale = s.value"
            >
              {{ s.label }}
            </button>
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
            <span>{{ person?.name }} · Action {{ currentAction?.action }} · {{ sleepPosName }}</span>
            <span class="frame-tag">第 {{ frameIdx }} 帧</span>
          </div>
          <HeatmapCanvas
            :frame="currentFrame"
            :mode="mode"
            :scale="scale"
            @hover="hoverCell = $event"
          />
        </div>
      </section>

      <aside class="panel right">
        <h2>当前帧</h2>
        <dl class="info">
          <div><dt>睡姿</dt><dd>{{ sleepPosName }}</dd></div>
          <div><dt>传感器点</dt><dd>44 × 24 = 1056</dd></div>
          <div><dt>最大压力</dt><dd>{{ metrics?.maxRaw ?? '-' }}</dd></div>
          <div><dt>净最大（扣空载）</dt><dd>{{ metrics ? metrics.maxNet.toFixed(0) : '-' }}</dd></div>
          <div><dt>有效接触点</dt><dd>{{ metrics ? `${metrics.activePoints}（${(metrics.contactRatio * 100).toFixed(1)}%）` : '-' }}</dd></div>
          <div><dt>悬浮读数</dt><dd>{{ hoverCell ? `(${hoverCell.row}, ${hoverCell.col}) = ${hoverCell.value}` : '悬停查看' }}</dd></div>
        </dl>
        <p class="hint">
          行 0 = 头端，列 12 = 中线。量程 0–250 与项目组参考热力图一致；"弱力增强"为显示增强模式（p^0.35 压扩）。
        </p>
      </aside>
    </main>

    <footer class="footer">
      <span v-for="p in phases" :key="p.id" class="phase" :class="{ done: p.done }">
        P{{ p.id }} {{ p.name }}
      </span>
    </footer>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
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
  gap: 16px;
  padding: 16px 20px;
  min-height: 0;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  overflow: auto;
}
.panel h2 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 14px;
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
select,
input[type='range'] {
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
}
.heatmap-panel {
  width: 100%;
  max-width: 560px;
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
.footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  font-size: 11px;
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
