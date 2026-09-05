"""Train and evaluate the participant-independent posture SVM.

Run from the repository root after placing the dataset under ``dataset/``::

    python train/posture_svm/train_svm.py --dataset-dir dataset

Module execution with ``python -m train.posture_svm.train_svm`` is also
supported.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import joblib
import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from backend.algorithms.posture_svm.features import FeatureConfig, extract_feature_matrix
from backend.data_utils.contracts import (
    CONTRACT_VERSION,
    LABEL_ID_TO_NAME,
    LABEL_ID_TO_NAME_ZH,
    MATRIX_SHAPE,
)
from backend.data_utils.data_augmentation import augment_training_frames
from backend.data_utils.data_loader import (
    PostureDataset,
    load_posture_dataset,
    validate_subject_coverage,
)


ARTIFACT_FORMAT = "sleepmatrix-posture-svm"
ARTIFACT_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = PROJECT_ROOT / "dataset"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "backend" / "models" / "posture_svm.joblib"


def split_by_subject(
    dataset: PostureDataset,
    *,
    test_size: float = 0.30,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Return train/test indices with no participant appearing in both."""

    if not 0.0 < test_size < 1.0:
        raise ValueError("test_size must be between 0 and 1.")
    subjects = np.unique(dataset.subjects)
    if subjects.size < 4:
        raise ValueError(
            "At least four participants are required for a meaningful 70/30 "
            "participant split."
        )
    validate_subject_coverage(dataset, LABEL_ID_TO_NAME)

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=test_size,
        random_state=random_state,
    )
    train_indices, test_indices = next(
        splitter.split(dataset.frames, dataset.labels, groups=dataset.subjects)
    )
    train_subjects = set(dataset.subjects[train_indices])
    test_subjects = set(dataset.subjects[test_indices])
    if train_subjects & test_subjects:
        raise RuntimeError("Participant leakage detected in train/test split.")
    return train_indices, test_indices


