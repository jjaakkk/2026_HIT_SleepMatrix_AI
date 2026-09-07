/**
 * 单帧聚合推理组合式函数：后端服务生命周期 + 设备帧轮询 + 节流逐帧分析 + 分模块降级。
 *
 * 行为约定：
 * - 实时推理模式（displayMode='inference'）：帧源为设备接口
 *   （轮询 GET /api/stream/latest，采集程序 POST /api/stream/ingest 推帧）。
 *   无设备输入时保持静止（黑屏），不回退播放任何演示数据；
 * - 离线回放模式（displayMode='demo'）：帧源为回放记录（未接入设备时的历史数据），
 *   回放帧同样逐帧调用 POST /api/frame/analyze（睡姿 + 身体分区 + 弱区增强），
 *   模型结果驱动界面；模型不可用时按模块回退记录标注；
 * - init() 探测 /api/health 与 /api/contracts/posture；离线时每 15s 静默重试，
 *   后端起服后自动恢复在线；
 * - 分析请求尾沿节流（350ms）+ 最新帧覆盖（latest-wins）+ 串行化：
 *   在途请求完成后自动用最新帧继续，持续播放时不饿死、不反复中止旧请求；
 * - 后端对不可用模块返回模块级错误对象（HTTP 200）：仅降级对应模块；
 * - 连续 3 次传输级失败（网络/超时/5xx）→ 后端标记离线并定时重连。
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
/** 数据模式：实时推理（设备帧输入，默认）| 离线回放（未接入设备时回放历史记录，仍接推理） */
export type DisplayMode = 'inference' | 'demo';

const HEALTH_RETRY_MS = 15000;
const ANALYZE_THROTTLE_MS = 350;
/** 设备帧轮询间隔（实时推理模式） */
const STREAM_POLL_MS = 150;
/** 连续无新帧超过该时长（ms）判定设备无输入 → 界面保持静止（黑屏） */
const STREAM_IDLE_MS = 2000;
/** 传输级连续失败达到该次数后判定后端离线 */
const TRANSPORT_FAIL_LIMIT = 3;

