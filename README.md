# 2026_HIT_SleepMatrix_AI

## 项目结构

当前版本采用以下项目结构。尚未实现的模块将在对应成员的开发过程中逐步补充。

```text
SleepMatrix_AI/
│
├── README.md                              # 项目介绍、安装、启动和协作说明
├── .gitignore
├── requirements.txt
│
├── shared/                                # 【前后端共享，不含 Python 业务代码】
│   └── contracts/
│       ├── README.md                      # 契约用途、版本和修改规则
│       ├── posture.json                   # 44×24、睡姿 ID、动作和镜像映射
│       └── pressure-frame.schema.json     # 压力矩阵 JSON Schema
│
├── backend/
│   ├── __init__.py
│   ├── app.py                             # 应用装配与 HTTP 服务入口
│   ├── config.py                          # 路径、端口等运行配置，不重复定义数据契约
│   │
│   ├── data_utils/                        # 【A/B/C/D 公共数据层】
│   │   ├── __init__.py
│   │   ├── contracts.py                  # 加载并校验 shared/contracts
│   │   ├── data_loader.py                # 当前解析 TXT；未来在此扩展 CSV 等格式
│   │   ├── pressure_processing.py         # 压力帧校验、裁剪和归一化
│   │   ├── data_augmentation.py          # 通用翻转、平移、噪声等增强
│   │   └── mock_streamer.py               # 模拟实时压力帧
│   │
│   ├── features/                          # 【A/B/C/D 可复用特征原语】
│   │   ├── __init__.py
│   │   └── pressure.py                    # 分块、投影、接触率、重心等具名特征
│   │
│   ├── algorithms/                        # 【算法私有实现】
│   │   ├── __init__.py
│   │   │
│   │   ├── posture_svm/                   # 【成员 A】传统机器学习睡姿识别
│   │   │   ├── __init__.py
│   │   │   ├── features.py                # HOG 与 SVM 997 维特征拼接协议
│   │   │   ├── inference.py               # SVM 推理接口
│   │   │   └── README.md
│   │   │
│   │   ├── posture_cnn/                   # 【成员 B】CNN 睡姿识别
│   │   │   ├── model_define.py
│   │   │   ├── train_cnn.py
│   │   │   └── inference.py
│   │   │
│   │   ├── body_partition/                # 【成员 C】身体部位划分
│   │   │   ├── partition.py
│   │   │   └── utils.py
│   │   │
│   │   └── weak_area_enhance/             # 【成员 D】弱压力区域增强
│   │       ├── enhance.py
│   │       └── compare.py
│   │
│   └── models/                            # 本地训练产物；整个目录不提交 Git
│
├── frontend/                              # 【成员 E】只通过共享契约和 HTTP API 获取数据
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── main.js
│   │   ├── api.js                         # 请求和响应解析
│   │   ├── heatmap.js
│   │   ├── dashboard.js
│   │   └── airbag_anim.js
│   └── assets/
│
├── dataset/                               # 本地数据集；整个目录不提交 Git
│
├── train/                                 # 训练入口脚本
│   └── posture_svm/
│       ├── train_svm.py                  # SVM 划分、调参、训练和评估
│       └── README.md                     # SVM 训练使用说明
│
├── docs/
│   ├── api/                               # 接口说明与示例
│   ├── reports/
│   ├── ai_conversations/
│   └── references/
│
└── tests/
    ├── test_data_utils.py                 # 公共契约、解析和增强测试
    ├── test_pressure_features.py          # 公共压力预处理与特征原语测试
    ├── test_posture_svm.py                # 成员 A 算法测试
    └── test_api.py                        # HTTP 集成测试
```

## SVM 睡姿识别：训练与推理

以下命令均在项目根目录执行，适用于 Windows PowerShell。

### 1. 准备环境

```powershell
conda activate sleepMatrix
python --version
python -m pip install -r requirements.txt
python -m pip check
```

项目使用 Python 3.10。当前睡姿数据应位于：

```text
dataset/睡姿 区域划分data/睡姿数据/
```

数据加载器会递归读取“受试者标识 + 动作编号”的 `.txt` 文件，自动排除空载与动态采集文件。

### 2. 训练 SVM

下面的命令使用现有数据完成按受试者划分、分组交叉验证、模型训练和测试集评估：

```powershell
python train\posture_svm\train_svm.py `
  --dataset-dir "dataset\睡姿 区域划分data\睡姿数据" `
  --model-path "backend\models\posture_svm.joblib" `
  --jitter-copies 0 `
  --n-jobs -1
```

当前数据集已经包含左右镜像帧，不要添加 `--include-horizontal-mirror`。上述命令使用 `--jitter-copies 0`，不会额外生成平移和噪声副本；如需实验额外增强，可改为正整数。

训练完成后生成：

```text
backend/models/posture_svm.joblib       # 本地生成的模型（不提交）
backend/models/posture_svm.metrics.json # 本地生成的指标（不提交）
```

模型和指标均属于本地训练产物，不提交 Git。其他成员需要在本地准备数据后运行同一训练命令生成。

