/**
 * 图表刻度计算：生成"好看"的坐标轴刻度（1/2/5 × 10^k 步进）。
 * 纯函数，便于单元测试。
 */
export interface Ticks {
  min: number;
  max: number;
  step: number;
  ticks: number[];
}

export function niceTicks(dataMin: number, dataMax: number, targetCount = 5): Ticks {
  if (dataMin === dataMax) {
    // 平坦数据：构造一个范围
    const v = Math.abs(dataMax) < 1e-9 ? 1 : dataMax;
    const step = v === 1 ? 1 : niceStep(Math.abs(v) / targetCount);
    return build(dataMin - step * 2, dataMax + step * 2, step);
  }
  const rawStep = (dataMax - dataMin) / Math.max(targetCount, 1);
  const step = niceStep(rawStep);
  return build(dataMin, dataMax, step);
}

function niceStep(raw: number): number {
  const pow = Math.floor(Math.log10(raw));
  const base = Math.pow(10, pow);
  const frac = raw / base;
  const niceFrac = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
  return niceFrac * base;
}

function build(dataMin: number, dataMax: number, step: number): Ticks {
  const min = Math.floor(dataMin / step) * step;
  const max = Math.ceil(dataMax / step) * step;
  const ticks: number[] = [];
  for (let t = min; t <= max + step * 0.001; t += step) {
    ticks.push(Number(t.toFixed(6)));
  }
  return { min, max, step, ticks };
}
