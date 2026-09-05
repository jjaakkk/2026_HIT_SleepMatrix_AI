<script setup lang="ts">
/**
 * 分段控件（Segmented Control）：滑动指示块（FLIP 定位，弹簧缓动）。
 * 键盘：Tab 聚焦组内按钮，方向键/回车天然可用（原生 button）。
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    options: { value: string | number; label: string; disabled?: boolean; title?: string }[];
    modelValue: string | number;
    size?: 'sm' | 'md';
    /** 等宽均分（默认按内容自适应） */
    equal?: boolean;
  }>(),
  { size: 'md', equal: true },
);

const emit = defineEmits<{ 'update:modelValue': [v: string | number] }>();

const wrapRef = ref<HTMLElement | null>(null);
const btnRefs = ref<(HTMLButtonElement | null)[]>([]);
const thumb = ref<{ x: number; w: number; visible: boolean }>({ x: 0, w: 0, visible: false });

function setRef(i: number) {
  return (el: unknown) => {
    btnRefs.value[i] = el as HTMLButtonElement | null;
  };
}

function measure() {
  const wrap = wrapRef.value;
  if (!wrap) return;
  const idx = props.options.findIndex((o) => o.value === props.modelValue && !o.disabled);
  const el = btnRefs.value[idx];
  if (!el) return;
  const wr = wrap.getBoundingClientRect();
  const er = el.getBoundingClientRect();
  // 相对 padding box 测量（排除 wrap 边框，thumb 以 left:0 为基准）
  const originX = wr.left + wrap.clientLeft;
  thumb.value = { x: er.left - originX, w: er.width, visible: true };
}

watch(() => props.modelValue, () => nextTick(measure));
watch(() => props.options, () => nextTick(measure), { deep: true });
onMounted(() => {
  measure();
  window.addEventListener('resize', measure);
});
onBeforeUnmount(() => window.removeEventListener('resize', measure));

function pick(v: string | number) {
  if (v !== props.modelValue) emit('update:modelValue', v);
}
</script>

<template>
  <div
    ref="wrapRef"
    class="seg"
    :class="[`sz-${size}`, { equal }]"
    role="group"
    :aria-label="$attrs['aria-label'] as string | undefined"
  >
    <span
      class="thumb"
      :style="{
        transform: `translateX(${thumb.x}px)`,
        width: thumb.w + 'px',
        opacity: thumb.visible ? 1 : 0,
      }"
      aria-hidden="true"
    />
    <button
      v-for="(o, i) in options"
      :key="o.value"
      :ref="setRef(i)"
      type="button"
      class="opt"
      :class="{ active: modelValue === o.value }"
      :disabled="o.disabled"
      :aria-pressed="modelValue === o.value"
      :title="o.title"
      @click="pick(o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: var(--surface-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--r-md);
  width: 100%;
}
.seg.equal .opt {
  flex: 1;
  justify-content: center;
}
.thumb {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 0;
  background: var(--surface-1);
  border-radius: calc(var(--r-md) - 4px);
  box-shadow:
    var(--shadow-xs),
    inset 0 0 0 1px var(--border-subtle);
  transition:
    transform var(--dur-slow) var(--ease-spring),
    width var(--dur-slow) var(--ease-spring),
    opacity var(--dur-fast) var(--ease-out);
  will-change: transform, width;
  pointer-events: none;
}
.opt {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  font-family: var(--font-ui);
  font-size: var(--fs-xs);
  color: var(--text-3);
  cursor: pointer;
  border-radius: calc(var(--r-md) - 3px);
  white-space: nowrap;
  transition: color var(--dur-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}
.sz-sm .opt {
  padding: 4px 10px;
  min-height: 24px;
}
.sz-md .opt {
  padding: 5px 10px;
  min-height: 27px;
}
.opt:hover:not(:disabled) {
  color: var(--text-1);
}
.opt.active {
  color: var(--text-1);
  font-weight: 560;
}
.opt:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
