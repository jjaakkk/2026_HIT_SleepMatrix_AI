/**
 * 单帧聚合推理（POST /api/frame/analyze）的类型与纯函数映射工具。
 *
 * 后端一次调用返回三个模块的结果（各自可独立降级为错误对象）：
 *   posture   睡姿推理（SVM/CNN/ensemble）
 *   partition 身体分区（U-Net 六类分割 → 掩码 + 区域矩形）
 *   enhanced  弱压力区域增强矩阵（可视化口径，非标定物理压力）
 *
 * 本模块只放无副作用纯函数，供组合式函数与单元测试共用。
 */
import { CELLS, COLS, type BodyRegion } from './types.ts';

/** 分区区域矩形（后端 /api/frame/analyze 的 partition.regions 元素） */
export interface PartitionRegion {
  class_id: number;
  key: string;
  name_zh: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** 分区推理结果（与 backend BodyPartitionPredictor 的 to_dict 对齐） */
export interface PartitionResult {
  mask: number[][];
  regions: (PartitionRegion | null)[];
  foreground_ratio: number;
}

/** 模块级错误对象（后端 analyze 对不可用模块返回该结构而非整体失败） */
export interface AnalyzeError {
  error: string;
  message: string;
}

export interface PosturePredictionPayload {
  label_id: number;
  label: string;
  label_zh: string;
  confidence: number;
  probabilities: Record<string, number>;
}

/** POST /api/frame/analyze 响应体 */
export interface AnalyzeFrameResponse {
  posture?:
    | { model: string; prediction: PosturePredictionPayload }
    | AnalyzeError;
  partition?: PartitionResult | AnalyzeError;
  enhanced?:
    | { enhanced_matrix: number[][]; config_used?: Record<string, unknown> }
    | AnalyzeError;
}

/** 判定某个模块返回值是否为错误对象 */
export function isAnalyzeError(value: unknown): value is AnalyzeError {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Record<string, unknown>).error === 'string' &&
    typeof (value as Record<string, unknown>).message === 'string'
  );
}

/** 分区区域矩形 → 前端 BodyRegion（null 区域占位为 valid:false，保持下标对齐） */
export function partitionRegionsToBodyRegions(
  partition: PartitionResult,
): BodyRegion[] {
  return partition.regions.map((r) =>
    r
      ? {
          name: r.name_zh,
          x1: r.x1,
          y1: r.y1,
          x2: r.x2,
          y2: r.y2,
          valid: true,
        }
      : { name: '', x1: 0, y1: 0, x2: 0, y2: 0, valid: false },
  );
}

/** 后端增强矩阵（44×24 二维）→ 1056 行优先 Float32Array（非数值按 0） */
export function flattenMatrix(matrix: number[][]): Float32Array {
  const out = new Float32Array(CELLS);
  for (let r = 0; r < matrix.length; r++) {
    const row = matrix[r];
    if (!row) continue;
    for (let c = 0; c < COLS; c++) {
      const v = row[c];
      out[r * COLS + c] = typeof v === 'number' && Number.isFinite(v) ? v : 0;
    }
  }
  return out;
}

/** 1056 行优先压力帧 → 44×24 二维矩阵（请求负载；非数值按 0） */
export function frameToMatrix(frame: ArrayLike<number>): number[][] {
  const matrix: number[][] = [];
  for (let r = 0; r < 44; r++) {
    const row: number[] = new Array(COLS);
    for (let c = 0; c < COLS; c++) {
      const v = frame[r * COLS + c];
      row[c] = typeof v === 'number' && Number.isFinite(v) ? v : 0;
    }
    matrix.push(row);
  }
  return matrix;
}
