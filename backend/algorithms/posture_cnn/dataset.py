"""PyTorch Dataset、训练集标准化和压力数据增强。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from .data_io import FrameRecord, read_pressure_frames, unique_files


@lru_cache(maxsize=256)
def _cached_frames(path: str) -> np.ndarray:
    return read_pressure_frames(path)


def pressure_transform(frame: np.ndarray) -> np.ndarray:
    """压缩压力动态范围；负压力值按无效值截断为0。"""

    return np.log1p(np.clip(frame, a_min=0.0, a_max=None)).astype(np.float32)


def compute_normalization(records: Sequence[FrameRecord]) -> dict[str, float]:
    """仅使用训练用户计算 log1p 压力值的均值与标准差。"""

    total = 0
    value_sum = 0.0
    square_sum = 0.0
    for path in unique_files(records):
        values = pressure_transform(read_pressure_frames(path)).astype(np.float64)
        total += values.size
        value_sum += float(values.sum())
        square_sum += float(np.square(values).sum())
    if total == 0:
        raise ValueError("训练记录为空，无法计算标准化参数")
    mean = value_sum / total
    variance = max(square_sum / total - mean * mean, 1e-12)
    return {"mean": float(mean), "std": float(np.sqrt(variance)), "transform": "log1p"}


def translate_with_zeros(frame: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """以0填充的整数网格平移，不产生环绕。"""

    result = np.zeros_like(frame)
    height, width = frame.shape
    src_y0, src_y1 = max(0, -dy), min(height, height - dy)
    src_x0, src_x1 = max(0, -dx), min(width, width - dx)
    dst_y0, dst_y1 = max(0, dy), min(height, height + dy)
    dst_x0, dst_x1 = max(0, dx), min(width, width + dx)
    if src_y0 < src_y1 and src_x0 < src_x1:
        result[dst_y0:dst_y1, dst_x0:dst_x1] = frame[src_y0:src_y1, src_x0:src_x1]
    return result


class PressureAugmenter:
    """保持睡姿语义的轻量训练增强；刻意不包含水平翻转。"""

    def __init__(
        self,
        max_shift: int = 2,
        scale_range: tuple[float, float] = (0.9, 1.1),
        noise_std: float = 2.0,
        dropout_probability: float = 0.005,
    ) -> None:
        self.max_shift = max_shift
        self.scale_range = scale_range
        self.noise_std = noise_std
        self.dropout_probability = dropout_probability

    def __call__(self, frame: np.ndarray) -> np.ndarray:
        output = frame.astype(np.float32, copy=True)
        if self.max_shift > 0:
            dy = int(np.random.randint(-self.max_shift, self.max_shift + 1))
            dx = int(np.random.randint(-self.max_shift, self.max_shift + 1))
            output = translate_with_zeros(output, dy, dx)
        scale = float(np.random.uniform(*self.scale_range))
        output *= scale
        if self.noise_std > 0:
            output += np.random.normal(0.0, self.noise_std, output.shape).astype(np.float32)
        if self.dropout_probability > 0:
            mask = np.random.random(output.shape) < self.dropout_probability
            output[mask] = 0.0
        return np.clip(output, a_min=0.0, a_max=None)


class PressureFrameDataset(Dataset):
    def __init__(
        self,
        records: Sequence[FrameRecord],
        normalization: dict[str, float],
        augment: bool = False,
    ) -> None:
        self.records = list(records)
        self.mean = float(normalization["mean"])
        self.std = float(normalization["std"])
        if self.std <= 0:
            raise ValueError("标准差必须大于0")
        self.augmenter = PressureAugmenter() if augment else None

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int):
        record = self.records[index]
        frame = _cached_frames(record.path)[record.frame_index]
        if self.augmenter is not None:
            frame = self.augmenter(frame)
        transformed = pressure_transform(frame)
        normalized = (transformed - self.mean) / self.std
        tensor = torch.from_numpy(normalized).unsqueeze(0)
        metadata = {
            "subject": record.subject,
            "action": record.action,
            "frame_index": record.frame_index,
            "path": record.path,
        }
        return tensor, torch.tensor(record.label, dtype=torch.long), metadata


def preprocess_single_frame(
    frame: np.ndarray,
    normalization: dict[str, float],
) -> torch.Tensor:
    transformed = pressure_transform(frame)
    normalized = (transformed - float(normalization["mean"])) / float(
        normalization["std"]
    )
    return torch.from_numpy(normalized.astype(np.float32)).unsqueeze(0).unsqueeze(0)
