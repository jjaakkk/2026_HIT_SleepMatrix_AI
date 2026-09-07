/**
 * 气囊-传感器布置图（气囊-传感器 标注 布置图20240624.pdf）结构化数据。
 *
 * 统一坐标系（仰卧者视角，也是后端压力矩阵的语义视角）：
 *   - 床体：1800mm（X，仰卧者左→右）× 2000mm（Y，头→脚）
 *   - 原点：床体左上角（仰卧者的左上 = 观者视角的右上，图纸是仰卧者视角镜像）
 *   - 气囊矩形坐标来自图纸人工校核（精确到 1mm，权威数据）
 *   - 传感器坐标由 PDF 矢量图形提取（60 个圆，12 列 × 5 行），转换到同一坐标系
 *
 * 对应关系（颜色 = 传感器→气囊归属）：
 *   绿色区域  → 气囊 40/41/42（仰卧者左上，肩背/腰/臀三条带）
 *   黄色区域  → 气囊 64/65/66（仰卧者右上，肩背/腰/臀三条带）
 *   红色区域  → 气囊 12（仰卧者左半）/ 13（仰卧者右半，大腿区）
 */

export const BED_WIDTH_MM = 1800;
export const BED_HEIGHT_MM = 2000;

export interface AirbagRect {
  id: string;
  color: 'green' | 'yellow' | 'red';
  /** 对应身体区域提示 */
  regionHint: string;
  /** 仰卧者坐标系 mm：x1=左边界, y1=上边界, x2=右边界, y2=下边界 */
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** 气囊矩形（权威校核数据，仰卧者坐标系 mm） */
export const AIRBAG_RECTS: AirbagRect[] = [
  { id: '40', color: 'green', regionHint: '肩背', x1: 198, y1: 400, x2: 802, y2: 487 },
  { id: '41', color: 'green', regionHint: '腰', x1: 198, y1: 519, x2: 802, y2: 606 },
  { id: '42', color: 'green', regionHint: '臀', x1: 198, y1: 637, x2: 802, y2: 726 },
  { id: '64', color: 'yellow', regionHint: '肩背', x1: 998, y1: 400, x2: 1602, y2: 487 },
  { id: '65', color: 'yellow', regionHint: '腰', x1: 998, y1: 519, x2: 1602, y2: 606 },
  { id: '66', color: 'yellow', regionHint: '臀', x1: 998, y1: 637, x2: 1602, y2: 726 },
  { id: '12', color: 'red', regionHint: '大腿', x1: 198, y1: 1497, x2: 802, y2: 1584 },
  { id: '13', color: 'red', regionHint: '大腿', x1: 998, y1: 1497, x2: 1602, y2: 1584 },
];

export interface AirbagSensor {
  id: number;
  /** 图中行 0-4（0=最上=头侧） */
  gridRow: number;
  /** 图中列 0-11（0=仰卧者最左） */
  gridCol: number;
  /** 仰卧者坐标系 mm */
  xMm: number;
  yMm: number;
  /** 所属气囊编号（行带近似划分：绿/黄区 行0-1→上带、行2→中带、行3-4→下带） */
  airbagId: string;
}

// 传感器列中心（仰卧者坐标系 mm，由 PDF 矢量圆换算：X_sleeper = 1800 - X_drawing）
const COL_X_MM = [47, 202, 358, 513, 668, 824, 979, 1134, 1290, 1445, 1600, 1756];
// 传感器行中心（仰卧者坐标系 mm，头→脚）
const ROW_Y_MM = [369, 585, 802, 1019, 1235];

/** 每格所属气囊：按 PDF 矢量颜色分区 + 行带近似划分 */
function airbagForCell(row: number, col: number): string {
  const greenRows = [0, 1]; // 行 0-1 → 上带（40/64）
  const isGreen = col <= 3 || (row === 4 && col === 4);
  const isRed = (col >= 4 && col <= 7) && !(row === 4 && col === 4);
  const isYellow = col >= 8 || (row === 4 && col === 7);
  if (isGreen) {
    const band = greenRows.includes(row) ? '0' : row === 2 ? '1' : '2';
    return ['40', '41', '42'][Number(band)];
  }
  if (isYellow) {
    const band = greenRows.includes(row) ? '0' : row === 2 ? '1' : '2';
    return ['64', '65', '66'][Number(band)];
  }
  if (isRed) {
    return COL_X_MM[col] < 900 ? '12' : '13';
  }
  // 行 4 的边界列按最近气囊归类
  if (col === 4) return '42';
  if (col === 7) return '66';
  return col < 6 ? '12' : '13';
}

// 传感器编号表（仰卧者视角，每行从最外侧读到中线，再读另一侧；
// 编号顺序来自布置图人工读取，颜色分区以 PDF 矢量为准）
const SENSOR_IDS_BY_ROW: number[][] = [
  [32, 33, 34, 35, 43, 14, 15, 67, 56, 57, 58, 59], // 行0：绿(0-3) 红(4-7) 黄(8-11)
  [24, 25, 26, 27, 4, 5, 6, 7, 48, 49, 50, 51],
  [36, 37, 38, 39, 16, 17, 18, 19, 60, 61, 62, 63],
  [28, 29, 30, 31, 8, 9, 10, 11, 52, 53, 54, 55],
  [20, 21, 22, 23, 0, 1, 2, 3, 44, 45, 46, 47],
];

function buildSensors(): AirbagSensor[] {
  const list: AirbagSensor[] = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 12; col++) {
      list.push({
        id: SENSOR_IDS_BY_ROW[row][col],
        gridRow: row,
        gridCol: col,
        xMm: Math.round(COL_X_MM[col]),
        yMm: Math.round(ROW_Y_MM[row]),
        airbagId: airbagForCell(row, col),
      });
    }
  }
  return list;
}

export const AIRBAG_SENSORS: AirbagSensor[] = buildSensors();

/** 气囊编号 → 传感器编号列表 */
export const AIRBAG_TO_SENSORS: Record<string, number[]> = {};
for (const sensor of AIRBAG_SENSORS) {
  (AIRBAG_TO_SENSORS[sensor.airbagId] ??= []).push(sensor.id);
}

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

// ---------------------------------------------------------------------------
// 坐标系转换助手（前端 2D 热力图 / 3D 场景统一使用）
// ---------------------------------------------------------------------------

/** 3D 场景：床中心为原点，X 仰卧者左(-0.9) → 右(+0.9)，Z 头(-1.0) → 脚(+1.0)，Y 向上 */
export function airbagRectTo3D(rect: AirbagRect): {
  x0: number;
  x1: number;
  z0: number;
  z1: number;
} {
  return {
    x0: (rect.x1 - BED_WIDTH_MM / 2) / 1000,
    x1: (rect.x2 - BED_WIDTH_MM / 2) / 1000,
    z0: -(BED_HEIGHT_MM / 2 - rect.y1) / 1000,
    z1: -(BED_HEIGHT_MM / 2 - rect.y2) / 1000,
  };
}

/** mm → 44×24 压力矩阵单元格（行=头→脚，列=仰卧者左→右；近似投影） */
export function mmToMatrixCell(xMm: number, yMm: number): { row: number; col: number } {
  return {
    row: Math.round((yMm / BED_HEIGHT_MM) * 43),
    col: Math.round((xMm / BED_WIDTH_MM) * 23),
  };
}
