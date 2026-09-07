/**
 * 3D 睡姿演示场景（three.js）。
 *
 * - 程序化床垫：顶面 44×24 压力热力图实时纹理，与 2D 热力图共用
 *   turbo 色带 / 自动量程（computeFrameMax + GAMMA.smooth）。
 * - 气囊分区：按布置图权威矩形坐标投影为半透明条带，随状态充气动画
 * - 人体：Cesium RiggedFigure（CC BY 4.0，见 public/models/CREDITS.md），
 *   骨骼旋转摆出仰卧/俯卧/左侧卧/右侧卧，附带呼吸起伏与转体过渡动画。
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import {
  AIRBAG_RECTS,
  AIRBAG_SENSORS,
  AIRBAG_ID_TO_COLOR,
  REGION_COLORS,
  airbagRectTo3D,
  mmTo3D,
} from '../core/airbag-layout';
import type { AirbagState } from '../core/airbag';
import { computeFrameMax, GAMMA, valueToColor } from '../render/heatmap';

export type PostureId = 0 | 1 | 2 | 3;

const ROWS = 44;
const COLS = 24;
// 床垫几何（米）：与气囊-传感器布置图一致（1800×2000mm）
const MATTRESS_LEN = 2.0; // z 方向（头→脚）
const MATTRESS_WID = 1.8; // x 方向（仰卧者左→右）
const MATTRESS_THK = 0.16;
const CELL_PX = 4; // 纹理每格像素（画布 96×176）
const AUTO_SCALE_MIN = 80;
// 人体身高（米）：与热力图数据中人体跨度（44 行中约 38 行 ≈ 1.73m）及 2m 床匹配
const FIGURE_LEN = 1.75;

interface BonePose {
  x?: number;
  y?: number;
  z?: number;
}

/**
 * 绕身体长轴的翻转角（模型为 Mixamo rig，GLTFLoader 加载后 Y-up：
 * 立姿头 +Y、正面 +Z（护目镜侧）、左半身 -X）。
 * 结构：fitGroup（世界轴对齐）⊃ rollGroup（绕世界 Z=床长轴翻转）⊃ modelRoot（绕 X 转 -90° 躺平，头→-Z）。
 * roll=0 正面朝上（仰卧）；俯卧=π、左侧卧=+π/2（左半身 -X 贴床）、右侧卧=-π/2。
 * （实测：rotX=-π/2 时骨架头 z<0 脚 z>0 平躺；roll 符号按左半身 -X 推导）
 */
const POSTURE_ROLL: Record<PostureId, number> = {
  0: 0,
  1: Math.PI,
  2: Math.PI / 2,
  3: -Math.PI / 2,
};

/**
 * 各睡姿的肢体调整（mixamorig 骨骼局部旋转增量，弧度；在绑定四元数之上叠加）。
 * 实测（躺平世界）：双肩 z=+1.35 均为手臂贴体侧指向脚端（左右臂坐标系同号，勿镜像）；
 * 髋/膝 x>0 = 屈髋屈膝；髋 z 为外展（侧卧翻滚后变成垂直抬膝，z 符号左右镜像）。
 */
const ARMS_DOWN: Record<string, BonePose> = {
  mixamorigLeftArm: { z: 1.35 },
  mixamorigRightArm: { z: 1.35 },
};

const LIMB_POSES: Record<PostureId, Record<string, BonePose>> = {
  // 仰卧：双臂贴体侧、双腿伸直
  0: { ...ARMS_DOWN },
  // 俯卧：头转向一侧
  1: { ...ARMS_DOWN, mixamorigHead: { y: 0.7 } },
  // 左侧卧：仅整体翻滚，肢体与仰卧/俯卧一致（直腿、手臂贴体侧）
  2: { ...ARMS_DOWN },
  // 右侧卧：同上（镜像翻滚）
  3: { ...ARMS_DOWN },
};

export interface Bed3DOptions {
  /** 创建 WebGL 渲染器；false 时仅构建场景图（用于无 GPU 环境的逻辑验证） */
  webgl?: boolean;
}

