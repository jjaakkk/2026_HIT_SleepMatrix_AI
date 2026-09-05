// 前后端端到端联调：npm run e2e:backend
// 前置：后端已启动（dev/arch 的 backend/app.py，127.0.0.1:5000）+ 前端 preview（4173）。
// 后端不可达时跳过（退出码 0），由 audit:ui 覆盖离线降级路径。
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
let health: { status: string; posture_svm: { model_available: boolean } };
try {
  const res = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(3000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  health = (await res.json()) as typeof health;
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

// ---- UI 层检查 ----
const browser = await puppeteer.launch({ headless: 'shell' });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto(`${BASE}?c=e2e#type=static&person=SAI&action=1&frame=10`, {
    waitUntil: 'networkidle0',
  });
  await page.waitForSelector('canvas');
  await sleep(1500); // 等待健康探测完成

  const badges = await page.evaluate(() =>
    [...document.querySelectorAll('.topbar .badge')].map((b) => b.textContent?.replace(/\s+/g, ' ').trim()),
  );
  check('顶栏显示「算法服务 · 已连接」', badges.some((t) => t?.includes('算法服务 · 已连接')), JSON.stringify(badges));
  check(
    '契约版本不一致徽章未出现',
    !badges.some((t) => t?.includes('契约版本不一致')),
  );

  const svmState = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLButtonElement[];
    const b = btns.find((x) => x.textContent?.includes('SVM 推理'));
    return b ? { disabled: b.disabled, pressed: b.getAttribute('aria-pressed') } : null;
  });
  check('后端在线时 SVM 推理选项可用', svmState?.disabled === false, JSON.stringify(svmState));

  // 切换到 SVM 推理
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLElement[];
    btns.find((x) => x.textContent?.includes('SVM 推理'))?.click();
  });
  await sleep(800);
  const srcBadge = await page.evaluate(() => document.querySelector('.pose-card .src-badge')?.textContent?.trim());
  check('睡姿卡显示识别来源徽章', !!srcBadge, String(srcBadge));

  if (!health.posture_svm.model_available) {
    // 模型缺失：连续换帧触发 3 次失败 → 自动降级回记录标签
    for (let i = 0; i < 3; i++) {
      await page.evaluate(() => {
        const btns = [...document.querySelectorAll('.transport .ctl')] as HTMLElement[];
        btns[2]?.click(); // 下一帧
      });
      await sleep(700);
    }
    await sleep(500);
    const after = await page.evaluate(() => ({
      badges: [...document.querySelectorAll('.topbar .badge')].map((b) => b.textContent?.replace(/\s+/g, ' ').trim()),
      activePoseSource: [...document.querySelectorAll('.seg button')].find(
        (b) => b.getAttribute('aria-pressed') === 'true' && b.textContent?.includes('SVM 推理'),
      )?.textContent?.trim(),
    }));
    check(
      '连续推理失败后自动降级（徽章回退未连接 + 切回记录标签）',
      after.badges.some((t) => t?.includes('未连接')) && after.activePoseSource === undefined,
      JSON.stringify(after),
    );
  }
} finally {
  await browser.close();
}

const fails = results.filter((r) => !r.pass);
console.log(`\n========== 端到端联调：${results.length - fails.length}/${results.length} 通过 ==========`);
if (fails.length) {
  for (const f of fails) console.log(`  ✗ ${f.name} — ${f.detail}`);
  process.exitCode = 1;
}
