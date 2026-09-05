import { CELLS, COLS, ROWS } from './types.ts';

/**
 * 水平镜像一帧（列 c → 23-c）。
 * 用于：验证镜像增强帧、以及渲染左/右翻转（如无必要不调用）。
 */
export function mirrorFrame(src: ArrayLike<number>): Float32Array {
  const out = new Float32Array(CELLS);
  for (let r = 0; r < ROWS; r++) {
    const base = r * COLS;
    for (let c = 0; c < COLS; c++) {
      out[base + c] = src[base + (COLS - 1 - c)];
    }
  }
  return out;
}

/**
 * 空载均值帧：对同一人的空载多帧逐点求平均（背景压力基准）。
 * 实测空载单点最大可达 42、均值约 4-5，接触类指标必须先扣背景。
 */
export function meanBackground(frames: ArrayLike<number>[]): Float32Array {
  if (frames.length === 0) throw new Error('空载帧不能为空');
  const acc = new Float64Array(CELLS);
  for (const f of frames) {
    for (let i = 0; i < CELLS; i++) acc[i] += f[i];
  }
  const out = new Float32Array(CELLS);
  for (let i = 0; i < CELLS; i++) out[i] = acc[i] / frames.length;
  return out;
}

export interface FrameMetrics {
  /** 原始最大压力（未扣背景） */
  maxRaw: number;
  /** 扣背景后最大净压力 */
  maxNet: number;
  /** 有效接触点净压力总和 */
  sumNet: number;
  /** 有效接触点数（净压力 > 阈值） */
  activePoints: number;
  /** 接触面积占比 = activePoints / 1056 */
  contactRatio: number;
  /** 有效接触点平均净压力 */
  meanNet: number;
}

/**
 * 单帧压力指标。
 * @param frame 当前帧
 * @param bg 该人空载均值帧（不传则视为无背景扣除）
 * @param threshold 有效接触阈值（净压力 > 阈值算接触；建议 20，基于空载实测提出，可调）
 */
export function computeMetrics(
  frame: ArrayLike<number>,
  bg?: ArrayLike<number> | null,
  threshold = 20,
): FrameMetrics {
  let maxRaw = 0;
  let maxNet = 0;
  let sumNet = 0;
  let active = 0;
  for (let i = 0; i < CELLS; i++) {
    const v = frame[i];
    if (v > maxRaw) maxRaw = v;
    const net = bg ? v - bg[i] : v;
    if (net > threshold) {
      active++;
      sumNet += net;
      if (net > maxNet) maxNet = net;
    }
  }
  return {
    maxRaw,
    maxNet,
    sumNet,
    activePoints: active,
    contactRatio: active / CELLS,
    meanNet: active > 0 ? sumNet / active : 0,
  };
}

/**
 * 候选"接触面指数"（资料无官方定义，需项目组确认）：
 * 接触面指数 = 接触面积占比 × 100，即有效接触点数占 1056 的百分比。
 */
export function contactIndex(metrics: FrameMetrics): number {
  return metrics.contactRatio * 100;
}

/**
 * 逐帧指标历史（用于指标卡 sparkline 与时间曲线）。
 * 帧序 = 回放顺序；对同一数据源一次性计算并缓存。
 */
export function metricsHistory(
  frames: ReadonlyArray<ArrayLike<number>>,
  bg: ArrayLike<number> | null,
  threshold = 20,
): FrameMetrics[] {
  return frames.map((f) => computeMetrics(f, bg, threshold));
}

/**
 * 在床/离床判定（自研启发式，无官方定义）：
 * 扣背景后有效接触点数 < limit 视为"离床/无人"。
 * limit 建议 50（约 1056 的 5%，基于空载实测：空载扣背景后有效点 ≈ 0）。
 */
export function isBedOccupied(metrics: FrameMetrics, limit = 50): boolean {
  return metrics.activePoints >= limit;
}

/**
 * 状态持续时长：从 idx 向前数，连续相同状态（按 poseKey）的帧数。
 * 用于睡姿卡显示"持续 N 帧 / M 秒"。
 */
export function poseDuration(poseKeys: ReadonlyArray<unknown>, idx: number): number {
  if (idx < 0 || idx >= poseKeys.length) return 0;
  const key = poseKeys[idx];
  let n = 1;
  for (let i = idx - 1; i >= 0 && poseKeys[i] === key; i--) n++;
  return n;
}
