"""Reusable, interpretable features derived from pressure matrices."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


def _finite_2d_array(values: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional matrix.")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or infinite values.")
    return array


def block_mean(
    normalized: np.ndarray,
    block_shape: tuple[int, int],
) -> np.ndarray:
    """Reduce a normalized matrix by averaging non-overlapping blocks."""

    matrix = _finite_2d_array(normalized, "normalized pressure matrix")
    block_rows, block_columns = block_shape
    if block_rows <= 0 or block_columns <= 0:
        raise ValueError("block_shape values must be positive.")
    rows, columns = matrix.shape
    if rows % block_rows or columns % block_columns:
        raise ValueError(
            f"Matrix shape {matrix.shape} is not divisible by block shape {block_shape}."
        )
    return matrix.reshape(
        rows // block_rows,
        block_rows,
        columns // block_columns,
        block_columns,
    ).mean(axis=(1, 3))


def normalized_projections(normalized: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return row and column pressure proportions whose total is one."""

    matrix = _finite_2d_array(normalized, "normalized pressure matrix")
    projection_scale = max(float(matrix.sum()), np.finfo(np.float32).eps)
    return matrix.sum(axis=1) / projection_scale, matrix.sum(axis=0) / projection_scale


def occupancy_projections(
    normalized: np.ndarray,
    threshold_ratio: float = 0.05,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the contact mask and row/column contact proportions."""

    if not 0.0 <= threshold_ratio <= 1.0:
        raise ValueError("threshold_ratio must be between 0 and 1.")
    matrix = _finite_2d_array(normalized, "normalized pressure matrix")
    occupied = matrix >= threshold_ratio
    return occupied, occupied.mean(axis=1), occupied.mean(axis=0)


@dataclass(frozen=True)
class PressureStatistics:
    """Named global pressure and contact-shape statistics."""

    log_total_pressure: float
    log_max_pressure: float
    log_positive_mean_pressure: float
    contact_ratio: float
    centroid_x: float
    centroid_y: float
    spread_x: float
    spread_y: float
    mirror_difference: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    def to_array(self) -> np.ndarray:
        """Return values in the stable order used by model feature vectors."""

        return np.asarray(
            [
                self.log_total_pressure,
                self.log_max_pressure,
                self.log_positive_mean_pressure,
                self.contact_ratio,
                self.centroid_x,
                self.centroid_y,
                self.spread_x,
                self.spread_y,
                self.mirror_difference,
            ],
            dtype=np.float32,
        )


def calculate_pressure_statistics(
    pressure: np.ndarray,
    normalized: np.ndarray,
    occupied: np.ndarray | None = None,
    contact_threshold_ratio: float = 0.05,
) -> PressureStatistics:
    """Calculate global intensity, contact, centroid and symmetry statistics."""

    pressure_matrix = _finite_2d_array(pressure, "pressure matrix")
    normalized_matrix = _finite_2d_array(normalized, "normalized pressure matrix")
    if pressure_matrix.shape != normalized_matrix.shape:
        raise ValueError("pressure and normalized matrices must have the same shape.")

    if occupied is None:
        occupied_matrix, _, _ = occupancy_projections(
            normalized_matrix,
            threshold_ratio=contact_threshold_ratio,
        )
    else:
        occupied_matrix = np.asarray(occupied, dtype=bool)
        if occupied_matrix.shape != pressure_matrix.shape:
            raise ValueError("occupied mask must have the same shape as pressure.")

    positive = pressure_matrix[pressure_matrix > 0]
    total_normalized = float(normalized_matrix.sum())
    rows, columns = pressure_matrix.shape
    y_grid, x_grid = np.indices(pressure_matrix.shape, dtype=np.float32)
    if total_normalized > 0:
        centroid_x = float(
            (normalized_matrix * x_grid).sum() / total_normalized
        ) / max(columns - 1, 1)
        centroid_y = float(
            (normalized_matrix * y_grid).sum() / total_normalized
        ) / max(rows - 1, 1)
        spread_x = float(
            np.sqrt(
                (
                    normalized_matrix
                    * (x_grid - centroid_x * (columns - 1)) ** 2
                ).sum()
                / total_normalized
            )
        ) / max(columns - 1, 1)
        spread_y = float(
            np.sqrt(
                (
                    normalized_matrix
                    * (y_grid - centroid_y * (rows - 1)) ** 2
                ).sum()
                / total_normalized
            )
        ) / max(rows - 1, 1)
    else:
        centroid_x = centroid_y = spread_x = spread_y = 0.0

    return PressureStatistics(
        log_total_pressure=float(np.log1p(float(pressure_matrix.sum()))),
        log_max_pressure=float(np.log1p(float(pressure_matrix.max(initial=0.0)))),
        log_positive_mean_pressure=(
            float(np.log1p(float(positive.mean()))) if positive.size else 0.0
        ),
        contact_ratio=float(occupied_matrix.mean()),
        centroid_x=centroid_x,
        centroid_y=centroid_y,
        spread_x=spread_x,
        spread_y=spread_y,
        mirror_difference=float(
            np.mean(np.abs(normalized_matrix - np.fliplr(normalized_matrix)))
        ),
    )
