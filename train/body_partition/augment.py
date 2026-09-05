"""Augmentation for body-partition training frames *and* their masks.

Horizontal flipping is deliberately **not** used: the documented final dataset
already contains left-right mirrored frames, so mirroring again would only
duplicate samples. Instead each synthetic copy combines

- a small joint translation of frame and mask (zero/background fill),
- per-frame Gaussian sensor noise relative to the pressure scale,
- a global gain and a small baseline offset (pillow/bedding variation),
- sparse dead pixels, simulating occasional sensor dropouts.
"""

from __future__ import annotations

import numpy as np


def _shift_joint(
    frame: np.ndarray,
    mask: np.ndarray,
    row_shift: int,
    column_shift: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Translate frame and mask by the same offset, filling with zeros."""

    shifted_frame = np.zeros_like(frame)
    shifted_mask = np.zeros_like(mask)
    rows, columns = frame.shape

    src_row = slice(max(0, -row_shift), min(rows, rows - row_shift))
    dst_row = slice(max(0, row_shift), min(rows, rows + row_shift))
    src_col = slice(max(0, -column_shift), min(columns, columns - column_shift))
    dst_col = slice(max(0, column_shift), min(columns, columns + column_shift))

    shifted_frame[dst_row, dst_col] = frame[src_row, src_col]
    shifted_mask[dst_row, dst_col] = mask[src_row, src_col]
    return shifted_frame, shifted_mask


def augment_frames_and_masks(
    frames: np.ndarray,
    masks: np.ndarray,
    *,
    copies: int = 2,
    max_row_shift: int = 2,
    max_column_shift: int = 1,
    noise_ratio: float = 0.03,
    gain_range: tuple[float, float] = (0.90, 1.10),
    baseline_ratio: float = 0.02,
    dead_pixel_ratio: float = 0.0005,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(1 + copies) x n`` augmented frames and masks.

    The original samples are always kept as the first block; every synthetic
    block applies an independent random transform. Augmented data is generated
    only for training partitions, never for validation or test data.
    """

    source_frames = np.asarray(frames, dtype=np.float32)
    source_masks = np.asarray(masks, dtype=np.uint8)
    if source_frames.ndim != 3 or source_masks.ndim != 3:
        raise ValueError("frames and masks must have shape (n, rows, columns).")
    if source_frames.shape != source_masks.shape:
        raise ValueError("frames and masks must share the same shape.")
    if copies < 0:
        raise ValueError("copies cannot be negative.")

    rng = np.random.default_rng(random_state)
    frame_blocks = [source_frames]
    mask_blocks = [source_masks]

    for _ in range(copies):
        new_frames = np.empty_like(source_frames)
        new_masks = np.empty_like(source_masks)
        for index, (frame, mask) in enumerate(zip(source_frames, source_masks)):
            row_shift = int(rng.integers(-max_row_shift, max_row_shift + 1)) if max_row_shift else 0
            column_shift = (
                int(rng.integers(-max_column_shift, max_column_shift + 1)) if max_column_shift else 0
            )
            shifted_frame, shifted_mask = _shift_joint(frame, mask, row_shift, column_shift)

            positive = shifted_frame[shifted_frame > 0]
            scale = float(np.percentile(positive, 99)) if positive.size else 0.0
            gain = float(rng.uniform(*gain_range))
            baseline = float(rng.uniform(-baseline_ratio, baseline_ratio)) * scale
            noise = rng.normal(0.0, noise_ratio * scale, shifted_frame.shape)
            augmented = shifted_frame * gain + baseline + noise

            if dead_pixel_ratio > 0:
                dead = rng.random(shifted_frame.shape) < dead_pixel_ratio
                augmented = np.where(dead, 0.0, augmented)

            new_frames[index] = np.maximum(augmented, 0.0)
            new_masks[index] = shifted_mask
        frame_blocks.append(new_frames)
        mask_blocks.append(new_masks)

    return np.concatenate(frame_blocks), np.concatenate(mask_blocks)
