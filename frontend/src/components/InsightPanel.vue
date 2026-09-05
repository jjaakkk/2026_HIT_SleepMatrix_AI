<script setup lang="ts">
/**
 * 右侧洞察面板：睡姿状态 + 压力指标（部位受力排行位于底部面板，与热力图相邻）。
 */
import PanelCard from './ui/PanelCard.vue';
import SleepPoseCard from './SleepPoseCard.vue';
import MetricCards from './MetricCards.vue';
import type { FrameMetrics } from '../core/metrics';

defineProps<{
  pose: string;
  durationFrames: number;
  poseNote?: string;
  playing: boolean;
  /** 睡姿判定来源 */
  poseSource?: 'label' | 'inference';
  /** 推理置信度 0-1 */
  confidence?: number | null;
  predicting?: boolean;
  metrics: FrameMetrics | null;
  history: FrameMetrics[];
}>();
</script>

<template>
  <PanelCard class="insight" flush>
    <div class="inner">
      <section class="sec">
        <h4 class="sec-title">睡姿状态</h4>
        <SleepPoseCard
          :pose="pose"
          :duration-frames="durationFrames"
          :fps="10"
          :note="poseNote"
          :live="playing"
          :source="poseSource"
          :confidence="confidence"
          :predicting="predicting"
        />
      </section>

      <div class="divider" role="separator" />

      <section class="sec">
        <h4 class="sec-title">压力指标</h4>
        <MetricCards :metrics="metrics" :history="history" />
        <p class="footnote">读数与热力图均为扣除空载后的净压力</p>
      </section>
    </div>
  </PanelCard>
</template>

<style scoped>
.insight {
  height: 100%;
  min-height: 0;
}
.inner {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 16px 18px;
  height: 100%;
  min-height: 0;
}
.sec {
  flex: none;
}
.sec-title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: var(--fs-2xs);
  font-weight: 600;
  letter-spacing: 0.07em;
  color: var(--text-3);
  margin-bottom: 10px;
  padding-left: 1px;
}
.divider {
  height: 1px;
  background: var(--border-subtle);
  flex: none;
}
.footnote {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-3);
  line-height: 1.5;
}
</style>
