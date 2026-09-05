/**
 * 内置模拟数据生成器：无需任何外部数据集即可运行与自检可视化。
 *
 * 用途：
 * 1. demo.json（真实数据子集）加载失败时的兜底数据源；
 * 2. 左栏"数据源 → 内置模拟"手动切换，便于无数据集环境演示/检查渲染质量。
 *
 * 原则：模拟数据在界面上必须明示（状态徽标 + 数据源面板），
 * 且其结构（44×24、region/spine 编码、镜像帧不参与）与真实数据完全一致，
 * 走同一套解析/指标/渲染管线。
 *
 * 人体模板由多个椭圆压力团叠加（头/肩/躯干/臀/腿）+ 背景噪声 + 逐帧抖动，
 * 压力量级参考真实数据（仰卧峰值 ~280，侧卧峰值 ~350-450，空载 < 60）。
 */
import { CELLS, COLS, ROWS } from './types.ts';

/** 可复现随机数（mulberry32） */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Blob {
  /** 行（0-43，头端在上） */
  r: number;
  /** 列（0-23） */
  c: number;
  /** 椭圆半径（行方向 / 列方向） */
  rr: number;
  rc: number;
  /** 峰值权重 */
  w: number;
}

// 仰卧：对称身体（头/肩/躯干/臀/双大腿/双小腿）
const SUPINE: Blob[] = [
  { r: 2.5, c: 12, rr: 2.2, rc: 3, w: 110 },
  { r: 6, c: 12, rr: 2.4, rc: 8.5, w: 150 },
  { r: 14, c: 12, rr: 6, rc: 6.8, w: 175 },
  { r: 22, c: 12, rr: 5, rc: 7.8, w: 235 },
  { r: 31, c: 9.5, rr: 6, rc: 2.9, w: 135 },
  { r: 31, c: 14.5, rr: 6, rc: 2.9, w: 135 },
  { r: 38.5, c: 9.5, rr: 4, rc: 2.2, w: 85 },
  { r: 38.5, c: 14.5, rr: 4, rc: 2.2, w: 85 },
];

// 俯卧：肩胸更宽、臀略降（颜色标签区分，几何略异）
const PRONE: Blob[] = [
  { r: 2.5, c: 12, rr: 2.2, rc: 3, w: 105 },
  { r: 6.5, c: 12, rr: 2.6, rc: 9, w: 165 },
  { r: 14, c: 12, rr: 6.2, rc: 7.2, w: 190 },
  { r: 22, c: 12, rr: 5, rc: 7.4, w: 215 },
  { r: 31, c: 9.5, rr: 6, rc: 2.9, w: 130 },
  { r: 31, c: 14.5, rr: 6, rc: 2.9, w: 130 },
  { r: 38.5, c: 9.5, rr: 4, rc: 2.2, w: 80 },
  { r: 38.5, c: 14.5, rr: 4, rc: 2.2, w: 80 },
];

// 左侧卧：窄长身体偏左、峰值更高（与真实侧卧特征一致）
const SIDE_LEFT: Blob[] = [
  { r: 2.5, c: 7, rr: 2, rc: 2.6, w: 120 },
  { r: 8, c: 7, rr: 3, rc: 3.2, w: 190 },
  { r: 15, c: 7.2, rr: 6.5, rc: 3.4, w: 260 },
  { r: 22, c: 7.5, rr: 4.5, rc: 3.8, w: 330 },
  { r: 30, c: 8, rr: 7, rc: 2.6, w: 200 },
  { r: 38, c: 8, rr: 4.5, rc: 2, w: 110 },
];

const SIDE_RIGHT: Blob[] = SIDE_LEFT.map((b) => ({ ...b, c: COLS - 1 - b.c }));

/** 背景压力（空载），单点 0-8 量级 */
function baseBg(rng: () => number): Float32Array {
  const bg = new Float32Array(CELLS);
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      // 中部略高 + 噪声
      const mid = Math.exp(-((c - 11.5) * (c - 11.5)) / 200) * 3;
      bg[r * COLS + c] = mid + rng() * 4;
    }
  }
  return bg;
}

