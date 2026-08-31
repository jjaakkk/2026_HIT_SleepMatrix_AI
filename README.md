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
│   │   ├── data_augmentation.py          # 通用翻转、平移、噪声等增强
│   │   └── mock_streamer.py               # 模拟实时压力帧
│   │
│   ├── algorithms/                        # 【算法私有实现】
│   │   ├── __init__.py
│   │   │
│   │   ├── posture_svm/                   # 【成员 A】传统机器学习睡姿识别
│   │   │   ├── __init__.py
│   │   │   ├── features.py                # SVM 专用特征工程
│   │   │   ├── train_svm.py               # 分组划分、调参、评估和模型保存
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
│   └── models/                            # 训练产物；按算法命名，代码中不硬编码多份副本
│       ├── posture_svm.joblib
│       └── posture_cnn.pth
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
├── dataset/                               # 本地数据，默认不提交 Git
│   ├── raw/                               # 老师提供的原始文件，只读保存
│   ├── processed/                         # 可再生的清洗/转换结果
│   └── README.md                          # 数据来源和放置说明，可提交
│
├── docs/
│   ├── api/                               # 接口说明与示例
│   ├── reports/
│   ├── ai_conversations/
│   └── references/
│
└── tests/
    ├── test_data_utils.py                 # 公共契约、解析和增强测试
    ├── test_posture_svm.py                # 成员 A 算法测试
    └── test_api.py                        # HTTP 集成测试
```
