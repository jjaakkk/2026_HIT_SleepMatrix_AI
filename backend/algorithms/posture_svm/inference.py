"""Reusable Python and command-line inference for the trained posture SVM."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Any

# Allow both `python -m backend...inference` and direct script execution.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import joblib
import numpy as np

from backend.algorithms.posture_svm.features import FeatureConfig, extract_feature_matrix
from backend.data_utils.contracts import (
    CONTRACT_VERSION,
    LABEL_ID_TO_NAME,
    LABEL_ID_TO_NAME_ZH,
    MATRIX_SHAPE,
)
from backend.data_utils.data_loader import iter_pressure_frames


DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "posture_svm.joblib"
EXPECTED_ARTIFACT_FORMAT = "sleepmatrix-posture-svm"
SUPPORTED_ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class PosturePrediction:
    label_id: int
    label: str
    label_zh: str
    confidence: float
    probabilities: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PostureSVMClassifier:
    """Load one immutable model artifact and classify pressure frames."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL_PATH) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Posture SVM model was not found at {self.model_path}. "
                "Train it with `python -m backend.algorithms.posture_svm.train_svm`."
            )

        try:
            artifact = joblib.load(self.model_path)
        except Exception as exc:
            raise ValueError(
                f"Posture SVM model at {self.model_path} could not be loaded."
            ) from exc
        if not isinstance(artifact, dict):
            raise ValueError("Invalid posture SVM artifact: expected a dictionary.")
        if artifact.get("format") != EXPECTED_ARTIFACT_FORMAT:
            raise ValueError("Invalid posture SVM artifact format.")
        if artifact.get("version") != SUPPORTED_ARTIFACT_VERSION:
            raise ValueError(
                f"Unsupported posture SVM artifact version: {artifact.get('version')!r}."
            )
        if artifact.get("contract_version") != CONTRACT_VERSION:
            raise ValueError(
                "Posture SVM model uses data contract "
                f"{artifact.get('contract_version')!r}; backend expects {CONTRACT_VERSION!r}."
            )
        if tuple(artifact.get("matrix_shape", ())) != MATRIX_SHAPE:
            raise ValueError(
                f"Model expects matrix shape {artifact.get('matrix_shape')}, not {MATRIX_SHAPE}."
            )

        self.pipeline = artifact["pipeline"]
        self.feature_config = FeatureConfig.from_dict(artifact["feature_config"])
        self.label_id_to_name = {
            int(key): value
            for key, value in artifact.get("label_id_to_name", LABEL_ID_TO_NAME).items()
        }
        self.label_id_to_name_zh = {
            int(key): value
            for key, value in artifact.get("label_id_to_name_zh", LABEL_ID_TO_NAME_ZH).items()
        }
        self.metadata = {key: value for key, value in artifact.items() if key != "pipeline"}

    def predict(self, pressure_matrix: np.ndarray | list[list[float]]) -> PosturePrediction:
        """Classify one 44x24 frame."""

        return self.predict_batch(np.asarray(pressure_matrix)[None, ...])[0]

    def predict_batch(self, pressure_matrices: np.ndarray) -> list[PosturePrediction]:
        """Classify a batch shaped ``(n, 44, 24)``."""

        features = extract_feature_matrix(pressure_matrices, self.feature_config)
        predicted_labels = self.pipeline.predict(features)
        probabilities = self.pipeline.predict_proba(features)
        model_classes = [int(value) for value in self.pipeline.classes_]

        results: list[PosturePrediction] = []
        for predicted, row in zip(predicted_labels, probabilities):
            label_id = int(predicted)
            probability_by_label = {
                self.label_id_to_name[class_id]: float(probability)
                for class_id, probability in zip(model_classes, row)
            }
            predicted_index = model_classes.index(label_id)
            results.append(
                PosturePrediction(
                    label_id=label_id,
                    label=self.label_id_to_name[label_id],
                    label_zh=self.label_id_to_name_zh[label_id],
                    confidence=float(row[predicted_index]),
                    probabilities=probability_by_label,
                )
            )
        return results


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SVM posture inference on frames from one dataset TXT file."
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        required=True,
        help="TXT file containing one or more 44x24 pressure frames.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help=f"Trained model artifact (default: {DEFAULT_MODEL_PATH}).",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--frame-index",
        type=_non_negative_integer,
        default=0,
        help="Zero-based frame index to classify (default: 0).",
    )
    selection.add_argument(
        "--all-frames",
        action="store_true",
        help="Classify every frame in the input file as one batch.",
    )
    return parser


def _prediction_payload(
    classifier: PostureSVMClassifier,
    input_file: Path,
    *,
    frame_index: int,
    all_frames: bool,
) -> dict[str, Any]:
    frames = list(iter_pressure_frames(input_file))
    if all_frames:
        predictions = classifier.predict_batch(np.stack(frames))
        return {
            "input_file": str(input_file),
            "frame_count": len(frames),
            "predictions": [
                {"frame_index": index, **prediction.to_dict()}
                for index, prediction in enumerate(predictions)
            ],
        }

    if frame_index >= len(frames):
        raise ValueError(
            f"Frame index {frame_index} is out of range for {input_file}; "
            f"the file contains {len(frames)} frames."
        )
    return {
        "input_file": str(input_file),
        "frame_index": frame_index,
        **classifier.predict(frames[frame_index]).to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        classifier = PostureSVMClassifier(args.model_path)
        payload = _prediction_payload(
            classifier,
            args.input_file,
            frame_index=args.frame_index,
            all_frames=args.all_frames,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Inference aborted: {exc}") from exc

    # ASCII JSON remains unambiguous in legacy Windows shells; JSON parsers
    # decode label_zh and non-ASCII paths back to their original text.
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
