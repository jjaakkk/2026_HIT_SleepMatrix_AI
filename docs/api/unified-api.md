# SleepMatrix 统一后端 API

基础地址默认 `http://127.0.0.1:5000`（`SLEEPMATRIX_HOST` / `SLEEPMATRIX_PORT` 可覆盖）。
所有接口围绕共享数据契约工作：压力矩阵严格为 **44×24**（`matrix[row][column]`），
睡姿标签、动作编号与镜像映射以 `shared/contracts/posture.json` 为唯一事实源。

## 通用约定

- 请求体为 JSON；压力矩阵字段名统一为 `pressure_matrix`（保留旧字段名 `data` 作为别名）。
- 错误响应统一信封：`{"error": "<code>", "message": "<说明>"}`。
- 模型均为懒加载：进程内首次推理请求时加载，之后复用。

### 错误码

| code | HTTP | 含义 |
|---|---|---|
| `invalid_request` | 400 | 请求体不是 JSON、`pressure_matrix` 缺失/非数值/形状非 44×24/含 NaN，或 `model`、`features`、`config` 参数非法 |
| `not_found` | 404 | 无对应样本（body-partition sample） |
| `metrics_unavailable` | 404 | 训练指标文件不存在 |
| `model_unavailable` | 503 | 模型工件缺失或无法加载（含契约/形状不匹配） |
| `dataset_unavailable` | 503 | 标注数据集不存在（body-partition 浏览接口） |
| `metrics_invalid` | 500 | 训练指标文件不是合法 JSON |

## 端点总览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务与各模型状态 |
| GET | `/api/contracts/posture` | 共享睡姿契约（唯一事实源） |
| POST | `/api/posture/predict` | 单帧睡姿推理（SVM / CNN / 集成） |
| POST | `/api/frame/analyze` | 单帧聚合分析（睡姿 + 分区 + 增强） |
| POST | `/api/weak-enhance` | 弱压力区域增强 |
| GET | `/api/weak-enhance/config` | 增强参数默认值 |
| POST | `/api/body-partition/predict` | 身体部位区域分割 |
| GET | `/api/body-partition/metrics` | 分区模型训练指标 |
| GET | `/api/body-partition/catalog` | 标注数据集目录 |
| GET | `/api/body-partition/sample` | 标注样本帧 + 真值掩码 |
| GET | `/api/body-partition/health` | 分区模块资源状态 |
| GET | `/body-partition/` | 分区数据展示静态页 |

---

## GET /api/health

服务状态与全部模块可用性。顶层 `posture_svm` 键为历史兼容保留
（旧版前端以此判断在线状态），`models` 面板为统一视图。

```json
{
  "status": "ok",
  "posture_svm": { "model_available": true, "model_path": "...\\posture_svm.joblib" },
  "models": {
    "posture_svm": { "model_available": true, "model_path": "..." },
    "posture_cnn": { "model_available": false, "model_path": "...\\outputs\\posture_cnn\\best_model.pt" },
    "body_partition": { "model_available": true, "model_path": "...", "dataset_available": false },
    "weak_area_enhance": { "available": true }
  }
}
```

## GET /api/contracts/posture

返回经过后端校验的共享契约文档（`contract_version`、`pressure_matrix`、
`postures`、`excluded_actions`、`mirrored_action_pairs`）。前端运行时据此
同步标签映射，避免各端硬编码。

## POST /api/posture/predict

单帧睡姿推理。请求：

```json
{
  "pressure_matrix": [[0, 0, "..."]],   // 44×24 有限数值
  "model": "svm"                         // 可选: "svm" | "cnn" | "ensemble"，缺省 "svm"
}
```

- `svm`：SVM 模型（`backend/models/posture_svm.joblib`，本地训练产物）。
- `cnn`：CNN 模型（`outputs/posture_cnn/best_model.pt`，本地训练产物）。
- `ensemble`：对两模型概率求平均后取最大；只有一个模型可用时自动退化为
  该模型，`model` 字段如实返回实际使用的模型名。

