# body_partition — 身体部位区域划分（成员 C）

将 44×24 压力矩阵分割为 6 类：背景、肩部、背部、腰部、臀部、大腿部
（小腿部仅 3 人有标注，按数据集说明不使用）。

## 模块组成

| 文件 | 职责 |
| --- | --- |
| `model_define.py` | 轻量 U-Net（两级下采样 + 空洞卷积瓶颈），训练与推理共用 |
| `partition.py` | region 标注解析、矩形↔掩码互转、像素准确率 / IoU / 边界误差等指标 |
| `preprocess.py` | 逐帧 99 分位归一化（消除体重 / 枕头基线差异，训练与推理必须一致） |
| `inference.py` | `BodyPartitionPredictor`：加载 `.pth` 工件，输出掩码与五区域矩形 |

## 训练（代码在仓库根目录 `train/`）

```powershell
python -m train.body_partition.dataset_prep                        # 解析 data.json -> npz
python -m train.body_partition.train_partition --split random      # 70/30 随机划分，目标 ≥95%
python -m train.body_partition.train_partition --split subject     # 留人法新用户评估，目标 ≥70%
```

产物：

- `backend/models/body_partition.pth` —— 生产模型（random 划分训练）
- `backend/models/body_partition.metrics.json` —— 验证集指标报告
- `docs/body-partition/body_partition_subject_eval.json` —— 新用户评估报告
- `dataset/processed/body_partition_train_augmented.npz` —— 增强后的训练集

## 推理示例

```python
from backend.algorithms.body_partition.inference import BodyPartitionPredictor

predictor = BodyPartitionPredictor()
result = predictor.predict(frame_44x24)   # numpy / list 均可
result.mask        # 44x24 六类分割结果（0 背景, 1..5 肩背腰臀腿）
result.regions     # 五区域矩形 [{key, name_zh, x1, x2, y1, y2}, ...]
```

## 算法要点

- 标注为五（六）个轴对齐矩形，渲染成逐像素分割掩码后按语义分割训练；
- 增强只做平移 / 高斯噪声 / 增益 / 基线偏移 / 稀疏死点，**不做左右翻转**
  （数据集已含翻转样本，说明文档明确禁止重复使用）；
- 归一化采用逐帧正值 99 分位缩放，保证跨用户泛化；
- 参考：`智能床垫数据集说明/图片和附件/Estimating pose from pressure data
  for smart bedswithdeep.pdf` 中压力垫身体部位分割的 CNN 编解码思路。
