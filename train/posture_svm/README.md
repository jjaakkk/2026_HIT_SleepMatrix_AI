# SVM 训练说明

本目录存放成员 A 的 SVM 训练入口。训练实现、参数和评估流程均位于
`train_svm.py`；模型和指标写入本地 `backend/models/`，该目录已被 Git 忽略。

## 环境

```powershell
conda activate sleepMatrix
python -m pip install -r requirements.txt
python -m pip check
```

## 训练

从仓库根目录执行：

```powershell
python train\posture_svm\train_svm.py `
  --dataset-dir "dataset\睡姿 区域划分data\睡姿数据" `
  --model-path "backend\models\posture_svm.joblib" `
  --jitter-copies 0 `
  --n-jobs -1
```

也支持模块方式：

```powershell
python -m train.posture_svm.train_svm --help
```

训练流程按受试者划分训练集和测试集，在训练集内部进行分组交叉验证，
再保存本地模型和评估指标。当前数据已经包含左右镜像帧，默认不要使用
`--include-horizontal-mirror`。

查看全部参数：

```powershell
python train\posture_svm\train_svm.py --help
```

## 本地产物

```text
backend/models/posture_svm.joblib
backend/models/posture_svm.metrics.json
```

以上文件均为可再生的本地训练产物，不提交 Git。推理命令见
`backend/algorithms/posture_svm/README.md` 和根目录 `README.md`。
