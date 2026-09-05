/**
 * 气囊模块核心：状态模型 + 模拟数据源 + 真实设备预留接口。
 *
 * ⚠️ 数据事实：数据集中没有任何气囊状态读数；气囊-传感器布置图仅为静态图纸。
 * 因此本模块 = 条带布局示意（按布置图编号体系）+ 模拟状态 + 预留接口，
 * UI 必须明示"模拟数据"。真实设备接入时实现同一 AirbagSource 接口即可替换。
 *
 * 布置图编号体系（视觉模型核验）：
 *   左半区：上段气囊带 40/41/42（绿） + 下段 12（红）
 *   右半区：上段气囊带 64/65/66（橙黄） + 下段 13（红）
 * 条带与身体部位的大致对应为推测（图纸未标注部位名），UI 中以"大致对应"呈现。
 */

export interface AirbagZone {
  id: string;
  side: '左半区' | '右半区';
  /** 大致对应部位（推测，图纸未明确标注） */
  regionHint: string;
  color: string;
}

export const AIRBAG_ZONES: AirbagZone[] = [
  { id: '40', side: '左半区', regionHint: '肩背', color: '#3FB950' },
  { id: '41', side: '左半区', regionHint: '腰', color: '#3FB950' },
  { id: '42', side: '左半区', regionHint: '臀', color: '#3FB950' },
  { id: '12', side: '左半区', regionHint: '大腿', color: '#F85149' },
  { id: '64', side: '右半区', regionHint: '肩背', color: '#D29922' },
  { id: '65', side: '右半区', regionHint: '腰', color: '#D29922' },
  { id: '66', side: '右半区', regionHint: '臀', color: '#D29922' },
  { id: '13', side: '右半区', regionHint: '大腿', color: '#F85149' },
];

/** 单个气囊的实时状态 */
export interface AirbagState {
  zoneId: string;
  /** 当前充气程度 0-100（模拟值平滑过渡） */
  pressure: number;
  /** 目标充气程度 */
  target: number;
  timestamp: number;
}

/** 真实设备接入时实现同一接口（WebSocket/串口适配器） */
export interface AirbagSource {
  readonly isSimulated: boolean;
  getStates(): AirbagState[];
  setTarget(zoneId: string, pressure: number): void;
  /** 每帧推进（充放气平滑过渡） */
  tick(dtMs: number): void;
  subscribe(cb: () => void): () => void;
}

/** 模拟数据源：目标值平滑爬坡，模拟充放气过程 */
export class SimulatedAirbagSource implements AirbagSource {
  readonly isSimulated = true;
  private states = new Map<string, AirbagState>();
  private listeners = new Set<() => void>();
  /** 充放气过渡时长（ms） */
  private rampMs = 600;

  constructor(initialPressure = 40) {
    for (const z of AIRBAG_ZONES) {
      this.states.set(z.id, { zoneId: z.id, pressure: initialPressure, target: initialPressure, timestamp: 0 });
    }
  }

  getStates(): AirbagState[] {
    return AIRBAG_ZONES.map((z) => this.states.get(z.id)!);
  }

  setTarget(zoneId: string, pressure: number): void {
    const s = this.states.get(zoneId);
    if (!s) throw new Error(`未知气囊编号：${zoneId}`);
    s.target = Math.min(Math.max(pressure, 0), 100);
    s.timestamp = Date.now();
  }

  tick(dtMs: number): void {
    if (dtMs <= 0) return;
    let changed = false;
    for (const s of this.states.values()) {
      if (s.pressure === s.target) continue;
      const step = (100 * dtMs) / this.rampMs;
      if (Math.abs(s.target - s.pressure) <= step) s.pressure = s.target;
      else s.pressure += Math.sign(s.target - s.pressure) * step;
      changed = true;
    }
    if (changed) for (const cb of this.listeners) cb();
  }

  subscribe(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
}

/** 演示剧本预设 */
export interface AirbagPreset {
  name: string;
  description: string;
  zones: Record<string, number>;
}

export const AIRBAG_PRESETS: AirbagPreset[] = [
  {
    name: '均衡支撑',
    description: '全部气囊中等充气',
    zones: { '40': 40, '41': 40, '42': 40, '12': 40, '64': 40, '65': 40, '66': 40, '13': 40 },
  },
  {
    name: '腰部支撑增强',
    description: '腰部气囊强充气，模拟腰部顶起',
    zones: { '40': 30, '41': 85, '42': 30, '12': 25, '64': 30, '65': 85, '66': 30, '13': 25 },
  },
  {
    name: '全身释压',
    description: '全部气囊放气',
    zones: { '40': 15, '41': 15, '42': 15, '12': 15, '64': 15, '65': 15, '66': 15, '13': 15 },
  },
];

/** 状态文案 */
export function airbagStateText(pressure: number): string {
  if (pressure >= 70) return '强支撑';
  if (pressure >= 35) return '均衡';
  return '释压';
}
