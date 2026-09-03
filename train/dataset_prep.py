"""Build the body-partition training dataset from the annotated JSON.

Reads the documented region-partition dataset (20 participants x 21 actions,
14400 frames), converts rectangle annotations into six-class segmentation
masks and stores one reproducible ``.npz`` under ``dataset/processed/`` for
both the random 70/30 split and the held-out-participant evaluation.

Run from the repository root::

    python -m train.dataset_prep
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from backend.algorithms.body_partition.partition import (
    NUM_CLASSES,
    REGION_KEYS,
    parse_region_field,
    rects_to_mask,
)
from backend.data_utils.contracts import MATRIX_SHAPE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "dataset" / "raw" / "body_partition_data.json"
DEFAULT_DESTINATION = PROJECT_ROOT / "dataset" / "processed" / "body_partition_base.npz"


class PartitionDatasetError(ValueError):
    """Raised when the annotated dataset is missing or inconsistent."""


def load_partition_records(source: str | Path = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    """Load and validate the raw JSON records."""

    path = Path(source)
    if not path.is_file():
        raise PartitionDatasetError(
            f"Annotated dataset not found: {path}. Copy `data.json` from the "
            "dataset manual into dataset/raw/body_partition_data.json."
        )
    with path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list) or not records:
        raise PartitionDatasetError("Annotated dataset must be a non-empty JSON array.")
    return records


def build_base_arrays(
    records: list[dict[str, Any]],
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
) -> dict[str, np.ndarray]:
    """Convert validated records into stacked frame/mask/metadata arrays."""

    rows, columns = matrix_shape
    frames: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    subjects: list[str] = []
    actions: list[int] = []
    sleep_positions: list[int] = []
    frame_numbers: list[int] = []

    for index, record in enumerate(records):
        values = [float(token) for token in str(record["data"]).split(",") if token.strip()]
        if len(values) != rows * columns:
            raise PartitionDatasetError(
                f"Record {index} has {len(values)} pressure values; expected {rows * columns}."
            )
        frame = np.asarray(values, dtype=np.float32).reshape(matrix_shape)
        rects = parse_region_field(record["region"])
        frames.append(frame)
        masks.append(rects_to_mask(rects, matrix_shape))
        subjects.append(str(record["people_name"]))
        actions.append(int(record["action"]))
        sleep_positions.append(int(record["sleep_pos"]))
        frame_numbers.append(int(record["frame"]))

    return {
        "frames": np.stack(frames),
        "masks": np.stack(masks),
        "subjects": np.asarray(subjects),
        "actions": np.asarray(actions, dtype=np.int64),
        "sleep_positions": np.asarray(sleep_positions, dtype=np.int64),
        "frame_numbers": np.asarray(frame_numbers, dtype=np.int64),
    }


def summarize(arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    """Dataset statistics printed for the preparation report."""

    frames = arrays["frames"]
    masks = arrays["masks"]
    class_fractions = {
        ("background" if class_id == 0 else REGION_KEYS[class_id - 1]): float((masks == class_id).mean())
        for class_id in range(NUM_CLASSES)
    }
    subjects, subject_counts = np.unique(arrays["subjects"], return_counts=True)
    return {
        "records": int(frames.shape[0]),
        "matrix_shape": list(frames.shape[1:]),
        "subjects": int(subjects.size),
        "frames_per_subject": {"min": int(subject_counts.min()), "max": int(subject_counts.max())},
        "actions": sorted(int(action) for action in np.unique(arrays["actions"])),
        "sleep_position_counts": {
            str(pos): int((arrays["sleep_positions"] == pos).sum())
            for pos in sorted(np.unique(arrays["sleep_positions"]))
        },
        "pressure_range": {"min": float(frames.min()), "max": float(frames.max())},
        "class_fractions": class_fractions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()

    records = load_partition_records(args.source)
    arrays = build_base_arrays(records)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.destination, **arrays)

    summary = summarize(arrays)
    summary["source"] = str(args.source)
    summary["destination"] = str(args.destination)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
