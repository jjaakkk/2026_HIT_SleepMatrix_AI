// 3D 睡姿视图可视化验证：npm run verify:3d
// 打开大屏 → 点击"打开 3D 睡姿视图" → 依次切换四种睡姿并截图
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:5173/';
const OUT_DIR = path.resolve(process.cwd(), '../_screenshots');
fs.mkdirSync(OUT_DIR, { recursive: true });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// 无 GPU 环境（CI/无头）下用 SwiftShader 软件渲染 WebGL
const browser = await puppeteer.launch({
  headless: 'shell',
  args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  // 错误收集需在导航前挂载
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await page.goto(
    `${BASE}?c=verify3d#type=static&person=SAI&action=1&frame=8&mode=smooth&scale=auto`,
    { waitUntil: 'networkidle0' },
  );
  await page.waitForSelector('.d3-open');
  await page.click('.d3-open');
  await page.waitForSelector('.bed3d canvas');
  await sleep(2000); // 等待 GLB 加载与首帧渲染

  // 无 WebGL 环境（无 GPU 的 CI/无头）时优雅跳过截图，逻辑验证用 verify:3d:logic
  const webglError = await page.evaluate(() => {
    const el = document.querySelector('.bed3d-error');
    return el ? el.textContent?.trim() : null;
  });
  if (webglError && webglError.includes('WebGL')) {
    console.log(`[跳过] 当前环境不支持 WebGL，无法截图（${webglError.slice(0, 60)}…）`);
    console.log('      场景逻辑请改用 npm run verify:3d:logic 验证');
    await browser.close();
    process.exit(0);
  }

  const postures = ['仰卧', '俯卧', '左侧卧', '右侧卧'];
  for (const name of postures) {
    await page.evaluate((label) => {
      const btns = [...document.querySelectorAll('.pose-chip')] as HTMLElement[];
      btns
        .find((b) => b.textContent?.trim() === label && !b.classList.contains('util'))
        ?.click();
    }, name);
    await sleep(1500); // 等待转体过渡动画
    const out = path.join(OUT_DIR, `3d-${name}.png`);
    await page.screenshot({ path: out });
    console.log(`✓ 3d-${name} → ${out}`);
  }

  // 页面控制台错误收集（模型加载/WebGL 报错会在此出现）
  await sleep(500);
  if (errors.length) {
    console.log('[页面错误]');
    for (const e of errors.slice(0, 10)) console.log('  ', e);
  } else {
    console.log('✓ 无页面报错');
  }
} finally {
  await browser.close();
}
console.log('截图完成，输出目录:', OUT_DIR);
