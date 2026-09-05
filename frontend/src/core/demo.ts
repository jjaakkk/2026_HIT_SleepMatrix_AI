/** 演示数据集类型（App 与各面板共享） */
export interface DemoAction {
  action: number;
  sleepPos: number;
  region: string;
  spine: string;
  frames: number[][];
}

export interface DemoPerson {
  name: string;
  height: number | null;
  weight: number | null;
  bg: number[];
  actions: DemoAction[];
}

export interface DemoData {
  people: DemoPerson[];
  dynamic: { person: string; bg: number[]; frames: number[][]; labels: number[] };
}