响应 200（统一睡姿结果 + 实际使用的模型）：

```json
{
  "model": "svm",
  "label_id": 0,
  "label": "supine",
  "label_zh": "仰卧",
  "confidence": 0.97,
  "probabilities": { "supine": 0.97, "prone": 0.01, "left_lateral": 0.01, "right_lateral": 0.01 }
}
```

错误：`400 invalid_request`（输入非法或 `model` 未知）、
`503 model_unavailable`（所选模型不可用；ensemble 在两模型都不可用时返回 503）。

## POST /api/frame/analyze

单帧聚合分析，一次请求返回睡姿、身体分区与弱区增强。请求：

```json
{
  "pressure_matrix": [[0, 0, "..."]],
  "model": "svm",
  "features": ["posture", "partition", "enhance"]
}
```

- `model` 与 `features` 均为可选；缺省 `model="svm"`、
  `features=["posture", "partition", "enhance"]`。

响应 200：按请求的 `features` 返回对应键；某模块不可用时该键为错误对象，
其余模块照常返回（优雅降级）：

```json
{
  "posture": {
    "model": "svm",
    "prediction": { "label_id": 0, "label": "supine", "label_zh": "仰卧", "confidence": 0.97, "probabilities": { "...": "..." } }
  },
  "partition": {
    "mask": [[0, 1, "..."]],
    "regions": [{ "key": "shoulder", "name_zh": "肩部", "class_id": 1, "x1": 6, "x2": 18, "y1": 3, "y2": 8 }, null],
    "foreground_ratio": 0.426
  },
  "enhanced": {
    "enhanced_matrix": [[0, 0, "..."]],
    "config_used": { "gamma": 0.55, "strength": 0.8, "...": "..." }
  }
}
```

某模块不可用时的降级示例：`"partition": {"error": "model_unavailable", "message": "..."}`。

## POST /api/weak-enhance

弱压力区域增强（纯 NumPy 管线，无模型，始终可用；输出用于可视化，
不是标定物理压力，不可用于体重估计）。请求：

```json
{
  "pressure_matrix": [[0, 0, "..."]],
  "config": { "gamma": 0.55, "strength": 0.8 }
}
```

- `config` 可选，只接受 `GET /api/weak-enhance/config` 列出的参数；
  未提供的参数使用默认值。

响应 200：

```json
{
  "enhanced_matrix": [[0, 0, "..."]],
  "config_used": { "gamma": 0.55, "strength": 0.8, "...": "..." }
}
```

## GET /api/weak-enhance/config

返回全部增强参数的默认值及含义（比率均为相对当前帧鲁棒高压值的比例）。

## /api/body-partition/* 与 /body-partition/

身体部位区域划分接口保持原契约，详见 `docs/api/body-partition.md`：
掩码类别 `0` 背景、`1` 肩、`2` 背、`3` 腰、`4` 臀、`5` 大腿；`regions`
为固定顺序（肩/背/腰/臀/大腿）的五个矩形，无像素时为 `null`。

---

## 模型工件与启动

| 模型 | 默认路径 | 说明 |
|---|---|---|
| posture SVM | `backend/models/posture_svm.joblib` | 本地训练产物（不入库）：`python train\posture_svm\train_svm.py ...` |
| posture CNN | `outputs/posture_cnn/best_model.pt` | 本地训练产物（不入库）：`python -m backend.algorithms.posture_cnn.train ...` |
| body partition | `backend/models/body_partition.pth` | 已入库，无需训练即可用 |

所有路径均可用环境变量覆盖（`SLEEPMATRIX_POSTURE_SVM_MODEL`、
`SLEEPMATRIX_POSTURE_CNN_MODEL`、`SLEEPMATRIX_POSTURE_CNN_DEVICE`、
`SLEEPMATRIX_BODY_PARTITION_*` 等，见 `backend/config.py`）。
