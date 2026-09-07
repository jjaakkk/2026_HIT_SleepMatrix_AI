// 3D 场景逻辑验证（无需 WebGL/GPU）：npm run verify:3d:logic
// 在页面中以 webgl:false 构建场景，验证模型加载、骨骼、睡姿 roll、贴床、
// 屏幕可见性（NDC 投影）与肢体姿态（屈膝/伸直）。
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
    const bedPath = '/src/three/bed3d.ts';
    const heatPath = '/src/render/heatmap.ts';
    const mod = await import(/* @vite-ignore */ bedPath);
    const heat = await import(/* @vite-ignore */ heatPath);
    const canvas = document.createElement('canvas');
    canvas.width = 1200;
    canvas.height = 750;
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

    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const dist = (a: number[], b: number[]) =>
      Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

    const perPosture: Record<string, unknown>[] = [];
    for (const p of [0, 1, 2, 3]) {
      scene.setPosture(p as never);
      await sleep(1400); // 转体过渡 + 贴床收敛
      const info = scene.debugInfo() as Record<string, unknown>;
      const joints = info.joints as Record<string, number[]>;
      const hip = joints['leg_joint_R_1'];
      const knee = joints['leg_joint_R_2'];
      const ankle = joints['leg_joint_R_3'];
      const lHip = joints['leg_joint_L_1'];
      const lKnee = joints['leg_joint_L_2'];
      const lAnkle = joints['leg_joint_L_3'];
      const head = joints['neck_joint_2'];
      perPosture.push({
        roll: info.roll,
        box: info.modelBox,
        screen: info.screenBounds,
        hip,
        knee,
        ankle,
        lHip,
        lKnee,
        lAnkle,
        head,
        thigh: dist(hip, knee),
        shin: dist(knee, ankle),
        hipAnkle: dist(hip, ankle),
        lThigh: dist(lHip, lKnee),
        lShin: dist(lKnee, lAnkle),
        lHipAnkle: dist(lHip, lAnkle),
      });
    }

    const scaleMax = Math.max(heat.computeFrameMax(frame), 80);
    const expected = heat.valueToColor(100, scaleMax, heat.GAMMA.smooth);

    return {
      before,
      loaded,
      perPosture,
      expected: [Math.round(expected[0] * 255), Math.round(expected[1] * 255), Math.round(expected[2] * 255)],
    };
  });

  // ---- 纹理 ----
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

  // ---- 模型加载 ----
  const loaded = result.loaded as Record<string, unknown>;
  check('人体模型加载成功', loaded.modelLoaded === true, `modelLoaded=${loaded.modelLoaded}`);
  check('19 根骨骼齐全', loaded.boneCount === 19, `boneCount=${loaded.boneCount}`);

  // ---- 四睡姿 ----
  const names = ['仰卧', '俯卧', '左侧卧', '右侧卧'];
  const expectRoll = [Math.PI, 0, -Math.PI / 2, Math.PI / 2];
  let allVisible = true;
  let allOnBed = true;
  const visibilityDetails: string[] = [];
  const fitDetails: string[] = [];
  for (let i = 0; i < 4; i++) {
    const p = result.perPosture[i] as Record<string, unknown>;
    const rollOk = Math.abs((p.roll as number) - expectRoll[i]) < 0.05;
    check(`${names[i]} roll 值正确`, rollOk, `roll=${(p.roll as number).toFixed(3)}（期望 ${expectRoll[i].toFixed(3)}）`);

    const screen = p.screen as Record<string, number>;
    const visible =
      screen.ndcX1 > -1.05 && screen.ndcX0 < 1.05 && screen.ndcY1 > -1.05 && screen.ndcY0 < 1.05;
    if (!visible) allVisible = false;
    visibilityDetails.push(
      `${names[i]}:ndcX[${screen.ndcX0.toFixed(2)},${screen.ndcX1.toFixed(2)}] ndcY[${screen.ndcY0.toFixed(2)},${screen.ndcY1.toFixed(2)}]`,
    );

    const box = p.box as { min: number[]; max: number[] };
    const onBed = box.min[1] > 0.12 && box.min[1] < 0.22;
    if (!onBed) allOnBed = false;
    fitDetails.push(`${names[i]}:y[${box.min[1].toFixed(3)},${box.max[1].toFixed(3)}] z[${box.min[2].toFixed(2)},${box.max[2].toFixed(2)}]`);
  }
  check('四种睡姿模型均在屏幕视野内（NDC 投影）', allVisible, visibilityDetails.join(' | '));
  check('四种睡姿最低点均贴住床面（不嵌入床垫）', allOnBed, `床面 y=0.172；` + fitDetails.join(' | '));

  // ---- 肢体姿态 ----
  const sup = result.perPosture[0] as Record<string, unknown>;
  const latL = result.perPosture[2] as Record<string, unknown>;
  const latR = result.perPosture[3] as Record<string, unknown>;
  const straight = (sup.hipAnkle as number) / ((sup.thigh as number) + (sup.shin as number));
  check('仰卧双腿伸直', straight > 0.96, `髋-踝/腿长=${straight.toFixed(3)}（≈1 为伸直）`);
  // 侧卧：上腿（远离床面的那条）屈曲更多；左侧卧上腿=右腿，右侧卧上腿=左腿
  const foldL = (latL.hipAnkle as number) / ((latL.thigh as number) + (latL.shin as number));
  const foldR = (latR.lHipAnkle as number) / ((latR.lThigh as number) + (latR.lShin as number));
  check('左侧卧上腿（右腿）屈膝', foldL < 0.9, `髋-踝/腿长=${foldL.toFixed(3)}（<0.9 为屈膝）`);
  check('右侧卧上腿（左腿）屈膝', foldR < 0.9, `髋-踝/腿长=${foldR.toFixed(3)}（<0.9 为屈膝）`);

  // 头在脚端之前（头端 -Z）
  const headZ = (sup.head as number[])[2];
  const ankleZ = (sup.ankle as number[])[2];
  check('头朝床垫远端（头 z < 脚 z）', headZ < ankleZ, `头 z=${headZ.toFixed(2)} 脚 z=${ankleZ.toFixed(2)}`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.log(`\n✗ 失败 ${failures.length} 项: ${failures.join('、')}`);
  process.exit(1);
}
console.log('\n✓ 3D 场景逻辑验证全部通过');
