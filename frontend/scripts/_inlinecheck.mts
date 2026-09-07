// temp: verify embedded 3D panel + heatmap airbag rects
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:5173/';
const OUT = path.resolve(process.cwd(), '../_screenshots');
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'pptr-'));

const browser = await puppeteer.launch({
  headless: false,
  executablePath: CHROME,
  args: [`--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check'],
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await page.goto(`${BASE}?c=inline3d#type=static&person=SAI&action=1&frame=8&mode=smooth&scale=auto`, {
    waitUntil: 'networkidle0',
  });
  await page.waitForSelector('.bed3d-inline canvas');
  await sleep(3500); // 模型加载 + 首帧渲染
  await page.screenshot({ path: path.join(OUT, 'inline-3d.png') });
  console.log('shot: inline-3d.png');

  // 切到压力曲线
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.vs-btn')] as HTMLElement[];
    btns.find((b) => b.textContent?.includes('压力曲线'))?.click();
  });
  await sleep(800);
  const chartVisible = await page.$('.chart-panel .chart-root') !== null;
  const inlineGone = await page.$('.bed3d-inline canvas') === null;
  console.log('after switch: chart visible =', chartVisible, ', inline hidden =', inlineGone);
  await page.screenshot({ path: path.join(OUT, 'inline-chart.png') });

  // 热力图气囊矩形存在性
  const rectCount = await page.evaluate(() => document.querySelectorAll('.airbag-rects rect').length);
  console.log('heatmap airbag rects:', rectCount);

  if (errors.length) {
    console.log('PAGE ERRORS:');
    for (const e of errors.slice(0, 8)) console.log('  ', e);
  } else {
    console.log('no page errors');
  }
} finally {
  await browser.close();
}
