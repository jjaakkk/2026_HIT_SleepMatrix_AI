# 测试模拟：设备推流与睡姿推理链路

本目录提供**设备模拟器**，配合后端设备帧接口与前端两种数据模式，
在未接入真实床垫设备时验证「采集 → 推理 → 展示」的完整链路。

## 一、前后端逻辑

### 两种数据模式的语义

| 模式 | 语义 | 帧源 | 推理 |
| --- | --- | --- | --- |
| 实时推理（默认） | 真实设备已接入，逐帧实时推理 | 设备接口（`POST /api/stream/ingest` 推帧，前端轮询） | 每帧 `POST /api/frame/analyze` |
| 离线回放 | 未接入设备，回放历史记录数据 | demo.json 记录 / `#dataset=` 直链加载的数据集帧 | 回放帧同样逐帧推理 |

关键行为：

- 实时推理模式**没有设备输入时保持静止（黑屏）**，侧栏显示「等待设备输入」，
  不会自动播放任何演示数据；设备停推约 2 秒后自动回到静止状态。
- 离线回放**不是模型离线**：回放帧同样走模型推理，睡姿卡/部位区域/3D
  均由模型结果驱动；只有模型不可用时才回退记录标注。

### 后端（`backend/app.py`）

| 端点 | 作用 |
| --- | --- |
| `POST /api/stream/ingest` | 设备逐帧上传 44×24 压力矩阵，写入内存最新帧缓冲（帧号递增） |
| `GET /api/stream/latest?after=N` | 前端轮询最新设备帧；无新帧时返回 `has_frame=false` |
| `GET /api/dataset/stream?files=dgs_1,dgs_10&limit=30` | 从数据集取帧拼接回放序列（离线回放数据源，`#dataset=` 直链） |
| `POST /api/frame/analyze` | 单帧聚合推理：睡姿（SVM/CNN/ensemble）+ 身体分区 + 弱区增强，两种模式共用 |

### 前端（`frontend/src`）

| 文件 | 职责 |
| --- | --- |
| `composables/useFrameInference.ts` | 实时模式每 150ms 轮询 `/api/stream/latest`，有新帧队列化分析（350ms 尾沿节流 + latest-wins）；连续 >2s 无新帧置 `streamIdle`（静止）；回放帧同样可 `queueAnalyze` |
| `App.vue` | 实时模式帧源 = 设备帧（`deviceFrame`）；回放模式帧号推进逐帧送推理；模型结果优先、不可用回退记录标注；`#dataset=` 参数加载数据集回放序列 |
| `components/SidebarControls.vue` | 模式切换、设备流状态行（等待设备输入 / 设备流 · 来源） |

## 二、设备模拟器

读取数据集 txt 文件，按指定帧率逐帧推送到 `/api/stream/ingest`，模拟真实床垫。

```powershell
# 默认：仰卧→左侧卧→右侧卧→俯卧 各 30 帧循环，2.5 fps
python backend/scripts/device_simulator.py --loop

# 自定义序列与帧率（文件名可省略 .txt；受试者/动作见 dataset 目录）
python backend/scripts/device_simulator.py --files dgs_1 dgs_7 --fps 5

# 参数
#   --files   数据集文件名列表（<subject>_<action>）
#   --fps     推送帧率（默认 2.5）
#   --limit   每文件帧数上限（默认 30，1-120）
#   --loop    序列循环推送
#   --source  设备来源标识（显示在前端侧栏「设备流 · <来源>」）
#   --base    后端地址（默认 http://127.0.0.1:5000）
```

## 三、完整演示步骤

```powershell
# 1. 启动后端（默认 http://127.0.0.1:5000）
python -m backend.app

# 2. 启动前端预览（默认 http://localhost:4173）
cd frontend
npm run build        # 首次或改代码后
npm run preview

# 3. 另开终端启动设备模拟器（模拟真实设备持续推流）
python backend/scripts/device_simulator.py --loop

# 4. 浏览器打开 http://localhost:4173
#    默认即「实时推理」：应看到「设备流 · dataset-simulator」、
#    睡姿卡「模型推理 · 置信度」、区域徽章「区域 · 模型推理」随帧变化
```

观察要点：

- **无输入静止**：停掉模拟器（Ctrl+C），约 2 秒后热力图变黑、
  侧栏显示「等待设备输入」，睡姿卡显示「未检测到设备输入 · 保持静止」。
- **离线回放接推理**：打开 `http://localhost:4173/#display=demo`，
  播放任一记录，睡姿卡仍显示「模型推理」，区域仍为「模型推理」。
- **数据集帧回放**：打开
  `http://localhost:4173/#display=demo&dataset=dgs_1,dgs_10,dgs_16,dgs_7`
  （回放数据集帧序列，同样逐帧推理）。

## 四、自动验证

前端 `frontend/scripts/verify-dataset-stream.ts`（puppeteer）自动验证三个场景：
无输入静止、设备推帧实时推理、离线回放接推理。

```powershell
cd frontend
node --experimental-strip-types scripts/verify-dataset-stream.ts
```

运行前提：后端、前端预览均已启动（见上文第 1、2 步）。

## 五、真实设备接入约定

采集程序只需按固定节奏调用：

```text
POST /api/stream/ingest
Content-Type: application/json

{
  "pressure_matrix": [[...44 行 × 24 列数值...]],
  "source": "bed-01"          // 可选，设备标识
}
```

前端无需任何改动即可切换到真实设备帧源（把模拟器换成采集程序即可）。
