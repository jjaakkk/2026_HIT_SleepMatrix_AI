import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TURBO } from '../src/render/turbo.ts';
import { bilinearSample, turboColor, valueToColor, computeFrameMax } from '../src/render/heatmap.ts';
import { COLS, ROWS, CELLS } from '../src/core/types.ts';

test('turbo LUT：256 项、数值在 [0,1]', () => {
  assert.equal(TURBO.length, 256);
  for (const [r, g, b] of TURBO) {
    for (const v of [r, g, b]) assert.ok(v >= 0 && v <= 1);
  }
});

test('turboColor 端点与插值', () => {
  assert.deepEqual(turboColor(0), TURBO[0]);
  assert.deepEqual(turboColor(1), TURBO[255]);
  const mid = turboColor(0.5);
  assert.ok(mid.every((v) => v >= 0 && v <= 1));
});

test('valueToColor：越界 clamp 与压扩', () => {
  assert.deepEqual(valueToColor(9999, 250, 1), TURBO[255]);
  assert.deepEqual(valueToColor(-5, 250, 1), TURBO[0]);
  // 压扩：t=0.25, gamma=0.5 → sqrt(0.25)=0.5
  const c = valueToColor(62.5, 250, 0.5);
  assert.deepEqual(c, turboColor(Math.sqrt(0.25)));
});

test('双线性采样：格心处精确还原原始值', () => {
  const frame = new Float32Array(CELLS);
  for (let i = 0; i < CELLS; i++) frame[i] = (i * 7) % 300;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      assert.equal(bilinearSample(frame, c, r), frame[r * COLS + c]);
    }
  }
});

test('双线性采样：边界外 clamp 到边缘格', () => {
  const frame = new Float32Array(CELLS);
  frame[0] = 123;
  frame[ROWS * COLS - 1] = 250;
  assert.equal(bilinearSample(frame, -0.5, -0.5), 123);
  assert.equal(bilinearSample(frame, COLS - 0.5, ROWS - 0.5), 250);
});

test('双线性采样：格间值为四邻加权（单调性 sanity）', () => {
  const frame = new Float32Array(CELLS);
  frame[0] = 0;
  frame[1] = 100;
  frame[COLS] = 100;
  frame[COLS + 1] = 0;
  const v = bilinearSample(frame, 0.5, 0.5);
  assert.equal(v, 50); // 中心点 = 均值
  const v1 = bilinearSample(frame, 0.25, 0.5);
  assert.ok(v1 > 0 && v1 < 100);
});

test('computeFrameMax', () => {
  const frame = new Float32Array([0, 42, 286, 7]);
  assert.equal(computeFrameMax(frame), 286);
});
