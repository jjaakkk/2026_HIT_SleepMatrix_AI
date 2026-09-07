/**
 * 气囊-传感器布置图（气囊-传感器 标注 布置图20240624.pdf，AutoCAD 导出）权威数据。
 *
 * 统一坐标系（按最终所见图纸方向，页面旋转已处理）：
 *   - 原点：床体左上角；X 向右 0→1800mm；Y 向下 0→2000mm
 *   - 床体：1800mm × 2000mm
 *   - 本坐标系 = 观者视角；3D 转换：x3 = (x - 900)/1000 m，z3 = (y - 1000)/1000 m
 *     （床头在 3D 的 -Z 方向）
 *
 * 数据来源：图纸人工精确校核（mm，3 位小数），为程序直接使用。
 */

export const BED_WIDTH_MM = 1800;
export const BED_HEIGHT_MM = 2000;

export type AirbagRegion = 'left_upper' | 'right_upper' | 'left_lower' | 'right_lower';
export type AirbagColor = 'green' | 'yellow' | 'red';

export interface AirbagRect {
  id: string;
  region: AirbagRegion;
  color: AirbagColor;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  cx: number;
  cy: number;
  width: number;
  height: number;
}

/** 8 个气囊矩形（权威校核数据，mm） */
export const AIRBAG_RECTS: AirbagRect[] = [
  { id: '40', region: 'left_upper', color: 'green', x1: 197.013, y1: 399.167, x2: 802.023, y2: 484.265, cx: 499.518, cy: 441.716, width: 605.01, height: 85.097 },
  { id: '41', region: 'left_upper', color: 'green', x1: 197.013, y1: 519.193, x2: 802.023, y2: 604.29, cx: 499.518, cy: 561.741, width: 605.01, height: 85.097 },
  { id: '42', region: 'left_upper', color: 'green', x1: 197.013, y1: 639.218, x2: 802.023, y2: 724.104, cx: 499.518, cy: 681.661, width: 605.01, height: 84.886 },
  { id: '64', region: 'right_upper', color: 'yellow', x1: 996.989, y1: 399.167, x2: 1601.999, y2: 484.265, cx: 1299.494, cy: 441.716, width: 605.01, height: 85.097 },
  { id: '65', region: 'right_upper', color: 'yellow', x1: 996.989, y1: 519.193, x2: 1601.999, y2: 604.29, cx: 1299.494, cy: 561.741, width: 605.01, height: 85.097 },
  { id: '66', region: 'right_upper', color: 'yellow', x1: 996.989, y1: 639.218, x2: 1601.999, y2: 724.104, cx: 1299.494, cy: 681.661, width: 605.01, height: 84.886 },
  { id: '12', region: 'left_lower', color: 'red', x1: 197.013, y1: 1494.426, x2: 802.023, y2: 1579.311, cx: 499.518, cy: 1536.868, width: 605.01, height: 84.886 },
  { id: '13', region: 'right_lower', color: 'red', x1: 996.989, y1: 1494.426, x2: 1601.999, y2: 1579.311, cx: 1299.494, cy: 1536.868, width: 605.01, height: 84.886 },
];

export const AIRBAG_BY_ID: Record<string, AirbagRect> = Object.fromEntries(
  AIRBAG_RECTS.map((r) => [r.id, r]),
);

/** 图底部三个无编号大矩形（不属于任何气囊，仅作 auxiliary 区域） */
export interface AuxiliaryRegion {
  color: AirbagColor;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export const AUXILIARY_REGIONS: AuxiliaryRegion[] = [
  { color: 'red', x1: 1107.915, y1: 1613.393, x2: 1524.521, y2: 1943.41 },
  { color: 'green', x1: 691.097, y1: 1613.393, x2: 1107.915, y2: 1943.41 },
  { color: 'yellow', x1: 274.491, y1: 1613.393, x2: 691.097, y2: 1943.41 },
];

// ---------------------------------------------------------------------------
// 60 个压力传感器（12 列 × 5 行，权威坐标）
// ---------------------------------------------------------------------------

export type SensorRegion = 'green' | 'yellow' | 'left_red' | 'right_red';

export interface AirbagSensor {
  id: number;
  gridRow: number; // 0-4，0=最上（头侧）
  gridCol: number; // 0-11，0=最左
  xMm: number;
  yMm: number;
  region: SensorRegion;
  /** 所属气囊编号 */
  airbagId: string;
}

const SENSOR_COL_X_MM = [
  140.174, 278.196, 416.218, 554.24, 692.262, 830.283,
  968.305, 1106.327, 1244.349, 1382.159, 1520.181, 1658.203,
];
const SENSOR_ROW_Y_MM = [806.979, 936.953, 1066.928, 1196.902, 1326.877];

/** 每行 12 个传感器 ID（从上到下、从左到右，权威读取） */
const SENSOR_IDS_BY_ROW: number[][] = [
  [32, 33, 34, 35, 43, 14, 15, 67, 56, 57, 58, 59],
  [24, 25, 26, 27, 4, 5, 6, 7, 48, 49, 50, 51],
  [36, 37, 38, 39, 16, 17, 18, 19, 60, 61, 62, 63],
  [28, 29, 30, 31, 8, 9, 10, 11, 52, 53, 54, 55],
  [20, 21, 22, 23, 0, 1, 2, 3, 44, 45, 46, 47],
];

/** 区域归属（权威颜色定义；注意 67 为黄色、右侧红色区缺 67 只有 9 个） */
const GREEN_IDS = new Set([32, 33, 34, 35, 24, 25, 26, 27, 36, 37, 38, 39, 28, 29, 30, 31, 20, 21, 22, 23]);
const LEFT_RED_IDS = new Set([43, 14, 4, 5, 16, 17, 8, 9, 0, 1]);
const RIGHT_RED_IDS = new Set([15, 6, 7, 18, 19, 10, 11, 2, 3]);
const YELLOW_IDS = new Set([67, 56, 57, 58, 59, 48, 49, 50, 51, 60, 61, 62, 63, 52, 53, 54, 55, 44, 45, 46, 47]);

/** 绿/黄区域行带划分（近似：行0-1→上带 40/64，行2→中带 41/65，行3-4→下带 42/66） */
function airbagForSensor(row: number, region: SensorRegion): string {
  if (region === 'left_red') return '12';
  if (region === 'right_red') return '13';
  const band = row <= 1 ? 0 : row === 2 ? 1 : 2;
  return region === 'green' ? ['40', '41', '42'][band] : ['64', '65', '66'][band];
}

function regionForId(id: number): SensorRegion {
  if (GREEN_IDS.has(id)) return 'green';
  if (LEFT_RED_IDS.has(id)) return 'left_red';
  if (RIGHT_RED_IDS.has(id)) return 'right_red';
  if (YELLOW_IDS.has(id)) return 'yellow';
  return 'green';
}

function buildSensors(): AirbagSensor[] {
  const list: AirbagSensor[] = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 12; col++) {
      const id = SENSOR_IDS_BY_ROW[row][col];
      const region = regionForId(id);
      list.push({
        id,
        gridRow: row,
        gridCol: col,
        xMm: SENSOR_COL_X_MM[col],
        yMm: SENSOR_ROW_Y_MM[row],
        region,
        airbagId: airbagForSensor(row, region),
      });
    }
  }
  return list;
}

