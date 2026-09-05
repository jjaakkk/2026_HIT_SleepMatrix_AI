# 智能床垫睡姿识别 CNN

本项目使用智能床垫的 `44×24` 压力传感器矩阵识别四种睡姿：仰卧、俯卧、左侧卧和右侧卧。模型测试严格采用训练阶段未见过的用户，避免连续帧和镜像帧造成数据泄漏。

## 数据范围

仅使用：

```text
dataset/睡姿 区域划分data/睡姿数据/<用户>/<用户>_<动作编号>.txt
```

为兼容原始压缩包解压后的双层目录，读取器也会自动检查 `dataset/睡姿 区域划分data/睡姿 区域划分data/睡姿数据/`。还可以通过各命令的 `--data-dir` 显式指定数据目录。

标签规则：

| 动作编号 | 标签 | 类别编号 |
| --- | --- | --- |
| 1-6 | 仰卧 | 0 |
| 7-9 | 俯卧 | 1 |
| 10-15 | 左侧卧 | 2 |
| 16-21 | 右侧卧 | 3 |

`动态一/二`、`空载`、预生成热力图和区域划分数据不参与训练。数据已经包含水平镜像，训练增强不会再次执行水平翻转。

## 环境安装

建议使用 Python 3.10 或更高版本。在 PowerShell 中执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

若使用 NVIDIA GPU，应先安装与显卡驱动兼容的 PyTorch CUDA 构建，再用清华镜像安装其余依赖。本次实验验证环境为 `torch 2.7.0+cu118`：

```powershell
pip install torch==2.7.0+cu118 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

安装完成后检查 GPU：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

即使 CUDA 不可用，所有命令也可在 CPU 上运行，只是训练速度较慢。

## 运行流程

### 1. 校验全部数据

```powershell
python -m backend.algorithms.posture_cnn.inspect_data
```

正确数据应满足：33名用户、693个静态文件、23,760帧、四类各5,940帧。结果默认保存到 `outputs/posture_cnn/data_summary.json`。

读取器不依赖帧间空行：它会忽略空行后每44行切为一帧，从而正确处理镜像数据拼接处缺失空行的问题。

### 2. 固定用户划分

```powershell
python -m backend.algorithms.posture_cnn.make_splits --seed 42
```

生成 `splits.json`：23名开发用户和10名最终测试用户；开发用户内部再分为18名训练用户和5名验证用户。测试用户不得用于选择模型或修改超参数。

### 3. 训练 CNN

```powershell
python -m backend.algorithms.posture_cnn.train --epochs 50 --batch-size 16 --device cuda
```

主要输出：

- `outputs/posture_cnn/best_model.pt`：验证集 macro-F1 最佳的模型；
- `outputs/posture_cnn/history.csv`：逐轮训练记录；
- `outputs/posture_cnn/training_curves.png`：训练曲线；
- `outputs/posture_cnn/training_summary.json`：训练配置和摘要。

Windows 首次运行建议保持 `--num-workers 0`。确认稳定后可尝试增加 worker 数量。

快速冒烟测试：

```powershell
python -m backend.algorithms.posture_cnn.train --epochs 1 --max-train-batches 2 --max-val-batches 2 --device auto --output-dir outputs/smoke
```

### 4. 最终测试

训练和参数选择结束后，在锁定的10名新用户上运行一次：

```powershell
python -m backend.algorithms.posture_cnn.evaluate --batch-size 16 --device cuda
```

输出包括 accuracy、macro precision、macro recall、macro F1、每名测试用户准确率、混淆矩阵和逐帧预测 CSV。

### 5. 单帧预测

```powershell
python -m backend.algorithms.posture_cnn.inference "dataset\睡姿 区域划分data\睡姿数据\dgs\dgs_1.txt" --frame-index 0 --device cuda
```

## 实验结果

随机种子为 42，最终测试集包含训练阶段从未出现的 10 名用户、共 7,200 帧。最佳模型在第 8 轮达到验证 macro-F1 1.0000，训练随后按连续 8 轮无提升的规则提前停止。

| 指标 | 结果 |
| --- | ---: |
| Accuracy | 0.9650 |
| Macro Precision | 0.9661 |
| Macro Recall | 0.9650 |
| Macro F1 | 0.9650 |

完整混淆矩阵、分类别指标和逐用户准确率保存在 `backend/models/posture_cnn.metrics.json`。模型权重和训练输出可以通过上述命令复现，不提交 Git。

## 测试

```powershell
python -m pytest tests/posture_cnn -q
```

测试覆盖动作标签、缺失空行时的切帧、错误列数、用户级划分、指标计算和 CNN 输出形状。

## 方法说明

模型由三层二维卷积、批归一化、池化、全局平均池化和分类层组成。输入压力先截断负值、执行 `log1p`，再使用训练用户计算的均值和标准差进行标准化。

训练增强包括小范围传感器网格平移、压力强度缩放、轻微噪声和少量传感器点失活。验证集和测试集不执行增强，也不会再次进行水平翻转。

## 主要文件

| 文件 | 作用 |
| --- | --- |
| `data_io.py` | 数据读取、标签映射与完整性检查 |
| `dataset.py` | PyTorch Dataset、标准化和数据增强 |
| `model.py` | 轻量二维 CNN 定义 |
| `train.py` | 训练、验证、早停和最佳模型保存 |
| `evaluate.py` | 独立测试集评估和结果导出 |
| `inference.py` | 单帧命令行与 Python 推理 |
| `splits.json` | 可复现的用户级数据划分 |
