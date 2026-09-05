"""Reusable inference interface for the trained body-partition network.

Loads one immutable ``.pth`` artifact produced by ``train.body_partition.train_partition``
and turns 44x24 pressure frames into a six-class segmentation mask plus the
five body-region rectangles (shoulder/back/waist/hip/thigh).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from backend.data_utils.contracts import CONTRACT_VERSION, MATRIX_SHAPE

from .model_define import BodyPartitionUNet
from .partition import NUM_CLASSES, REGION_KEYS, REGION_NAMES_ZH, RegionRect, mask_to_rects
from .preprocess import normalize_frames

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "body_partition.pth"
EXPECTED_ARTIFACT_FORMAT = "sleepmatrix-body-partition"
SUPPORTED_ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class PartitionPrediction:
    """Segmentation result for one pressure frame."""

    mask: list[list[int]]
    regions: list[dict[str, Any]]
    foreground_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "mask": self.mask,
            "regions": self.regions,
            "foreground_ratio": self.foreground_ratio,
        }


class BodyPartitionPredictor:
    """Load the trained U-Net once and segment pressure frames."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Body-partition model was not found at {self.model_path}. "
                "Train it with `python -m train.body_partition.train_partition --split random`."
            )
        try:
            artifact = torch.load(self.model_path, map_location="cpu", weights_only=False)
        except Exception as exc:
            raise ValueError(
                f"Body-partition model at {self.model_path} could not be loaded."
            ) from exc
        if not isinstance(artifact, dict):
            raise ValueError("Invalid body-partition artifact: expected a dictionary.")
        if artifact.get("format") != EXPECTED_ARTIFACT_FORMAT:
            raise ValueError("Invalid body-partition artifact format.")
        if artifact.get("version") != SUPPORTED_ARTIFACT_VERSION:
            raise ValueError(
                f"Unsupported body-partition artifact version: {artifact.get('version')!r}."
            )
        if artifact.get("contract_version") != CONTRACT_VERSION:
            raise ValueError(
                "Body-partition model uses data contract "
                f"{artifact.get('contract_version')!r}; backend expects {CONTRACT_VERSION!r}."
            )
        if tuple(artifact.get("matrix_shape", ())) != MATRIX_SHAPE:
            raise ValueError(
                f"Model expects matrix shape {artifact.get('matrix_shape')}, not {MATRIX_SHAPE}."
            )

        config = artifact.get("model_config", {})
        self.model = BodyPartitionUNet(
            in_channels=int(config.get("in_channels", 1)),
            num_classes=int(config.get("num_classes", NUM_CLASSES)),
            base_channels=int(config.get("base_channels", 24)),
        )
        self.model.load_state_dict(artifact["state_dict"])
        self.model.eval()
        self.region_keys = list(artifact.get("region_keys", REGION_KEYS))
        self.region_names_zh = list(artifact.get("region_names_zh", REGION_NAMES_ZH))
        self.metadata = {key: value for key, value in artifact.items() if key != "state_dict"}

    def predict_mask_batch(self, pressure_matrices: np.ndarray) -> np.ndarray:
        """Segment a batch shaped ``(n, 44, 24)`` into uint8 masks."""

        array = np.asarray(pressure_matrices, dtype=np.float32)
        if array.ndim != 3 or array.shape[1:] != MATRIX_SHAPE:
            raise ValueError(
                f"pressure_matrices must have shape (n, {MATRIX_SHAPE[0]}, {MATRIX_SHAPE[1]}); "
                f"received {array.shape}."
            )
        normalized = normalize_frames(array)
        outputs: list[np.ndarray] = []
        with torch.no_grad():
            for start in range(0, normalized.shape[0], 512):
                batch = torch.from_numpy(normalized[start : start + 512])[:, None, :, :]
                logits = self.model(batch)
                outputs.append(logits.argmax(dim=1).numpy().astype(np.uint8))
        return np.concatenate(outputs)

    def predict(self, pressure_matrix: np.ndarray | list[list[float]]) -> PartitionPrediction:
        """Segment one 44x24 frame into body regions."""

        array = np.asarray(pressure_matrix, dtype=np.float32)
        if array.shape != MATRIX_SHAPE:
            raise ValueError(
                f"pressure_matrix must have shape {MATRIX_SHAPE}; received {array.shape}."
            )
        mask = self.predict_mask_batch(array[None, ...])[0]
        regions = self._regions_from_mask(mask)
        return PartitionPrediction(
            mask=mask.astype(int).tolist(),
            regions=regions,
            foreground_ratio=float((mask > 0).mean()),
        )

    @staticmethod
    def _regions_from_mask(mask: np.ndarray) -> list[dict[str, Any]]:
        rects = mask_to_rects(mask)
        return [rect.to_dict() if isinstance(rect, RegionRect) else None for rect in rects]
