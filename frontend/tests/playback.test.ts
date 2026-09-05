import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PlaybackController } from '../src/core/playback.ts';

const frames = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((v) => new Float32Array([v]));

function make(opts = {}) {
  const c = new PlaybackController(frames, opts);
  const visited: number[] = [];
  c.onFrame = (i) => visited.push(i);
  return { c, visited };
}

test('初始状态：帧 0、暂停', () => {
  const { c } = make();
  assert.equal(c.frameIndex, 0);
  assert.equal(c.isPlaying, false);
  assert.equal(c.phaseValue, 'idle');
});

test('播放推进：10fps 下 tick(100ms) 前进 1 帧', () => {
  const { c, visited } = make();
  c.play();
  c.tick(100);
  assert.equal(c.frameIndex, 1);
  assert.deepEqual(visited, [1]);
  c.tick(50); // 不足一帧不前进
  assert.equal(c.frameIndex, 1);
  c.tick(50);
  assert.equal(c.frameIndex, 2);
});

test('倍速：2× 下 tick(100ms) 前进 2 帧', () => {
  const { c } = make();
  c.speed = 2;
  c.play();
  c.tick(100);
  assert.equal(c.frameIndex, 2);
});

test('播到末尾停止（不循环），重新播放从头开始', () => {
  const { c } = make();
  let endAt = -1;
  c.onEnd = (i) => (endAt = i);
  c.play();
  c.tick(500);
  c.tick(500); // 两次共 10 帧（单次 tick 最多 8 帧）
  assert.equal(c.frameIndex, 9);
  assert.equal(c.phaseValue, 'ended');
  assert.equal(endAt, 9);
  c.play();
  assert.equal(c.frameIndex, 0);
  assert.equal(c.phaseValue, 'playing');
});

test('单次 tick 最多前进 8 帧（防后台切回跳帧）', () => {
  const { c } = make();
  c.play();
  c.tick(5000); // 50 帧的量，但被钳制为 8
  assert.equal(c.frameIndex, 8);
  assert.equal(c.phaseValue, 'playing');
});

test('循环模式：末尾回到帧 0 继续', () => {
  const { c } = make({ loop: true });
  c.play();
  c.tick(1000); // 8 帧 → 8
  assert.equal(c.frameIndex, 8);
  c.tick(1000); // 再 8 帧：9→0→1..→6
  assert.equal(c.frameIndex, 6);
  assert.equal(c.phaseValue, 'playing');
});

test('step/seek：边界 clamp，步进后暂停', () => {
  const { c, visited } = make();
  c.step(1);
  assert.equal(c.frameIndex, 1);
  assert.equal(c.phaseValue, 'paused');
  c.seek(99);
  assert.equal(c.frameIndex, 9);
  c.step(1);
  assert.equal(c.frameIndex, 9); // clamp
  c.step(-1);
  assert.equal(c.frameIndex, 8);
  c.seek(0);
  c.step(-1);
  assert.equal(c.frameIndex, 0); // clamp
  assert.ok(visited.length > 0);
});

test('seek 触发 onFrame 回调', () => {
  const { c, visited } = make();
  c.seek(5);
  assert.deepEqual(visited, [5]);
  c.seek(5); // 同帧不重复回调
  assert.deepEqual(visited, [5]);
});

test('pause 后 tick 不再推进', () => {
  const { c } = make();
  c.play();
  c.tick(100);
  c.pause();
  c.tick(500);
  assert.equal(c.frameIndex, 1);
});

test('非法倍速抛出异常', () => {
  const { c } = make();
  assert.throws(() => (c.speed = 3));
});
