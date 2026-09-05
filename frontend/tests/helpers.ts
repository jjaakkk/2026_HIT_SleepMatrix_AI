import fs from 'node:fs';
import path from 'node:path';
import { dataRoot } from '../scripts/paths.ts';

/** 仓库根目录（npm test 从仓库根或 frontend/ 执行） */
export const REPO_ROOT = process.cwd();

/** 数据集根目录（见 scripts/paths.ts：环境变量 + 多级候选探测） */
export function dataRootPath(): string {
  return dataRoot();
}

export function loadText(relative: string): string {
  return fs.readFileSync(path.join(dataRootPath(), relative), 'utf8');
}
