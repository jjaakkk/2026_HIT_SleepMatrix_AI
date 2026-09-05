<script setup lang="ts">
/**
 * 开关（Switch）：布尔设置项。role="switch" + 键盘空格切换。
 */
withDefaults(
  defineProps<{
    modelValue: boolean;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>();
</script>

<template>
  <button
    type="button"
    class="switch"
    :class="{ on: modelValue }"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span class="knob" aria-hidden="true" />
  </button>
</template>

<style scoped>
.switch {
  position: relative;
  flex: none;
  width: 34px;
  height: 20px;
  border-radius: var(--r-pill);
  border: 1px solid var(--border-strong);
  background: var(--surface-3);
  cursor: pointer;
  padding: 0;
  transition:
    background-color var(--dur-base) var(--ease-in-out),
    border-color var(--dur-base) var(--ease-in-out);
  -webkit-tap-highlight-color: transparent;
}
.switch.on {
  background: var(--accent);
  border-color: var(--accent);
}
.switch:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.knob {
  position: absolute;
  top: 50%;
  left: 2.5px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--surface-1);
  box-shadow: var(--shadow-float);
  transform: translateY(-50%);
  transition: transform var(--dur-base) var(--ease-spring);
}
.switch.on .knob {
  transform: translate(14px, -50%);
}
.switch:active:not(:disabled) .knob {
  width: 17px;
}
.switch.on:active:not(:disabled) .knob {
  transform: translate(11px, -50%);
  width: 17px;
}
</style>
