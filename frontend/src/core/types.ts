// 核心类型与常量：44×24 压力矩阵（新版数据，勿与旧版 40×26 混淆）
//
// 睡姿 ID / 动作映射 / 镜像关系一律取自共享数据契约
// （shared/contracts/posture.json，前端消费端见 core/contracts.ts），
// 本文件不再硬编码映射表 —— 与后端 dev/arch 架构对齐。
import { sleepPosNames, actionToLabelId, mirrorAction as contractMirrorAction } from './contracts.ts';

export const ROWS = 44; // 行 = 人体纵轴，行 0 = 头端，行 43 = 脚端
export const COLS = 24; // 列 = 人体横轴，列 12 = 中线
export const CELLS = ROWS * COLS; // 1056

export type SleepPos = 0 | 1 | 2 | 3;

/** 睡姿 label id → 中文名（由契约文档驱动） */
export const SLEEP_POS_NAMES: Record<number, string> = sleepPosNames();

/**
 * action(1-21) → sleep_pos（由契约文档驱动）
 * 契约 excluded_actions：0 = 空载、22 = 动态序列，两者返回 null。
 */
export function actionToSleepPos(action: number): SleepPos | null {
  const id = actionToLabelId(action);
  return id !== null && id >= 0 && id <= 3 ? (id as SleepPos) : null;
}

/** 侧卧镜像动作对（由契约 mirrored_action_pairs 驱动）；仰卧/俯卧返回 null */
export function mirrorAction(action: number): number | null {
  return contractMirrorAction(action);
}

/** 俯卧动作（7-9）每动作 30 帧（其余 15 帧） */
export function isProneAction(action: number): boolean {
  return action >= 7 && action <= 9;
}

/** data.json 单条记录（解析后） */
export interface FrameRecord {
  /** 记录在 json 数组中的下标 */
  index: number;
  people: number;
  peopleName: string;
  action: number;
  frame: number;
  sleepPos: SleepPos;
  /** 1056 个压力值，行优先 */
  data: Float32Array;
  /** 原始 region 字符串（24 token：12 x + 12 y，可含 na） */
  region: string;
  /** 原始 spine 字符串（10 token 或全 na） */
  spine: string;
  /** 该记录是否为左右镜像增强帧（副本 B） */
  isMirrored: boolean;
}

/** 解析后的身体部位区域（坐标 x=列 0-23，y=行 0-43） */
export interface BodyRegion {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  /** 标注缺失（na）时为 false（小腿部仅前 3 人有标注） */
  valid: boolean;
}

/** 解析后的脊柱点（x=列，y=行） */
export interface SpinePoint {
  x: number;
  y: number;
}
