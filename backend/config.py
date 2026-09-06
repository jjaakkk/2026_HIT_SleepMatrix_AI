"""Configuration for the SleepMatrix backend service.

Every model artifact path is defined here (env-overridable), so algorithms
and HTTP endpoints share one source of truth. Data contract values (matrix
shape, labels) come from ``backend.data_utils.contracts`` and are never
redefined here.
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.data_utils.contracts import MATRIX_SHAPE


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = Path(os.getenv("SLEEPMATRIX_DATASET_DIR", PROJECT_ROOT / "dataset"))
PRESSURE_MATRIX_SHAPE = MATRIX_SHAPE

# --- posture SVM (member A) -------------------------------------------------
POSTURE_SVM_MODEL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_POSTURE_SVM_MODEL",
        PROJECT_ROOT / "backend" / "models" / "posture_svm.joblib",
    )
)

# --- posture CNN (member B) -------------------------------------------------
# The training script writes `outputs/posture_cnn/best_model.pt`; the artifact
# is a local training product and is not committed to Git.
POSTURE_CNN_MODEL_PATH = Path(
    os.getenv(
        "SLEEPMATRIX_POSTURE_CNN_MODEL",
        PROJECT_ROOT / "outputs" / "posture_cnn" / "best_model.pt",
    )
)
POSTURE_CNN_DEVICE = os.getenv("SLEEPMATRIX_POSTURE_CNN_DEVICE", "auto")

# --- body partition (member C) ----------------------------------------------
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
        PROJECT_ROOT / "docs" / "body-partition" / "body_partition_subject_eval.json",
    )
)
BODY_PARTITION_FRONTEND_DIR = PROJECT_ROOT / "frontend" / "body-partition"

HOST = os.getenv("SLEEPMATRIX_HOST", "127.0.0.1")
PORT = int(os.getenv("SLEEPMATRIX_PORT", "5000"))
DEBUG = os.getenv("SLEEPMATRIX_DEBUG", "0").lower() in {"1", "true", "yes"}
