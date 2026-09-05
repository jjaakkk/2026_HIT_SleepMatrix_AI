"""Configuration for the SleepMatrix backend service."""

from __future__ import annotations

import os
from pathlib import Path

from backend.data_utils.contracts import MATRIX_SHAPE


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(os.getenv("SLEEPMATRIX_DATASET_DIR", PROJECT_ROOT / "dataset"))
POSTURE_SVM_MODEL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_POSTURE_SVM_MODEL",
        PROJECT_ROOT / "backend" / "models" / "posture_svm.joblib",
    )
)
PRESSURE_MATRIX_SHAPE = MATRIX_SHAPE

HOST = os.getenv("SLEEPMATRIX_HOST", "127.0.0.1")
PORT = int(os.getenv("SLEEPMATRIX_PORT", "5000"))
DEBUG = os.getenv("SLEEPMATRIX_DEBUG", "0").lower() in {"1", "true", "yes"}
