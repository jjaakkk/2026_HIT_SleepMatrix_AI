/**
 * 验证改造后的模式语义：
 * 1. 实时推理默认：无设备输入 → 静止（等待设备输入，黑屏）
 * 2. 模拟设备推帧（POST /api/stream/ingest）→ 前端实时推理（睡姿卡=模型推理）
 * 3. 离线回放（#dataset= 或默认 demo 数据）→ 回放帧同样接推理（睡姿卡=模型推理）
 * 用法：node --experimental-strip-types scripts/verify-dataset-stream.ts
 */
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:4173';
const API = 'http://127.0.0.1:5000';

const browser = await puppeteer.launch({
  headless: 'shell',
  executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
});
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

const sample = () =>
  page.evaluate(() => {
    const body = document.body?.innerText ?? '';
    const pose = body.match(/(仰卧|俯卧|左侧卧|右侧卧)\s*模型推理/)?.[1] ?? null;
    const idle = body.includes('等待设备输入');
    const deviceStream = body.match(/设备流 · ([\w-]+)/)?.[1] ?? null;
    return { pose, idle, deviceStream };
  });

// --- 场景 1：实时推理 + 无输入（默认打开） ---
await page.goto(`${BASE}/#display=inference`, { waitUntil: 'domcontentloaded', timeout: 60000 });
await new Promise((r) => setTimeout(r, 4000));
const idleState = await sample();
console.log('场景1 无输入静止:', JSON.stringify(idleState));

// --- 场景 2：模拟设备推帧（持续推流中采样：应显示模型推理，且非 idle） ---
const fs = await import('node:fs');
const frames: number[][][] = [];
for (const file of ['dgs_1', 'dgs_10', 'dgs_16', 'dgs_7']) {
  const raw = fs.readFileSync(
    'W:\\Project\\sleep\\2026_HIT_SleepMatrix_AI\\dataset\\睡姿 区域划分data\\睡姿数据\\dgs\\' + file + '.txt',
    'utf-8',
  );
  const rows = raw.split(/\r?\n/).filter((l) => l.trim()).slice(0, 44);
  frames.push(rows.map((line) => line.split(',').map(Number)));
}
// 后台持续推帧（每 350ms 一帧，循环），期间采样
let push = true;
const pusher = (async () => {
  let i = 0;
  while (push) {
    await fetch(`${API}/api/stream/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pressure_matrix: frames[i % frames.length], source: 'verify-sim' }),
    });
    i++;
    await new Promise((r) => setTimeout(r, 350));
  }
})();
await new Promise((r) => setTimeout(r, 2500));
const liveState = await sample();
push = false;
await pusher;
console.log('场景2 设备推帧实时推理:', JSON.stringify(liveState));

// --- 场景 3：离线回放（demo 数据回放同样接推理） ---
await page.goto('about:blank');
await page.goto(`${BASE}/#display=demo&type=dynamic&autoplay=1`, {
  waitUntil: 'domcontentloaded',
  timeout: 60000,
});
await new Promise((r) => setTimeout(r, 4000));
const demoState = await sample();
console.log('场景3 离线回放接推理:', JSON.stringify(demoState));

await page.screenshot({ path: 'scripts/_verify_dataset_stream.png' });
await browser.close();
console.log('完成');
