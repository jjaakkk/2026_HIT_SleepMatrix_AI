"""Feature extraction for 44x24 pressure matrices."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from skimage.feature import hog

from backend.data_utils.contracts import MATRIX_SHAPE


@dataclass(frozen=True)
class FeatureConfig:
    matrix_shape: tuple[int, int] = MATRIX_SHAPE
    hog_orientations: int = 9
    hog_pixels_per_cell: tuple[int, int] = (8, 4)
    hog_cells_per_block: tuple[int, int] = (2, 2)
    pressure_percentile: float = 99.0
    contact_threshold_ratio: float = 0.05

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> "FeatureConfig":
        normalized = dict(values)
        for key in ("matrix_shape", "hog_pixels_per_cell", "hog_cells_per_block"):
            if key in normalized:
                normalized[key] = tuple(normalized[key])
        return cls(**normalized)


def _validate_frame(frame: np.ndarray, config: FeatureConfig) -> np.ndarray:
    array = np.asarray(frame, dtype=np.float32)
    if array.shape != config.matrix_shape:
        raise ValueError(
            f"Pressure matrix shape must be {config.matrix_shape}, received {array.shape}."
        )
    if not np.isfinite(array).all():
        raise ValueError("Pressure matrix contains NaN or infinite values.")
    # Small negative sensor offsets are not physical pressure and would distort HOG.
    return np.maximum(array, 0.0)


def extract_frame_features(
    frame: np.ndarray,
    config: FeatureConfig | None = None,
) -> np.ndarray:
    """Extract scale-robust spatial features from one pressure frame.

    The vector combines HOG, coarse block averages, row/column projections,
    occupancy projections and a few global pressure/shape statistics.  It
    retains absolute total/max pressure as log-scaled features while most
    spatial features are normalized, reducing sensitivity to participant
    weight.
    """

    feature_config = config or FeatureConfig()
    pressure = _validate_frame(frame, feature_config)
    positive = pressure[pressure > 0]
    if positive.size:
        scale = float(np.percentile(positive, feature_config.pressure_percentile))
    else:
        scale = 1.0
    if not np.isfinite(scale) or scale <= np.finfo(np.float32).eps:
        scale = 1.0
    normalized = np.clip(pressure / scale, 0.0, 1.0)

    hog_features = hog(
        normalized,
        orientations=feature_config.hog_orientations,
        pixels_per_cell=feature_config.hog_pixels_per_cell,
        cells_per_block=feature_config.hog_cells_per_block,
        block_norm="L2-Hys",
        transform_sqrt=True,
        feature_vector=True,
    ).astype(np.float32, copy=False)

    rows, columns = feature_config.matrix_shape
    # 44x24 -> 11x12 block means.  The documented shape is divisible by 4x2.
    coarse = normalized.reshape(rows // 4, 4, columns // 2, 2).mean(axis=(1, 3))

    total_normalized = float(normalized.sum())
    projection_scale = max(total_normalized, np.finfo(np.float32).eps)
    row_projection = normalized.sum(axis=1) / projection_scale
    column_projection = normalized.sum(axis=0) / projection_scale

    occupied = normalized >= feature_config.contact_threshold_ratio
    row_occupancy = occupied.mean(axis=1)
    column_occupancy = occupied.mean(axis=0)

    y_grid, x_grid = np.indices(feature_config.matrix_shape, dtype=np.float32)
    if total_normalized > 0:
        centroid_x = float((normalized * x_grid).sum() / total_normalized) / max(
            columns - 1, 1
        )
        centroid_y = float((normalized * y_grid).sum() / total_normalized) / max(
            rows - 1, 1
        )
        spread_x = float(
            np.sqrt(
                (
                    normalized * (x_grid - centroid_x * (columns - 1)) ** 2
                ).sum()
                / total_normalized
            )
        ) / max(columns - 1, 1)
        spread_y = float(
            np.sqrt(
                (normalized * (y_grid - centroid_y * (rows - 1)) ** 2).sum()
                / total_normalized
            )
        ) / max(rows - 1, 1)
    else:
        centroid_x = centroid_y = spread_x = spread_y = 0.0

    mirror_difference = float(np.mean(np.abs(normalized - np.fliplr(normalized))))
    global_features = np.asarray(
        [
            np.log1p(float(pressure.sum())),
            np.log1p(float(pressure.max(initial=0.0))),
            np.log1p(float(positive.mean())) if positive.size else 0.0,
            float(occupied.mean()),
            centroid_x,
            centroid_y,
            spread_x,
            spread_y,
            mirror_difference,
        ],
        dtype=np.float32,
    )

    return np.concatenate(
        [
            hog_features,
            coarse.ravel(),
            row_projection,
            column_projection,
            row_occupancy,
            column_occupancy,
            global_features,
        ]
    ).astype(np.float32, copy=False)


def extract_feature_matrix(
    frames: np.ndarray,
    config: FeatureConfig | None = None,
) -> np.ndarray:
    """Extract a 2-D feature matrix from a batch of pressure frames."""

    feature_config = config or FeatureConfig()
    batch = np.asarray(frames)
    if batch.ndim != 3 or tuple(batch.shape[1:]) != feature_config.matrix_shape:
        raise ValueError(
            "Expected pressure frames with shape "
            f"(n, {feature_config.matrix_shape[0]}, {feature_config.matrix_shape[1]}), "
            f"received {batch.shape}."
        )
    if batch.shape[0] == 0:
        raise ValueError("At least one pressure frame is required.")
    return np.stack([extract_frame_features(frame, feature_config) for frame in batch])
