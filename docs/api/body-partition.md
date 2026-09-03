# Body-Partition API

身体部位区域划分（成员 C）的 HTTP 接口。基础地址默认 `http://127.0.0.1:5000`。
掩码类别约定：`0` 背景，`1` 肩部，`2` 背部，`3` 腰部，`4` 臀部，`5` 大腿部。

## GET /api/health

服务与模型可用性。`body_partition` 块包含 `model_available`、`model_path`、
`dataset_available`。

## POST /api/body-partition/predict

对任意一帧 44×24 压力矩阵做区域分割。

请求：

```json
{ "pressure_matrix": [[0, 0, ...], ...] }
```

响应 200：

```json
{
  "mask": [[0, 0, ...], ...],
  "regions": [
    { "key": "shoulder", "name_zh": "肩部", "class_id": 1,
      "x1": 6, "x2": 18, "y1": 3, "y2": 8 },
    null
  ],
  "foreground_ratio": 0.426
}
```

- `regions` 为五区域矩形列表（顺序固定：肩/背/腰/臀/大腿），某区域无像素时为 `null`；
  坐标为左闭右开 `[x1, x2) × [y1, y2)`，与数据集标注口径一致。
- 错误：`400 invalid_request`（矩阵缺失/非数值/形状非 44×24/含 NaN），
  `503 model_unavailable`（模型未训练或未放置）。

## GET /api/body-partition/sample?subject=<名>&action=<1-21>&frame=<n>

返回标注数据集中的一帧及其真值掩码；模型可用时附预测结果。

响应 200：

```json
{
  "subject": "SAI", "action": 1, "frame": 0, "sleep_pos": 0,
  "pressure_matrix": [[...]],
  "ground_truth_mask": [[...]],
  "predicted_mask": [[...]],
  "predicted_regions": [ ... ]
}
```

`sleep_pos`：`0` 仰卧，`1` 俯卧，`2` 左侧卧，`3` 右侧卧。
错误：`400` 缺参数，`404 not_found`（无此样本），`503 dataset_unavailable`。

## GET /api/body-partition/catalog

受试者 → 动作 → `{frames, sleep_pos}` 的完整目录，供前端构建选择器。

## GET /api/body-partition/metrics

训练指标报告（`backend/models/body_partition.metrics.json` 内容）：

- `metrics.pixel_accuracy`：70/30 随机划分验证集像素准确率
- `metrics.pixel_accuracy_by_position`：分睡姿准确率
- `subject_eval.pixel_accuracy_mean/std`：留人法多种子新用户准确率摘要

模型未训练时返回 `404 metrics_unavailable`。

## 静态展示页

`GET /body-partition/` —— 数据展示前端（睡姿切换、逐帧浏览、预测/真值叠加）。
