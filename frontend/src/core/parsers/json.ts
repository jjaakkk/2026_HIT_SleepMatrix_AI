import { CELLS, type FrameRecord } from '../types.ts';

/**
 * 解析新版 data.json（76MB，数组形式）。
 * 每个 (people, action, frame) 键有 2 份记录：
 * 副本 A（先出现）= 原始帧；副本 B = 左右镜像增强帧（列 c → 23-c）。
 * 两份的 region 都是人工标注（镜像帧的标注不是坐标镜像），可直接使用。
 */
export function parseDatasetJson(text: string): FrameRecord[] {
  const raw: unknown[] = JSON.parse(text);
  const seen = new Set<string>();
  const records: FrameRecord[] = raw.map((item, index) => {
    const r = item as Record<string, unknown>;
    const key = `${r.people}|${r.action}|${r.frame}`;
    const isMirrored = seen.has(key);
    seen.add(key);
    const data = (r.data as string).split(',').map(Number);
    if (data.length !== CELLS) {
      throw new Error(`data 应为 ${CELLS} 个值，实际 ${data.length}（记录 #${index}）`);
    }
    return {
      index,
      people: r.people as number,
      peopleName: r.people_name as string,
      action: r.action as number,
      frame: r.frame as number,
      sleepPos: r.sleep_pos as FrameRecord['sleepPos'],
      data: Float32Array.from(data),
      region: r.region as string,
      spine: r.spine as string,
      isMirrored,
    };
  });
  return records;
}

/**
 * 生成回放序列：
 * 默认只回放原始帧（按 frame 升序）；includeMirrored=true 时，原始帧播完后再播镜像帧。
 * 镜像帧是数据增强产物、非时间延续，回放时界面需标注"镜像增强帧"。
 */
export function buildPlaybackList(
  records: FrameRecord[],
  includeMirrored = false,
): FrameRecord[] {
  const originals = records.filter((r) => !r.isMirrored).sort((a, b) => a.frame - b.frame);
  if (!includeMirrored) return originals;
  const mirrored = records.filter((r) => r.isMirrored).sort((a, b) => a.frame - b.frame);
  return [...originals, ...mirrored];
}
