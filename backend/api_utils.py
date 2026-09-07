"""Shared helpers for HTTP endpoints.

Every endpoint in the unified backend uses the same conventions:

- request bodies carry a 44x24 ``pressure_matrix`` (legacy ``data`` alias);
- errors use the ``{"error": <code>, "message": <text>}`` envelope;
- model artifacts are loaded lazily, once per process, on first use.
"""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable, TypeVar

from flask import jsonify
import numpy as np

from backend.data_utils.contracts import MATRIX_SHAPE
from backend.data_utils.pressure_processing import validate_pressure_frame


T = TypeVar("T")


class EndpointError(Exception):
    """Error carrying the unified HTTP envelope fields."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def invalid_request(message: str) -> EndpointError:
    """HTTP 400 error with the ``invalid_request`` code."""

    return EndpointError("invalid_request", message, 400)


def model_unavailable(message: str) -> EndpointError:
    """HTTP 503 error with the ``model_unavailable`` code."""

    return EndpointError("model_unavailable", message, 503)


def error_response(code: str, message: str, status: int) -> tuple[Any, int]:
    """Build the unified ``{error, message}`` response envelope."""

    return jsonify({"error": code, "message": message}), status


def extract_pressure_matrix(
    payload: Any,
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
) -> np.ndarray:
    """Extract the ``pressure_matrix`` (or legacy ``data``) field from a JSON body.

    Raises :class:`ValueError` with a user-facing message when the body is
    not a JSON object, the field is missing, or the matrix does not match the
    agreed shape / contains non-finite values.
    """

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    raw_matrix = payload.get("pressure_matrix", payload.get("data"))
    if raw_matrix is None:
        raise ValueError("JSON field `pressure_matrix` is required.")
    return validate_pressure_frame(raw_matrix, matrix_shape)


def pressure_matrix_from_payload(payload: Any) -> np.ndarray:
    """Extract and validate the pressure matrix, raising :class:`EndpointError`."""

    try:
        return extract_pressure_matrix(payload)
    except ValueError as exc:
        raise invalid_request(str(exc)) from exc


class LazyModelLoader:
    """Load one model artifact lazily, once per process, thread-safely."""

    def __init__(self, model_path: str | Path, factory: Callable[[Path], T]) -> None:
        self.model_path = Path(model_path)
        self._factory = factory
        self._instance: T | None = None
        self._lock = Lock()

    @property
    def is_available(self) -> bool:
        return self.model_path.is_file()

    def get(self) -> T:
        """Return the loaded model, creating it on the first call."""

        if self._instance is None:
            with self._lock:
                if self._instance is None:
                    self._instance = self._factory(self.model_path)
        return self._instance

    def status(self) -> dict[str, Any]:
        """Standard ``{model_available, model_path}`` health entry."""

        return {
            "model_available": self.is_available,
            "model_path": str(self.model_path),
        }
