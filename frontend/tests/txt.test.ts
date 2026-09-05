import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTxt } from '../src/core/parsers/txt.ts';
import { mirrorFrame } from '../src/core/metrics.ts';
import { loadText } from './helpers.ts';

test('静态文件：wzh_10.txt = 30 帧 × 1056 值，空行分隔', () => {
  const { frames, labels } = parseTxt(loadText('睡姿数据/wzh/wzh_10.txt'));
  assert.equal(frames.length, 30);
  assert.equal(labels.length, 0);
  for (const f of frames) assert.equal(f.length, 1056);
  // 帧0 首行前 5 个值（与文件原文一致）
  assert.deepEqual(Array.from(frames[0].slice(0, 5)), [3, 1, 1, 0, 2]);
});

test('仰卧：帧15 = 帧0 的左右镜像（增强帧追加在自身文件后半）', () => {
  const { frames } = parseTxt(loadText('睡姿数据/wzh/wzh_1.txt'));
  assert.equal(frames.length, 30);
  assert.deepEqual(Array.from(frames[15]), Array.from(mirrorFrame(frames[0])));
});

test('俯卧：60 帧 = 30 原始 + 30 镜像，帧30 = 帧0 镜像', () => {
  const { frames } = parseTxt(loadText('睡姿数据/wzh/wzh_7.txt'));
  assert.equal(frames.length, 60);
  assert.deepEqual(Array.from(frames[30]), Array.from(mirrorFrame(frames[0])));
});

test('侧卧跨动作镜像：动作10 后半 = 动作16 前半的镜像（10↔16）', () => {
  const a10 = parseTxt(loadText('睡姿数据/wzh/wzh_10.txt')).frames;
  const a16 = parseTxt(loadText('睡姿数据/wzh/wzh_16.txt')).frames;
  assert.deepEqual(Array.from(a10[15]), Array.from(mirrorFrame(a16[0])));
  assert.deepEqual(Array.from(a16[15]), Array.from(mirrorFrame(a10[0])));
});

test('空载文件：15 帧，单点最大不超过 60（背景压力）', () => {
  const { frames, labels } = parseTxt(loadText('睡姿数据/wzh/wzh_空载.txt'));
  assert.equal(frames.length, 15);
  assert.equal(labels.length, 0);
  let max = 0;
  for (const f of frames) for (const v of f) if (v > max) max = v;
  assert.ok(max > 0 && max <= 60, `空载最大应为 (0,60]，实际 ${max}`);
});

test('动态文件：159 帧 + 159 个标签行，标签序列前段为 0×11→2×10', () => {
  const { frames, labels } = parseTxt(loadText('睡姿数据/wzh/whz_动态一.txt'));
  assert.equal(frames.length, 159);
  assert.equal(labels.length, 159);
  assert.deepEqual(labels.slice(0, 11), Array(11).fill(0));
  assert.deepEqual(labels.slice(11, 21), Array(10).fill(2));
  for (const f of frames) assert.equal(f.length, 1056);
});
