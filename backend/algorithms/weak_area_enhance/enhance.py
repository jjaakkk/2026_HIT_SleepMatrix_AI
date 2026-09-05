"""Enhance weak but meaningful pressure regions in a mattress sensor frame.

The public function keeps the matrix size unchanged.  The output is intended
for heat-map display or as an optional downstream preprocessing result; its
values are not calibrated physical pressure and must not be used for weight
estimation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _window_filter(data: np.ndarray, size: int, mode: str) -> np.ndarray:
    """Small dependency-free min/max filter used by morphology."""

    radius = size // 2
    padded = np.pad(data, radius, mode="edge")
    is_integer = np.issubdtype(data.dtype, np.integer)
    if mode == "max":
        fill_value = np.iinfo(data.dtype).min if is_integer else -np.inf
        result = np.full_like(data, fill_value)
        operation = np.maximum
    elif mode == "min":
        fill_value = np.iinfo(data.dtype).max if is_integer else np.inf
        result = np.full_like(data, fill_value)
        operation = np.minimum
    else:
        raise ValueError(f"unsupported filter mode: {mode}")
    for row_offset in range(size):
        for col_offset in range(size):
            window = padded[
                row_offset : row_offset + data.shape[0],
                col_offset : col_offset + data.shape[1],
            ]
            operation(result, window, out=result)
    return result


def _binary_dilation(mask: np.ndarray, iterations: int) -> np.ndarray:
    result = mask.astype(bool, copy=True)
    for _ in range(iterations):
        result = _window_filter(result.astype(np.uint8), 3, "max").astype(bool)
    return result


def _binary_closing(mask: np.ndarray, size: int) -> np.ndarray:
    dilated = _window_filter(mask.astype(np.uint8), size, "max")
    return _window_filter(dilated, size, "min").astype(bool)


def _grey_closing(data: np.ndarray, size: int) -> np.ndarray:
    return _window_filter(_window_filter(data, size, "max"), size, "min")


def _gaussian_filter(data: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.0:
        return data.copy()
    radius = max(1, int(np.ceil(3.0 * sigma)))
    coordinates = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel_1d = np.exp(-(coordinates**2) / (2.0 * sigma**2))
    kernel_1d /= kernel_1d.sum()
    kernel = np.outer(kernel_1d, kernel_1d)
    padded = np.pad(data, radius, mode="edge")
    result = np.zeros_like(data)
    for row_offset in range(kernel.shape[0]):
        for col_offset in range(kernel.shape[1]):
            result += kernel[row_offset, col_offset] * padded[
                row_offset : row_offset + data.shape[0],
                col_offset : col_offset + data.shape[1],
            ]
    return result


def _mean_filter(data: np.ndarray, size: int) -> np.ndarray:
    """Return a small square-window mean without an extra dependency."""

    radius = size // 2
    padded = np.pad(data, radius, mode="edge")
    result = np.zeros_like(data, dtype=np.float64)
    for row_offset in range(size):
        for col_offset in range(size):
            result += padded[
                row_offset : row_offset + data.shape[0],
                col_offset : col_offset + data.shape[1],
            ]
    return result / float(size * size)


def _seed_proximity(seed: np.ndarray, radius: int) -> np.ndarray:
    """Estimate closeness to reliable pressure while staying dependency-free."""

    proximity = seed.astype(np.float64)
    expanded = seed.astype(bool, copy=True)
    for distance in range(1, radius + 1):
        expanded = _binary_dilation(expanded, iterations=1)
        weight = 1.0 - distance / float(radius + 1)
        proximity = np.maximum(proximity, expanded * weight)
    return proximity


def _retain_seed_connected(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Keep candidate pixels that are 8-connected to a reliable seed."""

    reachable = seed.astype(bool, copy=True)
    allowed = mask.astype(bool, copy=False) | reachable
    while True:
        expanded = _binary_dilation(reachable, iterations=1) & allowed
        updated = reachable | expanded
        if np.array_equal(updated, reachable):
            return reachable
        reachable = updated


@dataclass(frozen=True)
class EnhancementConfig:
    """Parameters for :func:`enhance_pressure`.

    Ratios are relative to a robust high-pressure value from the current
    frame, which makes the defaults usable for people of different weights.
    """

    gamma: float = 0.55
    strength: float = 0.80
    noise_floor_ratio: float = 0.015
    seed_ratio: float = 0.08
    weak_upper_ratio: float = 0.35
    gaussian_sigma: float = 0.55
    context_radius: int = 2
    density_radius: int = 1
    min_local_density: float = 0.22
    closing_size: int = 3
    bridge_strength: float = 0.70
    bridge_floor_ratio: float = 0.025
    visible_floor_ratio: float = 0.04
    scale_percentile: float = 99.5

    def validate(self) -> None:
        if not 0.0 < self.gamma < 1.0:
            raise ValueError("gamma must be between 0 and 1")
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be between 0 and 1")
        if not 0.0 <= self.noise_floor_ratio < self.seed_ratio:
            raise ValueError("noise_floor_ratio must be smaller than seed_ratio")
        if not self.seed_ratio < self.weak_upper_ratio <= 1.0:
            raise ValueError("weak_upper_ratio must be above seed_ratio and at most 1")
        if self.gaussian_sigma < 0.0:
            raise ValueError("gaussian_sigma cannot be negative")
        if self.context_radius < 0:
            raise ValueError("context_radius cannot be negative")
        if self.density_radius < 0:
            raise ValueError("density_radius cannot be negative")
        if not 0.0 <= self.min_local_density <= 1.0:
            raise ValueError("min_local_density must be between 0 and 1")
        if self.closing_size < 1 or self.closing_size % 2 == 0:
            raise ValueError("closing_size must be a positive odd integer")
        if not 0.0 <= self.bridge_strength <= 1.0:
            raise ValueError("bridge_strength must be between 0 and 1")
        if not self.noise_floor_ratio <= self.bridge_floor_ratio <= self.weak_upper_ratio:
            raise ValueError(
                "bridge_floor_ratio must be between noise_floor_ratio and weak_upper_ratio"
            )
        if not self.noise_floor_ratio <= self.visible_floor_ratio <= self.seed_ratio:
            raise ValueError(
                "visible_floor_ratio must be between noise_floor_ratio and seed_ratio"
            )
        if not 50.0 <= self.scale_percentile <= 100.0:
            raise ValueError("scale_percentile must be between 50 and 100")


