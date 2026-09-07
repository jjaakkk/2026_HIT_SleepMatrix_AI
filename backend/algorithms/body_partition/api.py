"""Blueprint exposing the body-partition HTTP API and the demo page.

Paths default to the centralized :mod:`backend.config` (env-overridable);
module-level aliases are kept so tests can patch them per module.

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
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, send_from_directory
import numpy as np

from backend import config
from backend.algorithms.body_partition.demo_data import AnnotatedSampleStore
from backend.algorithms.body_partition.inference import BodyPartitionPredictor
from backend.api_utils import LazyModelLoader, extract_pressure_matrix

# ----------------------------------------------------------------------
# Module-level paths (aliases of backend.config; patchable in tests).
# ----------------------------------------------------------------------

MODEL_PATH = config.BODY_PARTITION_MODEL_PATH
DATASET_PATH = config.BODY_PARTITION_DATASET_PATH
METRICS_PATH = config.BODY_PARTITION_METRICS_PATH
SUBJECT_EVAL_PATH = config.BODY_PARTITION_SUBJECT_EVAL_PATH
FRONTEND_DIR = config.BODY_PARTITION_FRONTEND_DIR


def create_blueprint(
    model_path: str | Path | None = None,
    resources: dict[str, Any] | None = None,
) -> Blueprint:
    """Build a fresh blueprint; paths default to the module configuration.

    When ``resources`` is provided it is filled with the lazy predictor and
    sample store so the hosting app can report them in its own endpoints.
    """
    predictor = LazyModelLoader(model_path or MODEL_PATH, BodyPartitionPredictor)
    samples = AnnotatedSampleStore(DATASET_PATH)
    if resources is not None:
        resources.update(
            {
                "predictor": predictor,
                "samples": samples,
                "model_path": predictor.model_path,
                "dataset_path": samples.dataset_path,
            }
        )
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
            matrix = extract_pressure_matrix(request.get_json(silent=True))
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
