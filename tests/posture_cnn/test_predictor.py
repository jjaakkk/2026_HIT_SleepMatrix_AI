"""Unit tests for the HTTP-facing posture CNN predictor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from backend.algorithms.posture_cnn.model import build_model
from backend.algorithms.posture_cnn.predictor import PostureCNNClassifier
from backend.data_utils.contracts import LABEL_ID_TO_NAME, MATRIX_SHAPE


def _save_checkpoint(
    path: Path,
    class_names: list[str] | None = None,
    normalization: dict[str, float] | None = None,
) -> Path:
    names = list(class_names) if class_names is not None else [
        "仰卧", "俯卧", "左侧卧", "右侧卧",
    ]
    torch.save(
        {
            "model_state": build_model(num_classes=len(names)).state_dict(),
            "class_names": names,
            "normalization": normalization or {"mean": 0.0, "std": 1.0},
            "dropout": 0.3,
        },
        path,
    )
    return path


class PostureCNNClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.checkpoint = _save_checkpoint(Path(self.tmpdir.name) / "best_model.pt")

    def test_missing_checkpoint_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            PostureCNNClassifier(Path(self.tmpdir.name) / "missing.pt", device="cpu")

    def test_predict_returns_contract_prediction(self) -> None:
        classifier = PostureCNNClassifier(self.checkpoint, device="cpu")
        prediction = classifier.predict(np.zeros(MATRIX_SHAPE, dtype=np.float32))
        self.assertIn(prediction.label_id, range(4))
        self.assertEqual(prediction.label, LABEL_ID_TO_NAME[prediction.label_id])
        self.assertEqual(
            set(prediction.probabilities), set(LABEL_ID_TO_NAME.values())
        )
        self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0, places=5)
        self.assertAlmostEqual(
            prediction.confidence,
            max(prediction.probabilities.values()),
            places=6,
        )

    def test_to_dict_is_json_ready(self) -> None:
        classifier = PostureCNNClassifier(self.checkpoint, device="cpu")
        payload = classifier.predict(
            np.zeros(MATRIX_SHAPE, dtype=np.float32)
        ).to_dict()
        self.assertEqual(set(payload), {"label_id", "label", "label_zh", "confidence", "probabilities"})
        self.assertIsInstance(payload["label_id"], int)
        self.assertIsInstance(payload["confidence"], float)

    def test_unknown_class_name_raises(self) -> None:
        path = _save_checkpoint(
            Path(self.tmpdir.name) / "bad.pt",
            class_names=["仰卧", "俯卧", "左侧卧", "不明"],
        )
        with self.assertRaises(ValueError):
            PostureCNNClassifier(path, device="cpu")

    def test_english_class_names_are_accepted(self) -> None:
        path = _save_checkpoint(
            Path(self.tmpdir.name) / "en.pt",
            class_names=["supine", "prone", "left_lateral", "right_lateral"],
        )
        classifier = PostureCNNClassifier(path, device="cpu")
        prediction = classifier.predict(np.zeros(MATRIX_SHAPE, dtype=np.float32))
        self.assertIn(prediction.label_id, range(4))

    def test_missing_normalization_raises(self) -> None:
        path = Path(self.tmpdir.name) / "nonorm.pt"
        torch.save(
            {
                "model_state": build_model(num_classes=4).state_dict(),
                "class_names": ["仰卧", "俯卧", "左侧卧", "右侧卧"],
                "dropout": 0.3,
            },
            path,
        )
        with self.assertRaises(ValueError):
            PostureCNNClassifier(path, device="cpu")


if __name__ == "__main__":
    unittest.main()