查看训练指标：

```powershell
cat -Raw -Encoding UTF8 backend\models\posture_svm.metrics.json
```

查看全部训练参数：

```powershell
python train\posture_svm\train_svm.py --help
```

### 3. 使用命令行推理

推理指定 TXT 文件中的第一帧：

```powershell
python backend\algorithms\posture_svm\inference.py `
  --input-file "dataset\睡姿 区域划分data\睡姿数据\SAI\SAI_1.txt" `
  --frame-index 0 `
  --model-path "backend\models\posture_svm.joblib"
```

对一个 TXT 文件中的全部帧进行批量推理：

```powershell
python backend\algorithms\posture_svm\inference.py `
  --input-file "dataset\睡姿 区域划分data\睡姿数据\SAI\SAI_1.txt" `
  --all-frames `
  --model-path "backend\models\posture_svm.joblib"
```

查看全部推理参数：

```powershell
python backend\algorithms\posture_svm\inference.py --help
```

CLI 输出为 JSON，包括输入文件、帧号、睡姿 ID、英文标签、中文标签、置信度和四类概率。

### 4. 使用 Python API 推理

下面的示例读取 `SAI_1.txt` 的第一帧并执行单帧推理。也可以将路径替换为其他静态动作文件。

```python
import json

from backend.algorithms.posture_svm.inference import PostureSVMClassifier
from backend.data_utils.data_loader import iter_pressure_frames

sample_path = r"dataset\睡姿 区域划分data\睡姿数据\SAI\SAI_1.txt"
pressure_matrix = next(iter_pressure_frames(sample_path))

classifier = PostureSVMClassifier("backend/models/posture_svm.joblib")
prediction = classifier.predict(pressure_matrix)
print(json.dumps(prediction.to_dict(), ensure_ascii=False, indent=2))
```

返回内容包括睡姿 ID、英文标签、中文标签、置信度和四类概率。批量推理可使用：

```python
predictions = classifier.predict_batch(pressure_matrices)  # (N, 44, 24)
```

### 5. 通过 HTTP 接口推理

在第一个 PowerShell 终端启动 Flask 服务：

```powershell
conda activate sleepMatrix
python -m backend.app
```

服务默认监听 `http://127.0.0.1:5000`。在第二个 PowerShell 终端检查服务和模型状态：

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/health"
```

读取真实 TXT 的第一帧并请求推理接口：

```powershell
$SamplePath = "dataset\睡姿 区域划分data\睡姿数据\SAI\SAI_1.txt"
$Rows = Get-Content $SamplePath | Where-Object { $_.Trim() } | Select-Object -First 44
$Matrix = [System.Collections.Generic.List[object]]::new()

foreach ($Row in $Rows) {
  [void]$Matrix.Add([double[]]($Row -split ','))
}

$Body = @{ pressure_matrix = $Matrix } | ConvertTo-Json -Depth 4
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:5000/api/posture/predict" `
  -ContentType "application/json" `
  -Body $Body
```

接口要求 `pressure_matrix` 严格为 44×24 的有限数值矩阵。模型不存在时推理接口返回 HTTP 503；输入格式错误时返回 HTTP 400。

## 测试说明

项目测试基于 Python 标准库 `unittest`，无需额外安装 `pytest`。测试使用临时目录、合成压力矩阵和临时模型，不依赖本地正式数据集，也不要求提前存在 `backend/models/posture_svm.joblib`。

### 测试范围

| 测试文件 | 主要覆盖内容 |
|---|---|
| `tests/test_data_utils.py` | 共享契约、动作标签映射、TXT 文件名和压力帧解析、镜像增强 |
| `tests/test_pressure_features.py` | 压力帧校验、负值裁剪、归一化、分块、投影和具名统计特征 |
| `tests/test_posture_svm.py` | 997 维特征、受试者隔离、模型产物、训练 CLI、单帧及批量推理 CLI |
| `tests/test_api.py` | 健康检查、前后端共享契约接口、推理请求格式校验 |

`test_posture_svm.py` 会使用小型合成数据实际执行分组网格搜索、训练、模型保存和重新加载，因此相较其他测试需要更多时间，但不会使用正式数据集。

### 运行全部测试

先激活项目环境，再从仓库根目录执行：

```powershell
conda activate sleepMatrix
python -m unittest discover -s tests -v
```

全部通过时，命令末尾会显示 `OK`。

### 按模块运行

```powershell
python -m unittest tests.test_data_utils -v
python -m unittest tests.test_pressure_features -v
python -m unittest tests.test_posture_svm -v
python -m unittest tests.test_api -v
```

### 运行单个测试

以下示例只验证训练 CLI 能否使用文档规定的 TXT 格式完成训练和模型落盘：

```powershell
python -m unittest `
  tests.test_posture_svm.SplitAndArtifactTests.test_direct_training_cli_runs_on_documented_text_format `
  -v
```

代码或公共数据契约发生修改后应运行全部测试；只修改单一模块时，可以先运行对应测试文件，再执行完整回归测试。
