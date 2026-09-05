import { onBeforeUnmount, onMounted, ref } from 'vue';

/**
 * 缩放适配（scale-to-fit）：以固定设计空间渲染，整体等比缩放铺满视口。
 * 任意分辨率下布局恒定 —— 无滚动条、无重叠、无断点碎片化。
 * 设计空间 1920×1080；缩放上限 1.5（4K 大屏适度放大），下限 0.5。
 */
export const DESIGN_W = 1920;
export const DESIGN_H = 1080;

export function useScaleToFit() {
  const scale = ref(1);

  function update() {
    const s = Math.min(window.innerWidth / DESIGN_W, window.innerHeight / DESIGN_H);
    scale.value = Math.min(Math.max(s, 0.5), 1.5);
  }

  onMounted(() => {
    update();
    window.addEventListener('resize', update);
  });
  onBeforeUnmount(() => window.removeEventListener('resize', update));

  return { scale, DESIGN_W, DESIGN_H };
}
