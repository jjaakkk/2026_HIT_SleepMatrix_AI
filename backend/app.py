"""Flask integration for posture SVM and body-partition inference."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import numpy as np

from backend import config
from backend.algorithms.body_partition.demo_data import AnnotatedSampleStore
from backend.algorithms.body_partition.inference import BodyPartitionPredictor
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


class LazyPartitionPredictor:
    """Load the trained body-partition network once, on first request."""

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._predictor: BodyPartitionPredictor | None = None
        self._lock = Lock()

    @property
    def is_available(self) -> bool:
        return self.model_path.is_file()

    def get(self) -> BodyPartitionPredictor:
        if self._predictor is None:
            with self._lock:
                if self._predictor is None:
                    self._predictor = BodyPartitionPredictor(self.model_path)
        return self._predictor


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
    partition = LazyPartitionPredictor(config.BODY_PARTITION_MODEL_PATH)
    samples = AnnotatedSampleStore(config.BODY_PARTITION_DATASET_PATH)
    app.extensions["posture_svm_classifier"] = classifier
    app.extensions["body_partition_predictor"] = partition
    app.extensions["body_partition_samples"] = samples

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
                    "body_partition": {
                        "model_available": partition.is_available,
                        "model_path": str(partition.model_path),
                        "dataset_available": samples.is_available,
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

    # ------------------------------------------------------------------
    # Body-part region partitioning (member C)
    # ------------------------------------------------------------------

    @app.post("/api/body-partition/predict")
    def predict_body_partition() -> tuple[Any, int]:
        try:
            matrix = _extract_pressure_matrix(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400
        try:
            predictor = partition.get()
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return jsonify({"error": "model_unavailable", "message": str(exc)}), 503
        prediction = predictor.predict(matrix)
        return jsonify(prediction.to_dict()), 200

    @app.get("/api/body-partition/metrics")
    def body_partition_metrics() -> tuple[Any, int]:
        metrics_path = Path(config.BODY_PARTITION_METRICS_PATH)
        if not metrics_path.is_file():
            return (
                jsonify(
                    {
                        "error": "metrics_unavailable",
                        "message": f"Training metrics were not found at {metrics_path}.",
                    }
                ),
                404,
            )
        try:
            document = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return jsonify({"error": "metrics_invalid", "message": str(exc)}), 500
        subject_eval_path = Path(config.BODY_PARTITION_SUBJECT_EVAL_PATH)
        if subject_eval_path.is_file():
            try:
                subject_eval = json.loads(subject_eval_path.read_text(encoding="utf-8"))
                document["subject_eval"] = subject_eval.get("summary") or {
                    "pixel_accuracy": subject_eval.get("metrics", {}).get("pixel_accuracy"),
                    "mean_iou": subject_eval.get("metrics", {}).get("mean_iou"),
                    "test_subjects": subject_eval.get("training", {}).get("test_subjects"),
                }
            except json.JSONDecodeError:
                pass
        return jsonify(document), 200

    @app.get("/api/body-partition/catalog")
    def body_partition_catalog() -> tuple[Any, int]:
        try:
            return jsonify(samples.catalog()), 200
        except FileNotFoundError as exc:
            return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503

    @app.get("/api/body-partition/sample")
    def body_partition_sample() -> tuple[Any, int]:
        subject = request.args.get("subject", type=str)
        action = request.args.get("action", type=int)
        frame = request.args.get("frame", default=0, type=int)
        if not subject or action is None:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "message": "Query parameters `subject` and `action` are required.",
                    }
                ),
                400,
            )
        try:
            sample = samples.sample(subject, action, frame)
        except FileNotFoundError as exc:
            return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
        except KeyError as exc:
            return jsonify({"error": "not_found", "message": str(exc)}), 404

        if partition.is_available:
            matrix = np.asarray(sample["pressure_matrix"], dtype=np.float32)
            prediction = partition.get().predict(matrix)
            sample["predicted_mask"] = prediction.mask
            sample["predicted_regions"] = prediction.regions
        return jsonify(sample), 200

    # ------------------------------------------------------------------
    # Static demo frontend for the body-partition task
    # ------------------------------------------------------------------

    @app.get("/body-partition/")
    def body_partition_page() -> Any:
        return send_from_directory(config.FRONTEND_DIR / "body-partition", "index.html")

    @app.get("/body-partition/<path:filename>")
    def body_partition_assets(filename: str) -> Any:
        return send_from_directory(config.FRONTEND_DIR / "body-partition", filename)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
