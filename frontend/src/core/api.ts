/**
 * 后端 HTTP API 客户端（架构：前端只通过共享契约和 HTTP API 获取数据）。
 *
 * 端点（backend/app.py）：
 *   GET  /api/health              → 服务与模型状态
 *   GET  /api/contracts/posture   → 语言中立共享契约（唯一事实源）
 *   POST /api/posture/predict     → 单帧睡姿推理（SVM/CNN）
 *
 * 基础地址：VITE_API_BASE 环境变量；默认同源（dev/preview 由 vite 代理到 127.0.0.1:5000）。
 * 后端不可用时前端优雅降级为本地记录标签 + 内置契约。
 */

const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/\/+$/, '');

export interface PostureSvmStatus {
  model_available: boolean;
  model_path: string;
}
export interface HealthInfo {
  status: string;
  posture_svm: PostureSvmStatus;
}
export interface PosturePrediction {
  label_id: number;
  label: string;
  label_zh: string;
  confidence: number;
  probabilities: Record<string, number>;
}

export type ApiErrorCode = 'network' | 'timeout' | 'http' | 'invalid_request' | 'model_unavailable';

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  constructor(code: ApiErrorCode, message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit,
  timeoutMs: number,
  externalSignal?: AbortSignal,
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const onAbort = () => ctrl.abort();
  if (externalSignal) {
    if (externalSignal.aborted) ctrl.abort();
    else externalSignal.addEventListener('abort', onAbort);
  }
  try {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, { ...init, signal: ctrl.signal });
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        throw new ApiError('timeout', `请求超时（${timeoutMs}ms）: ${path}`);
      }
      throw new ApiError('network', `无法连接后端: ${path}`);
    }
    if (!res.ok) {
      let body: Record<string, unknown> | null = null;
      try {
        body = (await res.json()) as Record<string, unknown>;
      } catch {
        /* 非 JSON 错误体 */
      }
      const errCode = body?.error;
      if (errCode === 'model_unavailable') {
        throw new ApiError('model_unavailable', String(body?.message ?? '模型不可用'), res.status);
      }
      if (errCode === 'invalid_request') {
        throw new ApiError('invalid_request', String(body?.message ?? '请求无效'), res.status);
      }
      throw new ApiError('http', `HTTP ${res.status}: ${path}`, res.status);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
    if (externalSignal) externalSignal.removeEventListener('abort', onAbort);
  }
}

/** GET /api/health */
export function fetchHealth(timeoutMs = 2500): Promise<HealthInfo> {
  return request<HealthInfo>('/api/health', { method: 'GET' }, timeoutMs);
}

/** GET /api/contracts/posture —— 返回未校验的原始契约文档，交由 contracts.ts 校验 */
export function fetchPostureContract(timeoutMs = 2500): Promise<unknown> {
  return request<unknown>('/api/contracts/posture', { method: 'GET' }, timeoutMs);
}

/**
 * POST /api/posture/predict —— 单帧睡姿推理。
 * frame 为 1056 长度行优先压力值，按契约序列化为 44×24 二维数组。
 */
export function predictPosture(
  frame: ArrayLike<number>,
  timeoutMs = 4000,
  externalSignal?: AbortSignal,
): Promise<PosturePrediction> {
  const rows = 44;
  const cols = 24;
  const matrix: number[][] = [];
  for (let r = 0; r < rows; r++) {
    const row: number[] = new Array(cols);
    for (let c = 0; c < cols; c++) {
      const v = frame[r * cols + c];
      row[c] = typeof v === 'number' && Number.isFinite(v) ? v : 0;
    }
    matrix.push(row);
  }
  return request<PosturePrediction>(
    '/api/posture/predict',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pressure_matrix: matrix }),
    },
    timeoutMs,
    externalSignal,
  );
}
