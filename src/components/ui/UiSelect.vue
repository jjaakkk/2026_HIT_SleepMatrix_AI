<script setup lang="ts">
/**
 * 自定义下拉选择：fixed 定位弹层（可穿透面板 overflow 裁剪）。
 * 键盘：Enter/Space/ArrowDown 打开；↑↓ 移动高亮；Enter 选中；Esc/Tab 关闭。
 * 注：不依赖 trigger blur 关闭（避免与选项 click 的失焦竞态）。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import Icon from './Icon.vue';

export interface SelectOption {
  value: string | number;
  label: string;
  hint?: string;
  disabled?: boolean;
}

const props = withDefaults(
  defineProps<{
    options: SelectOption[];
    modelValue: string | number | null;
    placeholder?: string;
    icon?: 'user' | 'body' | 'none';
    ariaLabel?: string;
    disabled?: boolean;
  }>(),
  { placeholder: '请选择', icon: 'none', ariaLabel: undefined, disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [v: string | number] }>();

const open = ref(false);
const activeIdx = ref(-1);
const btnRef = ref<HTMLButtonElement | null>(null);
const listRef = ref<HTMLElement | null>(null);
const pop = ref<{ x: number; y: number; w: number; up: boolean; bottom: number } | null>(null);

const selected = computed(() => props.options.find((o) => o.value === props.modelValue) ?? null);

function updatePos() {
  const btn = btnRef.value;
  if (!btn) return;
  const r = btn.getBoundingClientRect();
  const listH = Math.min(300, props.options.length * 32 + 16);
  const spaceBelow = window.innerHeight - r.bottom - 8;
  const up = spaceBelow < listH && r.top > spaceBelow;
  pop.value = {
    x: r.left,
    y: up ? r.top - 6 : r.bottom + 6,
    w: r.width,
    up,
    bottom: window.innerHeight - r.top + 6,
  };
}

function scrollActiveIntoView() {
  const list = listRef.value;
  const items = list?.querySelectorAll<HTMLElement>('.opt');
  const el = items?.[activeIdx.value];
  if (!el || !list) return;
  const lr = list.getBoundingClientRect();
  const er = el.getBoundingClientRect();
  if (er.top < lr.top) list.scrollTop += er.top - lr.top - 4;
  else if (er.bottom > lr.bottom) list.scrollTop += er.bottom - lr.bottom + 4;
}

function openList() {
  if (props.disabled) return;
  open.value = true;
  activeIdx.value = Math.max(props.options.findIndex((o) => o.value === props.modelValue), 0);
  nextTick(() => {
    updatePos();
    scrollActiveIntoView();
  });
}

function closeList(restoreFocus = true) {
  if (!open.value) return;
  open.value = false;
  if (restoreFocus) btnRef.value?.focus();
}

function choose(v: string | number) {
  emit('update:modelValue', v);
  closeList();
}

function onBtnClick() {
  if (open.value) closeList(false);
  else openList();
}

function moveActive(dir: 1 | -1) {
  const enabled = props.options;
  let i = activeIdx.value;
  for (let step = 0; step < enabled.length; step++) {
    i = (i + dir + enabled.length) % enabled.length;
    if (!enabled[i].disabled) break;
  }
  activeIdx.value = i;
  nextTick(scrollActiveIntoView);
}

/** 触发器键盘（焦点保留在按钮上，如原生 select） */
function onBtnKey(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    if (!open.value) {
      openList();
    } else if (e.key === 'ArrowDown') {
      moveActive(1);
    } else if (e.key === 'ArrowUp') {
      moveActive(-1);
    } else {
      // Enter / Space：选中当前高亮项
      const o = props.options[activeIdx.value];
      if (o && !o.disabled) choose(o.value);
    }
  } else if (e.key === 'Escape') {
    closeList();
  } else if (e.key === 'Tab') {
    closeList(false);
  }
}

function onListKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    moveActive(e.key === 'ArrowDown' ? 1 : -1);
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    const o = props.options[activeIdx.value];
    if (o && !o.disabled) choose(o.value);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    closeList();
  } else if (e.key === 'Tab') {
    closeList(false);
  }
}

