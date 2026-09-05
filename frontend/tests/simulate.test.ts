import { test } from 'node:test';
import assert from 'node:assert/strict';
import { generateSimulatedDataset } from '../src/core/simulate.ts';
import { parseRegion, parseSpine } from '../src/core/parsers/annotations.ts';
import { computeMetrics, isBedOccupied } from '../src/core/metrics.ts';

test('确定性：同 seed 生成结果一致', () => {
  const a = generateSimulatedDataset(42);
  const b = generateSimulatedDataset(42);
  assert.deepEqual(a.people[0].actions[1].frames[0], b.people[0].actions[1].frames[0]);
  const c = generateSimulatedDataset(43);
  assert.notDeepEqual(a.people[0].actions[1].frames[0], c.people[0].actions[1].frames[0]);
});

test('结构完整：帧数/维度与真实数据一致', () => {
  const ds = generateSimulatedDataset();
  const p = ds.people[0];
  assert.equal(p.actions.length, 5);
  assert.equal(p.actions[0].frames.length, 15); // 空载
  assert.equal(p.actions[1].frames.length, 15); // 仰卧
  assert.equal(p.actions[2].frames.length, 30); // 俯卧
  for (const f of p.actions[1].frames) assert.equal(f.length, 1056);
  assert.equal(ds.dynamic.frames.length, 80);
  assert.equal(ds.dynamic.labels.length, 80);
});

test('量级合理：仰卧峰值 ~280，侧卧峰值更高且接触更窄，空载为背景', () => {
  const ds = generateSimulatedDataset();
  const p = ds.people[0];
  const bg = p.bg;
  const supine = computeMetrics(p.actions[1].frames[5], bg, 20);
  const sideL = computeMetrics(p.actions[3].frames[5], bg, 20);
  const empty = computeMetrics(p.actions[0].frames[5], bg, 20);
  assert.ok(supine.maxRaw > 200 && supine.maxRaw < 380, `仰卧峰值 ${supine.maxRaw}`);
  assert.ok(sideL.maxRaw > supine.maxRaw, '侧卧峰值应高于仰卧');
  assert.ok(sideL.activePoints < supine.activePoints, '侧卧接触点应少于仰卧（更窄）');
  assert.equal(isBedOccupied(empty, 50), false); // 空载 → 离床
  assert.equal(isBedOccupied(supine, 50), true);
});

test('标注可用：region/spine 可解析，小腿部 valid', () => {
  const ds = generateSimulatedDataset();
  const p = ds.people[0];
  const regions = parseRegion(p.actions[1].region);
  assert.equal(regions.length, 6);
  assert.ok(regions.every((r) => r.valid));
  const spine = parseSpine(p.actions[1].spine)!;
  assert.equal(spine.length, 5);
  assert.ok(spine.every((s) => s.x === 12)); // 仰卧中线
});

test('动态标签与真实动态文件同风格（0/2/0/1/0 分段）', () => {
  const ds = generateSimulatedDataset();
  const l = ds.dynamic.labels;
  assert.deepEqual(l.slice(0, 15), Array(15).fill(0));
  assert.deepEqual(l.slice(15, 30), Array(15).fill(2));
  assert.deepEqual(l.slice(45, 60), Array(15).fill(1));
});
