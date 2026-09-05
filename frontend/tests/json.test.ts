import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseDatasetJson, buildPlaybackList } from '../src/core/parsers/json.ts';
import { parseRegion, parseSpine } from '../src/core/parsers/annotations.ts';
import { actionToSleepPos } from '../src/core/types.ts';
import { mirrorFrame } from '../src/core/metrics.ts';
import { loadText } from './helpers.ts';

// 76MB 全量解析（约数秒），只解析一次供全部用例使用
const records = parseDatasetJson(loadText('区域划分/data.json'));

test('规模：14400 条记录，20 人，字段完整', () => {
  assert.equal(records.length, 14400);
  const people = new Set(records.map((r) => r.peopleName));
  assert.equal(people.size, 20);
  for (const r of records) {
    assert.equal(r.data.length, 1056);
    assert.equal(typeof r.region, 'string');
    assert.equal(typeof r.spine, 'string');
  }
});

test('每个 (people,action,frame) 键恰有 2 份记录（原始 + 镜像）', () => {
  const count = new Map<string, number>();
  for (const r of records) {
    const k = `${r.people}|${r.action}|${r.frame}`;
    count.set(k, (count.get(k) ?? 0) + 1);
  }
  const keys = count.size;
  const dups = [...count.values()].filter((c) => c === 2).length;
  assert.equal(keys, 7200);
  // 已知有 2 个键出现 3 次、2 个键出现 1 次（数据本身的不规则）
  assert.ok(dups >= 7196, `2 份记录的键应 ≥7196，实际 ${dups}`);
});

test('副本 B = 副本 A 的左右镜像（已与飞书增强规则互证）', () => {
  const key = (p: number, a: number, f: number) =>
    records.filter((r) => r.people === p && r.action === a && r.frame === f);
  const [a, b] = key(0, 1, 0);
  assert.equal(a.isMirrored, false);
  assert.equal(b.isMirrored, true);
  assert.deepEqual(Array.from(b.data), Array.from(mirrorFrame(a.data)));
});

test('action→sleep_pos 映射全量核验（1-6仰卧 7-9俯卧 10-15左 16-21右）', () => {
  for (const r of records) {
    assert.equal(actionToSleepPos(r.action), r.sleepPos);
  }
});

test('回放列表：默认仅原始帧（按帧号升序），镜像帧可选', () => {
  const act1 = records.filter((r) => r.people === 0 && r.action === 1);
  const list = buildPlaybackList(act1);
  assert.equal(list.length, 15);
  assert.deepEqual(list.map((r) => r.frame), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]);
  assert.ok(list.every((r) => !r.isMirrored));
  const withMirror = buildPlaybackList(act1, true);
  assert.equal(withMirror.length, 30);
  assert.ok(withMirror.slice(15).every((r) => r.isMirrored));
});

test('region 解析：SAI 仰卧 6 区域坐标（x=列, y=行）', () => {
  const r = records.find((x) => x.people === 0 && x.action === 1 && x.frame === 0 && !x.isMirrored)!;
  const regions = parseRegion(r.region);
  assert.equal(regions.length, 6);
  assert.deepEqual(regions.map((g) => g.name), ['肩部', '背部', '腰部', '臀部', '大腿部', '小腿部']);
  const [shoulder, , , hip] = regions;
  assert.deepEqual([shoulder.x1, shoulder.y1, shoulder.x2, shoulder.y2], [6, 3, 18, 8]);
  assert.deepEqual([hip.x1, hip.y1, hip.x2, hip.y2], [5, 18, 20, 27]);
  // y2=44 排他边界 → clamp 到 43
  assert.equal(regions[5].y2, 43);
  assert.ok(regions.every((g) => g.valid));
});

test('region 解析：小腿部仅前 3 人标注（其余 na → valid=false）', () => {
  const hpy = records.find((r) => r.peopleName === 'hpy' && !r.isMirrored)!;
  const regions = parseRegion(hpy.region);
  assert.equal(regions[5].valid, false);
  assert.ok(regions.slice(0, 5).every((g) => g.valid));
});

test('spine 解析：SAI 5 点在中线（列12），17 人无标注返回 null', () => {
  const sai = records.find((r) => r.people === 0 && !r.isMirrored)!;
  const pts = parseSpine(sai.spine)!;
  assert.equal(pts.length, 5);
  assert.deepEqual(pts.map((p) => [p.x, p.y]), [[12, 3], [12, 6], [12, 11], [12, 15], [12, 19]]);
  const hpy = records.find((r) => r.peopleName === 'hpy' && !r.isMirrored)!;
  assert.equal(parseSpine(hpy.spine), null);
});
