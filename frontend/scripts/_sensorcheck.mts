// temp: headed screenshot of the main screen with sensor overlay
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:5173/';
const OUT = path.resolve(process.cwd(), '../_screenshots/airbag-sensors.png');
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
  await page.goto(`${BASE}?c=sensorcheck#type=static&person=SAI&action=1&frame=8&mode=smooth&scale=auto`, {
    waitUntil: 'networkidle0',
  });
  await page.waitForSelector('.sensor-toggle');
  await sleep(1200);
  await page.screenshot({ path: OUT });
  console.log('screenshot ->', OUT);
  // 页面错误收集
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await sleep(800);
  if (errors.length) {
    console.log('PAGE ERRORS:');
    for (const e of errors.slice(0, 6)) console.log('  ', e);
  } else {
    console.log('no page errors');
  }
} finally {
  await browser.close();
}
