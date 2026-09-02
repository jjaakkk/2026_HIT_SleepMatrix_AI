"""Feature extraction for 44x24 pressure matrices."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from skimage.feature import hog

from backend.data_utils.contracts import MATRIX_SHAPE
from backend.data_utils.pressure_processing import prepare_pressure_frame
from backend.features.pressure import (
    block_mean,
    calculate_pressure_statistics,
    normalized_projections,
    occupancy_projections,
)


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
    prepared = prepare_pressure_frame(
        frame,
        matrix_shape=feature_config.matrix_shape,
        pressure_percentile=feature_config.pressure_percentile,
    )
    pressure = prepared.pressure
    normalized = prepared.normalized

    hog_features = hog(
        normalized,
        orientations=feature_config.hog_orientations,
        pixels_per_cell=feature_config.hog_pixels_per_cell,
        cells_per_block=feature_config.hog_cells_per_block,
        block_norm="L2-Hys",
        transform_sqrt=True,
        feature_vector=True,
    ).astype(np.float32, copy=False)

    coarse = block_mean(normalized, block_shape=(4, 2))
    row_projection, column_projection = normalized_projections(normalized)
    occupied, row_occupancy, column_occupancy = occupancy_projections(
        normalized,
        threshold_ratio=feature_config.contact_threshold_ratio,
    )
    global_features = calculate_pressure_statistics(
        pressure,
        normalized,
        occupied,
    ).to_array()

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
