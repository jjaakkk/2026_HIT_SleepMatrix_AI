"""Blueprint exposing the weak-pressure enhancement HTTP API.

The enhancement pipeline is pure NumPy (no model artifact), so the endpoint
is always available. The returned matrix is intended for visualization or as
optional downstream preprocessing; it is not calibrated physical pressure.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from flask import Blueprint, jsonify, request

from backend.api_utils import (
    EndpointError,
    error_response,
    pressure_matrix_from_payload,
)

from .enhance import EnhancementConfig, enhance_pressure


def create_blueprint() -> Blueprint:
    """Build the weak-area-enhancement blueprint."""

    bp = Blueprint("weak_area_enhance", __name__)

    @bp.get("/api/weak-enhance/config")
    def default_config() -> tuple[Any, int]:
        """Default enhancement parameters (ratios relative to frame scale)."""

        return jsonify(asdict(EnhancementConfig())), 200

    @bp.post("/api/weak-enhance")
    def enhance() -> tuple[Any, int]:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error_response(
                "invalid_request", "Request body must be a JSON object.", 400
            )
        try:
            matrix = pressure_matrix_from_payload(payload)
        except EndpointError as exc:
            return error_response(exc.code, exc.message, exc.status)

        config = EnhancementConfig()
        overrides = payload.get("config")
        if overrides is not None:
            if not isinstance(overrides, dict):
                return error_response(
                    "invalid_request", "`config` must be a JSON object.", 400
                )
            unknown = sorted(set(overrides) - set(asdict(config)))
            if unknown:
                return error_response(
                    "invalid_request",
                    f"Unknown enhancement parameter(s): {unknown}. "
                    "See GET /api/weak-enhance/config for the supported set.",
                    400,
                )
            try:
                config = EnhancementConfig(**overrides)
            except (TypeError, ValueError) as exc:
                return error_response("invalid_request", str(exc), 400)
        try:
            config.validate()
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)

        enhanced = enhance_pressure(matrix, config)
        return (
            jsonify(
                {
                    "enhanced_matrix": enhanced.tolist(),
                    "config_used": asdict(config),
                }
            ),
            200,
        )

    return bp
