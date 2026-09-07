import test from 'node:test';
import assert from 'node:assert/strict';
import {
  flattenMatrix,
  frameToMatrix,
  isAnalyzeError,
  partitionRegionsToBodyRegions,
  type PartitionResult,
} from '../src/core/frame-inference.ts';

test('flattenMatrix：44×24 → 1056 行优先，非数值按 0', () => {
  const matrix: number[][] = [];
  for (let r = 0; r < 44; r++) matrix.push(new Array(24).fill(0));
  matrix[0][0] = 7.5;
  matrix[43][23] = 99;
  matrix[1][2] = Number.NaN;
  const flat = flattenMatrix(matrix);
  assert.equal(flat.length, 1056);
  assert.equal(flat[0], 7.5);
  assert.equal(flat[43 * 24 + 23], 99);
  assert.equal(flat[1 * 24 + 2], 0);
});

test('frameToMatrix：1056 行优先 → 44×24，非数值按 0', () => {
  const frame = new Float32Array(1056);
  frame[2 * 24 + 3] = 42;
  frame[10 * 24 + 5] = Number.POSITIVE_INFINITY;
  const matrix = frameToMatrix(frame);
  assert.equal(matrix.length, 44);
  assert.equal(matrix[0].length, 24);
  assert.equal(matrix[2][3], 42);
  assert.equal(matrix[10][5], 0);
});

test('partitionRegionsToBodyRegions：区域映射 + null 占位 valid:false', () => {
  const partition: PartitionResult = {
    mask: [[0]],
    foreground_ratio: 0.5,
    regions: [
      { class_id: 1, key: 'shoulder', name_zh: '肩部', x1: 10, y1: 12, x2: 15, y2: 17 },
      null,
      { class_id: 4, key: 'hip', name_zh: '臀部', x1: 8, y1: 20, x2: 18, y2: 26 },
    ],
  };
  const regions = partitionRegionsToBodyRegions(partition);
  assert.equal(regions.length, 3);
  assert.deepEqual(regions[0], { name: '肩部', x1: 10, y1: 12, x2: 15, y2: 17, valid: true });
  assert.equal(regions[1].valid, false);
  assert.equal(regions[1].name, '');
  assert.deepEqual(regions[2], { name: '臀部', x1: 8, y1: 20, x2: 18, y2: 26, valid: true });
});

test('isAnalyzeError：模块错误对象判定', () => {
  assert.equal(isAnalyzeError({ error: 'model_unavailable', message: 'x' }), true);
  assert.equal(isAnalyzeError({ error: 'model_unavailable' }), false);
  assert.equal(isAnalyzeError({ prediction: { label_id: 0 } }), false);
  assert.equal(isAnalyzeError(null), false);
  assert.equal(isAnalyzeError('err'), false);
});
