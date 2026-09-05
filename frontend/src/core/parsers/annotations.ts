import { COLS, ROWS, type BodyRegion, type SpinePoint } from '../types.ts';

export const REGION_NAMES = ['肩部', '背部', '腰部', '臀部', '大腿部', '小腿部'] as const;

/**
 * 解析 region 字符串。
 * 格式（实测）："x1 x2 ... x12 y1 y2 ... y12"（24 个 token，先 12 个 x 再 12 个 y）。
 * 第 i 个部位（i=0..5）：左上角 (x[2i], y[2i])，右下角 (x[2i+1], y[2i+1])。
 * 坐标含义：x = 列（0-23），y = 行（0-43，行 0 = 头端）。
 * 注：部分 y2 标注为 44（排他边界），渲染时统一 clamp 到 [0, ROWS-1]。
 * 小腿部仅 SAI/dgs/gzy 三人有标注，其余为 na（valid=false，按飞书说明不使用）。
 */
export function parseRegion(str: string): BodyRegion[] {
  const tokens = str.split(' ').map((t) => (t === 'na' ? NaN : Number(t)));
  if (tokens.length !== 24) {
    throw new Error(`region 应为 24 个 token，实际 ${tokens.length}：${str.slice(0, 80)}`);
  }
  const xs = tokens.slice(0, 12);
  const ys = tokens.slice(12);
  return REGION_NAMES.map((name, i) => {
    const x1 = xs[2 * i];
    const y1 = ys[2 * i];
    const x2 = xs[2 * i + 1];
    const y2 = ys[2 * i + 1];
    const valid = [x1, y1, x2, y2].every(Number.isFinite);
    return {
      name,
      x1,
      y1,
      x2: Math.min(x2, COLS - 1),
      y2: Math.min(y2, ROWS - 1),
      valid,
    };
  });
}

/**
 * 解析 spine 字符串。
 * 格式（docx 原文）："x1 x2 x3 x4 x5 y1 y2 y3 y4 y5"（先 5 个 x 再 5 个 y）。
 * 5 个点 (x_i, y_i)，x=列，y=行。仅前 3 人（SAI/dgs/gzy）有标注，其余为 na。
 * @returns 无标注时返回 null
 */
export function parseSpine(str: string): SpinePoint[] | null {
  if (str.includes('na')) return null;
  const tokens = str.split(' ').map(Number);
  if (tokens.length !== 10 || tokens.some(Number.isNaN)) {
    throw new Error(`spine 应为 10 个数字，实际：${str.slice(0, 60)}`);
  }
  return tokens.slice(0, 5).map((x, i) => ({ x, y: tokens[5 + i] }));
}