export const AIRBAG_SENSORS: AirbagSensor[] = buildSensors();

export const SENSOR_BY_ID: Record<number, AirbagSensor> = Object.fromEntries(
  AIRBAG_SENSORS.map((s) => [s.id, s]),
);

/** 气囊编号 → 传感器编号列表 */
export const AIRBAG_TO_SENSORS: Record<string, number[]> = {};
for (const sensor of AIRBAG_SENSORS) {
  (AIRBAG_TO_SENSORS[sensor.airbagId] ??= []).push(sensor.id);
}

/** 传感器区域 → 颜色（与 2D/3D 视觉一致） */
export const REGION_COLORS: Record<SensorRegion | AirbagColor, string> = {
  green: '#3FB950',
  yellow: '#D29922',
  left_red: '#F85149',
  right_red: '#F85149',
  red: '#F85149',
};

export const AIRBAG_ID_TO_COLOR: Record<string, string> = {
  '40': '#3FB950',
  '41': '#3FB950',
  '42': '#3FB950',
  '64': '#D29922',
  '65': '#D29922',
  '66': '#D29922',
  '12': '#F85149',
  '13': '#F85149',
};

/** 气囊 → 大致对应身体部位（布置图未标注部位名，为展示提示；12/13 位于腿区） */
export const AIRBAG_HINTS: Record<string, string> = {
  '40': '肩背',
  '41': '腰',
  '42': '臀',
  '12': '腿',
  '64': '肩背',
  '65': '腰',
  '66': '臀',
  '13': '腿',
};

// ---------------------------------------------------------------------------
// 坐标系转换助手
// ---------------------------------------------------------------------------

/** mm（图纸坐标）→ 3D 场景坐标：床中心原点，X 左(-0.9)→右(+0.9)，Z 头(-1)→脚(+1)，Y 向上 */
export function mmTo3D(xMm: number, yMm: number): { x: number; y: number; z: number } {
  return {
    x: (xMm - BED_WIDTH_MM / 2) / 1000,
    y: 0,
    z: (yMm - BED_HEIGHT_MM / 2) / 1000,
  };
}

/** 气囊矩形 → 3D 范围（x0<x1 左→右；z0<z1 头→脚） */
export function airbagRectTo3D(rect: AirbagRect): {
  x0: number;
  x1: number;
  z0: number;
  z1: number;
} {
  const a = mmTo3D(rect.x1, rect.y1);
  const b = mmTo3D(rect.x2, rect.y2);
  return { x0: a.x, x1: b.x, z0: a.z, z1: b.z };
}

/** mm → 44×24 压力矩阵单元格（行=头→脚 0-43，列=左→右 0-23，近似投影） */
export function mmToMatrixCell(xMm: number, yMm: number): { row: number; col: number } {
  return {
    row: Math.min(43, Math.max(0, Math.round((yMm / BED_HEIGHT_MM) * 43))),
    col: Math.min(23, Math.max(0, Math.round((xMm / BED_WIDTH_MM) * 23))),
  };
}

/** 气囊矩形 → 矩阵单元格范围（用于 2D 热力图叠加层，左闭右开） */
export function airbagRectToCells(rect: AirbagRect): {
  row0: number;
  row1: number;
  col0: number;
  col1: number;
} {
  const a = mmToMatrixCell(rect.x1, rect.y1);
  const b = mmToMatrixCell(rect.x2, rect.y2);
  return {
    row0: a.row,
    row1: Math.min(43, b.row + 1),
    col0: a.col,
    col1: Math.min(23, b.col + 1),
  };
}
