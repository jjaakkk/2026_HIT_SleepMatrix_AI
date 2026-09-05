"""Train and evaluate the body-partition segmentation network.

Two evaluation protocols are supported, matching the task requirements:

- ``--split random``: frame-level 70/30 train/validation split (stratified by
  sleep position). Requirement: validation pixel accuracy above 95%%.
- ``--split subject``: participant-level holdout (30%% of participants act as
  brand-new users). Requirement: pixel accuracy above 70%%.

Only the training partition is augmented. Run from the repository root::

    python -m train.body_partition.dataset_prep            # once, builds the base arrays
    python -m train.body_partition.train_partition --split random
    python -m train.body_partition.train_partition --split subject
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import torch
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from backend.algorithms.body_partition.model_define import BodyPartitionUNet, count_parameters
from backend.algorithms.body_partition.partition import (
    NUM_CLASSES,
    REGION_KEYS,
    REGION_NAMES_ZH,
    mask_to_rects,
    mean_iou,
    per_class_iou,
    pixel_accuracy,
    region_rect_metrics,
)
from backend.algorithms.body_partition.preprocess import normalize_frames
from backend.data_utils.contracts import CONTRACT_VERSION, MATRIX_SHAPE
from train.body_partition.augment import augment_frames_and_masks
from train.body_partition.dataset_prep import DEFAULT_SOURCE, build_base_arrays, load_partition_records

ARTIFACT_FORMAT = "sleepmatrix-body-partition"
ARTIFACT_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "backend" / "models" / "body_partition.pth"
HOLDOUT_MODEL_PATH = PROJECT_ROOT / "backend" / "models" / "body_partition_holdout.pth"
HOLDOUT_REPORT_PATH = PROJECT_ROOT / "docs" / "body-partition" / "body_partition_subject_eval.json"
AUGMENTED_DATASET_PATH = PROJECT_ROOT / "dataset" / "processed" / "body_partition_train_augmented.npz"
SLEEP_POSITION_NAMES = {0: "supine", 1: "prone", 2: "left_lateral", 3: "right_lateral"}


def split_indices(
    arrays: dict[str, np.ndarray],
    split: str,
    test_size: float,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Frame-level random or participant-level holdout indices."""

    size = arrays["frames"].shape[0]
    indices = np.arange(size)
    if split == "random":
        train_idx, test_idx = train_test_split(
            indices,
            test_size=test_size,
            random_state=random_state,
            stratify=arrays["sleep_positions"],
        )
    elif split == "subject":
        subjects = arrays["subjects"]
        if np.unique(subjects).size < 4:
            raise ValueError("At least four participants are required for a subject holdout.")
        splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
        train_idx, test_idx = next(splitter.split(indices, groups=subjects))
        if set(subjects[train_idx]) & set(subjects[test_idx]):
            raise RuntimeError("Participant leakage detected in subject split.")
    else:
        raise ValueError(f"Unknown split mode: {split}")
    return np.asarray(train_idx), np.asarray(test_idx)


def class_weights(masks: np.ndarray) -> torch.Tensor:
    """Inverse-sqrt frequency weights, normalised to mean one."""

    counts = np.bincount(masks.ravel(), minlength=NUM_CLASSES).astype(np.float64)
    frequencies = np.maximum(counts / counts.sum(), 1e-8)
    weights = 1.0 / np.sqrt(frequencies)
    weights /= weights.mean()
    return torch.tensor(weights, dtype=torch.float32)


def evaluate_arrays(model: nn.Module, frames: np.ndarray, masks: np.ndarray) -> dict[str, Any]:
    """Full metric suite of the model on raw (unnormalised) frames."""

    model.eval()
    normalized = normalize_frames(frames)
    predictions: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, normalized.shape[0], 512):
            batch = torch.from_numpy(normalized[start : start + 512])[:, None, :, :]
            logits = model(batch)
            predictions.append(logits.argmax(dim=1).numpy().astype(np.uint8))
    predicted = np.concatenate(predictions)

    iou_per_class = per_class_iou(predicted, masks)
    rect_metrics_accumulated = [
        region_rect_metrics(predicted[index], masks[index]) for index in range(masks.shape[0])
    ]
    return {
        "pixel_accuracy": pixel_accuracy(predicted, masks),
        "mean_iou": mean_iou(predicted, masks),
        "iou_per_class": {
            ("background" if class_id == 0 else REGION_KEYS[class_id - 1]): (
                None if score is None else float(score)
            )
            for class_id, score in enumerate(iou_per_class)
        },
        "mean_rect_iou": float(np.mean([m["mean_rect_iou"] for m in rect_metrics_accumulated])),
        "mean_boundary_mae": float(
            np.mean([m["mean_boundary_mae"] for m in rect_metrics_accumulated])
        ),
    }, predicted


