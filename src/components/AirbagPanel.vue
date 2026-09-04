<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import {
  AIRBAG_ZONES,
  AIRBAG_PRESETS,
  airbagStateText,
  type AirbagSource,
  type AirbagState,
} from '../core/airbag.ts';

const props = defineProps<{ source: AirbagSource }>();
const emit = defineEmits<{ preset: [name: string] }>();

const states = ref<AirbagState[]>(props.source.getStates());
let off: (() => void) | null = props.source.subscribe(() => {
  states.value = props.source.getStates();
});
onBeforeUnmount(() => off?.());

function stateOf(id: string) {
  return states.value.find((s) => s.zoneId === id)!;
}
function onSlider(id: string, e: Event) {
  props.source.setTarget(id, Number((e.target as HTMLInputElement).value));
}
function applyPreset(name: string) {
  const p = AIRBAG_PRESETS.find((x) => x.name === name);
  if (!p) return;
  for (const [id, v] of Object.entries(p.zones)) props.source.setTarget(id, v);
  emit('preset', name);
}

const left = computed(() => AIRBAG_ZONES.filter((z) => z.side === '左半区'));
const right = computed(() => AIRBAG_ZONES.filter((z) => z.side === '右半区'));
</script>

<template>
  <div class="airbag">
    <div class="head">
      <h2>气囊状态</h2>
      <span
        class="sim-badge"
        title="条带布局依据气囊-传感器布置图编号体系；条带与部位对应为推测；压力数据为回放，不受模拟气囊影响"
      >
        模拟数据 · 无真实气囊接口
      </span>
    </div>
    <div class="presets">
      <button v-for="p in AIRBAG_PRESETS" :key="p.name" :title="p.description" @click="applyPreset(p.name)">
        {{ p.name }}
      </button>
    </div>
    <div class="groups">
      <div class="group">
        <div class="group-title">左半区</div>
        <div v-for="z in left" :key="z.id" class="zone">
          <span class="zid" :style="{ borderColor: z.color, color: z.color }">{{ z.id }}</span>
          <span class="hint">{{ z.regionHint }}</span>
          <span class="bar">
            <span class="fill" :style="{ width: stateOf(z.id).pressure + '%', background: z.color }"></span>
          </span>
          <span class="pct">{{ stateOf(z.id).pressure.toFixed(0) }}%</span>
          <span class="st">{{ airbagStateText(stateOf(z.id).pressure) }}</span>
        </div>
      </div>
      <div class="group">
        <div class="group-title">右半区</div>
        <div v-for="z in right" :key="z.id" class="zone">
          <span class="zid" :style="{ borderColor: z.color, color: z.color }">{{ z.id }}</span>
          <span class="hint">{{ z.regionHint }}</span>
          <span class="bar">
            <span class="fill" :style="{ width: stateOf(z.id).pressure + '%', background: z.color }"></span>
          </span>
          <span class="pct">{{ stateOf(z.id).pressure.toFixed(0) }}%</span>
          <span class="st">{{ airbagStateText(stateOf(z.id).pressure) }}</span>
        </div>
      </div>
    </div>
    <div class="slider-row">
      <span>调节</span>
      <input type="range" min="0" max="100" :value="stateOf('41').pressure" @input="onSlider('41', $event)" />
      <span class="slider-label">41（腰）</span>
    </div>
  </div>
</template>

<style scoped>
.airbag {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  overflow: auto;
}
.head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.head h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-secondary);
}
.sim-badge {
  font-size: 10.5px;
  color: #d29922;
  border: 1px solid #d29922;
  border-radius: 999px;
  padding: 1px 8px;
}
.presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.presets button {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.presets button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.groups {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  flex: 1;
  min-height: 0;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.group-title {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 2px;
}
.zone {
  display: grid;
  grid-template-columns: 22px 30px 1fr 34px 38px;
  align-items: center;
  gap: 5px;
  font-size: 11px;
}
.zid {
  border: 1px solid;
  border-radius: 4px;
  text-align: center;
  padding: 1px 0;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
}
.hint {
  color: var(--text-secondary);
}
.bar {
  height: 6px;
  background: #21262d;
  border-radius: 3px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  transition: width 0.2s linear;
}
.pct {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.st {
  color: var(--text-secondary);
  font-size: 10px;
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
}
.slider-row input {
  flex: 1;
  accent-color: #3fb950;
}
.slider-label {
  white-space: nowrap;
}
</style>
