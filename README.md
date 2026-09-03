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
│   │   ├── body_partition/                # 【成员 C】身体部位划分（已实现）
│   │   │   ├── model_define.py            # 轻量 U-Net 六类分割网络（训练/推理共用）
│   │   │   ├── partition.py               # region 标注解析、矩形↔掩码互转、指标
│   │   │   ├── preprocess.py              # 逐帧 99 分位归一化
│   │   │   ├── demo_data.py               # 标注数据集懒加载（供展示 API 浏览）
│   │   │   ├── inference.py               # 分割推理接口
│   │   │   └── README.md
│   │   │
│   │   └── weak_area_enhance/             # 【成员 D】弱压力区域增强
│   │       ├── enhance.py
│   │       └── compare.py
│   │
│   └── models/                            # 训练产物；按算法命名，代码中不硬编码多份副本
│       ├── posture_svm.joblib
│       ├── posture_cnn.pth
│       └── body_partition.pth             # 成员 C 分割模型（+ .metrics.json）
│
├── train/                                 # 【成员 C】身体部位划分训练代码
│   ├── dataset_prep.py                    # 标注 JSON -> 帧/掩码数组
│   ├── augment.py                         # 帧-掩码联合增强（不做翻转）
│   ├── train_partition.py                 # 70/30 随机划分与留人法两种训练协议
│   ├── visualize.py                       # 报告用对比图与训练曲线
│   └── README.md
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
│   ├── assets/
│   └── body-partition/                    # 【成员 C】区域划分展示页（/body-partition/）
│       └── index.html                     # 自包含页面：睡姿切换、逐帧浏览、预测/真值叠加
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
    ├── test_body_partition.py             # 成员 C 标注解析、掩码、指标与增强测试
    └── test_api.py                        # HTTP 集成测试
```
