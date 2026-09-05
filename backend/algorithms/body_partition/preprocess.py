"""Input normalization shared by training and inference.

Raw sensor counts vary with participant weight and bedding (the dataset manual
notes pillow/baseline differences between sessions), so each frame is scaled
by its own 99th percentile of positive values. This keeps the network focused
on the pressure *distribution* instead of absolute counts, which is what makes
the model transfer to previously unseen participants.
"""

from __future__ import annotations

import numpy as np

NORMALIZATION_PERCENTILE = 99.0
EPSILON = 1e-6


def normalize_frames(frames: np.ndarray, percentile: float = NORMALIZATION_PERCENTILE) -> np.ndarray:
    """Scale each frame to [0, 1] by its percentile of positive values.

    Accepts a single ``(44, 24)`` frame or a batch ``(n, 44, 24)`` and returns
    float32 values in the same shape.
    """

    array = np.asarray(frames, dtype=np.float32)
    single = array.ndim == 2
    if single:
        array = array[None, ...]
    if array.ndim != 3:
        raise ValueError(f"frames must have shape (n, rows, columns); received {array.shape}.")

    scales = np.ones(array.shape[0], dtype=np.float32)
    for index, frame in enumerate(array):
        positive = frame[frame > 0]
        if positive.size:
            scales[index] = max(float(np.percentile(positive, percentile)), EPSILON)
    normalized = np.clip(array / scales[:, None, None], 0.0, 1.0).astype(np.float32)
    return normalized[0] if single else normalized
