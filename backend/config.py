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
BODY_PARTITION_MODEL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_MODEL",
        PROJECT_ROOT / "backend" / "models" / "body_partition.pth",
    )
)
BODY_PARTITION_DATASET_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_DATASET",
        PROJECT_ROOT / "dataset" / "raw" / "body_partition_data.json",
    )
)
BODY_PARTITION_METRICS_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_METRICS",
        PROJECT_ROOT / "backend" / "models" / "body_partition.metrics.json",
    )
)
BODY_PARTITION_SUBJECT_EVAL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_BODY_PARTITION_SUBJECT_EVAL",
        PROJECT_ROOT / "docs" / "reports" / "body_partition_subject_eval.json",
    )
)
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PRESSURE_MATRIX_SHAPE = MATRIX_SHAPE

HOST = os.getenv("SLEEPMATRIX_HOST", "127.0.0.1")
PORT = int(os.getenv("SLEEPMATRIX_PORT", "5000"))
DEBUG = os.getenv("SLEEPMATRIX_DEBUG", "0").lower() in {"1", "true", "yes"}
