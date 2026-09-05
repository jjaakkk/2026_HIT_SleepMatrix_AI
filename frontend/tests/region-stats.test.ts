import { test } from 'node:test';
import assert from 'node:assert/strict';
import { regionMetrics, regionStatsAll } from '../src/core/region-stats.ts';
import { parseRegion } from '../src/core/parsers/annotations.ts';
import { CELLS, COLS } from '../src/core/types.ts';

test('regionMetrics：合成帧内区域统计正确', () => {
  const frame = new Float32Array(CELLS);
  // 区域 (列0-3, 行0-2)：放已知值
  const put = (r: number, c: number, v: number) => (frame[r * COLS + c] = v);
  put(0, 0, 100);
  put(0, 1, 50);
  put(1, 2, 30);
  put(2, 3, 10); // 净压 10 < 阈值 20，不算有效点
  const region = { name: '测试', x1: 0, y1: 0, x2: 3, y2: 2, valid: true };
  const m = regionMetrics(frame, null, region, 20);
  assert.equal(m.activePoints, 3);
  assert.equal(m.maxNet, 100);
  assert.equal(m.sumNet, 180);
  assert.equal(m.meanNet, 60);
});

test('regionMetrics：扣背景后统计', () => {
  const frame = new Float32Array(CELLS);
  const bg = new Float32Array(CELLS);
  frame[0] = 100;
  bg[0] = 30; // 净 70
  const region = { name: '测试', x1: 0, y1: 0, x2: 0, y2: 0, valid: true };
  const m = regionMetrics(frame, bg, region, 20);
  assert.equal(m.maxNet, 70);
  assert.equal(m.activePoints, 1);
});

test('regionStatsAll：按平均净压力降序排列', () => {
  const frame = new Float32Array(CELLS);
  const regions = [
    { name: 'A', x1: 0, y1: 0, x2: 0, y2: 0, valid: true }, // 峰值 80
    { name: 'B', x1: 0, y1: 1, x2: 0, y2: 1, valid: true }, // 峰值 200（第 1 行第 0 列 = index COLS）
    { name: 'C', x1: 2, y1: 0, x2: 2, y2: 0, valid: false }, // 无效区域不参与
  ];
  frame[0] = 80;
  frame[COLS] = 200;
  frame[2] = 999;
  const stats = regionStatsAll(frame, null, regions, 20);
  assert.equal(stats.length, 2);
  assert.equal(stats[0].name, 'B');
  assert.equal(stats[1].name, 'A');
});

test('真实标注：SAI 仰卧区域统计（臀部为最大受力部位；注意区域边界行共享）', () => {
  const regionStr = '6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44';
  const regions = parseRegion(regionStr);
  const frame = new Float32Array(CELLS);
  for (let r = 3; r <= 7; r++) for (let c = 6; c <= 18; c++) frame[r * COLS + c] = 60; // 肩(避开与背共享的行8)
  for (let r = 9; r <= 12; r++) for (let c = 6; c <= 18; c++) frame[r * COLS + c] = 70; // 背(避开共享行8/13)
  for (let r = 13; r <= 17; r++) for (let c = 6; c <= 18; c++) frame[r * COLS + c] = 90; // 腰(避开与臀共享的行18)
  for (let r = 19; r <= 26; r++) for (let c = 5; c <= 20; c++) frame[r * COLS + c] = 200; // 臀(避开与大腿共享的行27)
  const stats = regionStatsAll(frame, null, regions, 20);
  assert.equal(stats[0].name, '臀部');
  assert.equal(stats[1].name, '腰部');
  assert.equal(stats[2].name, '背部');
  assert.equal(stats[3].name, '肩部');
});
