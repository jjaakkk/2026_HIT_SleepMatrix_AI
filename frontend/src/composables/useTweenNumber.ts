import { onBeforeUnmount, ref, watch } from 'vue';

/**
 * 数值滚动动画：指标变化时从当前值平滑滚向目标值（easeOutCubic）。
 * 尊重 prefers-reduced-motion：直接跳到目标值。
 */
export function useTweenNumber(
  getter: () => number | null,
  opts: { duration?: number; decimals?: number } = {},
) {
  const { duration = 420, decimals = 0 } = opts;
  const display = ref('—');
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let current = 0;
  let raf = 0;

  watch(
    getter,
    (v) => {
      cancelAnimationFrame(raf);
      if (v === null || Number.isNaN(v)) {
        display.value = '—';
        return;
      }
      if (reduced) {
        current = v;
        display.value = v.toFixed(decimals);
        return;
      }
      const from = current;
      const target = v;
      const start = performance.now();
      const step = (now: number) => {
        const p = Math.min((now - start) / duration, 1);
        const e = 1 - Math.pow(1 - p, 3);
        current = from + (target - from) * e;
        display.value = current.toFixed(decimals);
        if (p < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    },
    { immediate: true },
  );

  onBeforeUnmount(() => cancelAnimationFrame(raf));
  return display;
}
