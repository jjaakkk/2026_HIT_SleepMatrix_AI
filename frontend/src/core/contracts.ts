/**
 * 共享数据契约（shared/contracts/posture.json）的前端消费端。
 *
 * 架构原则：睡姿 ID、动作映射、镜像关系只以契约文档为唯一事实源。
 * - 模块初始化时以内置副本（src/core/contracts/posture.json）同步生效；
 * - 后端可用时通过 GET /api/contracts/posture 拉取远端契约并校验版本，
 *   版本一致才替换生效；不一致则保持本地基线并上报，UI 显示警告徽章。
 *
 * 校验规则与 backend/data_utils/contracts.py 对齐（语言中立契约）。
 */
import bundledRaw from './contracts/posture.json' with { type: 'json' };

export interface PostureContractEntry {
  id: number;
  key: string;
  name_zh: string;
  actions: number[];
  mirrored_label_id: number;
}

export interface PostureContract {
  contract_version: string;
  pressure_matrix: { rows: number; columns: number; index_order: string };
  postures: PostureContractEntry[];
  excluded_actions: Record<string, string>;
  mirrored_action_pairs: [number, number][];
}

export class ContractValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ContractValidationError';
  }
}

function isPositiveInt(v: unknown, field: string): number {
  if (typeof v !== 'number' || !Number.isInteger(v) || v <= 0) {
    throw new ContractValidationError(`Contract field ${field} must be a positive integer.`);
  }
  return v;
}

/** 校验契约文档（与后端 _build_contract_values 对齐的规则） */
export function validateContract(raw: unknown): PostureContract {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ContractValidationError('Contract root must be a JSON object.');
  }
  const doc = raw as Record<string, unknown>;
  const version = doc.contract_version;
  if (typeof version !== 'string' || !version) {
    throw new ContractValidationError('Contract field contract_version must be a non-empty string.');
  }

  const matrix = doc.pressure_matrix;
  if (typeof matrix !== 'object' || matrix === null || Array.isArray(matrix)) {
    throw new ContractValidationError('Contract field pressure_matrix must be an object.');
  }
  const m = matrix as Record<string, unknown>;
  const rows = isPositiveInt(m.rows, 'pressure_matrix.rows');
  const cols = isPositiveInt(m.columns, 'pressure_matrix.columns');
  if (m.index_order !== 'row_column') {
    throw new ContractValidationError('Only matrix[row][column] ordering is currently supported.');
  }

  const postures = doc.postures;
  if (!Array.isArray(postures) || postures.length === 0) {
    throw new ContractValidationError('Contract field postures must be a non-empty array.');
  }
  const seenIds = new Set<number>();
  const entries: PostureContractEntry[] = [];
  for (const record of postures) {
    if (typeof record !== 'object' || record === null) {
      throw new ContractValidationError('Every posture entry must be an object.');
    }
    const r = record as Record<string, unknown>;
    const id = r.id;
    if (typeof id !== 'number' || !Number.isInteger(id) || id < 0) {
      throw new ContractValidationError('Every posture ID must be a non-negative integer.');
    }
    if (seenIds.has(id)) throw new ContractValidationError(`Duplicate posture ID in contract: ${id}`);
    seenIds.add(id);
    const key = r.key;
    const nameZh = r.name_zh;
    if (typeof key !== 'string' || !key || typeof nameZh !== 'string' || !nameZh) {
      throw new ContractValidationError(`Posture ${id} must have non-empty names.`);
    }
    if (!Array.isArray(r.actions) || r.actions.length === 0) {
      throw new ContractValidationError(`Posture ${id} must contain action IDs.`);
    }
    if (typeof r.mirrored_label_id !== 'number' || !Number.isInteger(r.mirrored_label_id)) {
      throw new ContractValidationError(`Posture ${id} has an invalid mirrored label ID.`);
    }
    entries.push({
      id,
      key,
      name_zh: nameZh,
      actions: r.actions as number[],
      mirrored_label_id: r.mirrored_label_id,
    });
  }

  const excluded = doc.excluded_actions;
  const excludedOut: Record<string, string> = {};
  if (typeof excluded === 'object' && excluded !== null && !Array.isArray(excluded)) {
    for (const [k, v] of Object.entries(excluded as Record<string, unknown>)) {
      if (typeof v === 'string') excludedOut[k] = v;
    }
  }

  const pairs = doc.mirrored_action_pairs;
  const pairOut: [number, number][] = [];
  if (Array.isArray(pairs)) {
    for (const p of pairs) {
      if (
        Array.isArray(p) &&
        p.length === 2 &&
        p.every((n) => typeof n === 'number' && Number.isInteger(n))
      ) {
        pairOut.push([p[0], p[1]]);
      }
    }
  }

  return {
    contract_version: version,
    pressure_matrix: { rows, columns: cols, index_order: String(m.index_order) },
    postures: entries,
    excluded_actions: excludedOut,
    mirrored_action_pairs: pairOut,
  };
}

/** 内置契约（随构建打包，离线可用） */
export const LOCAL_CONTRACT: PostureContract = validateContract(bundledRaw);

let active: PostureContract = LOCAL_CONTRACT;

export interface ApplyResult {
  ok: boolean;
  error?: string;
  /** 远端版本与本地基线不一致 */
  versionMismatch?: boolean;
}

/**
 * 应用后端返回的契约文档。
 * 版本一致 → 替换生效；版本不一致 → 保持本地基线并标记 versionMismatch。
 */
export function applyRemoteContract(raw: unknown): ApplyResult {
  try {
    const parsed = validateContract(raw);
    if (parsed.contract_version !== LOCAL_CONTRACT.contract_version) {
      return {
        ok: false,
        versionMismatch: true,
        error: `远端契约 v${parsed.contract_version} 与前端基线 v${LOCAL_CONTRACT.contract_version} 不一致`,
      };
    }
    active = parsed;
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export function contractVersion(): string {
  return active.contract_version;
}
export function matrixShape(): { rows: number; columns: number } {
  return { rows: active.pressure_matrix.rows, columns: active.pressure_matrix.columns };
}
export function isRemoteContractActive(): boolean {
  return active !== LOCAL_CONTRACT;
}

/** label id → 中文名（0 仰卧 / 1 俯卧 / 2 左侧卧 / 3 右侧卧） */
export function sleepPosNames(): Record<number, string> {
  const out: Record<number, string> = {};
  for (const p of active.postures) out[p.id] = p.name_zh;
  return out;
}

/** action → 睡姿 label id；excluded（0 空载 / 22 动态）返回 null */
export function actionToLabelId(action: number): number | null {
  if (Object.prototype.hasOwnProperty.call(active.excluded_actions, String(action))) return null;
  for (const p of active.postures) {
    if (p.actions.includes(action)) return p.id;
  }
  return null;
}

/** 镜像动作：契约镜像对内取对侧；无镜像（仰卧/俯卧等）返回 null */
export function mirrorAction(action: number): number | null {
  for (const [a, b] of active.mirrored_action_pairs) {
    if (action === a) return b;
    if (action === b) return a;
  }
  return null;
}