export class Bed3DScene {
  private renderer: THREE.WebGLRenderer | null = null;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera | null = null;
  private controls: OrbitControls | null = null;
  private canvas2d: HTMLCanvasElement;
  private ctx2d: CanvasRenderingContext2D;
  private texture: THREE.CanvasTexture;
  /** 世界坐标系对齐的贴床/呼吸组（不旋转，位置修正始终沿世界 +Y） */
  private fitGroup = new THREE.Group();
  private modelRoot: THREE.Group | null = null;
  private rollGroup: THREE.Group | null = null;
  private bones = new Map<string, THREE.Bone>();
  private pose: PostureId = 0;
  private targetRoll = 0;
  private breathing = true;
  private baseY = 0;
  /** 站立摆姿下半厚（z 向）/半宽（x 向），用于躯干贴床偏移 */
  private halfDepth = 0.2;
  private halfWidth = 0.25;
  /** 各骨骼绑定姿态四元数（摆姿"复位"必须恢复绑定值，而非置零） */
  private bindQuats = new Map<string, THREE.Quaternion>();
  private rafId = 0;
  private disposed = false;
  private clock = new THREE.Clock();
  private figureRawBox: THREE.Box3 | null = null;
  private figureScaledBox: THREE.Box3 | null = null;
  private figureScale = 1;

  constructor(
    private canvas: HTMLCanvasElement,
    options: Bed3DOptions = {},
  ) {
    if (options.webgl !== false) {
      this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    this.scene.background = new THREE.Color('#0a1016');

    // 相机与控制器不依赖 WebGL（纯数学），无渲染环境也创建以便投影验证
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 60);
    this.camera.position.set(2.9, 1.9, 3.3);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 0.35, 0.05);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 8;
    this.controls.maxPolarAngle = Math.PI * 0.52;

    if (this.renderer) {
      // 灯光：半球环境 + 主方向光（投影）+ 冷色轮廓光
      this.scene.add(new THREE.HemisphereLight(0xdce8f4, 0x0c1520, 1.0));
      const key = new THREE.DirectionalLight(0xffffff, 1.7);
      key.position.set(3, 5, 2.5);
      key.castShadow = true;
      key.shadow.mapSize.set(1024, 1024);
      key.shadow.camera.left = -2.4;
      key.shadow.camera.right = 2.4;
      key.shadow.camera.top = 3;
      key.shadow.camera.bottom = -2;
      key.shadow.camera.far = 20;
      key.shadow.bias = -0.0002;
      this.scene.add(key);
      const rim = new THREE.DirectionalLight(0x9fd4c3, 0.55);
      rim.position.set(-3, 2.5, -2);
      this.scene.add(rim);
    }

    // 地面
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(30, 30),
      new THREE.MeshStandardMaterial({ color: '#0c131b', roughness: 0.95 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.002;
    floor.receiveShadow = true;
    this.scene.add(floor);
    this.scene.add(this.fitGroup);

    // 热力图纹理画布（行 0=头端在画布顶部）
    this.canvas2d = document.createElement('canvas');
    this.canvas2d.width = COLS * CELL_PX;
    this.canvas2d.height = ROWS * CELL_PX;
    this.ctx2d = this.canvas2d.getContext('2d')!;
    this.texture = new THREE.CanvasTexture(this.canvas2d);
    this.texture.magFilter = THREE.NearestFilter;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.colorSpace = THREE.SRGBColorSpace;

    this.buildMattress();
    this.buildAirbagStrips();
    this.buildSensorDots();
    this.setFrame(new Float32Array(ROWS * COLS));
  }

  /** 床垫：实体底座 + 顶面热力图平面（显式 UV，头端在 -Z 远端） */
  private buildMattress(): void {
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(MATTRESS_LEN, MATTRESS_THK, MATTRESS_WID),
      new THREE.MeshStandardMaterial({ color: '#27313c', roughness: 0.9 }),
    );
    body.position.y = MATTRESS_THK / 2;
    body.castShadow = true;
    body.receiveShadow = true;
    this.scene.add(body);

    const topGeo = new THREE.PlaneGeometry(MATTRESS_LEN, MATTRESS_WID);
    const uv = topGeo.attributes.uv;
    for (let i = 0; i < uv.count; i++) {
      const x = topGeo.attributes.position.getX(i);
      const z = topGeo.attributes.position.getZ(i);
      // 行 0（头）→ z=-L/2；列 0 → x=-W/2
      uv.setXY(i, 0.5 + x / MATTRESS_WID, 0.5 - z / MATTRESS_LEN);
    }
    topGeo.rotateX(-Math.PI / 2);
    const top = new THREE.Mesh(
      topGeo,
      new THREE.MeshBasicMaterial({ map: this.texture, toneMapped: false }),
    );
    top.position.y = MATTRESS_THK + 0.002;
    this.scene.add(top);
  }

