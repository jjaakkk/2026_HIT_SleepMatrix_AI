<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import {
  AIRBAG_ZONES,
  AIRBAG_PRESETS,
  airbagStateText,
  type AirbagSource,
  type AirbagState,
} from '../core/airbag.ts';
import PanelCard from './ui/PanelCard.vue';
import UiBadge from './ui/UiBadge.vue';
import Icon from './ui/Icon.vue';

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
/** 当前选中的气囊（点击行选中，滑杆调节该气囊） */
const selectedId = ref('41');
const selectedZone = computed(() => AIRBAG_ZONES.find((z) => z.id === selectedId.value) ?? AIRBAG_ZONES[1]);
function selectZone(id: string) {
  selectedId.value = id;
}
function onSlider(e: Event) {
  props.source.setTarget(selectedId.value, Number((e.target as HTMLInputElement).value));
}
function applyPreset(name: string) {
  const p = AIRBAG_PRESETS.find((x) => x.name === name);
  if (!p) return;
  for (const [id, v] of Object.entries(p.zones)) props.source.setTarget(id, v);
  emit('preset', name);
}

const left = computed(() => AIRBAG_ZONES.filter((z) => z.side === '左半区'));
const right = computed(() => AIRBAG_ZONES.filter((z) => z.side === '右半区'));

const sliderValue = computed(() => stateOf(selectedId.value).pressure);
</script>

<template>
  <PanelCard class="airbag-panel" flush title="气囊状态" icon="wind">
    <template #actions>
      <UiBadge variant="warning" :dot="false">
        <Icon name="info" :size="11" />模拟信号 · 未接入设备
      </UiBadge>
    </template>
    <div class="airbag">
      <div class="presets" role="group" aria-label="气囊预设">
        <button
          v-for="p in AIRBAG_PRESETS"
          :key="p.name"
          type="button"
          :title="p.description"
          @click="applyPreset(p.name)"
        >
          <Icon name="wind" :size="13" />
          {{ p.name }}
        </button>
      </div>

      <div class="groups">
        <div v-for="(zones, gi) in [left, right]" :key="gi" class="group">
          <div class="group-title">{{ gi === 0 ? '左半区' : '右半区' }}</div>
          <button
            v-for="z in zones"
            :key="z.id"
            type="button"
            class="zone"
            :class="{ sel: selectedId === z.id }"
            :title="`点击选中 ${z.id} 号气囊（${z.regionHint}），滑杆调节其充气程度`"
            @click="selectZone(z.id)"
          >
            <span
              class="zid num"
              :style="{ color: z.color, borderColor: `color-mix(in srgb, ${z.color} 45%, transparent)`, background: `color-mix(in srgb, ${z.color} 10%, transparent)` }"
              >{{ z.id }}</span
            >
            <span class="hint">{{ z.regionHint }}</span>
            <span class="bar" aria-hidden="true">
              <span
                class="fill"
                :style="{ width: stateOf(z.id).pressure + '%', background: z.color }"
              />
            </span>
            <span class="pct num">{{ stateOf(z.id).pressure.toFixed(0) }}%</span>
            <span class="st">{{ airbagStateText(stateOf(z.id).pressure) }}</span>
          </button>
        </div>
      </div>

      <div class="slider-row">
        <Icon name="sliders" :size="12" class="slider-icon" />
        <span class="slider-label">调节</span>
        <input
          type="range"
          min="0"
          max="100"
          :value="sliderValue"
          :aria-label="`调节 ${selectedZone.id} 号气囊（${selectedZone.regionHint}）`"
          @input="onSlider"
        />
        <span class="zone-tag num">{{ selectedZone.id }} · {{ selectedZone.regionHint }}</span>
      </div>
      <p class="foot">点击气囊行选中 · 滑杆调节所选气囊 · 预设一键切换</p>
    </div>
  </PanelCard>
</template>

<style scoped>
.airbag-panel {
  height: 100%;
  min-height: 0;
}
.airbag {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px 12px;
  height: 100%;
  min-height: 0;
}
.presets {
  display: flex;
  gap: 7px;
  flex: none;
}
.presets button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  justify-content: center;
  background: var(--surface-2);
  color: var(--text-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  padding: 5px 8px;
  font-size: var(--fs-xs);
  font-family: var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}
.presets button:hover {
  border-color: var(--accent-soft-strong);
  color: var(--accent);
  background: var(--accent-soft);
}
.presets button:active {
  transform: scale(0.96);
}
.groups {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
  align-content: start;
}
.group {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}
.group-title {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--text-3);
  padding-bottom: 1px;
  border-bottom: 1px solid var(--border-subtle);
}
.zone {
  display: grid;
  grid-template-columns: 24px 30px minmax(0, 1fr) 42px 32px;
  align-items: center;
  gap: 7px;
  font-size: var(--fs-2xs);
  width: 100%;
  min-width: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-xs);
  padding: 3px 5px;
  margin: 0 -5px;
  text-align: left;
  font-family: var(--font-ui);
  cursor: pointer;
  transition:
    background-color var(--dur-fast) var(--ease-out),
    border-color var(--dur-fast) var(--ease-out);
}
.zone:hover {
  background: var(--surface-2);
  border-color: var(--border);
}
.zone.sel {
  background: var(--accent-soft);
  border-color: var(--accent-soft-strong);
}
.zid {
  border: 1px solid;
  border-radius: var(--r-xs);
  text-align: center;
  padding: 1.5px 0;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0;
}
.hint {
  color: var(--text-2);
  white-space: nowrap;
}
.bar {
  height: 6px;
  background: var(--surface-3);
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width var(--dur-slow) var(--ease-out);
}
.pct {
  text-align: right;
  color: var(--text-1);
  font-weight: 500;
  font-size: 11px;
}
.st {
  color: var(--text-3);
  font-size: 10px;
  text-align: right;
  white-space: nowrap;
}
.slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-2xs);
  color: var(--text-2);
  flex: none;
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
}
.slider-icon {
  color: var(--text-3);
}
.slider-label {
  white-space: nowrap;
}
.slider-row input {
  flex: 1;
  min-width: 40px;
  accent-color: var(--accent);
  height: 16px;
  cursor: pointer;
}
.zone-tag {
  white-space: nowrap;
  color: var(--accent);
  font-size: 10.5px;
  font-weight: 500;
  border: 1px solid var(--accent-soft-strong);
  background: var(--accent-soft);
  border-radius: var(--r-pill);
  padding: 1.5px 9px;
}
.foot {
  flex: none;
  font-size: 10px;
  color: var(--text-3);
  text-align: right;
  padding: 0 2px;
  margin-top: -2px;
}
</style>
