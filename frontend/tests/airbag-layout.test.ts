// 气囊-传感器布置图数据层测试：60 传感器完整性、气囊归属计数与坐标转换。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  AIRBAG_RECTS,
  AIRBAG_SENSORS,
  AIRBAG_TO_SENSORS,
  AIRBAG_BY_ID,
  SENSOR_BY_ID,
  AUXILIARY_REGIONS,
  BED_WIDTH_MM,
  BED_HEIGHT_MM,
  mmTo3D,
  mmToMatrixCell,
  airbagRectTo3D,
} from '../src/core/airbag-layout.ts';

test('8 个气囊矩形，编号齐全', () => {
  assert.equal(AIRBAG_RECTS.length, 8);
  for (const id of ['40', '41', '42', '64', '65', '66', '12', '13']) {
    const r = AIRBAG_BY_ID[id];
    assert.ok(r, `缺少气囊 ${id}`);
    assert.ok(r.x1 < r.x2 && r.y1 < r.y2, `${id} 矩形坐标非法`);
    assert.ok(r.x1 >= 0 && r.x2 <= BED_WIDTH_MM, `${id} 超出床宽`);
    assert.ok(r.y1 >= 0 && r.y2 <= BED_HEIGHT_MM, `${id} 超出床长`);
  }
});

test('60 个传感器，ID 唯一且在 0-67 范围', () => {
  assert.equal(AIRBAG_SENSORS.length, 60);
  const ids = AIRBAG_SENSORS.map((s) => s.id);
  assert.equal(new Set(ids).size, 60, '传感器 ID 重复');
  for (const id of ids) assert.ok(id >= 0 && id <= 67, `非法 ID ${id}`);
});

test('传感器位置在床体范围内，矩阵投影合法', () => {
  for (const s of AIRBAG_SENSORS) {
    assert.ok(s.xMm >= 0 && s.xMm <= BED_WIDTH_MM, `传感器 ${s.id} x 越界`);
    assert.ok(s.yMm >= 0 && s.yMm <= BED_HEIGHT_MM, `传感器 ${s.id} y 越界`);
    const cell = mmToMatrixCell(s.xMm, s.yMm);
    assert.ok(cell.row >= 0 && cell.row <= 43 && cell.col >= 0 && cell.col <= 23, `传感器 ${s.id} 投影越界`);
  }
});

test('气囊→传感器计数符合布置图权威定义', () => {
  const sum = (id: string) => AIRBAG_TO_SENSORS[id]?.length ?? 0;
  assert.equal(sum('12'), 10, '左侧红色 10 个');
  assert.equal(sum('13'), 9, '右侧红色 9 个（67 为黄色）');
  assert.equal(sum('40') + sum('41') + sum('42'), 20, '绿色 20 个');
  assert.equal(sum('64') + sum('65') + sum('66'), 21, '黄色 21 个（含 67）');
  const total = Object.values(AIRBAG_TO_SENSORS).reduce((a, l) => a + l.length, 0);
  assert.equal(total, 60, '传感器总数');
});

test('特殊点归属（权威定义）：67 黄色、8/0 左侧红色', () => {
  assert.equal(SENSOR_BY_ID[67].region, 'yellow');
  assert.equal(SENSOR_BY_ID[8].region, 'left_red');
  assert.equal(SENSOR_BY_ID[0].region, 'left_red');
  assert.equal(SENSOR_BY_ID[15].region, 'right_red');
  assert.equal(SENSOR_BY_ID[32].region, 'green');
  assert.equal(SENSOR_BY_ID[47].region, 'yellow');
});

test('坐标转换：mm → 3D（床中心原点，头在 -Z）', () => {
  const p = mmTo3D(900, 1000);
  assert.ok(Math.abs(p.x) < 1e-9 && Math.abs(p.z) < 1e-9, '床中心应为原点');
  const head = mmTo3D(900, 0);
  assert.equal(head.z, -1, '床头 z=-1');
  const left = mmTo3D(0, 1000);
  assert.equal(left.x, -0.9, '最左 x=-0.9');
  const r = airbagRectTo3D(AIRBAG_BY_ID['40']);
  assert.ok(Math.abs(r.x0 - (197.013 - 900) / 1000) < 1e-6, '40 左边界');
  assert.ok(Math.abs(r.z0 - (399.167 - 1000) / 1000) < 1e-6, '40 上边界（头侧）');
});

test('底部辅助区：3 个、颜色齐全、无编号', () => {
  assert.equal(AUXILIARY_REGIONS.length, 3);
  assert.deepEqual(new Set(AUXILIARY_REGIONS.map((r) => r.color)), new Set(['red', 'green', 'yellow']));
  for (const r of AUXILIARY_REGIONS) {
    assert.ok(r.y1 > 1500, '辅助区位于床体底部');
  }
});
