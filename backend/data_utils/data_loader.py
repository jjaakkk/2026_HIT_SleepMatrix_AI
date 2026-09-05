"""Load the shared raw 44x24 pressure-matrix text dataset.

The documented raw format is one participant/action per ``.txt`` file. A
frame contains 44 comma-separated rows of 24 values, and frames may be
separated by blank lines. The loader also accepts files without blank lines
by cutting every 44 rows into a frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterator, Sequence

import numpy as np

from .contracts import ACTION_TO_LABEL, MATRIX_SHAPE, action_to_label


class DatasetFormatError(ValueError):
    """Raised when a dataset file does not match the documented format."""


@dataclass(frozen=True)
class FileIdentity:
    subject_id: str
    action_id: int


@dataclass
class PostureDataset:
    frames: np.ndarray
    labels: np.ndarray
    subjects: np.ndarray
    actions: np.ndarray
    frame_numbers: np.ndarray
    source_files: np.ndarray

    def __len__(self) -> int:
        return int(self.labels.size)


def parse_file_identity(path: str | Path) -> FileIdentity:
    """Parse ``participant + action number`` from a text filename."""

    stem = Path(path).stem.strip()
    separated = re.fullmatch(r"(.+?)[_\-\s]+(\d{1,2})", stem)
    if separated:
        subject = separated.group(1).strip(" _-")
        action = int(separated.group(2))
        if subject and 0 <= action <= 22:
            return FileIdentity(subject, action)

    for action in sorted(range(23), key=lambda value: (-len(str(value)), value)):
        suffix = str(action)
        if not stem.endswith(suffix):
            continue
        subject = stem[: -len(suffix)].strip(" _-")
        if subject:
            return FileIdentity(subject, action)

    raise DatasetFormatError(
        f"Cannot infer participant and action (0-22) from filename: {Path(path).name}"
    )


def iter_pressure_frames(
    path: str | Path,
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
) -> Iterator[np.ndarray]:
    """Yield validated pressure frames from one raw text file."""

    source = Path(path)
    expected_rows, expected_columns = matrix_shape
    buffered_rows: list[list[float]] = []
    frame_number = 0

    def finish_frame(line_number: int) -> np.ndarray:
        nonlocal buffered_rows, frame_number
        if len(buffered_rows) != expected_rows:
            raise DatasetFormatError(
                f"{source}:{line_number}: frame {frame_number} has "
                f"{len(buffered_rows)} rows; expected {expected_rows}."
            )
        frame = np.asarray(buffered_rows, dtype=np.float32)
        buffered_rows = []
        if frame.shape != matrix_shape or not np.isfinite(frame).all():
            raise DatasetFormatError(
                f"{source}: frame {frame_number} contains an invalid shape or "
                "non-finite values."
            )
        frame_number += 1
        return frame

    try:
        with source.open("r", encoding="utf-8-sig") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    if buffered_rows:
                        yield finish_frame(line_number)
                    continue

                values = [part.strip() for part in stripped.rstrip(",").split(",")]
                if len(values) != expected_columns:
                    raise DatasetFormatError(
                        f"{source}:{line_number}: found {len(values)} columns; "
                        f"expected {expected_columns}."
                    )
                try:
                    row = [float(value) for value in values]
                except ValueError as exc:
                    raise DatasetFormatError(
                        f"{source}:{line_number}: row contains a non-numeric value."
                    ) from exc
                buffered_rows.append(row)
                if len(buffered_rows) == expected_rows:
                    yield finish_frame(line_number)
    except UnicodeDecodeError as exc:
        raise DatasetFormatError(f"{source}: file is not UTF-8 text.") from exc

    if buffered_rows:
        yield finish_frame(line_number if "line_number" in locals() else 0)
    if frame_number == 0:
        raise DatasetFormatError(f"{source}: no pressure frames were found.")


def discover_static_posture_files(
    dataset_dir: str | Path,
) -> list[tuple[Path, FileIdentity]]:
    """Return all static-posture text files in deterministic order."""

    root = Path(dataset_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {root}")

    discovered: list[tuple[Path, FileIdentity]] = []
    unrecognized: list[Path] = []
    for path in sorted(root.rglob("*.txt"), key=lambda item: str(item).lower()):
        try:
            identity = parse_file_identity(path)
        except DatasetFormatError:
            unrecognized.append(path)
            continue
        if identity.action_id in ACTION_TO_LABEL:
            discovered.append((path, identity))

    if not discovered:
        note = (
            f" ({len(unrecognized)} unrelated .txt files were ignored)"
            if unrecognized
            else ""
        )
        raise FileNotFoundError(
            "No static posture files named as participant+action were found "
            f"in {root}{note}."
        )
    return discovered


def load_posture_dataset(
    dataset_dir: str | Path,
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
    max_frames_per_file: int | None = None,
) -> PostureDataset:
    """Load all static-posture frames into arrays suitable for algorithms."""

    if max_frames_per_file is not None and max_frames_per_file <= 0:
        raise ValueError("max_frames_per_file must be positive or None.")

    frames: list[np.ndarray] = []
    labels: list[int] = []
    subjects: list[str] = []
    actions: list[int] = []
    frame_numbers: list[int] = []
    source_files: list[str] = []

    root = Path(dataset_dir).resolve()
    for path, identity in discover_static_posture_files(root):
        for frame_number, frame in enumerate(iter_pressure_frames(path, matrix_shape)):
            if max_frames_per_file is not None and frame_number >= max_frames_per_file:
                break
            frames.append(frame)
            labels.append(action_to_label(identity.action_id))
            subjects.append(identity.subject_id)
            actions.append(identity.action_id)
            frame_numbers.append(frame_number)
            try:
                source_files.append(str(path.resolve().relative_to(root)))
            except ValueError:
                source_files.append(str(path.resolve()))

    if not frames:
        raise DatasetFormatError("Static posture files were found, but no frames were loaded.")

    return PostureDataset(
        frames=np.stack(frames).astype(np.float32, copy=False),
        labels=np.asarray(labels, dtype=np.int64),
        subjects=np.asarray(subjects, dtype=str),
        actions=np.asarray(actions, dtype=np.int64),
        frame_numbers=np.asarray(frame_numbers, dtype=np.int64),
        source_files=np.asarray(source_files, dtype=str),
    )


def validate_subject_coverage(
    dataset: PostureDataset,
    expected_labels: Sequence[int],
) -> None:
    """Ensure every participant contains every class required by group splitting."""

    expected = set(int(label) for label in expected_labels)
    failures: list[str] = []
    for subject in np.unique(dataset.subjects):
        actual = set(dataset.labels[dataset.subjects == subject].tolist())
        if actual != expected:
            failures.append(f"{subject}: labels={sorted(actual)}")
    if failures:
        details = "; ".join(failures[:10])
        raise DatasetFormatError(
            "Each participant must contain all required postures for a reliable "
            f"participant-level split. Invalid participants: {details}"
        )
