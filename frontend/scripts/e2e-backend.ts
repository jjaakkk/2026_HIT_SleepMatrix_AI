// 前后端端到端联调：npm run e2e:backend
// 前置：后端已启动（backend/app.py，127.0.0.1:5000）+ 前端 preview（4173）。
// 后端不可达时跳过（退出码 0），由 audit:ui 覆盖离线降级路径。
//
// 数据模式语义（frontend/src/composables/useFrameInference.ts）：
//   实时推理（默认）：动态翻身序列作为模拟实时流循环播放，/api/frame/analyze 逐帧分析驱动界面；
//   离线回放：播放预存数据，仅此模式显示 数据源/回放/受测者/姿态记录 选择器，用记录标签与标注渲染。
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import puppeteer from 'puppeteer';

const API = 'http://127.0.0.1:5000';
const BASE = 'http://localhost:4173/';
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

interface Check {
  name: string;
  pass: boolean;
  detail: string;
}
const results: Check[] = [];
function check(name: string, pass: boolean, detail = '') {
  results.push({ name, pass, detail });
  console.log(`${pass ? '✓' : '✗'} ${name}${detail ? ' — ' + detail : ''}`);
}

// ---- 前置：后端可达性 ----
interface HealthInfo {
  status: string;
  posture_svm: { model_available: boolean };
  models: { body_partition: { model_available: boolean } };
}
let health: HealthInfo;
try {
  const res = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(3000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  health = (await res.json()) as HealthInfo;
} catch (e) {
  console.log(`⊙ 后端未启动（${e instanceof Error ? e.message : e}），跳过端到端联调；离线路径由 audit:ui 覆盖`);
  process.exit(0);
}

console.log(`后端在线：${JSON.stringify(health)}\n`);

// ---- API 层检查 ----
check('/api/health 返回 status=ok', health.status === 'ok');

const contractRes = await fetch(`${API}/api/contracts/posture`);
check('/api/contracts/posture 可访问', contractRes.ok, `HTTP ${contractRes.status}`);
const remoteContract = (await contractRes.json()) as Record<string, unknown>;

const vendoredPath = path.resolve(import.meta.dirname, '../src/core/contracts/posture.json');
const vendored = JSON.parse(fs.readFileSync(vendoredPath, 'utf8')) as Record<string, unknown>;
let contractMatches = true;
let contractDetail = `version=${String(remoteContract.contract_version)}`;
try {
  // Flask 默认按字母序序列化键，字节序与文件不同：用深度语义比较
  assert.deepEqual(remoteContract, vendored);
} catch (e) {
  contractMatches = false;
  contractDetail = e instanceof Error ? e.message.slice(0, 200) : String(e);
}
check('远端契约与前端 vendored 副本语义一致', contractMatches, contractDetail);

// ---- 预测端点（模型缺失 → 503 model_unavailable）----
const predRes = await fetch(`${API}/api/posture/predict`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ pressure_matrix: Array.from({ length: 44 }, () => new Array(24).fill(5)) }),
});
let predBody: Record<string, unknown> | null = null;
try {
  predBody = (await predRes.json()) as Record<string, unknown>;
} catch {
  /* ignore */
}
if (health.posture_svm.model_available) {
  check('预测端点返回 200（模型可用）', predRes.ok, JSON.stringify(predBody ?? {}));
} else {
  check(
    '预测端点返回 503 model_unavailable（模型缺失）',
    predRes.status === 503 && predBody?.error === 'model_unavailable',
    `HTTP ${predRes.status} ${JSON.stringify(predBody ?? {})}`,
  );
}

// ---- 聚合分析端点：分区/增强应可用，睡姿按模型状态 ----
const analyzeRes = await fetch(`${API}/api/frame/analyze`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    pressure_matrix: Array.from({ length: 44 }, () => new Array(24).fill(40)),
    features: ['posture', 'partition', 'enhance'],
    model: 'ensemble',
  }),
});
check('/api/frame/analyze 返回 200', analyzeRes.ok, `HTTP ${analyzeRes.status}`);
const analyzeBody = (await analyzeRes.json()) as {
  posture?: Record<string, unknown>;
  partition?: Record<string, unknown>;
  enhanced?: Record<string, unknown>;
};
const partitionOk = analyzeBody.partition !== undefined && !('error' in analyzeBody.partition);
const postureOk = analyzeBody.posture !== undefined && !('error' in analyzeBody.posture);
const enhanceOk = analyzeBody.enhanced !== undefined && !('error' in analyzeBody.enhanced);
check(
  'analyze 分区模块返回结果',
  partitionOk === health.models.body_partition.model_available,
  JSON.stringify({ partitionOk, expected: health.models.body_partition.model_available }),
);
check('analyze 增强模块返回结果', enhanceOk, 'enhanced_matrix 44×24');

