"""Unified Flask application for the SleepMatrix backend.

Endpoints:
    GET  /api/health                -> service + per-model status
    GET  /api/contracts/posture     -> shared language-neutral contract
    POST /api/posture/predict       -> posture inference (svm | cnn | ensemble)
    POST /api/frame/analyze         -> posture + partition + enhance in one call
    /api/body-partition/*           -> body-partition blueprint
    /api/weak-enhance*              -> weak-pressure enhancement blueprint

All errors use the ``{"error": <code>, "message": <text>}`` envelope defined
in :mod:`backend.api_utils`.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from backend import config
from backend.algorithms.body_partition.api import (
    create_blueprint as create_body_partition_blueprint,
)
from backend.algorithms.posture_cnn.data_io import DEFAULT_DATA_DIR, read_pressure_frames
from backend.algorithms.posture_cnn.predictor import PostureCNNClassifier
from backend.algorithms.posture_svm.inference import PostureSVMClassifier
from backend.algorithms.weak_area_enhance.api import (
    create_blueprint as create_weak_enhance_blueprint,
)
from backend.algorithms.weak_area_enhance.enhance import EnhancementConfig, enhance_pressure
from backend.api_utils import (
    EndpointError,
    LazyModelLoader,
    error_response,
    invalid_request,
    model_unavailable,
    pressure_matrix_from_payload,
)
from backend.data_utils.contracts import CONTRACT
from backend.data_utils.predictions import PosturePrediction, merged_prediction

POSTURE_MODELS = ("svm", "cnn", "ensemble")
ANALYZE_FEATURES = ("posture", "partition", "enhance")


def create_app(
    model_path: str | Path | None = None,
    posture_cnn_model_path: str | Path | None = None,
    posture_cnn_device: str | None = None,
) -> Flask:
    app = Flask(__name__)
    CORS(app)

    svm_path = Path(model_path or config.POSTURE_SVM_MODEL_PATH)
    cnn_path = Path(posture_cnn_model_path or config.POSTURE_CNN_MODEL_PATH)
    cnn_device = posture_cnn_device or config.POSTURE_CNN_DEVICE

    svm_classifier = LazyModelLoader(svm_path, PostureSVMClassifier)
    cnn_classifier = LazyModelLoader(
        cnn_path,
        partial(PostureCNNClassifier, device=cnn_device),
    )

    body_partition_resources: dict[str, Any] = {}
    app.register_blueprint(
        create_body_partition_blueprint(resources=body_partition_resources)
    )
    app.register_blueprint(create_weak_enhance_blueprint())

    app.extensions["posture_svm_classifier"] = svm_classifier
    app.extensions["posture_cnn_classifier"] = cnn_classifier
    app.extensions["body_partition"] = body_partition_resources
    # 设备实时帧缓冲：POST /api/stream/ingest 写入，GET /api/stream/latest 读取
    app.extensions["device_stream"] = {
        "seq": -1,
        "matrix": [],
        "source": None,
        "timestamp": None,
    }

    # ------------------------------------------------------------------
    # Posture inference helpers (shared by /predict and /analyze)
    # ------------------------------------------------------------------

    def _svm_prediction(matrix: Any) -> PosturePrediction:
        try:
            classifier = app.extensions["posture_svm_classifier"].get()
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise model_unavailable(str(exc)) from exc
        try:
            return classifier.predict(matrix)
        except ValueError as exc:
            raise invalid_request(str(exc)) from exc

    def _cnn_prediction(matrix: Any) -> PosturePrediction:
        try:
            classifier = app.extensions["posture_cnn_classifier"].get()
        except (FileNotFoundError, KeyError, ValueError) as exc:
            raise model_unavailable(str(exc)) from exc
        try:
            return classifier.predict(matrix)
        except ValueError as exc:
            raise invalid_request(str(exc)) from exc

    def _classify(
        matrix: Any,
        choice: str,
    ) -> tuple[PosturePrediction, str]:
        """Run the requested posture model(s); returns (prediction, used_model)."""

        if choice == "svm":
            return _svm_prediction(matrix), "svm"
        if choice == "cnn":
            return _cnn_prediction(matrix), "cnn"

        # ensemble: average the probabilities of every available model and
        # degrade gracefully to a single model when only one is usable.
        svm_prediction = cnn_prediction = None
        svm_error = cnn_error = None
        try:
            svm_prediction = _svm_prediction(matrix)
        except EndpointError as exc:
            svm_error = exc
        try:
            cnn_prediction = _cnn_prediction(matrix)
        except EndpointError as exc:
            cnn_error = exc

        if svm_prediction is None and cnn_prediction is None:
            details = "; ".join(
                f"{name}: {exc.message}"
                for name, exc in (("svm", svm_error), ("cnn", cnn_error))
                if exc is not None
            )
            raise model_unavailable(f"No posture model is available. {details}")
        if svm_prediction is None:
            return cnn_prediction, "cnn"
        if cnn_prediction is None:
            return svm_prediction, "svm"
        return (
            merged_prediction(
                [svm_prediction.probabilities, cnn_prediction.probabilities]
            ),
            "ensemble",
        )

    def _parse_model_choice(payload: Any) -> str:
        if not isinstance(payload, dict):
            return "svm"
        raw = payload.get("model", "svm")
        if not isinstance(raw, str):
            raise invalid_request("`model` must be one of: svm, cnn, ensemble.")
        choice = raw.strip().lower()
        if choice not in POSTURE_MODELS:
            raise invalid_request(
                f"Unknown model {raw!r}; expected one of {list(POSTURE_MODELS)}."
            )
        return choice

    def _parse_features(payload: Any) -> list[str]:
        if not isinstance(payload, dict) or "features" not in payload:
            return list(ANALYZE_FEATURES)
        raw = payload["features"]
        if (
            not isinstance(raw, list)
            or not raw
            or not all(isinstance(item, str) for item in raw)
        ):
            raise invalid_request(
                "`features` must be a non-empty array of feature names."
            )
        unknown = sorted(set(raw) - set(ANALYZE_FEATURES))
        if unknown:
            raise invalid_request(
                f"Unknown feature(s) {unknown}; expected one of {list(ANALYZE_FEATURES)}."
            )
        return list(dict.fromkeys(raw))

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> tuple[Any, int]:
        svm_loader = app.extensions["posture_svm_classifier"]
        cnn_loader = app.extensions["posture_cnn_classifier"]
        partition_predictor = body_partition_resources.get("predictor")
        samples = body_partition_resources.get("samples")
        return (
            jsonify(
                {
                    "status": "ok",
                    # Legacy top-level key kept for the existing frontend.
                    "posture_svm": svm_loader.status(),
                    "models": {
                        "posture_svm": svm_loader.status(),
                        "posture_cnn": cnn_loader.status(),
                        "body_partition": {
                            "model_available": bool(
                                partition_predictor and partition_predictor.is_available
                            ),
                            "model_path": (
                                str(partition_predictor.model_path)
                                if partition_predictor
                                else None
                            ),
                            "dataset_available": bool(
                                samples is not None and samples.is_available
                            ),
                        },
                        "weak_area_enhance": {"available": True},
                    },
                }
            ),
            200,
        )

    @app.get("/api/contracts/posture")
    def posture_contract() -> tuple[Any, int]:
        """Expose the validated language-neutral contract to the frontend."""

        return jsonify(CONTRACT), 200

    @app.get("/api/dataset/stream")
    def dataset_stream() -> tuple[Any, int]:
        """Build a demo realtime stream from dataset pressure files.

        Query: ``files`` (comma separated ``<subject>_<action>.txt`` names) and
        ``limit`` (frames per file, 1-120, default 30). Returns the same
        ``{person, bg, frames, labels}`` dynamic shape the frontend plays as
        its realtime inference stream.
        """

        raw_files = request.args.get("files", "")
        names = [name.strip() for name in raw_files.split(",") if name.strip()]
        if not names:
            return error_response(
                "invalid_request",
                "Provide `files` (comma separated, e.g. dgs_1.txt,dgs_10.txt).",
                400,
            )
        if len(names) > 12:
            return error_response("invalid_request", "At most 12 files per stream.", 400)
        try:
            limit = int(request.args.get("limit", "30"))
        except ValueError:
            return error_response("invalid_request", "`limit` must be an integer.", 400)
        limit = max(1, min(limit, 120))

        pattern = re.compile(r"^([A-Za-z0-9]+)_(\d{1,2})(\.txt)?$")
        frames: list[list[float]] = []
        labels: list[int] = []
        used: list[str] = []
        for name in names:
            match = pattern.match(Path(name).name)
            if match is None:
                return error_response(
                    "invalid_request",
                    f"Bad file name {name!r}; expected <subject>_<action>.txt.",
                    400,
                )
            subject, action_text = match.group(1), int(match.group(2))
            if not 1 <= action_text <= 21:
                return error_response(
                    "invalid_request", f"Action out of range in {name!r}.", 400
                )
            source = DEFAULT_DATA_DIR / subject / f"{subject}_{action_text}.txt"
            if not source.is_file():
                return error_response(
                    "not_found", f"Dataset file not found: {source.name}", 404
                )
            for frame in read_pressure_frames(source)[:limit]:
                frames.append([float(value) for value in frame.flatten()])
                labels.append(action_text)
            used.append(f"{subject}_{action_text}")

        if not frames:
            return error_response("invalid_request", "No frames loaded.", 400)
        return (
            jsonify(
                {
                    "person": "+".join(used),
                    "bg": [0.0] * 1056,
                    "frames": frames,
                    "labels": labels,
                }
            ),
            200,
        )

    @app.post("/api/stream/ingest")
    def stream_ingest() -> tuple[Any, int]:
        """设备实时帧输入：把一帧 44×24 压力矩阵写入最新帧缓冲。

        真实设备/采集程序逐帧 POST 到本端点；前端实时推理模式轮询
        ``/api/stream/latest`` 获取最新帧并驱动推理。
        """

        try:
            payload = request.get_json(silent=True)
            matrix = pressure_matrix_from_payload(payload)
        except EndpointError as exc:
            return error_response(exc.code, exc.message, exc.status)
        stream = app.extensions["device_stream"]
        stream["seq"] += 1
        stream["matrix"] = matrix.tolist()
        stream["source"] = (
            str(payload.get("source", "device"))
            if isinstance(payload, dict)
            else "device"
        )
        stream["timestamp"] = time.time()
        return jsonify({"seq": stream["seq"], "received": True}), 200

    @app.get("/api/stream/latest")
    def stream_latest() -> tuple[Any, int]:
        """读取最新设备帧；``after`` 指定已知帧号，无新帧时返回 has_frame=false。"""

        try:
            after = int(request.args.get("after", "-1"))
        except ValueError:
            return error_response("invalid_request", "`after` must be an integer.", 400)
        stream = app.extensions["device_stream"]
        if stream["seq"] <= after:
            return jsonify({"has_frame": False, "seq": stream["seq"]}), 200
        return (
            jsonify(
                {
                    "has_frame": True,
                    "seq": stream["seq"],
                    "source": stream["source"],
                    "timestamp": stream["timestamp"],
                    "pressure_matrix": stream["matrix"],
                }
            ),
            200,
        )

    @app.post("/api/posture/predict")
    def predict_posture() -> tuple[Any, int]:
        try:
            payload = request.get_json(silent=True)
            matrix = pressure_matrix_from_payload(payload)
            choice = _parse_model_choice(payload)
            prediction, used_model = _classify(matrix, choice)
        except EndpointError as exc:
            return error_response(exc.code, exc.message, exc.status)
        return jsonify({"model": used_model, **prediction.to_dict()}), 200

    @app.post("/api/frame/analyze")
    def analyze_frame() -> tuple[Any, int]:
        try:
            payload = request.get_json(silent=True)
            matrix = pressure_matrix_from_payload(payload)
            choice = _parse_model_choice(payload)
            features = _parse_features(payload)
        except EndpointError as exc:
            return error_response(exc.code, exc.message, exc.status)

        result: dict[str, Any] = {}

        if "posture" in features:
            try:
                prediction, used_model = _classify(matrix, choice)
                result["posture"] = {
                    "model": used_model,
                    "prediction": prediction.to_dict(),
                }
            except EndpointError as exc:
                result["posture"] = {"error": exc.code, "message": exc.message}

        if "partition" in features:
            predictor = body_partition_resources.get("predictor")
            if predictor is None or not predictor.is_available:
                model_path = body_partition_resources.get("model_path", "unknown")
                result["partition"] = {
                    "error": "model_unavailable",
                    "message": f"Body-partition model was not found at {model_path}.",
                }
            else:
                try:
                    prediction = predictor.get().predict(matrix)
                    result["partition"] = prediction.to_dict()
                except (FileNotFoundError, KeyError, ValueError) as exc:
                    result["partition"] = {
                        "error": "model_unavailable",
                        "message": str(exc),
                    }

        if "enhance" in features:
            try:
                enhanced = enhance_pressure(matrix)
                result["enhanced"] = {
                    "enhanced_matrix": enhanced.tolist(),
                    "config_used": asdict(EnhancementConfig()),
                }
            except ValueError as exc:
                result["enhanced"] = {
                    "error": "invalid_request",
                    "message": str(exc),
                }

        return jsonify(result), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
