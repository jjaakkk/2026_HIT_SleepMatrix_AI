"""Shared training-only augmentation for pressure matrices."""

from __future__ import annotations

import numpy as np

from .contracts import MIRRORED_ACTION, MIRRORED_LABEL


def _translate_with_zeros(frame: np.ndarray, row_shift: int, column_shift: int) -> np.ndarray:
    translated = np.zeros_like(frame)
    rows, columns = frame.shape

    source_row_start = max(0, -row_shift)
    source_row_end = min(rows, rows - row_shift)
    target_row_start = max(0, row_shift)
    target_row_end = min(rows, rows + row_shift)

    source_column_start = max(0, -column_shift)
    source_column_end = min(columns, columns - column_shift)
    target_column_start = max(0, column_shift)
    target_column_end = min(columns, columns + column_shift)

    translated[target_row_start:target_row_end, target_column_start:target_column_end] = frame[
        source_row_start:source_row_end, source_column_start:source_column_end
    ]
    return translated


def augment_training_frames(
    frames: np.ndarray,
    labels: np.ndarray,
    subjects: np.ndarray,
    actions: np.ndarray,
    *,
    jitter_copies: int = 1,
    noise_ratio: float = 0.01,
    max_shift: int = 1,
    include_horizontal_mirror: bool = False,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Augment a training partition while retaining participant groups.

    Mirroring is disabled by default because the documented final dataset
    already includes flips. If enabled explicitly, lateral labels and action
    IDs are swapped according to the shared contract.
    """

    source_frames = np.asarray(frames, dtype=np.float32)
    source_labels = np.asarray(labels, dtype=np.int64)
    source_subjects = np.asarray(subjects)
    source_actions = np.asarray(actions, dtype=np.int64)

    size = source_frames.shape[0]
    if source_frames.ndim != 3:
        raise ValueError("frames must have shape (n, rows, columns).")
    if any(len(array) != size for array in (source_labels, source_subjects, source_actions)):
        raise ValueError("frames, labels, subjects and actions must have equal lengths.")
    if jitter_copies < 0 or max_shift < 0 or noise_ratio < 0:
        raise ValueError("Augmentation parameters cannot be negative.")

    frame_batches = [source_frames]
    label_batches = [source_labels]
    subject_batches = [source_subjects]
    action_batches = [source_actions]
    rng = np.random.default_rng(random_state)

    for _ in range(jitter_copies):
        augmented = np.empty_like(source_frames)
        for index, frame in enumerate(source_frames):
            row_shift = int(rng.integers(-max_shift, max_shift + 1)) if max_shift else 0
            column_shift = int(rng.integers(-max_shift, max_shift + 1)) if max_shift else 0
            shifted = _translate_with_zeros(frame, row_shift, column_shift)
            positive = shifted[shifted > 0]
            scale = float(np.percentile(positive, 99)) if positive.size else 0.0
            noise = rng.normal(0.0, noise_ratio * scale, shifted.shape)
            augmented[index] = np.maximum(shifted + noise, 0.0)
        frame_batches.append(augmented)
        label_batches.append(source_labels.copy())
        subject_batches.append(source_subjects.copy())
        action_batches.append(source_actions.copy())

    if include_horizontal_mirror:
        frame_batches.append(np.flip(source_frames, axis=2).copy())
        label_batches.append(
            np.asarray([MIRRORED_LABEL[int(label)] for label in source_labels], dtype=np.int64)
        )
        subject_batches.append(source_subjects.copy())
        action_batches.append(
            np.asarray([MIRRORED_ACTION[int(action)] for action in source_actions], dtype=np.int64)
        )

    return (
        np.concatenate(frame_batches),
        np.concatenate(label_batches),
        np.concatenate(subject_batches),
        np.concatenate(action_batches),
    )
