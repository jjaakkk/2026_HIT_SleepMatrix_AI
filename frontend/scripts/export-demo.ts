// 导出浏览器演示数据集：npm run export:demo
// 从全量 data.json / txt 生成 public/data/demo.json（紧凑子集，随仓库提交）
import fs from 'node:fs';
import path from 'node:path';
import { parseTxt } from '../src/core/parsers/txt.ts';
import { parseDatasetJson, buildPlaybackList } from '../src/core/parsers/json.ts';
import { meanBackground } from '../src/core/metrics.ts';
import { dataRoot } from './paths.ts';

const root = dataRoot();
const load = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

// 成员身高体重（readme）
const MEMBERS: Record<string, [number, number]> = {
  SAI: [188, 105],
  wzh: [167, 66],
};

// 演示子集：两人（SAI/wzh）四代表动作 + SAI 空载（无人状态演示）+ wzh 动态过程前 40 帧
const PEOPLE: { name: string; actions: number[]; includeEmpty: boolean }[] = [
  { name: 'SAI', actions: [1, 7, 10, 16], includeEmpty: true },
  { name: 'wzh', actions: [1, 7, 10, 16], includeEmpty: false },
];
const DYNAMIC_PERSON = 'wzh';
const DYNAMIC_FRAMES = 80; // 覆盖仰卧→左侧卧→仰卧→俯卧段，睡姿事件条可展示多色分段

console.log('=== 导出浏览器演示数据集 ===');

// 1) 全量 json（76MB，约 2-3s）
const records = parseDatasetJson(load('区域划分/data.json'));

// 2) 校验所有压力值都是整数（压缩为 int 数组）
let allInt = true;
for (const r of records.slice(0, 100)) {
  for (const v of r.data) if (!Number.isInteger(v)) { allInt = false; break; }
  if (!allInt) break;
}
console.log('压力值均为整数:', allInt);

const people = [];
for (const { name, actions, includeEmpty } of PEOPLE) {
  const bg = meanBackground(parseTxt(load(`睡姿数据/${name}/${name}_空载.txt`)).frames);
  const [height, weight] = MEMBERS[name] ?? [null, null];
  const actionList = [];
  if (includeEmpty) {
    // 空载动作：用于"离床/无人"状态演示（action 0）
    actionList.push({
      action: 0,
      sleepPos: -1,
      region: '',
      spine: '',
      frames: parseTxt(load(`睡姿数据/${name}/${name}_空载.txt`)).frames.map((f) => Array.from(f)),
    });
  }
  for (const a of actions) {
    const recs = buildPlaybackList(records.filter((r) => r.peopleName === name && r.action === a));
    actionList.push({
      action: a,
      sleepPos: recs[0]?.sleepPos ?? -1,
      region: recs[0]?.region ?? '',
      spine: recs[0]?.spine ?? '',
      frames: recs.map((r) => Array.from(r.data)),
    });
  }
  people.push({ name, height, weight, bg: Array.from(bg), actions: actionList });
}

// 3) 动态过程（文件名不规则，如 wzh 目录下为 whz_动态一.txt，扫描匹配）
const dynDir = path.join(root, '睡姿数据', DYNAMIC_PERSON);
const dynFile = fs.readdirSync(dynDir).find((f) => f.includes('动态') && f.endsWith('.txt'));
if (!dynFile) throw new Error(`${DYNAMIC_PERSON} 目录下未找到动态文件`);
const dyn = parseTxt(load(`睡姿数据/${DYNAMIC_PERSON}/${dynFile}`));
const dynBg = meanBackground(parseTxt(load(`睡姿数据/${DYNAMIC_PERSON}/${DYNAMIC_PERSON}_空载.txt`)).frames);
const dynamic = {
  person: DYNAMIC_PERSON,
  bg: Array.from(dynBg), // 动态帧指标同样扣该人空载背景
  frames: dyn.frames.slice(0, DYNAMIC_FRAMES).map((f) => Array.from(f)),
  labels: dyn.labels.slice(0, DYNAMIC_FRAMES), // 官方：忽视，仅保留
};

const demo = {
  meta: {
    matrix: '44x24',
    generatedAt: new Date().toISOString(),
    note: '演示子集：SAI 四睡姿原始帧 + wzh 动态过程前40帧；完整数据用 npm run export:full 生成本地版本',
  },
  people,
  dynamic,
};

const outDir = path.resolve(process.cwd(), 'public/data');
fs.mkdirSync(outDir, { recursive: true });
const outPath = path.join(outDir, 'demo.json');
fs.writeFileSync(outPath, JSON.stringify(demo));
const kb = (fs.statSync(outPath).size / 1024).toFixed(0);
console.log(`已写出 ${outPath}（${kb} KB）`);
console.log(
  `内容：${people
    .map((p) => `${p.name} ${p.actions.reduce((s, a) => s + a.frames.length, 0)} 帧`)
    .join('、')} + ${dynamic.frames.length} 动态帧`,
);