function renderBlobs(blobs: Blob[], bg: Float32Array, rng: () => number): Float32Array {
  const out = new Float32Array(CELLS);
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      let v = 0;
      for (const b of blobs) {
        const dx = (c - b.c) / b.rc;
        const dy = (r - b.r) / b.rr;
        v += b.w * Math.exp(-0.5 * (dx * dx + dy * dy));
      }
      v += rng() * 7; // 逐帧抖动
      out[r * COLS + c] = v + bg[r * COLS + c];
    }
  }
  return out;
}

/** 区域标注（沿用真实数据的编码与量级；侧卧用真实 SAI 标注串） */
const REGION_SUPINE = '6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44';
const REGION_SIDE_L = '7 16 9 18 8 20 9 20 2 16 2 13 2 7 7 12 12 17 17 26 24 31 31 44';
const REGION_SIDE_R = '8 17 6 15 4 16 4 15 8 22 11 22 2 7 7 12 12 17 17 26 24 31 31 44';
const SPINE_SUPINE = '12 12 12 12 12 3 6 11 15 19';
const SPINE_SIDE = '9 12 14 16 16 3 6 10 15 19';

export interface SimulatedAction {
  action: number;
  sleepPos: number;
  region: string;
  spine: string;
  frames: number[][];
}

export interface SimulatedPerson {
  name: string;
  height: number | null;
  weight: number | null;
  bg: number[];
  actions: SimulatedAction[];
}

export interface SimulatedDataset {
  meta: { matrix: string; note: string };
  people: SimulatedPerson[];
  dynamic: { person: string; bg: number[]; frames: number[][]; labels: number[] };
}

/**
 * 生成内置模拟数据集（确定性：同 seed 同结果）。
 * 结构对齐 public/data/demo.json 的真实子集结构。
 */
export function generateSimulatedDataset(seed = 20260831): SimulatedDataset {
  const rng = mulberry32(seed);
  const bg = baseBg(rng);

  const framesOf = (blobs: Blob[], count: number): number[][] => {
    const out: number[][] = [];
    for (let i = 0; i < count; i++) {
      out.push(Array.from(renderBlobs(blobs, bg, rng)));
    }
    return out;
  };

  const actions: SimulatedAction[] = [
    { action: 0, sleepPos: -1, region: '', spine: '', frames: framesOf([], 15) }, // 空载
    { action: 1, sleepPos: 0, region: REGION_SUPINE, spine: SPINE_SUPINE, frames: framesOf(SUPINE, 15) },
    { action: 7, sleepPos: 1, region: REGION_SUPINE, spine: SPINE_SUPINE, frames: framesOf(PRONE, 30) },
    { action: 10, sleepPos: 2, region: REGION_SIDE_L, spine: SPINE_SIDE, frames: framesOf(SIDE_LEFT, 15) },
    { action: 16, sleepPos: 3, region: REGION_SIDE_R, spine: SPINE_SIDE, frames: framesOf(SIDE_RIGHT, 15) },
  ];

  // 动态序列：仰卧→左侧卧→仰卧→俯卧→仰卧（与真实动态文件同风格）
  const segs: [Blob[], number][] = [
    [SUPINE, 15],
    [SIDE_LEFT, 15],
    [SUPINE, 15],
    [PRONE, 15],
    [SUPINE, 20],
  ];
  const dynFrames: number[][] = [];
  const dynLabels: number[] = [];
  const labelOf: [number, number][] = [
    [0, 15],
    [2, 15],
    [0, 15],
    [1, 15],
    [0, 20],
  ];
  for (let s = 0; s < segs.length; s++) {
    const frames = framesOf(segs[s][0], segs[s][1]);
    dynFrames.push(...frames);
    dynLabels.push(...Array(segs[s][1]).fill(labelOf[s][0]));
  }

  return {
    meta: { matrix: '44x24', note: '内置模拟数据（演示/自检用，非真实采集）' },
    people: [
      {
        name: 'SIM-01',
        height: 175,
        weight: 70,
        bg: Array.from(bg),
        actions,
      },
    ],
    dynamic: { person: 'SIM-01', bg: Array.from(bg), frames: dynFrames, labels: dynLabels },
  };
}
