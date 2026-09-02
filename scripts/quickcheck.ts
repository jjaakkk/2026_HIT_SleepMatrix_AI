// 快速自检脚本：npm run demo
// 用真实数据跑一遍 Phase 1 解析链，打印关键数字
import path from 'node:path';
import fs from 'node:fs';
import { parseTxt } from '../src/core/parsers/txt.ts';
import { parseDatasetJson, buildPlaybackList } from '../src/core/parsers/json.ts';
import { parseRegion, parseSpine } from '../src/core/parsers/annotations.ts';
import { computeMetrics, meanBackground, contactIndex, mirrorFrame } from '../src/core/metrics.ts';
import { actionToSleepPos, SLEEP_POS_NAMES } from '../src/core/types.ts';

const root =
  process.env.SLEEP_DATA_ROOT ??
  path.resolve(process.cwd(), '../睡姿 区域划分data/睡姿 区域划分data');
const load = (rel: string) => fs.readFileSync(path.join(root, rel), 'utf8');

console.log('=== 智能床垫 Phase 1 数据读取自检 ===\n');

// 1) txt 解析
const wzh10 = parseTxt(load('睡姿数据/wzh/wzh_10.txt'));
console.log(`[txt]  wzh_10.txt → ${wzh10.frames.length} 帧 × ${wzh10.frames[0].length} 值`);
const dyn = parseTxt(load('睡姿数据/wzh/whz_动态一.txt'));
console.log(`[txt]  whz_动态一.txt → ${dyn.frames.length} 帧 + ${dyn.labels.length} 个标签行（官方：忽视）`);
const wzh1 = parseTxt(load('睡姿数据/wzh/wzh_1.txt'));
const selfMirrorOk = wzh1.frames[15].every((v, i) => v === mirrorFrame(wzh1.frames[0])[i]);
console.log(`[增强] 仰卧镜像校验（wzh_1 帧15 = 帧0镜像）: ${selfMirrorOk ? '通过' : '不通过'}`);
const crossMirrorOk = wzh10.frames[15].every(
  (v, i) => v === mirrorFrame(parseTxt(load('睡姿数据/wzh/wzh_16.txt')).frames[0])[i],
);
console.log(`[增强] 侧卧跨动作镜像校验（动作10帧15 = 动作16帧0镜像）: ${crossMirrorOk ? '通过' : '不通过'}`);

// 2) json 解析（76MB）
const t0 = Date.now();
const records = parseDatasetJson(load('区域划分/data.json'));
console.log(`[json] data.json → ${records.length} 条记录，解析耗时 ${Date.now() - t0}ms`);
const list = buildPlaybackList(records.filter((r) => r.people === 0 && r.action === 1));
console.log(`[回放] SAI action1 原始帧序列：${list.map((r) => r.frame).join(',')}`);

// 3) 标注解析
const sai = records.find((r) => r.people === 0 && r.action === 1 && r.frame === 0 && !r.isMirrored)!;
const regions = parseRegion(sai.region);
console.log(
  '[region] SAI 仰卧:',
  regions.map((g) => (g.valid ? `${g.name}[列${g.x1}-${g.x2},行${g.y1}-${g.y2}]` : `${g.name}[na]`)).join('  '),
);
const spine = parseSpine(sai.spine)!;
console.log('[spine ] 5 点:', spine.map((p) => `(${p.x},${p.y})`).join(' '));

// 4) 指标
const bg = meanBackground(parseTxt(load('睡姿数据/SAI/SAI_空载.txt')).frames);
const m = computeMetrics(sai.data, bg, 20);
console.log(
  `[指标 ] SAI action1 frame0（扣空载，阈值20）: maxRaw=${m.maxRaw} 净最大=${m.maxNet.toFixed(0)} ` +
    `有效点=${m.activePoints} (${(m.contactRatio * 100).toFixed(1)}%) 平均净压=${m.meanNet.toFixed(1)} ` +
    `候选接触面指数=${contactIndex(m).toFixed(1)}`,
);

// 5) 动作↔睡姿映射抽查
console.log(
  '[睡姿 ] action 1→' + SLEEP_POS_NAMES[actionToSleepPos(1)!] +
    ' 7→' + SLEEP_POS_NAMES[actionToSleepPos(7)!] +
    ' 10→' + SLEEP_POS_NAMES[actionToSleepPos(10)!] +
    ' 16→' + SLEEP_POS_NAMES[actionToSleepPos(16)!],
);
console.log('\nPhase 1 自检完成 ✔');
