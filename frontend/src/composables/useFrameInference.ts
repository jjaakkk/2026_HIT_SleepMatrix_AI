/**
 * 单帧聚合推理组合式函数：后端服务生命周期 + 节流逐帧分析 + 分模块降级。
 *
 * 行为约定：
 * - 默认数据模式 = 实时推理（displayMode='inference'）：逐帧调用
 *   POST /api/frame/analyze（睡姿 + 身体分区 + 弱区增强一次返回）；
 * - init() 探测 /api/health 与 /api/contracts/posture；离线时每 15s 静默重试，
 *   后端起服后自动恢复在线（实时推理模式自动开始工作）；
 * - 分析请求 latest-wins（新帧到达即中止旧请求），350ms 节流；
 * - 后端对不可用模块返回模块级错误对象（HTTP 200）：仅降级对应模块
 *   （如睡姿模型缺失 → 睡姿回退记录标签，但分区/增强继续用推理结果）；
 * - 连续 3 次传输级失败（网络/超时/5xx）→ 后端标记离线并定时重连，
 *   期间全部模块回退离线回放。
 */
import { onScopeDispose, ref } from 'vue';
import {
  fetchHealth,
  fetchPostureContract,
  analyzeFrame,
  ApiError,
  type PosturePrediction,
} from '../core/api.ts';
import { applyRemoteContract } from '../core/contracts.ts';
import {
  flattenMatrix,
  isAnalyzeError,
  type PartitionResult,
} from '../core/frame-inference.ts';

export type BackendState = 'checking' | 'online' | 'offline';
/** 数据模式：实时推理（默认，模型结果驱动界面）| 离线回放（记录标签与标注） */
export type DisplayMode = 'inference' | 'demo';

const HEALTH_RETRY_MS = 15000;
const ANALYZE_THROTTLE_MS = 350;
/** 传输级连续失败达到该次数后判定后端离线 */
const TRANSPORT_FAIL_LIMIT = 3;

