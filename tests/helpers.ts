import fs from 'node:fs';
import path from 'node:path';

/** 仓库根目录（npm test 从仓库根执行） */
export const REPO_ROOT = process.cwd();

/**
 * 数据集根目录：
 * 默认 = 仓库上一级的「睡姿 区域划分data/睡姿 区域划分data」，
 * 也可通过环境变量 SLEEP_DATA_ROOT 覆盖。
 */
export function dataRoot(): string {
  return (
    process.env.SLEEP_DATA_ROOT ??
    path.resolve(REPO_ROOT, '../睡姿 区域划分data/睡姿 区域划分data')
  );
}

export function loadText(relative: string): string {
  return fs.readFileSync(path.join(dataRoot(), relative), 'utf8');
}
