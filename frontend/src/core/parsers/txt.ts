import { CELLS, COLS, ROWS } from '../types.ts';

export interface TxtFrames {
  /** 解析出的所有帧（每帧 1056 个值，行优先） */
  frames: Float32Array[];
  /**
   * 动态文件中每帧后的 0/1/2 标签行（静态文件为空数组）。
   * 官方说明："标签行忽视即可"——保留解析但默认不使用。
   */
  labels: number[];
}

/**
 * 解析压力 txt 文件。
 * 格式（飞书说明，已实测）：
 * - 每帧 = 44 行 × 24 个逗号分隔值；
 * - 帧间通常以 1 行空行分隔（静态动作文件），但个别文件存在缺分隔空行
 *   （两帧首尾相连）的情况，因此本解析器按"攒满 44 行即成帧"实现，不依赖空行；
 * - 动态文件（xxx_动态一/二.txt）的帧间隔为「空行 + 0/1/2 标签行 + 空行」；
 * - 空载文件（xxx_空载.txt）同静态格式。
 */
export function parseTxt(text: string): TxtFrames {
  const lines = text.split(/\r?\n/);
  const frames: Float32Array[] = [];
  const labels: number[] = [];
  let block: string[] = [];

  const flush = () => {
    const vals = new Float32Array(CELLS);
    let k = 0;
    for (const row of block) {
      const toks = row.split(',');
      if (toks.length !== COLS) {
        throw new Error(`帧内行值数应为 ${COLS}，实际 ${toks.length}`);
      }
      for (let c = 0; c < COLS; c++) {
        const v = Number(toks[c]);
        if (Number.isNaN(v)) throw new Error(`非数字压力值：${toks[c]}`);
        vals[k++] = v;
      }
    }
    frames.push(vals);
    block = [];
  };

  for (const line of lines) {
    const t = line.trim();
    if (t === '') continue; // 分隔空行：跳过（不依赖它判帧）
    const toks = t.split(',');
    if (toks.length === 1) {
      // 单值行 = 动态文件的睡姿标签行（0/1/2），位于两帧之间，忽视
      labels.push(Number(toks[0]));
      continue;
    }
    block.push(t);
    if (block.length === ROWS) flush();
  }
  if (block.length > 0) {
    throw new Error(`文件末尾存在不完整帧（${block.length}/${ROWS} 行）`);
  }

  return { frames, labels };
}
