"""Reusable inference wrapper for the trained posture CNN.

Loads one immutable checkpoint produced by ``backend.algorithms.posture_cnn.train``
and returns the same :class:`~backend.data_utils.predictions.PosturePrediction`
payload as the SVM classifier, so the HTTP layer can treat both models
identically.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from backend.data_utils.contracts import (
    LABEL_ID_TO_NAME,
    LABEL_ID_TO_NAME_ZH,
    MATRIX_SHAPE,
)
from backend.data_utils.predictions import PosturePrediction
from backend.data_utils.pressure_processing import validate_pressure_frame

from .dataset import preprocess_single_frame
from .model import build_model
from .utils import choose_device, load_checkpoint


DEFAULT_CHECKPOINT = (
    Path(__file__).resolve().parents[3] / "outputs" / "posture_cnn" / "best_model.pt"
)


def _map_class_names_to_label_ids(class_names: list[str]) -> list[int]:
    """Map checkpoint class names to posture-contract label IDs.

    The training pipeline stores Chinese class names (``仰卧`` ... ``右侧卧``);
    English contract keys are accepted as well for future checkpoints.
    """

    if not class_names:
        raise ValueError("Posture CNN checkpoint has no `class_names`.")
    label_ids: list[int] = []
    for name in class_names:
        matches = [label_id for label_id, zh in LABEL_ID_TO_NAME_ZH.items() if zh == name]
        if not matches:
            matches = [label_id for label_id, key in LABEL_ID_TO_NAME.items() if key == name]
        if len(matches) != 1:
            raise ValueError(
                f"Cannot map CNN class name {name!r} to a posture-contract label."
            )
        label_ids.append(matches[0])
    if len(set(label_ids)) != len(label_ids):
        raise ValueError("Posture CNN class names map to duplicate posture labels.")
    return label_ids


class PostureCNNClassifier:
    """Load one immutable CNN checkpoint and classify pressure frames."""

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
        device: str = "auto",
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        self.device = choose_device(device)
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(
                f"Posture CNN checkpoint was not found at {self.checkpoint_path}. "
                "Train it with `python -m backend.algorithms.posture_cnn.train`."
            )
        try:
            checkpoint = load_checkpoint(self.checkpoint_path, self.device)
        except Exception as exc:
            raise ValueError(
                f"Posture CNN checkpoint at {self.checkpoint_path} could not be loaded."
            ) from exc
        if not isinstance(checkpoint, dict):
            raise ValueError("Invalid posture CNN checkpoint: expected a dictionary.")

        self.class_names = [str(name) for name in checkpoint.get("class_names", [])]
        self.label_ids = _map_class_names_to_label_ids(self.class_names)
        self.normalization = checkpoint.get("normalization")
        if (
            not isinstance(self.normalization, dict)
            or "mean" not in self.normalization
            or "std" not in self.normalization
        ):
            raise ValueError(
                "Posture CNN checkpoint is missing its `normalization` statistics."
            )
        if float(self.normalization.get("std", 0.0)) <= 0:
            raise ValueError("Posture CNN checkpoint normalization `std` must be positive.")

        try:
            self.model = build_model(
                num_classes=len(self.class_names),
                dropout=float(checkpoint.get("dropout", 0.3)),
            )
            self.model.load_state_dict(checkpoint["model_state"])
        except (KeyError, RuntimeError) as exc:
            raise ValueError("Posture CNN checkpoint state is invalid.") from exc
        self.model.to(self.device)
        self.model.eval()

    def predict(self, pressure_matrix: np.ndarray | list[list[float]]) -> PosturePrediction:
        """Classify one 44x24 frame."""

        frame = validate_pressure_frame(pressure_matrix, MATRIX_SHAPE)
        inputs = preprocess_single_frame(frame, self.normalization).to(self.device)
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(inputs), dim=1)[0].cpu().tolist()
        probability_by_label = {
            LABEL_ID_TO_NAME[label_id]: float(probabilities[index])
            for index, label_id in enumerate(self.label_ids)
        }
        predicted_index = int(np.argmax(probabilities))
        label_id = self.label_ids[predicted_index]
        return PosturePrediction(
            label_id=label_id,
            label=LABEL_ID_TO_NAME[label_id],
            label_zh=LABEL_ID_TO_NAME_ZH[label_id],
            confidence=float(probabilities[predicted_index]),
            probabilities=probability_by_label,
        )
