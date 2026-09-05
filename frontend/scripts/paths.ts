import fs from 'node:fs';
import path from 'node:path';

/** 数据集根目录（睡姿 区域划分data/睡姿 区域划分data）。 */
const DATA_CANDIDATES = [
  '../睡姿 区域划分data/睡姿 区域划分data', // 仓库根执行
  '../../睡姿 区域划分data/睡姿 区域划分data', // frontend/ 目录执行
];

/**
 * 解析数据集根目录：
 * 优先 SLEEP_DATA_ROOT 环境变量；否则按候选相对路径逐一探测（适配
 * 从仓库根或 frontend/ 子目录启动），取第一个存在的目录。
 */
export function dataRoot(): string {
  if (process.env.SLEEP_DATA_ROOT) return process.env.SLEEP_DATA_ROOT;
  for (const c of DATA_CANDIDATES) {
    const p = path.resolve(process.cwd(), c);
    if (fs.existsSync(p)) return p;
  }
  return path.resolve(process.cwd(), DATA_CANDIDATES[0]);
}
