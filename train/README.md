# train/ — 身体部位区域划分训练代码

对应算法模块：`backend/algorithms/body_partition/`（推理代码与模型定义）。
本目录只放训练相关代码，全部命令在仓库根目录下执行。

## 环境

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

数据准备：将数据集说明中的 `区域划分/data.json` 复制到
`dataset/raw/body_partition_data.json`（当前仓库已完成该步骤）。

## 流程

```powershell
# 1. 解析标注 JSON -> 基础数组（帧 + 六类掩码 + 元数据）
python -m train.body_partition.dataset_prep

# 2a. 随机 70/30 划分训练（要求验证集像素准确率 >95%）→ 生产模型
python -m train.body_partition.train_partition --split random

# 2b. 留人法新用户评估（30% 受试者作为全新用户，要求 >70%）
python -m train.body_partition.train_partition --split subject

# 3. 生成报告用可视化图（每种睡姿的 真值/预测 对比）
python -m train.body_partition.visualize
```

## 文件

| 文件 | 职责 |
| --- | --- |
| `dataset_prep.py` | 解析 14400 条标注记录为 `frames/masks/subjects/actions/sleep_positions` |
| `augment.py` | 帧与掩码联合增强（平移/噪声/增益/基线/死点，不做翻转） |
| `train_partition.py` | 两种划分协议、加权交叉熵训练、早停、全套指标与工件落盘 |
| `visualize.py` | 分睡姿的对比图与训练曲线，输出到 `docs/body-partition/` |

## 增强说明

数据集说明明确指出最终数据集已包含左右对称翻转样本，**禁止重复使用翻转
增强**。本实现仅对训练划分做：±2 行 / ±1 列联合平移、按压力尺度的高斯噪声、
0.9–1.1 增益、±2% 基线偏移、0.05% 稀疏死点。增强后的训练集保存为
`dataset/processed/body_partition_train_augmented.npz` 备查。

## 指标口径

- **像素准确率（pixel accuracy）**：全部 44×24 像素中预测类别与真值一致的比例，
  即题目“验证集准确率”的口径；
- 辅助指标：mIoU、各类 IoU、区域矩形 IoU、纵向边界平均绝对误差（行）；
- 新用户口径：`GroupShuffleSplit` 按受试者留出 30%，逐受试者报告准确率。
