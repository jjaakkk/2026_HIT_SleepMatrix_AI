/**
 * 睡姿推理组合式函数：后端服务生命周期 + 节流单帧推理 + 契约同步。
 *
 * 行为约定：
 * - init() 探测 /api/health 与 /api/contracts/posture；
 * - 离线时每 15s 静默重试（答辩现场后端起服后自动恢复在线）；
 * - 推理请求 latest-wins（新帧到达即中止旧请求），350ms 节流；
 * - 连续 3 次推理失败 → 降级回本地标签模式。
 */
import { onScopeDispose, ref } from 'vue';
import {
  fetchHealth,
  fetchPostureContract,
  predictPosture,
  ApiError,
  type PosturePrediction,
} from '../core/api.ts';
import { applyRemoteContract } from '../core/contracts.ts';

export type BackendState = 'checking' | 'online' | 'offline';
export type PoseSource = 'label' | 'inference';

const HEALTH_RETRY_MS = 15000;
const INFER_THROTTLE_MS = 350;

export function usePostureInference() {
  const backend = ref<BackendState>('checking');
  const modelAvailable = ref(false);
  const modelPath = ref<string | null>(null);
  const contractSynced = ref(false);
  const contractMismatch = ref(false);
  const mismatchDetail = ref<string | null>(null);

  const poseSource = ref<PoseSource>('label');
  const prediction = ref<PosturePrediction | null>(null);
  const predicting = ref(false);
  const lastError = ref<string | null>(null);

  let retryTimer = 0;
  let throttleTimer = 0;
  let inflightCtrl: AbortController | null = null;
  let failStreak = 0;
  let disposed = false;

  async function probe(): Promise<void> {
    if (disposed) return;
    backend.value = backend.value === 'offline' ? 'offline' : 'checking';
    try {
      const health = await fetchHealth();
      modelAvailable.value = health.posture_svm.model_available;
      modelPath.value = health.posture_svm.model_path ?? null;
      backend.value = 'online';
      lastError.value = null;
      failStreak = 0;
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

  /** 队列化一帧推理（内部节流 + 中止旧请求） */
  function queueInference(frame: ArrayLike<number>) {
    if (disposed || backend.value !== 'online' || poseSource.value !== 'inference') return;
    if (!frame || frame.length === 0) return;
    window.clearTimeout(throttleTimer);
    throttleTimer = window.setTimeout(() => {
      void runInference(frame);
    }, INFER_THROTTLE_MS);
  }

  async function runInference(frame: ArrayLike<number>) {
    if (disposed || backend.value !== 'online') return;
    inflightCtrl?.abort();
    const ctrl = new AbortController();
    inflightCtrl = ctrl;
    predicting.value = true;
    try {
      const p = await predictPosture(frame, 4000, ctrl.signal);
      if (disposed) return;
      prediction.value = p;
      failStreak = 0;
      lastError.value = null;
    } catch (e) {
      if (disposed) return;
      if (e instanceof DOMException && e.name === 'AbortError') return;
      lastError.value = e instanceof Error ? e.message : String(e);
      failStreak += 1;
      if (failStreak >= 3) {
        backend.value = 'offline';
        poseSource.value = 'label';
        scheduleRetry();
      }
    } finally {
      if (inflightCtrl === ctrl) {
        inflightCtrl = null;
        predicting.value = false;
      }
    }
  }

  function setPoseSource(v: PoseSource) {
    // 与侧栏禁用语义一致：后端离线时推理不可用，保持标签模式
    if (v === 'inference' && backend.value !== 'online') {
      poseSource.value = 'label';
      return;
    }
    poseSource.value = v;
    if (v === 'inference') {
      prediction.value = null;
      failStreak = 0;
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
    modelAvailable,
    modelPath,
    contractSynced,
    contractMismatch,
    mismatchDetail,
    poseSource,
    prediction,
    predicting,
    lastError,
    probe,
    queueInference,
    setPoseSource,
  };
}
