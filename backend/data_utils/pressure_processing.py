"""Shared validation and normalization for pressure matrices."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import MATRIX_SHAPE


@dataclass(frozen=True)
class PreparedPressureFrame:
    """A validated frame and its scale-normalized representation."""

    pressure: np.ndarray
    normalized: np.ndarray
    normalization_scale: float


def validate_pressure_frame(
    frame: np.ndarray | list[list[float]],
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
) -> np.ndarray:
    """Convert one pressure frame to finite ``float32`` data of the agreed shape."""

    try:
        array = np.asarray(frame, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError("Pressure matrix must contain only numeric values.") from exc
    if array.shape != matrix_shape:
        raise ValueError(
            f"Pressure matrix shape must be {matrix_shape}, received {array.shape}."
        )
    if not np.isfinite(array).all():
        raise ValueError("Pressure matrix contains NaN or infinite values.")
    return array


def prepare_pressure_frame(
    frame: np.ndarray | list[list[float]],
    *,
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
    pressure_percentile: float = 99.0,
) -> PreparedPressureFrame:
    """Validate, clip negative sensor offsets and normalize a pressure frame.

    Normalization uses a percentile of positive readings so algorithms are
    less sensitive to participant weight and isolated sensor peaks.
    """

    if not 0.0 < pressure_percentile <= 100.0:
        raise ValueError("pressure_percentile must be in the interval (0, 100].")

    pressure = np.maximum(validate_pressure_frame(frame, matrix_shape), 0.0)
    positive = pressure[pressure > 0]
    if positive.size:
        scale = float(np.percentile(positive, pressure_percentile))
    else:
        scale = 1.0
    if not np.isfinite(scale) or scale <= np.finfo(np.float32).eps:
        scale = 1.0
    normalized = np.clip(pressure / scale, 0.0, 1.0)
    return PreparedPressureFrame(
        pressure=pressure,
        normalized=normalized,
        normalization_scale=scale,
    )