def train_model(
    *,
    train_frames: np.ndarray,
    train_masks: np.ndarray,
    val_frames: np.ndarray,
    val_masks: np.ndarray,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    patience: int,
    seed: int,
    num_threads: int,
) -> tuple[nn.Module, list[dict[str, float]]]:
    """Train the U-Net with early stopping on validation pixel accuracy."""

    torch.manual_seed(seed)
    torch.set_num_threads(num_threads)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    normalized_train = normalize_frames(train_frames)
    normalized_val = normalize_frames(val_frames)

    dataset = TensorDataset(
        torch.from_numpy(normalized_train)[:, None, :, :],
        torch.from_numpy(train_masks.astype(np.int64)),
    )
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)
    val_inputs = torch.from_numpy(normalized_val)[:, None, :, :].to(device)
    val_targets = torch.from_numpy(val_masks.astype(np.int64)).to(device)

    model = BodyPartitionUNet().to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights(train_masks).to(device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    history: list[dict[str, float]] = []
    best_accuracy = -1.0
    best_state: dict[str, torch.Tensor] | None = None
    epochs_without_improvement = 0

    for epoch in range(1, epochs + 1):
        model.train()
        started = time.perf_counter()
        running_loss = 0.0
        for inputs, targets in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            optimizer.zero_grad()
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * inputs.shape[0]
        scheduler.step()

        model.eval()
        with torch.no_grad():
            correct = 0
            for start in range(0, val_inputs.shape[0], 1024):
                logits = model(val_inputs[start : start + 1024])
                correct += int((logits.argmax(dim=1) == val_targets[start : start + 1024]).sum())
        val_accuracy = correct / val_targets.numel()
        epoch_loss = running_loss / len(dataset)
        history.append(
            {
                "epoch": float(epoch),
                "train_loss": float(epoch_loss),
                "val_pixel_accuracy": float(val_accuracy),
                "seconds": float(time.perf_counter() - started),
            }
        )
        print(
            f"epoch {epoch:02d}/{epochs}  loss {epoch_loss:.4f}  "
            f"val pixel acc {val_accuracy:.4f}  ({history[-1]['seconds']:.1f}s)",
            flush=True,
        )

        if val_accuracy > best_accuracy:
            best_accuracy = val_accuracy
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                print(f"early stop at epoch {epoch} (best val acc {best_accuracy:.4f})", flush=True)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model.cpu(), history


def save_augmented_dataset(frames: np.ndarray, masks: np.ndarray, destination: Path) -> None:
    """Persist the augmented training partition as an auditable dataset file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        frames=frames.astype(np.float16),
        masks=masks.astype(np.uint8),
    )


def build_artifact(
    model: nn.Module,
    metrics: dict[str, Any],
    history: list[dict[str, float]],
    args: argparse.Namespace,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Versioned model artifact, mirroring the posture-SVM conventions."""

    return {
        "format": ARTIFACT_FORMAT,
        "version": ARTIFACT_VERSION,
        "contract_version": CONTRACT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "matrix_shape": MATRIX_SHAPE,
        "model_config": {"in_channels": 1, "num_classes": NUM_CLASSES, "base_channels": 24},
        "normalization": {"type": "percentile", "percentile": 99.0},
        "region_keys": list(REGION_KEYS),
        "region_names_zh": list(REGION_NAMES_ZH),
        "state_dict": model.state_dict(),
        "training": {
            "split": args.split,
            "test_size": args.test_size,
            "random_state": args.random_state,
            "epochs_ran": len(history),
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "augmentation": {
                "copies": args.aug_copies,
                "max_row_shift": 2,
                "max_column_shift": 1,
                "noise_ratio": 0.03,
                "gain_range": [0.90, 1.10],
                "baseline_ratio": 0.02,
                "dead_pixel_ratio": 0.0005,
                "horizontal_mirror": False,
            },
            "parameters": count_parameters(model),
            **extra,
        },
        "history": history,
        "metrics": metrics,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    records = load_partition_records(args.data)
    arrays = build_base_arrays(records)
    train_idx, test_idx = split_indices(arrays, args.split, args.test_size, args.random_state)

    train_frames, test_frames = arrays["frames"][train_idx], arrays["frames"][test_idx]
    train_masks, test_masks = arrays["masks"][train_idx], arrays["masks"][test_idx]

    if args.aug_copies > 0:
        train_frames, train_masks = augment_frames_and_masks(
            train_frames,
            train_masks,
            copies=args.aug_copies,
            random_state=args.random_state,
        )
        if args.save_augmented:
            save_augmented_dataset(train_frames, train_masks, AUGMENTED_DATASET_PATH)

    model, history = train_model(
        train_frames=train_frames,
        train_masks=train_masks,
        val_frames=test_frames,
        val_masks=test_masks,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        patience=args.patience,
        seed=args.random_state,
        num_threads=args.num_threads,
    )

    metrics, predicted = evaluate_arrays(model, test_frames, test_masks)

    per_position: dict[str, Any] = {}
    for position, name in SLEEP_POSITION_NAMES.items():
        selector = arrays["sleep_positions"][test_idx] == position
        if selector.any():
            per_position[name] = pixel_accuracy(predicted[selector], test_masks[selector])
    metrics["pixel_accuracy_by_position"] = per_position

    extra: dict[str, Any] = {
        "train_frames": int(train_idx.size),
        "augmented_train_frames": int(train_frames.shape[0]),
        "test_frames": int(test_idx.size),
    }

    if args.split == "subject":
        test_subjects = arrays["subjects"][test_idx]
        per_subject: dict[str, Any] = {}
        for subject in sorted(np.unique(test_subjects)):
            selector = test_subjects == subject
            subject_metrics = {
                "pixel_accuracy": pixel_accuracy(predicted[selector], test_masks[selector]),
                "mean_iou": mean_iou(predicted[selector], test_masks[selector]),
                "frames": int(selector.sum()),
            }
            per_subject[subject] = subject_metrics
        metrics["per_subject"] = per_subject
        extra["train_subjects"] = sorted(np.unique(arrays["subjects"][train_idx]).tolist())
        extra["test_subjects"] = sorted(np.unique(test_subjects).tolist())

    artifact = build_artifact(model, metrics, history, args, extra)
    model_path = Path(args.model_path or (DEFAULT_MODEL_PATH if args.split == "random" else HOLDOUT_MODEL_PATH))
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(artifact, model_path)

    report = {
        "split": args.split,
        "model_path": str(model_path),
        "metrics": metrics,
        "training": artifact["training"],
        "history": history,
    }
    report_path = Path(
        args.report_path
        or (
            model_path.with_suffix(".metrics.json")
            if args.split == "random"
            else HOLDOUT_REPORT_PATH
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--split", choices=["random", "subject"], default="random")
    parser.add_argument("--test-size", type=float, default=0.30)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=3e-3)
    parser.add_argument("--aug-copies", type=int, default=2)
    parser.add_argument("--num-threads", type=int, default=max(1, (torch.get_num_threads() or 4)))
    parser.add_argument("--save-augmented", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--report-path", type=Path)
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    report = run(args)
    metrics = report["metrics"]
    print(
        json.dumps(
            {
                "split": report["split"],
                "pixel_accuracy": metrics["pixel_accuracy"],
                "mean_iou": metrics["mean_iou"],
                "mean_rect_iou": metrics["mean_rect_iou"],
                "mean_boundary_mae": metrics["mean_boundary_mae"],
                "pixel_accuracy_by_position": metrics["pixel_accuracy_by_position"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