export function useFrameInference() {
  const backend = ref<BackendState>('checking');
  /** 默认实时推理：设备帧输入；无输入时静止等待 */
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

  // 设备实时帧流（实时推理模式的帧源）
  const deviceFrame = ref<Float32Array | null>(null);
  const deviceSeq = ref(-1);
  const deviceSource = ref<string | null>(null);
  /** true = 当前没有设备输入（界面应保持静止/黑屏，不播演示数据） */
  const streamIdle = ref(true);

  const analyzing = ref(false);
  const lastError = ref<string | null>(null);

  let retryTimer = 0;
  let throttleTimer = 0;
  let streamPollTimer = 0;
  let lastFrameAt = 0;
  /** 节流窗口内最新待分析帧（latest-wins，自动播放时每帧更新） */
  let pendingFrame: ArrayLike<number> | null = null;
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
      if (displayMode.value === 'inference') startStreamPolling();
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

  // ------------------------------------------------------------------
  // 设备帧流轮询（实时推理模式帧源）
  // ------------------------------------------------------------------

  async function pollDeviceStream() {
    if (disposed || backend.value !== 'online' || displayMode.value !== 'inference') return;
    try {
      const res = await fetch(
        `/api/stream/latest?after=${deviceSeq.value}&_=${Date.now()}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as {
        has_frame: boolean;
        seq: number;
        source?: string | null;
        pressure_matrix?: number[][];
      };
      if (payload.has_frame && Array.isArray(payload.pressure_matrix)) {
        const flat = flattenMatrix(payload.pressure_matrix);
        deviceFrame.value = flat;
        deviceSeq.value = payload.seq;
        deviceSource.value = payload.source ?? 'device';
        streamIdle.value = false;
        lastFrameAt = Date.now();
        queueAnalyze(flat);
      } else {
        // 没有新帧：超过阈值后进入静止等待状态
        if (Date.now() - lastFrameAt > STREAM_IDLE_MS && !streamIdle.value) {
          streamIdle.value = true;
          deviceFrame.value = null;
          deviceSource.value = null;
          prediction.value = null;
          partition.value = null;
          enhancedFrame.value = null;
          postureAvailable.value = false;
          partitionAvailable.value = false;
          enhanceAvailable.value = false;
        }
      }
    } catch (e) {
      if (disposed) return;
      if (e instanceof TypeError) {
        // 传输级失败累计，达到阈值判离线
        transportFailStreak += 1;
        if (transportFailStreak >= TRANSPORT_FAIL_LIMIT) {
          backend.value = 'offline';
          scheduleRetry();
        }
      }
    } finally {
      if (!disposed && backend.value === 'online' && displayMode.value === 'inference') {
        streamPollTimer = window.setTimeout(pollDeviceStream, STREAM_POLL_MS);
      }
    }
  }

  function startStreamPolling() {
    if (disposed || streamPollTimer !== 0 || backend.value !== 'online') return;
    streamIdle.value = true;
    lastFrameAt = 0;
    void pollDeviceStream();
  }

  function stopStreamPolling() {
    window.clearTimeout(streamPollTimer);
    streamPollTimer = 0;
  }

  /**
   * 队列化一帧分析（尾沿节流 + 最新帧覆盖 + 中止旧请求）。
   *
   * 定时器已挂起时只更新 pendingFrame（latest-wins），不重置定时器——
   * 否则持续播放（帧号每 100ms 变化）会把 350ms 节流定时器无限重置，
   * 推理请求永远无法发出（自动播放饿死问题）。
   */
  function queueAnalyze(frame: ArrayLike<number>) {
    if (disposed || backend.value !== 'online') return;
    if (!frame || frame.length === 0) return;
    pendingFrame = frame;
    if (throttleTimer !== 0) return;
    throttleTimer = window.setTimeout(() => {
      throttleTimer = 0;
      const next = pendingFrame;
      pendingFrame = null;
      if (next) void runAnalyze(next);
    }, ANALYZE_THROTTLE_MS);
  }

  async function runAnalyze(frame: ArrayLike<number>) {
    // 串行化：在途请求未完成时不发新请求（pendingFrame 已保存最新帧，完成后自续），
    // 避免持续播放时新请求反复中止即将完成的旧请求造成饿死。
    if (disposed || backend.value !== 'online' || inflightCtrl !== null) return;
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
        // 在途期间有新帧到达 → 立即用最新帧继续分析（自续，不饿死）
        const next = pendingFrame;
        pendingFrame = null;
        if (next && !disposed && backend.value === 'online') {
          throttleTimer = window.setTimeout(() => {
            throttleTimer = 0;
            void runAnalyze(next);
          }, 0);
        }
      }
    }
  }

  function setDisplayMode(v: DisplayMode) {
    if (v === displayMode.value) return;
    displayMode.value = v;
    // 清空旧推理结果，避免与当前帧错位
    prediction.value = null;
    partition.value = null;
    enhancedFrame.value = null;
    postureAvailable.value = false;
    partitionAvailable.value = false;
    enhanceAvailable.value = false;
    if (v === 'inference') {
      if (backend.value === 'online') startStreamPolling();
    } else {
      stopStreamPolling();
      streamIdle.value = true;
      deviceFrame.value = null;
      deviceSource.value = null;
    }
  }

  onScopeDispose(() => {
    disposed = true;
    inflightCtrl?.abort();
    window.clearTimeout(retryTimer);
    window.clearTimeout(throttleTimer);
    stopStreamPolling();
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
    deviceFrame,
    deviceSeq,
    deviceSource,
    streamIdle,
    analyzing,
    lastError,
    probe,
    queueAnalyze,
    setDisplayMode,
  };
}
