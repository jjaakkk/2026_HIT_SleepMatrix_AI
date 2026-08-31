# SVM 睡姿识别模块

本模块实现 44×24 压力矩阵的四分类。矩阵尺寸、标签和动作映射以 `shared/contracts/posture.json` 为唯一公共定义，数据读取与通用增强位于 `backend/data_utils/`。

| 标签 ID | 睡姿 | 动作编号 |
|---:|---|---|
| 0 | 仰卧 | 1–6 |
| 1 | 俯卧 | 7–9 |
| 2 | 左侧卧 | 10–15 |
| 3 | 右侧卧 | 16–21 |

动作 0 是空载采集，动作 22 是动态采集流程，不参与静态睡姿四分类。

## 预期数据布局

将原始 `.txt` 文件放入仓库的 `dataset/`，允许任意层级子目录。文件名应为“受试者标识 + 动作编号”，例如：

```text
dataset/
├── 张三_1.txt
├── 张三_2.txt
├── ...
└── 李四_21.txt
```

每帧由 44 行、每行 24 个逗号分隔数值组成。帧之间可以有空行；即使没有空行，读取器也会每 44 行切分一帧。

## 训练

在仓库根目录激活项目环境后运行：

```powershell
conda activate sleepMatrix
python -m backend.algorithms.posture_svm.train_svm
```

默认执行以下流程：

1. 通过公共数据层读取并校验数据，再按受试者将原始数据划分为 70% 训练集、30% 测试集；同一受试者不会同时出现在两侧。
2. 在原始训练集内部使用按受试者分组的交叉验证选择 RBF-SVM 参数。
3. 选定参数后，只对训练集添加小幅平移和噪声；增强帧不会充当验证或测试数据。
4. 提取 HOG、粗粒度压力分布、行列投影、接触区域和压力统计特征。
5. 将模型写入 `backend/models/posture_svm.joblib`，指标写入同目录的 `posture_svm.metrics.json`。

数据说明指出最终数据已经包含镜像帧，因此默认不会再次左右翻转。只有确认拿到的是未增强原始数据时才使用：

```powershell
python -m backend.algorithms.posture_svm.train_svm --include-horizontal-mirror
```

可用 `--help` 查看数据目录、模型路径、随机种子、增强强度和并行数等参数。

## Python 推理

```python
from backend.algorithms.posture_svm.inference import PostureSVMClassifier

classifier = PostureSVMClassifier()
result = classifier.predict(pressure_matrix)  # 44×24 数值矩阵
print(result.to_dict())
```

## HTTP 推理

训练出模型后启动服务：

```powershell
python -m backend.app
```

请求 `POST /api/posture/predict`：

```json
{
  "pressure_matrix": [[0, 0, 0], [0, 0, 0]]
}
```

实际数组必须严格为 44×24。返回标签、中英文睡姿、置信度和四类概率。没有模型时 `/api/health` 仍可用，而推理接口返回 HTTP 503。
