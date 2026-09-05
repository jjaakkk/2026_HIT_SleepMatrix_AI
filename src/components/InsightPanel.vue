<script setup lang="ts">
/**
 * 右侧洞察面板：睡姿状态 + 压力指标 + 部位受力排行。
 */
import PanelCard from './ui/PanelCard.vue';
import SleepPoseCard from './SleepPoseCard.vue';
import MetricCards from './MetricCards.vue';
import RegionRanking from './RegionRanking.vue';
import type { FrameMetrics } from '../core/metrics';
import type { RegionMetrics } from '../core/region-stats';

defineProps<{
  pose: string;
  durationFrames: number;
  poseNote?: string;
  playing: boolean;
  metrics: FrameMetrics | null;
  history: FrameMetrics[];
  regionStats: RegionMetrics[];
  selectedRegion: number | null;
  hoverRegion: number | null;
}>();

const emit = defineEmits<{ 'select-region': [index: number] }>();
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
        />
      </section>

      <div class="divider" role="separator" />

      <section class="sec">
        <h4 class="sec-title">压力指标</h4>
        <MetricCards :metrics="metrics" :history="history" />
        <p class="footnote">读数与热力图均为扣除空载后的净压力</p>
      </section>

      <div class="divider" role="separator" />

      <section class="sec">
        <h4 class="sec-title">
          部位受力
          <span class="sec-sub">按平均净压排序</span>
        </h4>
        <RegionRanking
          :stats="regionStats"
          :selected="selectedRegion"
          :hovered="hoverRegion"
          @select="emit('select-region', $event)"
        />
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
  gap: 15px;
  padding: 16px 16px 18px;
  overflow-y: auto;
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
.sec-sub {
  font-weight: 400;
  letter-spacing: 0;
  color: var(--text-3);
  opacity: 0.85;
}
.divider {
  height: 1px;
  background: var(--border-subtle);
  flex: none;
}
.footnote {
  margin-top: 10px;
  font-size: 10.5px;
  color: var(--text-3);
  line-height: 1.5;
}
</style>