// ---- UI 层检查 ----
// 实时推理模式持续发起 /api 请求（串行自续），页面网络永不空闲：
// 导航用 waitUntil:'load'，禁止 networkidle0。
const browser = await puppeteer.launch({ headless: 'shell' });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto(`${BASE}?c=e2e#display=inference`, { waitUntil: 'load' });
  await page.waitForSelector('canvas');
  await sleep(1500); // 等待健康探测完成

  const badges = await page.evaluate(() =>
    [...document.querySelectorAll('.status-list .status-row')].map((b) => b.textContent?.replace(/\s+/g, ' ').trim()),
  );
  check('侧栏状态显示「算法服务在线」', badges.some((t) => t?.includes('算法服务在线')), JSON.stringify(badges));
  check('契约版本不一致警告未出现', !badges.some((t) => t?.includes('契约版本不一致')));

  // 默认数据模式 = 实时推理
  const segState = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLButtonElement[];
    const b = btns.find((x) => x.textContent?.includes('实时推理'));
    return b ? { disabled: b.disabled, pressed: b.getAttribute('aria-pressed') } : null;
  });
  check('默认数据模式为「实时推理」', segState?.pressed === 'true' && segState?.disabled === false, JSON.stringify(segState));

  // 实时推理模式下不显示离线回放选择器
  const realtimeSidebar = await page.evaluate(() => document.querySelector('.col-left')?.textContent ?? '');
  check(
    '实时推理模式隐藏「数据源/回放」选择器',
    !realtimeSidebar.includes('数据源') && !realtimeSidebar.includes('姿态动作'),
  );
  // 模拟实时流自动播放
  const frameBefore = await page.$eval('.frame-num', (el) => el.textContent?.trim() ?? '');
  await sleep(1200);
  const frameAfter = await page.$eval('.frame-num', (el) => el.textContent?.trim() ?? '');
  check('实时推理模式模拟流自动播放（帧号推进）', frameBefore !== frameAfter, `${frameBefore} → ${frameAfter}`);

  await sleep(2000); // 等待逐帧分析（350ms 节流 + 网络往返）完成

  // 分区模型就绪 → 热力图区域与掩码应来自模型推理
  const partitionUi = await page.evaluate(() => ({
    chip: [...document.querySelectorAll('.region-source-chip')].map((e) => e.textContent?.trim()),
    maskCells: document.querySelectorAll('.partition-mask rect').length,
    regionRects: document.querySelectorAll('.overlay .region').length,
  }));
  if (health.models.body_partition.model_available) {
    check(
      '分区推理驱动热力图：掩码覆盖层与区域矩形存在',
      partitionUi.maskCells > 0 && partitionUi.regionRects > 0,
      JSON.stringify(partitionUi),
    );
    check('区域来源徽章显示「模型推理」', partitionUi.chip.includes('区域 · 模型推理'), JSON.stringify(partitionUi));
  }

  // 睡姿卡：模型可用 → 模型推理徽章；缺失 → 回退记录标签
  const poseNote = await page.evaluate(() => document.querySelector('.pose-card .note')?.textContent?.trim() ?? '');
  if (health.posture_svm.model_available) {
    const srcBadge = await page.evaluate(() => document.querySelector('.pose-card .src-badge')?.textContent?.trim());
    check('睡姿卡显示「模型推理」来源徽章', srcBadge === '模型推理', String(srcBadge));
  } else {
    check(
      '睡姿模型缺失 → 睡姿卡回退记录标签',
      poseNote.includes('睡姿模型不可用') && poseNote.includes('记录标签'),
      String(poseNote),
    );
  }

  // 切换到离线回放模式：回放选择器出现、区域回退记录标注、掩码移除
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLElement[];
    btns.find((x) => x.textContent?.includes('离线回放'))?.click();
  });
  await sleep(500);
  const demoUi = await page.evaluate(() => ({
    sidebar: document.querySelector('.col-left')?.textContent ?? '',
    chip: [...document.querySelectorAll('.region-source-chip')].map((e) => e.textContent?.trim()),
    maskCells: document.querySelectorAll('.partition-mask rect').length,
  }));
  check(
    '离线回放模式：回放选择器出现、掩码移除、来源回退「记录标注」',
    demoUi.sidebar.includes('数据源') &&
      demoUi.sidebar.includes('姿态动作') &&
      demoUi.maskCells === 0 &&
      demoUi.chip.includes('区域 · 记录标注'),
    JSON.stringify({ chip: demoUi.chip, maskCells: demoUi.maskCells }),
  );

  // 切回实时推理（按钮恢复可用性）
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLElement[];
    btns.find((x) => x.textContent?.includes('实时推理'))?.click();
  });
  await sleep(300);
  const backState = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLButtonElement[];
    const b = btns.find((x) => x.textContent?.includes('实时推理'));
    return b?.getAttribute('aria-pressed');
  });
  check('可切回「实时推理」模式', backState === 'true', String(backState));

  // 带回放参数的演示直链隐含「离线回放」模式
  await page.goto(`${BASE}?c=e2e-playback#type=static&person=SAI&action=1&frame=10`, { waitUntil: 'load' });
  await page.waitForSelector('canvas');
  await sleep(1500);
  const playbackState = await page.evaluate(() => ({
    demoPressed: [...document.querySelectorAll('.seg button')].find(
      (b) => b.textContent?.includes('离线回放'),
    )?.getAttribute('aria-pressed'),
    pose: document.querySelector('.pose-card .pose-name')?.textContent?.trim(),
    chip: [...document.querySelectorAll('.region-source-chip')].map((e) => e.textContent?.trim()),
  }));
  check(
    '回放参数直链进入「离线回放」（睡姿卡=记录标签）',
    playbackState.demoPressed === 'true' && playbackState.pose === '仰卧',
    JSON.stringify(playbackState),
  );
} finally {
  await browser.close();
}

const fails = results.filter((r) => !r.pass);
console.log(`\n========== 端到端联调：${results.length - fails.length}/${results.length} 通过 ==========`);
if (fails.length) {
  for (const f of fails) console.log(`  ✗ ${f.name} — ${f.detail}`);
  process.exitCode = 1;
}
