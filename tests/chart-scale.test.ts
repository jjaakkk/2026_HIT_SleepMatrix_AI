import { test } from 'node:test';
import assert from 'node:assert/strict';
import { niceTicks } from '../src/render/chart-scale.ts';

test('常规范围：0-289 → 0..300 步进 100', () => {
  const t = niceTicks(0, 289, 5);
  assert.deepEqual(t.ticks, [0, 100, 200, 300]);
  assert.equal(t.min, 0);
  assert.equal(t.max, 300);
});

test('小范围：0-52 → 步进 20（1/2/5 系列）', () => {
  const t = niceTicks(0, 52, 5);
  assert.equal(t.step, 20);
  assert.deepEqual(t.ticks, [0, 20, 40, 60]);
});

test('百分比范围：0-100 → 0..100 步进 20', () => {
  const t = niceTicks(0, 100, 5);
  assert.equal(t.step, 20);
  assert.equal(t.max, 100);
});

test('平坦数据不崩溃', () => {
  const t = niceTicks(250, 250, 5);
  assert.ok(t.ticks.length >= 2);
  assert.ok(t.min < t.max);
});

test('包含负值', () => {
  const t = niceTicks(-45, 120, 5);
  assert.ok(t.min <= -45 && t.max >= 120);
  assert.ok(t.ticks.includes(0) || Math.abs(t.step % 10) < 1e-9 || t.step % 5 < 1e-9);
});
