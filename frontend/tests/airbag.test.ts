import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AIRBAG_ZONES,
  AIRBAG_PRESETS,
  SimulatedAirbagSource,
  airbagStateText,
} from '../src/core/airbag.ts';

test('区域配置：8 个气囊，编号与布置图一致且唯一', () => {
  assert.equal(AIRBAG_ZONES.length, 8);
  const ids = AIRBAG_ZONES.map((z) => z.id);
  assert.deepEqual(ids, ['40', '41', '42', '12', '64', '65', '66', '13']);
  assert.equal(new Set(ids).size, 8);
});

test('setTarget：越界 clamp 到 0-100', () => {
  const s = new SimulatedAirbagSource();
  s.setTarget('41', 150);
  assert.equal(s.getStates().find((x) => x.zoneId === '41')!.target, 100);
  s.setTarget('41', -20);
  assert.equal(s.getStates().find((x) => x.zoneId === '41')!.target, 0);
});

test('tick：压力向目标平滑爬坡，到达后停止变化', () => {
  const s = new SimulatedAirbagSource();
  s.setTarget('41', 100);
  let prev = 40;
  for (let i = 0; i < 100 && prev < 100; i++) {
    s.tick(50);
    const p = s.getStates().find((x) => x.zoneId === '41')!.pressure;
    assert.ok(p >= prev && p <= 100); // 单调不减
    prev = p;
  }
  assert.equal(prev, 100);
});

test('subscribe：状态变化时通知，退订后不再通知', () => {
  const s = new SimulatedAirbagSource();
  let calls = 0;
  const off = s.subscribe(() => calls++);
  s.setTarget('40', 90);
  s.tick(100);
  assert.ok(calls > 0);
  const before = calls;
  off();
  s.setTarget('40', 10);
  s.tick(100);
  assert.equal(calls, before);
});

test('预设剧本：腰部支撑增强中腰气囊目标最高', () => {
  const preset = AIRBAG_PRESETS.find((p) => p.name === '腰部支撑增强')!;
  assert.ok(preset.zones['41'] > preset.zones['40']);
  assert.ok(preset.zones['65'] > preset.zones['66']);
});

test('状态文案分档', () => {
  assert.equal(airbagStateText(80), '强支撑');
  assert.equal(airbagStateText(50), '均衡');
  assert.equal(airbagStateText(10), '释压');
});
