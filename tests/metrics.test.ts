import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTxt } from '../src/core/parsers/txt.ts';
import { parseDatasetJson } from '../src/core/parsers/json.ts';
import { computeMetrics, meanBackground, mirrorFrame, contactIndex, isBedOccupied, poseDuration } from '../src/core/metrics.ts';
import { loadText } from './helpers.ts';

test('镜像往返：mirror(mirror(x)) === x', () => {
  const { frames } = parseTxt(loadText('睡姿数据/wzh/wzh_1.txt'));
  const twice = mirrorFrame(mirrorFrame(frames[0]));
  assert.deepEqual(Array.from(twice), Array.from(frames[0]));
});

test('空载均值帧：均值约 4-5，单点最大 ≤ 42', () => {
  const { frames } = parseTxt(loadText('睡姿数据/SAI/SAI_空载.txt'));
  const bg = meanBackground(frames);
  const sum = bg.reduce((a, b) => a + b, 0);
  const mean = sum / bg.length;
  assert.ok(mean > 3 && mean < 6, `空载均值应在 (3,6)，实际 ${mean.toFixed(2)}`);
  const max = Math.max(...bg);
  assert.ok(max <= 42, `空载均值帧单点最大应 ≤42，实际 ${max}`);
});

test('指标：SAI 仰卧 frame0（扣背景，阈值20）', () => {
  const records = parseDatasetJson(loadText('区域划分/data.json'));
  const frame = records.find((r) => r.people === 0 && r.action === 1 && r.frame === 0 && !r.isMirrored)!;
  const bg = meanBackground(parseTxt(loadText('睡姿数据/SAI/SAI_空载.txt')).frames);
  const m = computeMetrics(frame.data, bg, 20);
  assert.equal(m.maxRaw, 286); // 与实测一致
  assert.ok(m.activePoints > 450 && m.activePoints < 650, `有效点数应在 (450,650)，实际 ${m.activePoints}`);
  assert.ok(m.maxNet > 200 && m.maxNet < 350, `净最大应在 (200,350)，实际 ${m.maxNet}`);
  assert.equal(m.contactRatio, m.activePoints / 1056);
  assert.equal(contactIndex(m), (m.activePoints / 1056) * 100);
});

test('指标：无背景扣除时阈值 0 = 全点参与统计', () => {
  const { frames } = parseTxt(loadText('睡姿数据/wzh/wzh_10.txt'));
  const m = computeMetrics(frames[0], null, 0);
  assert.ok(m.activePoints <= 1056 && m.maxRaw > 100);
});

test('在床/离床判定：空载帧扣背景后为离床，人体帧为在床', () => {
  const records = parseDatasetJson(loadText('区域划分/data.json'));
  const frame = records.find((r) => r.people === 0 && r.action === 1 && r.frame === 0 && !r.isMirrored)!;
  const empty = parseTxt(loadText('睡姿数据/SAI/SAI_空载.txt')).frames;
  const bg = meanBackground(empty);
  const mBody = computeMetrics(frame.data, bg, 20);
  assert.equal(isBedOccupied(mBody), true);
  const mEmpty = computeMetrics(empty[0], bg, 20);
  assert.equal(isBedOccupied(mEmpty), false);
});

test('状态持续时长：连续相同状态计数', () => {
  const poses = ['仰卧', '仰卧', '仰卧', '左侧卧', '左侧卧'];
  assert.equal(poseDuration(poses, 0), 1);
  assert.equal(poseDuration(poses, 2), 3);
  assert.equal(poseDuration(poses, 3), 2);
  assert.equal(poseDuration(poses, 4), 2);
  assert.equal(poseDuration(poses, -1), 0);
  assert.equal(poseDuration(poses, 99), 0);
});