export function useFrameInference() {
  const backend = ref<BackendState>('checking');
  /** 默认实时推理：模型就位后开箱即运转；不可用时按模块回退记录数据 */
  const displayMode = ref<DisplayMode>('inference');

  const postureModelAvailable = ref(false);
  const partitionModelAvailable = ref(false);
  const postureModelPath = ref<string | null>(null);
  const contractSynced = ref(false);
  const contractMismatch = ref(false);
  const mismatchDetail = ref<string | null>(null);

  // 分模块推理结果（null = 该模块不可用/未返回）
  const prediction = ref<PosturePrediction | null>(null);
  const partition = ref<PartitionResult | null>(null);
  const enhancedFrame = ref<Float32Array | null>(null);

  const postureAvailable = ref(false);
  const partitionAvailable = ref(false);
  const enhanceAvailable = ref(false);

  const analyzing = ref(false);
  const lastError = ref<string | null>(null);

  let retryTimer = 0;
  let throttleTimer = 0;
  let inflightCtrl: AbortController | null = null;
  let transportFailStreak = 0;
  let disposed = false;

  async function probe(): Promise<void> {
    if (disposed) return;
    backend.value = backend.value === 'offline' ? 'offline' : 'checking';
    try {
      const health = await fetchHealth();
      postureModelAvailable.value = health.posture_svm.model_available;
      postureModelPath.value = health.posture_svm.model_path ?? null;
      partitionModelAvailable.value = health.models?.body_partition?.model_available ?? false;
      backend.value = 'online';
      lastError.value = null;
      transportFailStreak = 0;
      try {
        const raw = await fetchPostureContract();
        const res = applyRemoteContract(raw);
        if (res.ok) {
          contractSynced.value = true;
          contractMismatch.value = false;
        } else if (res.versionMismatch) {
          contractMismatch.value = true;
          mismatchDetail.value = res.error ?? null;
        }
      } catch {
        /* 契约端点失败不影响在线判定 */
      }
    } catch (e) {
      backend.value = 'offline';
      lastError.value = e instanceof ApiError ? e.message : '后端不可达';
      scheduleRetry();
    }
  }

  function scheduleRetry() {
    if (disposed) return;
    window.clearTimeout(retryTimer);
    retryTimer = window.setTimeout(() => {
      if (backend.value === 'offline') void probe();
    }, HEALTH_RETRY_MS);
  }

  /** 队列化一帧分析（内部节流 + 中止旧请求） */
  function queueAnalyze(frame: ArrayLike<number>) {
    if (disposed || displayMode.value !== 'inference' || backend.value !== 'online') return;
    if (!frame || frame.length === 0) return;
    window.clearTimeout(throttleTimer);
    throttleTimer = window.setTimeout(() => {
      void runAnalyze(frame);
    }, ANALYZE_THROTTLE_MS);
  }

  async function runAnalyze(frame: ArrayLike<number>) {
    if (disposed || backend.value !== 'online') return;
    inflightCtrl?.abort();
    const ctrl = new AbortController();
    inflightCtrl = ctrl;
    analyzing.value = true;
    try {
      const res = await analyzeFrame(frame, {
        timeoutMs: 6000,
        signal: ctrl.signal,
        model: 'ensemble',
      });
      if (disposed) return;

      // 睡姿：不可用/错误 → 清空结果（界面回退记录标签）
      const posture = res.posture;
      if (posture && !isAnalyzeError(posture) && posture.prediction) {
        prediction.value = posture.prediction;
        postureAvailable.value = true;
      } else {
        postureAvailable.value = false;
        prediction.value = null;
      }

      // 身体分区：不可用/错误 → 清空结果（界面回退记录标注）
      const part = res.partition;
      if (part && !isAnalyzeError(part) && Array.isArray(part.mask)) {
        partition.value = part;
        partitionAvailable.value = true;
      } else {
        partitionAvailable.value = false;
        partition.value = null;
      }

      // 弱区增强：不可用/错误 → 清空结果（热力图回退原始帧）
      const enhanced = res.enhanced;
      if (enhanced && !isAnalyzeError(enhanced) && Array.isArray(enhanced.enhanced_matrix)) {
        enhancedFrame.value = flattenMatrix(enhanced.enhanced_matrix);
        enhanceAvailable.value = true;
      } else {
        enhanceAvailable.value = false;
        enhancedFrame.value = null;
      }

      transportFailStreak = 0;
      lastError.value = null;
    } catch (e) {
      if (disposed) return;
      if (e instanceof DOMException && e.name === 'AbortError') return;
      lastError.value = e instanceof Error ? e.message : String(e);
      transportFailStreak += 1;
      if (transportFailStreak >= TRANSPORT_FAIL_LIMIT) {
        backend.value = 'offline';
        scheduleRetry();
      }
    } finally {
      if (inflightCtrl === ctrl) {
        inflightCtrl = null;
        analyzing.value = false;
      }
    }
  }

  function setDisplayMode(v: DisplayMode) {
    if (v === displayMode.value) return;
    displayMode.value = v;
    if (v === 'inference') {
      // 清空旧推理结果，避免与当前帧错位；帧 watcher 会立即重新排队
      prediction.value = null;
      partition.value = null;
      enhancedFrame.value = null;
      postureAvailable.value = false;
      partitionAvailable.value = false;
      enhanceAvailable.value = false;
    }
  }

  onScopeDispose(() => {
    disposed = true;
    inflightCtrl?.abort();
    window.clearTimeout(retryTimer);
    window.clearTimeout(throttleTimer);
  });

  return {
    backend,
    displayMode,
    postureModelAvailable,
    partitionModelAvailable,
    postureModelPath,
    contractSynced,
    contractMismatch,
    mismatchDetail,
    prediction,
    partition,
    enhancedFrame,
    postureAvailable,
    partitionAvailable,
    enhanceAvailable,
    analyzing,
    lastError,
    probe,
    queueAnalyze,
    setDisplayMode,
  };
}
