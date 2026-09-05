"""Blueprint exposing the body-partition HTTP API and the demo page.

Self-contained by design (own configuration, lazy singletons and routes)
so that wiring it into :mod:`backend.app` is a two-line change: shared
files such as ``app.py`` / ``config.py`` stay conflict-free while other
members work on them in parallel.

Routes:
    POST /api/body-partition/predict
    GET  /api/body-partition/metrics
    GET  /api/body-partition/catalog
    GET  /api/body-partition/sample?subject=&action=&frame=
    GET  /api/body-partition/health
    GET  /body-partition/            (static demo frontend)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Blueprint, jsonify, request, send_from_directory
import numpy as np

from backend.algorithms.body_partition.demo_data import AnnotatedSampleStore
from backend.algorithms.body_partition.inference import BodyPartitionPredictor
from backend.data_utils.contracts import MATRIX_SHAPE

# ----------------------------------------------------------------------
# Module-level configuration (env-overridable), independent of config.py
# ----------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

MODEL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_MODEL",
        _PROJECT_ROOT / "backend" / "models" / "body_partition.pth",
    )
)
DATASET_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_DATASET",
        _PROJECT_ROOT / "dataset" / "raw" / "body_partition_data.json",
    )
)
METRICS_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_METRICS",
        _PROJECT_ROOT / "backend" / "models" / "body_partition.metrics.json",
    )
)
SUBJECT_EVAL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_SUBJECT_EVAL",
        _PROJECT_ROOT / "docs" / "body-partition" / "body_partition_subject_eval.json",
    )
)
FRONTEND_DIR = _PROJECT_ROOT / "frontend" / "body-partition"


class _LazyPredictor:
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
    if matrix.shape != MATRIX_SHAPE:
        raise ValueError(
            f"`pressure_matrix` must have shape {MATRIX_SHAPE}; received {matrix.shape}."
        )
    if not np.isfinite(matrix).all():
        raise ValueError("`pressure_matrix` cannot contain NaN or infinite values.")
    return matrix


def create_blueprint(model_path: str | Path | None = None) -> Blueprint:
    """Build a fresh blueprint; paths default to the module configuration."""
    predictor = _LazyPredictor(model_path or MODEL_PATH)
    samples = AnnotatedSampleStore(DATASET_PATH)
    bp = Blueprint("body_partition", __name__)

    @bp.get("/api/body-partition/health")
    def health() -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "model_available": predictor.is_available,
                    "model_path": str(predictor.model_path),
                    "dataset_available": samples.is_available,
                }
            ),
            200,
        )

    @bp.post("/api/body-partition/predict")
    def predict() -> tuple[Any, int]:
        try:
            matrix = _extract_pressure_matrix(request.get_json(silent=True))
        except ValueError as exc:
            return jsonify({"error": "invalid_request", "message": str(exc)}), 400
        try:
            model = predictor.get()
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return jsonify({"error": "model_unavailable", "message": str(exc)}), 503
        prediction = model.predict(matrix)
        return jsonify(prediction.to_dict()), 200

    @bp.get("/api/body-partition/metrics")
    def metrics() -> tuple[Any, int]:
        if not METRICS_PATH.is_file():
            return (
                jsonify(
                    {
                        "error": "metrics_unavailable",
                        "message": f"Training metrics were not found at {METRICS_PATH}.",
                    }
                ),
                404,
            )
        try:
            document = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return jsonify({"error": "metrics_invalid", "message": str(exc)}), 500
        if SUBJECT_EVAL_PATH.is_file():
            try:
                subject_eval = json.loads(SUBJECT_EVAL_PATH.read_text(encoding="utf-8"))
                document["subject_eval"] = subject_eval.get("summary") or {
                    "pixel_accuracy": subject_eval.get("metrics", {}).get("pixel_accuracy"),
                    "mean_iou": subject_eval.get("metrics", {}).get("mean_iou"),
                    "test_subjects": subject_eval.get("training", {}).get("test_subjects"),
                }
            except json.JSONDecodeError:
                pass
        return jsonify(document), 200

    @bp.get("/api/body-partition/catalog")
    def catalog() -> tuple[Any, int]:
        try:
            return jsonify(samples.catalog()), 200
        except FileNotFoundError as exc:
            return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503

    @bp.get("/api/body-partition/sample")
    def sample() -> tuple[Any, int]:
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
            record = samples.sample(subject, action, frame)
        except FileNotFoundError as exc:
            return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
        except KeyError as exc:
            return jsonify({"error": "not_found", "message": str(exc)}), 404

        if predictor.is_available:
            matrix = np.asarray(record["pressure_matrix"], dtype=np.float32)
            prediction = predictor.get().predict(matrix)
            record["predicted_mask"] = prediction.mask
            record["predicted_regions"] = prediction.regions
        return jsonify(record), 200

    @bp.get("/body-partition/")
    def page() -> Any:
        return send_from_directory(FRONTEND_DIR, "index.html")

    @bp.get("/body-partition/<path:filename>")
    def assets(filename: str) -> Any:
        return send_from_directory(FRONTEND_DIR, filename)

    return bp
