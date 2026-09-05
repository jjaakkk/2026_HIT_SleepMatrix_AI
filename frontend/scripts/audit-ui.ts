// UI 视觉/交互审计：npm run audit:ui
// 无头浏览器做量化验证：布局溢出、关键元素可见性、主题切换、
// 下拉/分段控件/开关交互、播放推进、控制台错误。
import puppeteer from 'puppeteer';

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

/** WCAG 相对亮度 */
function lum(r: number, g: number, b: number): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(fg: string, bg: string): number {
  const p = (c: string): readonly [number, number, number] => {
    const hex = c.match(/^#([0-9a-f]{6})$/i);
    if (hex) {
      return [
        parseInt(hex[1].slice(0, 2), 16),
        parseInt(hex[1].slice(2, 4), 16),
        parseInt(hex[1].slice(4, 6), 16),
      ];
    }
    const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)/);
    if (!m) return [128, 128, 128];
    return [+m[1], +m[2], +m[3]];
  };
  const [r1, g1, b1] = p(fg);
  const [r2, g2, b2] = p(bg);
  const l1 = lum(r1, g1, b1);
  const l2 = lum(r2, g2, b2);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

const browser = await puppeteer.launch({ headless: 'shell' });
try {
  const page = await browser.newPage();
  const consoleErrors: string[] = [];
  /** /api 探针失败数（后端未启动时的预期降级行为，不计入控制台错误） */
  let apiProbeFailures = 0;
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + String(err)));
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/') && res.status() >= 400) apiProbeFailures += 1;
  });

  for (const [w, h, tag] of [
    [1920, 1080, '1920×1080'],
    [1600, 1000, '1600×1000'],
  ] as const) {
    await page.setViewport({ width: w, height: h });
    await page.goto(`${BASE}?c=audit-${tag}#type=static&person=SAI&action=1&frame=10&mode=smooth&scale=auto`, {
      waitUntil: 'networkidle0',
    });
    await page.waitForSelector('canvas');
    await sleep(900);

    const audit = (await page.evaluate(() => {
      const q = (sel: string) => document.querySelector(sel);
      const rect = (sel: string) => q(sel)?.getBoundingClientRect();
      const out: Record<string, unknown> = {};
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // 全局水平溢出检查：收集所有元素
      const hOverflow: string[] = [];
      document.querySelectorAll('*').forEach((el) => {
        const r = (el as HTMLElement).getBoundingClientRect();
        if (r.width > 4 && (r.right > vw + 1 || r.left < -1) && r.bottom > 0 && r.top < vh) {
          const cs = getComputedStyle(el);
          if (cs.position === 'fixed') return; // 下拉/工具提示浮层豁免
          hOverflow.push(`${el.tagName}.${(el.className + '').split(' ')[0]}(${Math.round(r.right)}>` + vw + ')');
        }
      });
      out.hOverflow = hOverflow.slice(0, 6);

      const heatmap = rect('.heatmap-panel');
      const canvas = rect('.heatmap-panel canvas');
      const rail = rect('.col-left');
      const right = rect('.col-right');
      const bottom = rect('.bottom');
      const chart = rect('.chart-panel canvas');
      const stageEl = q('.stage') as HTMLElement | null;

      out.sizes = {
        stageW: stageEl ? stageEl.offsetWidth : 0,
        stageH: stageEl ? stageEl.offsetHeight : 0,
        heatmapPanel: heatmap ? `${Math.round(heatmap.width)}×${Math.round(heatmap.height)}` : 'missing',
        heatmapCanvas: canvas ? `${Math.round(canvas.width)}×${Math.round(canvas.height)}` : 'missing',
        railW: rail ? Math.round(rail.width) : 0,
        rightW: right ? Math.round(right.width) : 0,
        bottomH: bottom ? Math.round(bottom.height) : 0,
        chartCanvas: chart ? `${Math.round(chart.width)}×${Math.round(chart.height)}` : 'missing',
      };

      // 纵向越界（bottom 行是否被挤出视口）
      out.bottomInView = bottom ? bottom.bottom <= vh + 1 : false;

      // 对比度抽查
      const css = getComputedStyle(document.documentElement);
      const bg = css.getPropertyValue('--surface-1').trim();
      const text1 = css.getPropertyValue('--text-1').trim();
      const text3 = css.getPropertyValue('--text-3').trim();
      const accent = css.getPropertyValue('--accent').trim();
      out.colors = { bg, text1, text3, accent };
      const railEl = q('.col-left') as HTMLElement | null;
      const rightEl = q('.col-right') as HTMLElement | null;
      out.railScrollable = railEl ? (railEl.scrollHeight > railEl.clientHeight ? 'scroll' : 'fit') : 'missing';
      out.rightScrollable = rightEl ? (rightEl.scrollHeight > rightEl.clientHeight ? 'scroll' : 'fit') : 'missing';

      // 指标卡数值是否渲染（非 '—'）
      const vals = [...document.querySelectorAll('.cards .value')].map((e) => e.textContent?.trim());
      out.metricVals = vals;

      // 图例
      out.legendBar = !!q('.legend-bar');
      // 分段控件滑动块是否已定位
      const thumb = q('.seg .thumb') as HTMLElement | null;
      out.thumbVisible = thumb ? thumb.style.opacity === '1' && thumb.style.width !== '0px' : false;
      return out;
    })) as {
      hOverflow: string[];
      sizes: {
        stageW: number;
        stageH: number;
        heatmapPanel: string;
        heatmapCanvas: string;
        railW: number;
        rightW: number;
        bottomH: number;
        chartCanvas: string;
      };
      bottomInView: boolean;
      colors: { bg: string; text1: string; text3: string; accent: string };
      railScrollable: string;
      rightScrollable: string;
      metricVals: string[];
      legendBar: boolean;
      thumbVisible: boolean;
    };

    console.log(`\n=== 布局审计 @ ${tag} ===`);
    check('无水平溢出', (audit.hOverflow as string[]).length === 0, JSON.stringify(audit.hOverflow));
    check(
      '设计空间固定 1920×1080（scale-to-fit 基座）',
      audit.sizes.stageW === 1920 && audit.sizes.stageH === 1080,
      `${audit.sizes.stageW}×${audit.sizes.stageH}`,
    );
    check('热力图画布存在且非零', /(\d+)×(\d+)/.test(audit.sizes.heatmapCanvas as string) && !/0×0/.test(audit.sizes.heatmapCanvas as string), String(audit.sizes.heatmapCanvas));
    check('底部行在视口内', audit.bottomInView as boolean);
    check('趋势图 canvas 存在', (audit.sizes.chartCanvas as string) !== 'missing');
    check('图例渐变条存在', audit.legendBar as boolean);
    check('分段控件滑动块已定位', audit.thumbVisible as boolean);
    check('指标卡数值已渲染', (audit.metricVals as string[]).length >= 4 && (audit.metricVals as string[]).every((v) => v !== '—'), JSON.stringify(audit.metricVals));

    // 对比度
    const c = audit.colors as { bg: string; text1: string; text3: string; accent: string };
    const r1 = contrast(c.text1, c.bg);
    const r3 = contrast(c.text3, c.bg);
    check('主文本对比度 ≥ 7（AAA）', r1 >= 7, `${r1.toFixed(1)}:1`);
    check('三级文本对比度 ≥ 4.5', r3 >= 4.5, `${r3.toFixed(1)}:1`);

    // 内部滚动条（用户要求：所有内容一屏呈现，不依赖滚轮）
    const scrollIssues = await page.evaluate(() => {
      const probes: Array<[string, string]> = [
        ['.col-left', ''],
        ['.col-right', '.insight .inner'],
        ['.chart-panel', '.chart-inner'],
        ['.airbag-panel', '.airbag'],
        ['.ranking-panel', '.ranking-inner'],
      ];
      const bad: string[] = [];
      for (const [rootSel, innerSel] of probes) {
        const root = document.querySelector(rootSel) as HTMLElement | null;
        if (!root) continue;
        const inner = innerSel ? (root.querySelector(innerSel) as HTMLElement | null) : root;
        if (!inner) continue;
        if (inner.scrollHeight > inner.clientHeight + 2) {
          bad.push(`${rootSel} ${innerSel} (${inner.scrollHeight} > ${inner.clientHeight})`);
        }
      }
      return bad;
    });
    check('无内部滚动条（内容一屏呈现）', scrollIssues.length === 0, JSON.stringify(scrollIssues));

    // 热力图容器收缩包裹（不留黑块）
    const wrapGap = await page.evaluate(() => {
      const wrap = document.querySelector('.heatmap-wrap') as HTMLElement | null;
      const canvas = document.querySelector('.heatmap-wrap canvas') as HTMLElement | null;
      if (!wrap || !canvas) return -1;
      return Math.abs(wrap.getBoundingClientRect().width - canvas.getBoundingClientRect().width);
    });
    check('热力图容器收缩包裹画布（无黑块）', wrapGap >= 0 && wrapGap <= 2, `偏差 ${wrapGap}px`);

    // 后代越界检测：每个面板的后代都不得溢出面板边界（重叠/溢出的机械判定）
    const outOfBounds = await page.evaluate(() => {
      const panels = [
        '.heatmap-panel',
        '.chart-panel',
        '.insight',
        '.airbag-panel',
        '.ranking-panel',
      ];
      const bad: string[] = [];
      for (const sel of panels) {
        const panel = document.querySelector(sel) as HTMLElement | null;
        if (!panel) continue;
        const pr = panel.getBoundingClientRect();
        const floatSel = '.tooltip, .pop, .tt-title';
        panel.querySelectorAll('*').forEach((el) => {
          const r = (el as HTMLElement).getBoundingClientRect();
          if (r.width === 0 && r.height === 0) return;
          const cs = getComputedStyle(el);
          if (cs.position === 'absolute' || cs.position === 'fixed') return; // 浮层/绝对定位豁免
          if (r.left < pr.left - 2 || r.right > pr.right + 2 || r.top < pr.top - 2 || r.bottom > pr.bottom + 2) {
            bad.push(`${sel} :: ${el.tagName}.${(el.className + '').split(' ')[0]} (${Math.round(r.right - pr.right)}px 越界)`);
          }
        });
      }
      return bad.slice(0, 8);
    });
    check('面板后代零越界（无重叠/溢出）', outOfBounds.length === 0, JSON.stringify(outOfBounds));
  }

  // ---- 交互审计 ----
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto(`${BASE}?c=interact#type=static&person=SAI&action=1&frame=10`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('canvas');
  await sleep(800);

  // 缩放适配：设计空间 1920×1080，整体等比缩放（无滚动条的关键保证）
  const scaleInfo = await page.evaluate(() => {
    const stage = document.querySelector('.stage') as HTMLElement | null;
    if (!stage) return null;
    const t = stage.style.transform;
    const m = t.match(/scale\(([\d.]+)\)/);
    return m ? Number(m[1]) : null;
  });
  check('scale-to-fit 缩放适配生效（<1）', scaleInfo !== null && scaleInfo > 0 && scaleInfo < 1, String(scaleInfo));

  // 渲染模式分段控件（位于热力图面板工具栏）
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.heatmap-panel .toolbar .seg button')] as HTMLElement[];
    btns.find((b) => b.textContent?.includes('网格'))?.click();
  });
  await sleep(400);
  const modeChip = await page.evaluate(() => document.querySelector('.mode-chip')?.textContent?.trim());
  check('渲染模式切换联动芯片', modeChip === '原始网格', String(modeChip));
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.heatmap-panel .toolbar .seg button')] as HTMLElement[];
    btns.find((b) => b.textContent?.includes('标准'))?.click();
  });
  await sleep(300);

  // 自定义下拉
  await page.click('.col-left .sel-root .trigger');
  await sleep(400);
  const popInfo = await page.evaluate(() => {
    const pop = document.querySelector('.pop') as HTMLElement | null;
    if (!pop) return null;
    const r = pop.getBoundingClientRect();
    return { w: Math.round(r.width), opts: pop.querySelectorAll('.opt').length, fixed: getComputedStyle(pop).position };
  });
  check('下拉弹层打开（fixed 定位）', !!popInfo && popInfo.fixed === 'fixed' && popInfo.opts >= 2, JSON.stringify(popInfo));
  const personBefore = await page.evaluate(() => document.querySelector('.col-left .trigger .val')?.textContent?.trim());
  await page.evaluate(() => {
    const opts = [...document.querySelectorAll('.pop .opt')] as HTMLElement[];
    opts[1]?.click();
  });
  await sleep(300);
  const personAfter = await page.evaluate(() => document.querySelector('.col-left .trigger .val')?.textContent?.trim());
  check('下拉选择生效', !!personBefore && !!personAfter && personBefore !== personAfter, `${personBefore} → ${personAfter}`);

  // 图层开关（芯片按钮）
  await page.evaluate(() => {
    const chips = document.querySelectorAll('.layer-grid .layer-chip') as NodeListOf<HTMLElement>;
    chips[0]?.click();
  });
  await sleep(300);
  const regionsHidden = await page.evaluate(() => document.querySelectorAll('.heatmap-panel .region').length === 0);
  check('图层开关（部位区域）生效', regionsHidden);
  await page.evaluate(() => {
    const chips = document.querySelectorAll('.layer-grid .layer-chip') as NodeListOf<HTMLElement>;
    chips[0]?.click();
  });
  await sleep(300);

  // 播放推进
  await page.click('.ctl.play');
  await sleep(1600);
  const frameAfterPlay = await page.evaluate(() => document.querySelector('.frame-num')?.textContent?.trim());
  const [a] = (frameAfterPlay ?? '0/0').split('/').map(Number);
  check('播放推进帧号', a > 0, String(frameAfterPlay));
  await page.click('.ctl.play');
  await sleep(300);

  // 区域点击联动
  await page.evaluate(() => {
    const rows = [...document.querySelectorAll('.ranking .row')] as HTMLElement[];
    rows[0]?.click();
  });
  await sleep(300);
  const regionLinked = await page.evaluate(() => ({
    selected: document.querySelector('.ranking .row.selected')?.textContent?.replace(/\s+/g, ' ').trim(),
    legendExtra: [...document.querySelectorAll('.chart-root .legend-item')].map((e) => e.textContent?.trim()),
  }));
  check('区域选择联动（排行高亮 + 曲线图例）', !!regionLinked.selected, JSON.stringify(regionLinked));

  // 速度切换
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.speed-seg button')] as HTMLElement[];
    btns.find((b) => b.textContent?.includes('4×'))?.click();
  });
  await sleep(300);
  const speedActive = await page.evaluate(() =>
    [...document.querySelectorAll('.speed-seg button')].find((b) => b.getAttribute('aria-pressed') === 'true')?.textContent?.trim(),
  );
  check('速度分段控件切换', speedActive === '4×', String(speedActive));

  // ---- 气囊：点击行选中 + 头部滑杆调节所选气囊 ----
  await page.evaluate(() => {
    const zones = [...document.querySelectorAll('.airbag .zone')] as HTMLElement[];
    zones.find((z) => z.querySelector('.zid')?.textContent === '40')?.click();
  });
  await sleep(250);
  const airbagTag = await page.evaluate(() => document.querySelector('.head-slider .zone-tag')?.textContent?.trim());
  check('气囊行选中 → 滑杆目标切换为所选气囊', airbagTag === '40 · 肩背', String(airbagTag));
  await page.evaluate(() => {
    const input = document.querySelector('.head-slider input') as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, '70');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await sleep(800); // 充气爬坡 600ms
  const airbagRows = await page.evaluate(() => {
    const read = (id: string) =>
      [...document.querySelectorAll('.airbag .zone')]
        .find((z) => z.querySelector('.zid')?.textContent === id)
        ?.textContent?.replace(/\s+/g, ' ')
        .trim();
    return { z40: read('40'), z41: read('41') };
  });
  check(
    '滑杆只调节所选气囊（40→70%、41 保持）',
    airbagRows.z40?.includes('70%') === true && !airbagRows.z41?.includes('70%'),
    JSON.stringify(airbagRows),
  );

  // 分段控件滑动块与激活按钮对齐精度（等待弹簧过渡完全沉降）
  await sleep(500);
  const thumbAlign = await page.evaluate(() => {
    const segs = [...document.querySelectorAll('.seg')] as HTMLElement[];
    let worst = 0;
    for (const seg of segs) {
      const wrap = seg.getBoundingClientRect();
      const thumb = seg.querySelector('.thumb')?.getBoundingClientRect();
      const active = [...seg.querySelectorAll('button')].find(
        (b) => b.getAttribute('aria-pressed') === 'true',
      )?.getBoundingClientRect();
      if (!thumb || !active || thumb.width === 0) continue;
      worst = Math.max(worst, Math.abs(thumb.left - active.left), Math.abs(thumb.width - active.width));
    }
    return Math.round(worst * 10) / 10;
  });
  check('分段控件滑动块对齐（偏差 < 2px）', thumbAlign < 2, `最大偏差 ${thumbAlign}px`);

  // 下拉键盘导航：重置为 SAI → 打开 → ↓↓ → Enter 应选中 wzh
  await page.click('.col-left .sel-root .trigger');
  await sleep(300);
  await page.evaluate(() => {
    const opts = [...document.querySelectorAll('.pop .opt')] as HTMLElement[];
    opts[0]?.click();
  });
  await sleep(300);
  await page.click('.col-left .sel-root .trigger');
  await sleep(300);
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await sleep(300);
  const kbPerson = await page.evaluate(() => document.querySelector('.col-left .trigger .val')?.textContent?.trim());
  check('下拉键盘导航（↓↓+Enter 切换）', kbPerson === 'wzh · 167 cm / 66 kg', String(kbPerson));

  // ---- 架构对齐检查（后端离线态，状态位于侧栏底部） ----
  const algoStatus = await page.evaluate(() =>
    [...document.querySelectorAll('.status-list .status-row')].map((b) =>
      b.textContent?.replace(/\s+/g, ' ').trim(),
    ),
  );
  check(
    '算法服务状态存在且为未连接态',
    algoStatus.some((t) => t?.includes('算法服务') && t.includes('未连接')),
    JSON.stringify(algoStatus),
  );
  const svmDisabled = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.seg button')] as HTMLButtonElement[];
    const b = btns.find((x) => x.textContent?.includes('SVM 推理'));
    return b ? b.disabled : null;
  });
  check('后端离线时 SVM 推理选项禁用', svmDisabled === true, String(svmDisabled));
  const weakRenamed = await page.evaluate(() =>
    [...document.querySelectorAll('.seg button')].some((b) => b.textContent?.includes('弱力')),
  );
  check('弱力可视化命名（与后端算法区分）', weakRenamed);

  const unexpectedErrors = consoleErrors.filter(
    (t) => !t.startsWith('Failed to load resource'),
  );
  check(
    '控制台无错误（豁免后端离线的 /api 探针失败）',
    unexpectedErrors.length === 0 && consoleErrors.length <= apiProbeFailures,
    `api探针失败 ${apiProbeFailures} 次 · 控制台错误 ${consoleErrors.length} 条：${consoleErrors.slice(0, 3).join(' | ')}`,
  );
} finally {
  await browser.close();
}

const fails = results.filter((r) => !r.pass);
console.log(`\n========== 审计结果：${results.length - fails.length}/${results.length} 通过 ==========`);
if (fails.length) {
  console.log('失败项：');
  for (const f of fails) console.log(`  ✗ ${f.name} — ${f.detail}`);
  process.exitCode = 1;
}
