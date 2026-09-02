# 数据集目录

本目录保存项目使用的正式数据集。为了让团队成员能够复现训练，原始 TXT、
区域标注 JSON 和数据说明文件纳入 Git；热力图 PNG 等可再生的二进制派生产物
不纳入 Git。

当前目录结构：

```text
dataset/
├── README.md
└── 睡姿 区域划分data/
    ├── readme                         # 受试者身高、体重
    ├── 睡姿数据/                      # 各受试者动作 TXT
    └── 区域划分/
        └── data.json                  # 身体区域标注
```

当前 TXT 数据加载器会递归搜索指定目录。SVM 训练使用：

```powershell
python backend\algorithms\posture_svm\train_svm.py `
  --dataset-dir "dataset\睡姿 区域划分data\睡姿数据"
```

项目采用的数据格式和标签定义见 `shared/contracts/posture.json` 与
`shared/contracts/pressure-frame.schema.json`。`assets/` 中的本地原始说明资料
按约定不纳入 Git 跟踪。