def _as_pressure_matrix(matrix: np.ndarray) -> np.ndarray:
    data = np.asarray(matrix, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError("pressure matrix must be two-dimensional")
    if data.size == 0:
        raise ValueError("pressure matrix cannot be empty")
    if not np.isfinite(data).all():
        raise ValueError("pressure matrix contains NaN or infinite values")
    # Negative readings are sensor artefacts and have no physical meaning.
    return np.maximum(data, 0.0)


def enhance_pressure(
    matrix: np.ndarray,
    config: EnhancementConfig | None = None,
) -> np.ndarray:
    """Return an enhanced pressure matrix with the same shape as ``matrix``.

    The method combines adaptive normalization, context-aware noise removal,
    gamma enhancement and a small morphological closing operation.  Weak
    values are only retained near a reliable body-pressure seed, which avoids
    amplifying isolated background sensor noise.
    """

    cfg = config or EnhancementConfig()
    cfg.validate()
    pressure = _as_pressure_matrix(matrix)

    positive = pressure[pressure > 0.0]
    if positive.size == 0:
        return np.zeros_like(pressure, dtype=np.float32)

    scale = float(np.percentile(positive, cfg.scale_percentile))
    if scale <= np.finfo(np.float64).eps:
        return np.zeros_like(pressure, dtype=np.float32)

    normalized = np.clip(pressure / scale, 0.0, 1.0)
    smoothed = _gaussian_filter(normalized, cfg.gaussian_sigma)
    measured = normalized >= cfg.noise_floor_ratio
    density_size = 2 * cfg.density_radius + 1
    local_density = _mean_filter(measured.astype(np.float64), density_size)

    # A reliable seed must be both strong enough and supported by neighbouring
    # measured sensors.  This rejects isolated spikes before any enhancement.
    seed = (normalized >= cfg.seed_ratio) & (
        local_density >= cfg.min_local_density
    )
    if not seed.any():
        # Do no harm when a frame contains no reliable body region.  Keeping
        # the measured values is safer than erasing a very light occupant.
        return pressure.astype(np.float32)

    vicinity = _binary_dilation(seed, iterations=cfg.context_radius)
    supported = measured & vicinity & (
        (local_density >= cfg.min_local_density) | seed
    )
    supported = _retain_seed_connected(supported, seed)

    # Enhance only genuinely measured weak values.  The previous implementation
    # applied smoothed values throughout the whole vicinity, which could create
    # a wide halo around the body outline.
    enhanced = normalized.copy()
    weak_target = supported & (normalized <= cfg.weak_upper_ratio)
    gamma_curve = np.power(normalized, cfg.gamma)
    weak_weight = np.clip(
        (cfg.weak_upper_ratio - normalized)
        / (cfg.weak_upper_ratio - cfg.noise_floor_ratio),
        0.0,
        1.0,
    )
    density_confidence = np.clip(
        (local_density - cfg.min_local_density)
        / max(1.0 - cfg.min_local_density, np.finfo(np.float64).eps),
        0.0,
        1.0,
    )
    proximity = _seed_proximity(seed, cfg.context_radius)
    confidence = (0.35 + 0.65 * density_confidence) * (0.5 + 0.5 * proximity)
    enhanced[weak_target] = normalized[weak_target] + (
        cfg.strength
        * confidence[weak_target]
        * weak_weight[weak_target]
        * (gamma_curve[weak_target] - normalized[weak_target])
    )

    # Fill only small holes/gaps inside the supported body mask.  Gaussian and
    # grey closing values are never spread across the full body vicinity.
    base_support = seed | supported
    closed_support = _binary_closing(base_support, cfg.closing_size) & vicinity
    bridge = closed_support & ~base_support
    closed_values = _grey_closing(
        np.where(base_support, normalized, 0.0), cfg.closing_size
    )
    bridge_values = np.maximum(smoothed * cfg.bridge_strength, closed_values)
    bridge_values = np.minimum(bridge_values, cfg.weak_upper_ratio)
    bridge &= bridge_values >= cfg.bridge_floor_ratio
    enhanced[bridge] = np.maximum(enhanced[bridge], bridge_values[bridge])

    # Do not turn a dim, detached cluster into a new visible island.  Newly
    # visible pixels must connect to pressure that was already visible in the
    # original frame.  This retains useful bridges while suppressing artefacts.
    original_visible = normalized >= cfg.visible_floor_ratio
    enhanced_visible = enhanced >= cfg.visible_floor_ratio
    visible_connected = _retain_seed_connected(enhanced_visible, original_visible)
    detached_new_visible = enhanced_visible & ~original_visible & ~visible_connected
    enhanced[detached_new_visible] = normalized[detached_new_visible]

    # Do not reduce reliable measured pressure, and keep the original scale.
    enhanced = np.maximum(enhanced, normalized)
    enhanced = np.clip(enhanced, 0.0, 1.0)
    return (enhanced * scale).astype(np.float32)
