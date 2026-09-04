// 可视化验证脚本：npm run capture
// 用无头浏览器打开构建产物，对真实数据集回放进行截图 + 播放推进数值验证
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:4173/';
const OUT_DIR = path.resolve(process.cwd(), '../_screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// 场景：[文件名, hash 状态]
const scenarios: [string, string][] = [
  ['01-仰卧-标准', '#type=static&action=1&frame=8&mode=smooth&scale=fixed250'],
  ['02-俯卧-标准', '#type=static&action=7&frame=10&mode=smooth&scale=fixed250'],
  ['03-左侧卧-标准', '#type=static&action=10&frame=8&mode=smooth&scale=fixed250'],
  ['04-右侧卧-标准', '#type=static&action=16&frame=8&mode=smooth&scale=fixed250'],
  ['05-仰卧-弱力增强', '#type=static&action=1&frame=8&mode=weak&scale=fixed250'],
  ['06-仰卧-原始网格', '#type=static&action=1&frame=8&mode=grid&scale=fixed250'],
  ['07-仰卧-自动量程', '#type=static&action=1&frame=8&mode=smooth&scale=auto'],
  ['08-动态过程', '#type=dynamic&frame=80&mode=smooth&scale=fixed250'],
  ['11-指标卡与曲线-仰卧', '#type=static&action=1&frame=10&mode=smooth&scale=auto'],
  ['12-指标卡与曲线-动态播放中', '#type=dynamic&frame=15&mode=smooth&scale=auto&autoplay=1'],
  ['13-区域叠加-仰卧', '#type=static&action=1&frame=8&mode=smooth&scale=auto'],
  ['14-区域叠加-左侧卧', '#type=static&action=10&frame=8&mode=smooth&scale=auto'],
  ['15-区域选中-臀部', '#type=static&action=1&frame=10&mode=smooth&scale=auto&region=3'],
  ['16-小腿部标注-SAI', '#type=static&action=1&frame=8&mode=smooth&scale=auto&calf=1'],
  ['17-睡姿卡-仰卧', '#type=static&person=SAI&action=1&frame=10&mode=smooth&scale=auto'],
  ['18-睡姿卡-离床无人', '#type=static&person=SAI&action=0&frame=5&mode=smooth&scale=auto'],
  ['19-用户切换-wzh右侧卧', '#type=static&person=wzh&action=16&frame=8&mode=smooth&scale=auto'],
];

const browser = await puppeteer.launch({ headless: 'shell' });
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });

  for (const [name, hash] of scenarios) {
    // 用查询参数做 cache-buster：同源 URL 仅变 hash 不会触发重新加载，
    // 必须保证每次都是全新的文档加载，hash 状态才会被重新应用
    await page.goto(`${BASE}?c=${encodeURIComponent(name)}${hash}`, { waitUntil: 'networkidle0' });
    await page.waitForSelector('canvas');
    await sleep(700); // 等待热力图渲染
    const out = path.join(OUT_DIR, `${name}.png`);
    await page.screenshot({ path: out });
    console.log(`✓ ${name} → ${out}`);
  }

  // 播放模拟：点播放按钮，验证帧号确实推进（数值验证）
  await page.goto(`${BASE}?c=playback#type=static&action=1&frame=0`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('.ctl.play');
  await sleep(700);
  const before = await page.$eval('.frame-num', (el) => el.textContent?.trim());
  await page.click('.ctl.play');
  await sleep(2000); // 10fps × 2s ≈ 20 帧
  const after = await page.$eval('.frame-num', (el) => el.textContent?.trim());
  const playing = await page.$eval('.ctl.play', (el) => el.textContent?.trim());
  const shot = path.join(OUT_DIR, '09-播放中.png');
  await page.screenshot({ path: shot });
  console.log(`\n[播放模拟] 播放前: ${before} → 播放2秒后: ${after}（按钮显示 ${playing}）`);
  const [a0, a1] = (after ?? '0/0').split('/').map(Number);
  if (a0 > 0) console.log(`✓ 帧号已从 ${before} 推进到 ${after}，回放引擎工作正常`);
  else console.log(`✗ 帧号未推进，需要排查`);

  // 1920×1080 大屏整体效果
  await page.setViewport({ width: 1920, height: 1080 });
  await page.goto(`${BASE}?c=bigscreen#type=static&person=SAI&action=1&frame=10&mode=smooth&scale=auto`, {
    waitUntil: 'networkidle0',
  });
  await page.waitForSelector('canvas');
  await sleep(700);
  await page.screenshot({ path: path.join(OUT_DIR, '20-大屏1920-整体.png') });
  console.log('✓ 20-大屏1920-整体 已截图');

  // 4× 倍速 + 动态过程播放中截图
  await page.goto(`${BASE}?c=dynamic4x#type=dynamic&frame=30`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('.speed-seg button');
  await sleep(700);
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.speed-seg button')] as HTMLElement[];
    btns.find((b) => b.textContent?.includes('4×'))?.click();
  });
  await page.click('.ctl.play');
  await sleep(1500);
  await page.screenshot({ path: path.join(OUT_DIR, '10-动态过程-4倍速播放中.png') });
  console.log('✓ 10-动态过程-4倍速播放中 已截图');
} finally {
  await browser.close();
}
console.log('\n截图完成，输出目录:', OUT_DIR);