  /** 气囊分区条带（真实布置图矩形坐标，半透明贴在床面上方；充气时抬升/增亮） */
  private airbagStrips = new Map<string, THREE.Mesh>();
  /** 布置图 60 传感器点 */
  private sensorDots = new Map<number, THREE.Mesh>();

  private buildAirbagStrips(): void {
    for (const rect of AIRBAG_RECTS) {
      const { x0, x1, z0, z1 } = airbagRectTo3D(rect);
      const strip = new THREE.Mesh(
        new THREE.BoxGeometry(Math.abs(x1 - x0), 0.02, Math.abs(z1 - z0)),
        new THREE.MeshBasicMaterial({
          color: AIRBAG_ID_TO_COLOR[rect.id] ?? '#888888',
          transparent: true,
          opacity: 0.3,
          depthWrite: false,
        }),
      );
      strip.position.set((x0 + x1) / 2, MATTRESS_THK + 0.012, (z0 + z1) / 2);
      this.scene.add(strip);
      this.airbagStrips.set(rect.id, strip);
    }
  }

  /** 布置图 60 传感器点（颜色 = 区域归属） */
  private buildSensorDots(): void {
    for (const sensor of AIRBAG_SENSORS) {
      const p = mmTo3D(sensor.xMm, sensor.yMm);
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.013, 10, 10),
        new THREE.MeshBasicMaterial({
          color: REGION_COLORS[sensor.region] ?? '#888888',
        }),
      );
      dot.position.set(p.x, MATTRESS_THK + 0.028, p.z);
      this.scene.add(dot);
      this.sensorDots.set(sensor.id, dot);
    }
  }

  /** 气囊状态 → 条带充气动画（抬升+增亮）与传感器点增强（模拟支撑效果） */
  setAirbagStates(states: AirbagState[]): void {
    const byId = new Map(states.map((s) => [s.zoneId, s.pressure]));
    for (const [id, strip] of this.airbagStrips) {
      const p = (byId.get(id) ?? 0) / 100;
      strip.scale.y = 0.35 + p * 0.9;
      strip.position.y = MATTRESS_THK + 0.008 + (0.02 * strip.scale.y) / 2;
      (strip.material as THREE.MeshBasicMaterial).opacity = 0.22 + p * 0.34;
    }
    for (const sensor of AIRBAG_SENSORS) {
      const dot = this.sensorDots.get(sensor.id);
      if (!dot) continue;
      const p = (byId.get(sensor.airbagId) ?? 0) / 100;
      const s = 0.9 + p * 1.1;
      dot.scale.setScalar(s);
    }
  }

  /** 加载人体模型并摆出当前睡姿 */
  async loadBody(url: string): Promise<void> {
    const gltf = await new GLTFLoader().loadAsync(url);
    const model = gltf.scene;

    // GLTFLoader 已转为 Y-up：身高 = y 轴跨度
    const box = new THREE.Box3().setFromObject(model);
    this.figureRawBox = box.clone();
    const height = Math.max(box.max.y - box.min.y, 0.01);
    this.figureScale = FIGURE_LEN / height;
    model.scale.setScalar(this.figureScale);
    // 水平居中（x），y 原点移到脚底
    const box2 = new THREE.Box3().setFromObject(model);
    this.figureScaledBox = box2.clone();
    model.position.x = -(box2.min.x + box2.max.x) / 2;
    model.position.y = -box2.min.y;

    model.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        // 保留模型自带贴图材质（士兵角色），仅微调粗糙度
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const m of mats) {
          const mat = m as THREE.MeshStandardMaterial;
          if ('roughness' in mat && mat.map === null) mat.roughness = 0.6;
        }
      }
      const bone = obj as THREE.Bone;
      if (bone.isBone) {
        this.bones.set(bone.name, bone);
        this.bindQuats.set(bone.name, bone.quaternion.clone());
      }
    });

    // 站立姿态下应用肢体摆姿，并用蒙皮后的世界包围盒测量半厚/半宽
    // （贴床偏移依据：仰卧/俯卧用半厚=前后深度(z)，侧卧用半宽=躯干宽度(x)。
    //  注意 Box3.setFromObject 不应用蒙皮，必须用 SkinnedMesh.computeBoundingBox）
    this.applyLimbPose(this.pose);
    const posedBoxes: THREE.Box3[] = [];
    model.traverse((obj) => {
      const skinned = obj as THREE.SkinnedMesh;
      if (!skinned.isSkinnedMesh) return;
      // 渲染器每帧会自动 skeleton.update()；无渲染环境需手动调用，
      // 否则 computeBoundingBox 使用的是绑定姿势（T-pose 臂展）
      skinned.skeleton.update();
      skinned.computeBoundingBox();
      const local = skinned.boundingBox;
      if (!local) return;
      skinned.updateWorldMatrix(true, false);
      posedBoxes.push(local.clone().applyMatrix4(skinned.matrixWorld));
    });
    const posedBox = posedBoxes.length
      ? posedBoxes.reduce((acc, box) => acc.union(box))
      : null;
    if (posedBox) {
      this.halfDepth = Math.max((posedBox.max.z - posedBox.min.z) / 2, 0.05);
    }
    // 半宽以肩关节间距为准（蒙皮包围盒受装备/手臂干扰不可靠；肩关节原点不随手部旋转移动）
    {
      const shoulderL = this.bones.get('mixamorigLeftArm');
      const shoulderR = this.bones.get('mixamorigRightArm');
      if (shoulderL && shoulderR) {
        const lw = shoulderL.getWorldPosition(new THREE.Vector3());
        const rw = shoulderR.getWorldPosition(new THREE.Vector3());
        this.halfWidth = Math.max(Math.abs(rw.x - lw.x) / 2 + 0.06, 0.15);
      }
    }

    // fitGroup（世界轴对齐，承载贴床/呼吸位移）⊃ rollGroup（绕世界 Z=床长轴翻转）
    // ⊃ modelRoot（绕 X 转 -90° 躺平：头→-Z）
    this.rollGroup = new THREE.Group();
    this.modelRoot = new THREE.Group();
    this.modelRoot.rotation.x = -Math.PI / 2;
    this.modelRoot.add(model);
    this.rollGroup.add(this.modelRoot);
    this.fitGroup.add(this.rollGroup);

    this.applyPose(this.pose, true);
    this.fitToMattress();
  }

  /** 初始摆位：水平居中、脚端距床边 3 行、躯干贴住床面（世界坐标系） */
  private fitToMattress(): void {
    if (!this.modelRoot) return;
    const box = new THREE.Box3().setFromObject(this.fitGroup);
    const footEnd = MATTRESS_LEN / 2 - (3 / ROWS) * MATTRESS_LEN;
    this.modelRoot.position.x -= (box.min.x + box.max.x) / 2;
    this.modelRoot.position.z += footEnd - box.max.z;
    this.fitBodyHeight();
  }

  /** 躯干支撑：躯干中线关节最低点（世界 y）与当前贴床偏移（随 roll 在 半厚↔半宽 间过渡） */
  private trunkSupport(): { minY: number; offset: number } {
    let minY = Infinity;
    for (const name of [
      'mixamorigHips',
      'mixamorigSpine',
      'mixamorigSpine1',
      'mixamorigSpine2',
      'mixamorigNeck',
      'mixamorigHead',
    ]) {
      const bone = this.bones.get(name);
      if (!bone) continue;
      const y = bone.getWorldPosition(new THREE.Vector3()).y;
      if (y < minY) minY = y;
    }
    if (!Number.isFinite(minY)) return { minY: 0, offset: this.halfDepth };
    const rollFactor = this.rollGroup ? Math.abs(Math.sin(this.rollGroup.rotation.z)) : 0;
    const offset = this.halfDepth + (this.halfWidth - this.halfDepth) * rollFactor;
    return { minY, offset };
  }

  /** 把躯干支撑面贴到床面（fitGroup 不旋转，修正始终沿世界 +Y） */
  private fitBodyHeight(): void {
    const { minY, offset } = this.trunkSupport();
    this.fitGroup.position.y += MATTRESS_THK + 0.012 - (minY - offset);
    this.baseY = this.fitGroup.position.y;
  }

  /** 更新床垫热力图纹理（1056 值，行优先） */
  setFrame(frame: ArrayLike<number>): void {
    const ctx = this.ctx2d;
    ctx.clearRect(0, 0, this.canvas2d.width, this.canvas2d.height);
    if (!frame || frame.length < ROWS * COLS) {
      this.texture.needsUpdate = true;
      return;
    }
    const scaleMax = Math.max(computeFrameMax(frame), AUTO_SCALE_MIN);
    const gamma = GAMMA.smooth;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const v = frame[r * COLS + c];
        if (v <= 0) continue;
        const [rr, gg, bb] = valueToColor(v, scaleMax, gamma);
        ctx.fillStyle = `rgb(${Math.round(rr * 255)},${Math.round(gg * 255)},${Math.round(bb * 255)})`;
        ctx.fillRect(c * CELL_PX, r * CELL_PX, CELL_PX, CELL_PX);
      }
    }
    this.texture.needsUpdate = true;
  }

  setPosture(posture: PostureId): void {
    if (posture < 0 || posture > 3) posture = 0;
    this.applyPose(posture, false);
  }

  setBreathing(on: boolean): void {
    this.breathing = on;
  }

  /** 调试：直接设置某骨骼局部旋转增量（用于摆姿调参） */
  debugSetBone(name: string, x: number, y: number, z: number): boolean {
    const bone = this.bones.get(name);
    const bind = this.bindQuats.get(name);
    if (!bone || !bind) return false;
    bone.quaternion.copy(bind);
    bone.quaternion.multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z)));
    return true;
  }

  /** 调试：恢复全部骨骼绑定姿态 */
  debugResetBones(): void {
    for (const [name, bone] of this.bones) {
      const bind = this.bindQuats.get(name);
      if (bind) bone.quaternion.copy(bind);
    }
  }

  /** 调试：设置躺平组绕 X 的旋转角（用于确定正确躺平变换） */
  debugSetRootRotationX(x: number): void {
    if (this.modelRoot) this.modelRoot.rotation.x = x;
  }

  /** 调试：返回蒙皮网格应用当前骨架姿势后的世界包围盒（真实渲染范围） */
  debugMeshWorldBox(): Record<string, number[]> | null {
    const boxes: THREE.Box3[] = [];
    this.fitGroup.traverse((obj) => {
      const skinned = obj as THREE.SkinnedMesh;
      if (!skinned.isSkinnedMesh) return;
      skinned.skeleton.update();
      skinned.computeBoundingBox();
      const local = skinned.boundingBox;
      if (!local) return;
      skinned.updateWorldMatrix(true, false);
      boxes.push(local.clone().applyMatrix4(skinned.matrixWorld));
    });
    if (!boxes.length) return null;
    const box = boxes.reduce((acc, b) => acc.union(b));
    return {
      min: box.min.toArray(),
      max: box.max.toArray(),
    };
  }

  /** 调试信息（供自动化验证读取场景真实状态） */
  debugInfo(): Record<string, unknown> {
    const roll = this.rollGroup ? this.rollGroup.rotation.z : 0;
    const modelBox = this.modelRoot ? new THREE.Box3().setFromObject(this.fitGroup) : null;
    const image = this.ctx2d.getImageData(0, 0, this.canvas2d.width, this.canvas2d.height);
    let activeCells = 0;
    let coloredPx = 0;
    const samples: [number, number, number, number][] = [];
    for (let i = 0; i < image.data.length; i += 4) {
      if (image.data[i + 3] > 0) {
        coloredPx++;
        if (samples.length < 3) samples.push([image.data[i], image.data[i + 1], image.data[i + 2], image.data[i + 3]]);
      }
    }
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const idx = (r * CELL_PX * COLS * CELL_PX + c * CELL_PX) * 4;
        if (image.data[idx + 3] > 0) activeCells++;
      }
    }
    const joints: Record<string, number[]> = {};
    for (const name of [
      'mixamorigHead',
      'mixamorigNeck',
      'mixamorigSpine2',
      'mixamorigHips',
      'mixamorigLeftUpLeg',
      'mixamorigLeftLeg',
      'mixamorigLeftFoot',
      'mixamorigRightUpLeg',
      'mixamorigRightLeg',
      'mixamorigRightFoot',
      'mixamorigLeftArm',
      'mixamorigLeftHand',
      'mixamorigRightArm',
      'mixamorigRightHand',
    ]) {
      const bone = this.bones.get(name);
      if (bone) joints[name] = bone.getWorldPosition(new THREE.Vector3()).toArray();
    }

    // 屏幕投影（NDC）验证可见性：相机数学不依赖渲染器
    let screenBounds: Record<string, number> | null = null;
    if (modelBox && this.camera) {
      this.camera.aspect = (this.canvas.clientWidth || 16) / (this.canvas.clientHeight || 9);
      this.camera.updateMatrixWorld();
      this.camera.updateProjectionMatrix();
      const corners: THREE.Vector3[] = [];
      for (const x of [modelBox.min.x, modelBox.max.x]) {
        for (const y of [modelBox.min.y, modelBox.max.y]) {
          for (const z of [modelBox.min.z, modelBox.max.z]) {
            corners.push(new THREE.Vector3(x, y, z).project(this.camera));
          }
        }
      }
      screenBounds = {
        ndcX0: Math.min(...corners.map((v) => v.x)),
        ndcX1: Math.max(...corners.map((v) => v.x)),
        ndcY0: Math.min(...corners.map((v) => v.y)),
        ndcY1: Math.max(...corners.map((v) => v.y)),
      };
    }

    const trunk = this.trunkSupport();

    return {
      webgl: this.renderer !== null,
      camera: this.camera ? this.camera.position.toArray() : null,
      target: this.controls ? this.controls.target.toArray() : null,
      fov: this.camera ? this.camera.fov : null,
      canvasBuf: this.renderer ? [this.renderer.domElement.width, this.renderer.domElement.height] : null,
      modelLoaded: this.modelRoot !== null,
      boneCount: this.bones.size,
      bones: [...this.bones.keys()].sort(),
      pose: this.pose,
      roll,
      modelBox: modelBox
        ? { min: modelBox.min.toArray(), max: modelBox.max.toArray() }
        : null,
      trunk: { minY: trunk.minY, offset: trunk.offset, halfDepth: this.halfDepth, halfWidth: this.halfWidth },
      screenBounds,
      joints,
      figureRawBox: this.figureRawBox
        ? {
            min: this.figureRawBox.min.toArray(),
            max: this.figureRawBox.max.toArray(),
          }
        : null,
      figureScaledBox: this.figureScaledBox
        ? {
            min: this.figureScaledBox.min.toArray(),
            max: this.figureScaledBox.max.toArray(),
          }
        : null,
      figureScale: this.figureScale,
      texture: { activeCells, coloredPx, samples },
    };
  }

  /** 恢复绑定姿态并应用肢体骨骼摆姿（增量叠加在绑定四元数之上，不影响 roll） */
  private applyLimbPose(posture: PostureId): void {
    const delta = new THREE.Quaternion();
    for (const [name, bone] of this.bones) {
      const bind = this.bindQuats.get(name);
      if (!bind) continue;
      bone.quaternion.copy(bind);
      const rot = LIMB_POSES[posture]?.[name];
      if (rot) {
        delta.setFromEuler(new THREE.Euler(rot.x ?? 0, rot.y ?? 0, rot.z ?? 0));
        bone.quaternion.multiply(delta);
      }
    }
  }

  private applyPose(posture: PostureId, immediate: boolean): void {
    this.pose = posture;
    this.targetRoll = POSTURE_ROLL[posture];
    this.applyLimbPose(posture);
    if (immediate && this.rollGroup) this.rollGroup.rotation.z = this.targetRoll;
  }

  start(): void {
    this.clock.start();
    const tick = () => {
      if (this.disposed) return;
      this.resize();
      const t = this.clock.getElapsedTime();
      if (this.modelRoot && this.rollGroup) {
        // 转体平滑过渡
        const cur = this.rollGroup.rotation.z;
        const diff = this.targetRoll - cur;
        if (Math.abs(diff) > 1e-4) {
          this.rollGroup.rotation.z = cur + diff * Math.min(1, 0.1);
        }
        // 躯干贴床（世界坐标系修正，转体过程中躯干支撑面持续贴床）
        this.fitBodyHeight();
        // 呼吸起伏：整体轻微上下浮动
        if (this.breathing) {
          const amp = 0.012 * (this.pose >= 2 ? 0.5 : 1);
          this.fitGroup.position.y = this.baseY + Math.sin(t * 1.7) * amp;
        }
      }
      this.controls?.update();
      if (this.renderer && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
      this.rafId = requestAnimationFrame(tick);
    };
    this.rafId = requestAnimationFrame(tick);
  }

  private resize(): void {
    if (!this.renderer || !this.camera) return;
    const w = this.canvas.clientWidth || 1;
    const h = this.canvas.clientHeight || 1;
    if (
      this.canvas.width !== Math.floor(w * this.renderer.getPixelRatio()) ||
      this.canvas.height !== Math.floor(h * this.renderer.getPixelRatio())
    ) {
      this.renderer.setSize(w, h, false);
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    }
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.rafId);
    this.controls?.dispose();
    this.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.geometry?.dispose();
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const m of mats) m.dispose();
      }
    });
    this.texture.dispose();
    this.renderer?.dispose();
  }
}
