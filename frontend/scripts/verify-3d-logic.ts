// 3D 场景逻辑验证（无需 WebGL/GPU）：npm run verify:3d:logic
// 在页面中以 webgl:false 构建场景，验证模型加载、骨骼、睡姿 roll 与热力图纹理。
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:5173/';

const browser = await puppeteer.launch({ headless: 'shell' });
const failures: string[] = [];
function check(name: string, ok: boolean, detail: string) {
  console.log(`${ok ? '✓' : '✗'} ${name}: ${detail}`);
  if (!ok) failures.push(name);
}

try {
  const page = await browser.newPage();
  await page.goto(`${BASE}?c=logic3d`, { waitUntil: 'networkidle0' });

  const result = await page.evaluate(async () => {
    // 从 dev 服务器按需加载源码模块（浏览器侧运行，不走本文件打包）
    const bedPath = '/src/three/bed3d.ts';
    const heatPath = '/src/render/heatmap.ts';
    const mod = await import(/* @vite-ignore */ bedPath);
    const heat = await import(/* @vite-ignore */ heatPath);
    const canvas = document.createElement('canvas');
    const scene = new mod.Bed3DScene(canvas, { webgl: false });
    scene.start();

    // 已知帧：3 个非零单元（头/中/脚）
    const frame = new Float32Array(44 * 24);
    frame[0] = 100;
    frame[10 * 24 + 5] = 200;
    frame[40 * 24 + 20] = 50;
    scene.setFrame(frame);
    const before = scene.debugInfo() as Record<string, unknown>;

    await scene.loadBody('/models/RiggedFigure.glb');
    const loaded = scene.debugInfo() as Record<string, unknown>;

    // 等转体动画收敛后读取四种睡姿的 roll
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const rollOf = async (p: number) => {
      scene.setPosture(p as never);
      await sleep(1200);
      return (scene.debugInfo() as { roll: number }).roll;
    };
    const rolls: number[] = [];
    for (const p of [0, 1, 2, 3]) rolls.push(await rollOf(p));

    // 期望颜色：直接调用同一色带函数
    const scaleMax = Math.max(heat.computeFrameMax(frame), 80);
    const expected = heat.valueToColor(100, scaleMax, heat.GAMMA.smooth);

    return {
      before,
      loaded,
      rolls,
      expected: [Math.round(expected[0] * 255), Math.round(expected[1] * 255), Math.round(expected[2] * 255)],
    };
  });

  const tex = result.before.texture as {
    activeCells: number;
    coloredPx: number;
    samples: number[][];
  };
  check('热力图纹理按帧绘制', tex.activeCells === 3, `activeCells=${tex.activeCells}（期望 3）`);
  check('纹理像素数 = 3 格 × 16px', tex.coloredPx === 48, `coloredPx=${tex.coloredPx}（期望 48）`);
  check(
    '纹理颜色与 turbo 色带一致',
    tex.samples.length > 0 &&
      Math.abs(tex.samples[0][0] - result.expected[0]) < 2 &&
      Math.abs(tex.samples[0][1] - result.expected[1]) < 2 &&
      Math.abs(tex.samples[0][2] - result.expected[2]) < 2,
    `首采样=${tex.samples[0]?.slice(0, 3)} 期望=${result.expected}`,
  );

  const loaded = result.loaded as Record<string, unknown>;
  const box = loaded.modelBox as { min: number[]; max: number[] } | null;
  check('人体模型加载成功', loaded.modelLoaded === true, `modelLoaded=${loaded.modelLoaded}`);
  check('19 根骨骼齐全', loaded.boneCount === 19, `boneCount=${loaded.boneCount}`);
  check(
    '关键骨骼存在',
    ['torso_joint_1', 'torso_joint_3', 'arm_joint_L_1', 'leg_joint_R_2'].every((n) =>
      (loaded.bones as string[]).includes(n),
    ),
    '全部命中',
  );

  if (box) {
    const [x0, y0, z0] = box.min;
    const [x1, y1, z1] = box.max;
    const onMattress =
      y0 >= 0.15 && y1 <= 0.75 && z0 >= -1.05 && z1 <= 1.05 && x0 >= -0.75 && x1 <= 0.75;
    check(
      '人体贴放于床垫之上',
      onMattress,
      `box=[${box.min.map((v) => v.toFixed(2))}]..[${box.max.map((v) => v.toFixed(2))}]（床面 y=0.16，床 z∈±1.1）`,
    );
    const len = Math.max(z1 - z0, x1 - x0, y1 - y0);
    check('人体长度合理（≈1.72m）', Math.abs(len - 1.72) < 0.25, `maxExtent=${len.toFixed(2)}`);
  } else {
    check('人体包围盒存在', false, 'modelBox=null');
  }

  const expectRoll = [0, Math.PI, -Math.PI / 2, Math.PI / 2];
  check(
    '四种睡姿 roll 值正确（仰卧=0 俯卧=π 左侧卧=-π/2 右侧卧=+π/2）',
    result.rolls.every((v, i) => Math.abs(v - expectRoll[i]) < 0.05),
    `rolls=${result.rolls.map((v) => v.toFixed(3)).join(',')}`,
  );
  check(
    '转体动画已收敛（仰卧 0 与俯卧 π 差异显著）',
    Math.abs(result.rolls[0] - result.rolls[1]) > 2.5,
    `Δ=${Math.abs(result.rolls[0] - result.rolls[1]).toFixed(3)}`,
  );
} finally {
  await browser.close();
}

if (failures.length) {
  console.log(`\n✗ 失败 ${failures.length} 项: ${failures.join('、')}`);
  process.exit(1);
}
console.log('\n✓ 3D 场景逻辑验证全部通过');