def build_search(*, number_of_train_subjects: int, n_jobs: int = -1) -> GridSearchCV:
    """Build participant-grouped cross-validation for SVM hyperparameters."""

    folds = min(5, number_of_train_subjects)
    if folds < 2:
        raise ValueError(
            "At least two training participants are needed for cross-validation."
        )
    pipeline = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "svm",
                SVC(
                    kernel="rbf",
                    class_weight="balanced",
                    probability=False,
                    random_state=42,
                ),
            ),
        ]
    )
    return GridSearchCV(
        estimator=pipeline,
        param_grid={
            "svm__C": [1.0, 10.0, 100.0],
            "svm__gamma": ["scale", 0.001, 0.01],
        },
        scoring="f1_macro",
        cv=GroupKFold(n_splits=folds),
        n_jobs=n_jobs,
        refit=True,
        return_train_score=False,
        verbose=1,
    )


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def train_and_evaluate(
    *,
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    model_path: str | Path = DEFAULT_MODEL_PATH,
    test_size: float = 0.30,
    random_state: int = 42,
    jitter_copies: int = 1,
    noise_ratio: float = 0.01,
    max_shift: int = 1,
    include_horizontal_mirror: bool = False,
    max_frames_per_file: int | None = None,
    n_jobs: int = -1,
) -> dict[str, Any]:
    """Load, split, augment, train, evaluate and persist an SVM model."""

    dataset = load_posture_dataset(
        dataset_dir,
        matrix_shape=MATRIX_SHAPE,
        max_frames_per_file=max_frames_per_file,
    )
    train_indices, test_indices = split_by_subject(
        dataset,
        test_size=test_size,
        random_state=random_state,
    )
    raw_train_frames = dataset.frames[train_indices]
    raw_train_labels = dataset.labels[train_indices]
    raw_train_subjects = dataset.subjects[train_indices]
    test_frames = dataset.frames[test_indices]
    test_labels = dataset.labels[test_indices]

    feature_config = FeatureConfig()
    raw_train_features = extract_feature_matrix(raw_train_frames, feature_config)
    search = build_search(
        number_of_train_subjects=np.unique(raw_train_subjects).size,
        n_jobs=n_jobs,
    )
    # Synthetic frames never act as validation truth during model selection.
    search.fit(raw_train_features, raw_train_labels, groups=raw_train_subjects)

    train_frames, train_labels, _, _ = augment_training_frames(
        raw_train_frames,
        raw_train_labels,
        raw_train_subjects,
        dataset.actions[train_indices],
        jitter_copies=jitter_copies,
        noise_ratio=noise_ratio,
        max_shift=max_shift,
        include_horizontal_mirror=include_horizontal_mirror,
        random_state=random_state,
    )
    train_features = extract_feature_matrix(train_frames, feature_config)
    test_features = extract_feature_matrix(test_frames, feature_config)

    # Probability estimation is enabled only for the final selected model.
    final_pipeline = clone(search.best_estimator_)
    final_pipeline.set_params(svm__probability=True)
    final_pipeline.fit(train_features, train_labels)
    predictions = final_pipeline.predict(test_features)

    ordered_labels = sorted(LABEL_ID_TO_NAME)
    target_names = [LABEL_ID_TO_NAME[label] for label in ordered_labels]
    report = classification_report(
        test_labels,
        predictions,
        labels=ordered_labels,
        target_names=target_names,
        output_dict=True,
        zero_division=0,
    )
    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(test_labels, predictions)),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(
            test_labels,
            predictions,
            labels=ordered_labels,
        ).tolist(),
        "best_cv_f1_macro": float(search.best_score_),
        "best_params": search.best_params_,
        "train_subjects": sorted(np.unique(dataset.subjects[train_indices]).tolist()),
        "test_subjects": sorted(np.unique(dataset.subjects[test_indices]).tolist()),
        "raw_train_frames": int(train_indices.size),
        "augmented_train_frames": int(train_frames.shape[0]),
        "test_frames": int(test_indices.size),
    }
    artifact = {
        "format": ARTIFACT_FORMAT,
        "version": ARTIFACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "matrix_shape": MATRIX_SHAPE,
        "feature_config": feature_config.to_dict(),
        "label_id_to_name": LABEL_ID_TO_NAME,
        "label_id_to_name_zh": LABEL_ID_TO_NAME_ZH,
        "pipeline": final_pipeline,
        "training": {
            "dataset_dir": str(Path(dataset_dir)),
            "test_size": test_size,
            "random_state": random_state,
            "jitter_copies": jitter_copies,
            "noise_ratio": noise_ratio,
            "max_shift": max_shift,
            "horizontal_mirror": include_horizontal_mirror,
            "sklearn_version": sklearn.__version__,
        },
        "metrics": metrics,
    }
    destination = Path(model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, destination)
    destination.with_suffix(".metrics.json").write_text(
        json.dumps(_json_compatible(metrics), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metrics


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--test-size", type=float, default=0.30)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--jitter-copies", type=int, default=1)
    parser.add_argument("--noise-ratio", type=float, default=0.01)
    parser.add_argument("--max-shift", type=int, default=1)
    parser.add_argument(
        "--include-horizontal-mirror",
        action="store_true",
        help=(
            "Add horizontal flips. Leave disabled for the documented final "
            "dataset, which already contains mirrored frames."
        ),
    )
    parser.add_argument("--max-frames-per-file", type=int)
    parser.add_argument("--n-jobs", type=int, default=-1)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        metrics = train_and_evaluate(
            dataset_dir=args.dataset_dir,
            model_path=args.model_path,
            test_size=args.test_size,
            random_state=args.random_state,
            jitter_copies=args.jitter_copies,
            noise_ratio=args.noise_ratio,
            max_shift=args.max_shift,
            include_horizontal_mirror=args.include_horizontal_mirror,
            max_frames_per_file=args.max_frames_per_file,
            n_jobs=args.n_jobs,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"Training aborted: {exc}") from exc
    print(json.dumps(_json_compatible(metrics), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
