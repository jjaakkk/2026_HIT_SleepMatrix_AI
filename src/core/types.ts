// 核心类型与常量：44×24 压力矩阵（新版数据，勿与旧版 40×26 混淆）
export const ROWS = 44; // 行 = 人体纵轴，行 0 = 头端，行 43 = 脚端
export const COLS = 24; // 列 = 人体横轴，列 12 = 中线
export const CELLS = ROWS * COLS; // 1056

export type SleepPos = 0 | 1 | 2 | 3;

export const SLEEP_POS_NAMES: Record<number, string> = {
  0: '仰卧',
  1: '俯卧',
  2: '左侧卧',
  3: '右侧卧',
} as const;

/**
 * action(1-21) → sleep_pos
 * 1-6 仰卧；7-9 俯卧（每动作帧数为 2 倍）；10-15 左侧卧；16-21 右侧卧
 * 依据：docx + 飞书数据集说明，已对 14400 条记录全量核验。
 */
export function actionToSleepPos(action: number): SleepPos | null {
  if (action >= 1 && action <= 6) return 0;
  if (action >= 7 && action <= 9) return 1;
  if (action >= 10 && action <= 15) return 2;
  if (action >= 16 && action <= 21) return 3;
  return null;
}

/**
 * 侧卧镜像动作对：10↔16, 11↔17, 12↔18, 13↔19, 14↔20, 15↔21。
 * 动作 N 的左右镜像帧追加在其镜像动作的文件末尾（飞书说明，已实测）。
 * 仰卧/俯卧的镜像帧追加在自身文件后半，故返回 null。
 */
export function mirrorAction(action: number): number | null {
  if (action >= 10 && action <= 15) return action + 6;
  if (action >= 16 && action <= 21) return action - 6;
  return null;
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
