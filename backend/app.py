"""Minimal Flask integration for posture SVM inference."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS
import numpy as np

from backend import config
from backend.algorithms.body_partition.api import create_blueprint
from backend.algorithms.posture_svm.inference import PostureSVMClassifier
from backend.data_utils.contracts import CONTRACT


class LazyPostureClassifier:
    """Load the trained model once, on the first inference request."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._classifier: PostureSVMClassifier | None = None
        self._lock = Lock()

    @property
    def is_available(self) -> bool:
        return self.model_path.is_file()

    def get(self) -> PostureSVMClassifier:
        if self._classifier is None:
            with self._lock:
                if self._classifier is None:
                    self._classifier = PostureSVMClassifier(self.model_path)
        return self._classifier


def _extract_pressure_matrix(payload: Any) -> np.ndarray:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    raw_matrix = payload.get("pressure_matrix", payload.get("data"))
    if raw_matrix is None:
        raise ValueError("JSON field `pressure_matrix` is required.")
    try:
        matrix = np.asarray(raw_matrix, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError("`pressure_matrix` must contain only numeric values.") from exc
    if matrix.shape != config.PRESSURE_MATRIX_SHAPE:
        raise ValueError(
            f"`pressure_matrix` must have shape {config.PRESSURE_MATRIX_SHAPE}; "
            f"received {matrix.shape}."
        )
    if not np.isfinite(matrix).all():
        raise ValueError("`pressure_matrix` cannot contain NaN or infinite values.")
    return matrix


def create_app(model_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)
    classifier = LazyPostureClassifier(model_path or config.POSTURE_SVM_MODEL_PATH)
    app.extensions["posture_svm_classifier"] = classifier
    app.register_blueprint(create_blueprint())

    @app.get("/api/health")
    def health() -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "status": "ok",
                    "posture_svm": {
                        "model_available": classifier.is_available,
                        "model_path": str(classifier.model_path),
                    },
                }
            ),
            200,
        )

    @app.get("/api/contracts/posture")
    def posture_contract() -> tuple[Any, int]:
        """Expose the validated language-neutral contract to the frontend."""

        return jsonify(CONTRACT), 200

    @app.post("/api/posture/predict")
    def predict_posture() -> tuple[Any, int]:
        try:
            matrix = _extract_pressure_matrix(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400
        try:
            model = classifier.get()
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return jsonify({"error": "model_unavailable", "message": str(exc)}), 503
        try:
            prediction = model.predict(matrix)
        except ValueError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400
        return jsonify(prediction.to_dict()), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
