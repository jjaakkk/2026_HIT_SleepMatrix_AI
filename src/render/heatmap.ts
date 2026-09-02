import { COLS, ROWS } from '../core/types.ts';
import { TURBO } from './turbo.ts';

export type HeatmapMode = 'smooth' | 'weak' | 'grid';
export type ScaleMode = 'fixed250' | 'auto' | 'fixed500';

export interface HeatmapOptions {
  mode: HeatmapMode;
  scale: ScaleMode;
  /** 画布宽度（像素） */
  width: number;
  /** 画布高度（像素） */
  height: number;
}

/** 压扩指数：标准 0.6，弱力增强 0.35（放大躯干弱压力区域，呼应弱力组课题） */
export const GAMMA: Record<HeatmapMode, number> = {
  smooth: 0.6,
  weak: 0.35,
  grid: 1.0,
};

/** 固定量程档位 */
export const FIXED_MAX: Record<Exclude<ScaleMode, 'auto'>, number> = {
  fixed250: 250,
  fixed500: 500,
};

/**
 * 双线性采样：在"格心坐标系"下取值。
 * fx ∈ [-0.5, COLS-0.5]，fy ∈ [-0.5, ROWS-0.5]，边界外 clamp 到边缘格。
 * 格心处（fx=整数）应精确返回该格原始值。
 */
export function bilinearSample(frame: ArrayLike<number>, fx: number, fy: number): number {
  const x0 = Math.floor(fx);
  const y0 = Math.floor(fy);
  const tx = fx - x0;
  const ty = fy - y0;
  const cx = (c: number) => Math.min(Math.max(c, 0), COLS - 1);
  const cy = (r: number) => Math.min(Math.max(r, 0), ROWS - 1);
  const x0c = cx(x0);
  const x1c = cx(x0 + 1);
  const y0c = cy(y0);
  const y1c = cy(y0 + 1);
  const v00 = frame[y0c * COLS + x0c];
  const v10 = frame[y0c * COLS + x1c];
  const v01 = frame[y1c * COLS + x0c];
  const v11 = frame[y1c * COLS + x1c];
  const top = v00 + (v10 - v00) * tx;
  const bottom = v01 + (v11 - v01) * tx;
  return top + (bottom - top) * ty;
}

/** turbo 色带取值（t ∈ [0,1]，线性插值相邻 LUT 项） */
export function turboColor(t: number): [number, number, number] {
  const idx = Math.min(Math.max(t, 0), 1) * 255;
  const i = Math.min(Math.floor(idx), 254);
  const f = idx - i;
  const a = TURBO[i];
  const b = TURBO[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** 归一化 + 压扩后映射颜色 */
export function valueToColor(v: number, scaleMax: number, gamma: number): [number, number, number] {
  const t = Math.min(Math.max(v / scaleMax, 0), 1);
  return turboColor(Math.pow(t, gamma));
}

/**
 * 将 44×24 压力帧渲染到画布（行 0 = 头端在上）。
 * - smooth/weak：双线性插值平滑热力图（压扩指数见 GAMMA）；
 * - grid：原始 44×24 格子直显（不插值）+ 细网格线（对应 matplotlib ax.grid）；
 * - 床垫外区域保持透明（不填充背景）。
 * @returns 当前帧实际最大值与生效量程
 */
export function renderHeatmap(
  ctx: CanvasRenderingContext2D,
  frame: ArrayLike<number>,
  opts: HeatmapOptions,
): { frameMax: number; scaleMax: number } {
  const { mode, scale, width, height } = opts;
  const frameMax = computeFrameMax(frame);
  const scaleMax = scale === 'auto' ? Math.max(frameMax, 1) : FIXED_MAX[scale];
  const gamma = GAMMA[mode];

  ctx.clearRect(0, 0, width, height);

  if (mode === 'grid') {
    const cw = width / COLS;
    const ch = height / ROWS;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const [rr, gg, bb] = valueToColor(frame[r * COLS + c], scaleMax, gamma);
        ctx.fillStyle = `rgb(${Math.round(rr * 255)},${Math.round(gg * 255)},${Math.round(bb * 255)})`;
        ctx.fillRect(c * cw, r * ch, cw + 0.5, ch + 0.5);
      }
    }
    // 网格线（alpha 0.3，同官方绘图示例）
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let c = 1; c < COLS; c++) {
      ctx.moveTo(c * cw, 0);
      ctx.lineTo(c * cw, height);
    }
    for (let r = 1; r < ROWS; r++) {
      ctx.moveTo(0, r * ch);
      ctx.lineTo(width, r * ch);
    }
    ctx.stroke();
    return { frameMax, scaleMax };
  }

  // 平滑模式：逐像素双线性 + ImageData
  const img = ctx.createImageData(width, height);
  const data = img.data;
  const sx = COLS / width;
  const sy = ROWS / height;
  for (let py = 0; py < height; py++) {
    const fy = (py + 0.5) * sy - 0.5;
    const y0 = Math.floor(fy);
    const ty = fy - y0;
    const cy = (r: number) => Math.min(Math.max(r, 0), ROWS - 1);
    const y0c = cy(y0);
    const y1c = cy(y0 + 1);
    const rowBase = py * width * 4;
    for (let px = 0; px < width; px++) {
      const fx = (px + 0.5) * sx - 0.5;
      const x0 = Math.floor(fx);
      const tx = fx - x0;
      const cx = (c: number) => Math.min(Math.max(c, 0), COLS - 1);
      const x0c = cx(x0);
      const x1c = cx(x0 + 1);
      const v00 = frame[y0c * COLS + x0c];
      const v10 = frame[y0c * COLS + x1c];
      const v01 = frame[y1c * COLS + x0c];
      const v11 = frame[y1c * COLS + x1c];
      const top = v00 + (v10 - v00) * tx;
      const bottom = v01 + (v11 - v01) * tx;
      const v = top + (bottom - top) * ty;
      const t = Math.min(Math.max(v / scaleMax, 0), 1);
      const g = Math.pow(t, gamma);
      const [rr, gg, bb] = turboColor(g);
      const o = rowBase + px * 4;
      data[o] = rr * 255;
      data[o + 1] = gg * 255;
      data[o + 2] = bb * 255;
      data[o + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { frameMax, scaleMax };
}

/** 帧内最大压力值 */
export function computeFrameMax(frame: ArrayLike<number>): number {
  let m = 0;
  for (let i = 0; i < frame.length; i++) if (frame[i] > m) m = frame[i];
  return m;
}

/** 画布像素坐标 → 最近的传感器格（用于悬浮读数） */
export function pickCell(
  px: number,
  py: number,
  width: number,
  height: number,
  frame: ArrayLike<number>,
): { row: number; col: number; value: number } {
  const col = Math.min(Math.max(Math.floor((px / width) * COLS), 0), COLS - 1);
  const row = Math.min(Math.max(Math.floor((py / height) * ROWS), 0), ROWS - 1);
  return { row, col, value: frame[row * COLS + col] };
}
