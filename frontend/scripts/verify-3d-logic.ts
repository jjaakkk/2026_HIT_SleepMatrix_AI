// 3D scene logic verification (no WebGL/GPU needed): npm run verify:3d:logic
// Builds the scene in-page with webgl:false and asserts model loading, bones,
// posture rolls, trunk-on-mattress fit, screen visibility (NDC projection),
// and limb poses.
import puppeteer from 'puppeteer';

const BASE = 'http://localhost:5173/';

const browser = await puppeteer.launch({ headless: 'shell' });
const failures: string[] = [];
function check(name: string, ok: boolean, detail: string) {
  console.log(`${ok ? 'PASS' : 'FAIL'} ${name}: ${detail}`);
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

    // known frame: 3 non-zero cells (head/middle/foot)
    const frame = new Float32Array(44 * 24);
    frame[0] = 100;
    frame[10 * 24 + 5] = 200;
    frame[40 * 24 + 20] = 50;
    scene.setFrame(frame);
    const before = scene.debugInfo() as Record<string, unknown>;

    await scene.loadBody('/models/Soldier.glb');
    const loaded = scene.debugInfo() as Record<string, unknown>;

    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const dist = (a: number[], b: number[]) =>
      Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

    const perPosture: Record<string, unknown>[] = [];
    for (const p of [0, 1, 2, 3]) {
      scene.setPosture(p as never);
      await sleep(1400); // roll transition + fit settle
      const info = scene.debugInfo() as Record<string, unknown>;
      const joints = info.joints as Record<string, number[]>;
      const per = {
        roll: info.roll,
        box: info.modelBox,
        screen: info.screenBounds,
        trunk: info.trunk,
        joints,
        lThigh: dist(joints['mixamorigLeftUpLeg'], joints['mixamorigLeftLeg']),
        lShin: dist(joints['mixamorigLeftLeg'], joints['mixamorigLeftFoot']),
        lHipAnkle: dist(joints['mixamorigLeftUpLeg'], joints['mixamorigLeftFoot']),
        rThigh: dist(joints['mixamorigRightUpLeg'], joints['mixamorigRightLeg']),
        rShin: dist(joints['mixamorigRightLeg'], joints['mixamorigRightFoot']),
        rHipAnkle: dist(joints['mixamorigRightUpLeg'], joints['mixamorigRightFoot']),
      };
      perPosture.push(per);
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

  // ---- texture ----
  const tex = result.before.texture as {
    activeCells: number;
    coloredPx: number;
    samples: number[][];
  };
  check('texture drawn per frame', tex.activeCells === 3, `activeCells=${tex.activeCells} (want 3)`);
  check('texture pixels = 3 cells x 16px', tex.coloredPx === 48, `coloredPx=${tex.coloredPx} (want 48)`);
  check(
    'texture color matches turbo colormap',
    tex.samples.length > 0 &&
      Math.abs(tex.samples[0][0] - result.expected[0]) < 2 &&
      Math.abs(tex.samples[0][1] - result.expected[1]) < 2 &&
      Math.abs(tex.samples[0][2] - result.expected[2]) < 2,
    `first=${tex.samples[0]?.slice(0, 3)} want=${result.expected}`,
  );

  // ---- model load ----
  const loaded = result.loaded as Record<string, unknown>;
  check('body model loaded', loaded.modelLoaded === true, `modelLoaded=${loaded.modelLoaded}`);
  check('49 mixamorig bones present', loaded.boneCount === 49, `boneCount=${loaded.boneCount}`);
  check(
    'key bones exist',
    ['mixamorigHips', 'mixamorigHead', 'mixamorigLeftArm', 'mixamorigRightLeg'].every((n) =>
      (loaded.bones as string[]).includes(n),
    ),
    'all found',
  );

  // ---- four postures ----
  const names = ['supine', 'prone', 'left-lateral', 'right-lateral'];
  const expectRoll = [0, Math.PI, Math.PI / 2, -Math.PI / 2];
  let allVisible = true;
  let allTrunkOnBed = true;
  const visibilityDetails: string[] = [];
  const trunkDetails: string[] = [];
  for (let i = 0; i < 4; i++) {
    const p = result.perPosture[i] as Record<string, unknown>;
    const rollOk = Math.abs((p.roll as number) - expectRoll[i]) < 0.05;
    check(`${names[i]} roll correct`, rollOk, `roll=${(p.roll as number).toFixed(3)} (want ${expectRoll[i].toFixed(3)})`);

    const screen = p.screen as Record<string, number>;
    const visible =
      screen.ndcX1 > -1.05 && screen.ndcX0 < 1.05 && screen.ndcY1 > -1.05 && screen.ndcY0 < 1.05;
    if (!visible) allVisible = false;
    visibilityDetails.push(
      `${names[i]}:ndcX[${screen.ndcX0.toFixed(2)},${screen.ndcX1.toFixed(2)}] ndcY[${screen.ndcY0.toFixed(2)},${screen.ndcY1.toFixed(2)}]`,
    );

    // trunk support surface height = trunk centerline min - offset
    const trunk = p.trunk as Record<string, number>;
    const supportY = trunk.minY - trunk.offset;
    const onBed = Math.abs(supportY - 0.172) < 0.07;
    if (!onBed) allTrunkOnBed = false;
    trunkDetails.push(
      `${names[i]}:supportY=${supportY.toFixed(3)} (bed 0.172) offset=${trunk.offset.toFixed(3)}`,
    );

    const box = p.box as { min: number[]; max: number[] };
    const inBedZ = box.min[2] > -1.15 && box.max[2] < 1.15;
    check(`${names[i]} body within mattress length`, inBedZ, `z[${box.min[2].toFixed(2)},${box.max[2].toFixed(2)}]`);
  }
  check('all postures visible on screen (NDC)', allVisible, visibilityDetails.join(' | '));
  check('all postures trunk-support touches bed (no float/sink)', allTrunkOnBed, trunkDetails.join(' | '));

  // ---- limb poses ----
  const sup = result.perPosture[0] as Record<string, unknown>;
  const latL = result.perPosture[2] as Record<string, unknown>;
  const latR = result.perPosture[3] as Record<string, unknown>;
  const supJoints = sup.joints as Record<string, number[]>;

  const straightL = (sup.lHipAnkle as number) / ((sup.lThigh as number) + (sup.lShin as number));
  check('supine legs straight', straightL > 0.97, `hip-ankle/leg=${straightL.toFixed(3)} (want ~1)`);

  // arms at sides: hand along the body toward feet (hand z > shoulder z), same height
  const handAtSide =
    supJoints['mixamorigLeftHand'][2] > supJoints['mixamorigLeftArm'][2] &&
    Math.abs(supJoints['mixamorigLeftHand'][1] - supJoints['mixamorigLeftArm'][1]) < 0.25;
  const rightHandAtSide =
    supJoints['mixamorigRightHand'][2] > supJoints['mixamorigRightArm'][2] &&
    Math.abs(supJoints['mixamorigRightHand'][1] - supJoints['mixamorigRightArm'][1]) < 0.25;
  check(
    'supine left arm at side (hand toward feet)',
    handAtSide,
    `hand z=${supJoints['mixamorigLeftHand'][2].toFixed(2)} shoulder z=${supJoints['mixamorigLeftArm'][2].toFixed(2)}`,
  );
  check(
    'supine right arm at side (hand toward feet, not raised)',
    rightHandAtSide,
    `hand z=${supJoints['mixamorigRightHand'][2].toFixed(2)} shoulder z=${supJoints['mixamorigRightArm'][2].toFixed(2)} hand y=${supJoints['mixamorigRightHand'][1].toFixed(2)}`,
  );

  // lateral: top leg folded (left-lateral top = right leg; right-lateral top = left leg)
  const foldLTop = (latL.rHipAnkle as number) / ((latL.rThigh as number) + (latL.rShin as number));
  const foldRTop = (latR.lHipAnkle as number) / ((latR.lThigh as number) + (latR.lShin as number));
  const straightLBottom = (latL.lHipAnkle as number) / ((latL.lThigh as number) + (latL.lShin as number));
  check('left-lateral top leg (right) bent', foldLTop < 0.9, `ratio=${foldLTop.toFixed(3)}`);
  check('right-lateral top leg (left) bent', foldRTop < 0.9, `ratio=${foldRTop.toFixed(3)}`);
  check('left-lateral bottom leg (left) near straight', straightLBottom > 0.9, `ratio=${straightLBottom.toFixed(3)}`);

  // lateral bottom leg foot and bottom arm hand must not sink below mattress
  const latLJoints = latL.joints as Record<string, number[]>;
  const latRJoints = latR.joints as Record<string, number[]>;
  const bottomFootOk = latLJoints['mixamorigLeftFoot'][1] > 0.05;
  const bottomHandOk = latLJoints['mixamorigLeftHand'][1] > 0.05;
  const topFootOk =
    latLJoints['mixamorigRightFoot'][1] > 0.1 && latRJoints['mixamorigLeftFoot'][1] > 0.1;
  check(
    'left-lateral bottom foot not sunk',
    bottomFootOk,
    `foot y=${latLJoints['mixamorigLeftFoot'][1].toFixed(2)} (want >0.05)`,
  );
  check(
    'left-lateral bottom hand not sunk',
    bottomHandOk,
    `hand y=${latLJoints['mixamorigLeftHand'][1].toFixed(2)} (want >0.05)`,
  );
  check(
    'lateral top foot rests above mattress (no penetration)',
    topFootOk,
    `left: ${latLJoints['mixamorigRightFoot'][1].toFixed(2)} / right: ${latRJoints['mixamorigLeftFoot'][1].toFixed(2)} (want >0.1)`,
  );

  // 侧卧上腿膝盖应抬离床面（胎儿式屈髋抬膝）
  const kneeLiftL = latLJoints['mixamorigRightLeg'][1] - latLJoints['mixamorigRightUpLeg'][1];
  const kneeLiftR = latRJoints['mixamorigLeftLeg'][1] - latRJoints['mixamorigLeftUpLeg'][1];
  check(
    'lateral top knee raised (fetal curl visible)',
    kneeLiftL > 0.1 && kneeLiftR > 0.1,
    `left: kneeLift=${kneeLiftL.toFixed(2)} / right: kneeLift=${kneeLiftR.toFixed(2)} (want >0.1)`,
  );

  // head toward the far end (-Z)
  const headZ = supJoints['mixamorigHead'][2];
  const footZ = (sup.joints as Record<string, number[]>)['mixamorigRightFoot'][2];
  check('head toward far end (head z < foot z)', headZ < footZ, `head z=${headZ.toFixed(2)} foot z=${footZ.toFixed(2)}`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.log(`\nFAILED ${failures.length}: ${failures.join(' | ')}`);
  process.exit(1);
}
console.log('\nALL 3D SCENE LOGIC CHECKS PASSED');
