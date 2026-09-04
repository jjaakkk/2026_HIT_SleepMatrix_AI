import { CELLS, COLS, type BodyRegion } from './types.ts';

/** 六部位主题色（v2 商业级配色：无紫色，区分度与热力图 turbo 色带协调） */
export const REGION_COLORS: Record<string, string> = {
  肩部: '#FF9F43',
  背部: '#F2C14E',
  腰部: '#4DD6E8',
  臀部: '#FF6B81',
  大腿部: '#7FB2F0',
  小腿部: '#6FE3C0',
};

export interface RegionMetrics {
  index: number;
  name: string;
  color: string;
  /** 区域平均净压力（有效接触点） */
  meanNet: number;
  /** 区域最大净压力 */
  maxNet: number;
  /** 区域有效接触点数 */
  activePoints: number;
  /** 区域净压力总和 */
  sumNet: number;
}

/** 单区域指标（扣背景后，阈值同上） */
export function regionMetrics(
  frame: ArrayLike<number>,
  bg: ArrayLike<number> | null,
  region: BodyRegion,
  threshold = 20,
): RegionMetrics {
  const { x1, y1, x2, y2 } = region;
  let sum = 0;
  let max = 0;
  let active = 0;
  for (let r = y1; r <= y2; r++) {
    for (let c = x1; c <= x2; c++) {
      const i = r * COLS + c;
      if (i < 0 || i >= CELLS) continue;
      const v = frame[i];
      const net = bg ? v - bg[i] : v;
      if (net > threshold) {
        active++;
        sum += net;
        if (net > max) max = net;
      }
    }
  }
  return {
    index: -1,
    name: region.name,
    color: REGION_COLORS[region.name] ?? '#8b949e',
    meanNet: active > 0 ? sum / active : 0,
    maxNet: max,
    activePoints: active,
    sumNet: sum,
  };
}

/** 全部区域指标，按平均净压力降序（"当前哪个部位受力最大"） */
export function regionStatsAll(
  frame: ArrayLike<number>,
  bg: ArrayLike<number> | null,
  regions: BodyRegion[],
  threshold = 20,
): RegionMetrics[] {
  return regions
    .filter((r) => r.valid)
    .map((r, index) => ({ ...regionMetrics(frame, bg, r, threshold), index }))
    .sort((a, b) => b.meanNet - a.meanNet);
}