function onOutside(e: MouseEvent) {
  if (!open.value) return;
  const list = listRef.value;
  const btn = btnRef.value;
  if (e.target instanceof Node && list?.contains(e.target)) return;
  if (e.target instanceof Node && btn?.contains(e.target)) return;
  closeList();
}

function onScrollOrResize() {
  if (open.value) updatePos();
}

watch(open, (v) => {
  if (v) {
    window.addEventListener('mousedown', onOutside);
    window.addEventListener('scroll', onScrollOrResize, true);
    window.addEventListener('resize', onScrollOrResize);
  } else {
    window.removeEventListener('mousedown', onOutside);
    window.removeEventListener('scroll', onScrollOrResize, true);
    window.removeEventListener('resize', onScrollOrResize);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('mousedown', onOutside);
  window.removeEventListener('scroll', onScrollOrResize, true);
  window.removeEventListener('resize', onScrollOrResize);
});
</script>

<template>
  <div class="sel-root">
    <button
      ref="btnRef"
      type="button"
      class="trigger"
      :class="{ open, disabled }"
      :disabled="disabled"
      :aria-haspopup="'listbox'"
      :aria-expanded="open"
      :aria-label="ariaLabel"
      @click="onBtnClick"
      @keydown="onBtnKey"
    >
      <Icon v-if="icon !== 'none'" :name="icon" :size="14" class="lead" />
      <span class="val" :class="{ ph: !selected }">{{ selected ? selected.label : placeholder }}</span>
      <Icon name="chevron-down" :size="14" class="caret" />
    </button>

    <Teleport to="body">
      <Transition name="dd">
        <div
          v-if="open"
          ref="listRef"
          class="pop"
          role="listbox"
          :style="{
            left: pop?.x + 'px',
            top: pop?.up ? undefined : pop?.y + 'px',
            bottom: pop?.up ? pop?.bottom + 'px' : undefined,
            width: pop?.w + 'px',
          }"
          @keydown="onListKey"
        >
          <button
            v-for="(o, i) in options"
            :key="o.value"
            type="button"
            class="opt"
            :class="{ sel: o.value === modelValue, act: i === activeIdx }"
            role="option"
            :aria-selected="o.value === modelValue"
            :disabled="o.disabled"
            @click="choose(o.value)"
            @mouseenter="activeIdx = i"
          >
            <span class="opt-label">{{ o.label }}</span>
            <span v-if="o.hint" class="opt-hint">{{ o.hint }}</span>
            <Icon v-if="o.value === modelValue" name="check" :size="14" class="opt-check" />
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.sel-root {
  width: 100%;
}
.trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  padding: 5px 9px 5px 10px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-family: var(--font-ui);
  font-size: var(--fs-xs);
  color: var(--text-1);
  cursor: pointer;
  text-align: left;
  transition:
    border-color var(--dur-fast) var(--ease-out),
    background-color var(--dur-fast) var(--ease-out),
    box-shadow var(--dur-fast) var(--ease-out);
}
.trigger:hover:not(.disabled) {
  border-color: var(--border-strong);
  background: var(--surface-1);
}
.trigger.open {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}
.trigger.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.lead {
  color: var(--text-3);
  flex: none;
}
.val {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.val.ph {
  color: var(--text-3);
}
.caret {
  color: var(--text-3);
  flex: none;
  transition: transform var(--dur-base) var(--ease-spring);
}
.trigger.open .caret {
  transform: rotate(180deg);
}

.pop {
  position: fixed;
  z-index: var(--z-pop);
  max-height: 300px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-pop);
  transform-origin: top center;
}
.opt {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  padding: 4px 8px 4px 10px;
  border: none;
  background: transparent;
  border-radius: var(--r-xs);
  font-family: var(--font-ui);
  font-size: var(--fs-xs);
  color: var(--text-1);
  cursor: pointer;
  text-align: left;
}
.opt.act:not(:disabled) {
  background: var(--surface-hover);
}
.opt.sel {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 560;
}
.opt:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.opt-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.opt-hint {
  font-size: var(--fs-2xs);
  color: var(--text-3);
  flex: none;
}
.opt-check {
  flex: none;
  color: var(--accent);
}

.dd-enter-active,
.dd-leave-active {
  transition:
    opacity var(--dur-base) var(--ease-out),
    transform var(--dur-base) var(--ease-spring);
}
.dd-enter-from,
.dd-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}
</style>
