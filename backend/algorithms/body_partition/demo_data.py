"""Lazy in-memory access to the annotated dataset for the demo frontend.

The training pipeline keeps its own loader under ``train/``; this read-only
variant lives in the backend so the HTTP API can browse annotated samples
(participant / action / frame) without importing training code.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

from backend.data_utils.contracts import MATRIX_SHAPE

from .partition import parse_region_field, rects_to_mask


class AnnotatedSampleStore:
    """Parse the annotated JSON once, then serve frames/masks by key."""

    def __init__(self, dataset_path: str | Path) -> None:
        self.dataset_path = Path(dataset_path)
        self._frames: np.ndarray | None = None
        self._masks: np.ndarray | None = None
        self._subjects: np.ndarray | None = None
        self._actions: np.ndarray | None = None
        self._sleep_positions: np.ndarray | None = None
        self._frame_numbers: np.ndarray | None = None
        self._lock = Lock()

    @property
    def is_available(self) -> bool:
        return self.dataset_path.is_file()

    def _ensure_loaded(self) -> None:
        if self._frames is not None:
            return
        with self._lock:
            if self._frames is not None:
                return
            if not self.dataset_path.is_file():
                raise FileNotFoundError(
                    f"Annotated dataset was not found at {self.dataset_path}."
                )
            with self.dataset_path.open("r", encoding="utf-8") as handle:
                records = json.load(handle)
            rows, columns = MATRIX_SHAPE
            frames: list[np.ndarray] = []
            masks: list[np.ndarray] = []
            subjects: list[str] = []
            actions: list[int] = []
            positions: list[int] = []
            numbers: list[int] = []
            for index, record in enumerate(records):
                values = [
                    float(token) for token in str(record["data"]).split(",") if token.strip()
                ]
                if len(values) != rows * columns:
                    raise ValueError(
                        f"Record {index} has {len(values)} pressure values; "
                        f"expected {rows * columns}."
                    )
                frames.append(np.asarray(values, dtype=np.float32).reshape(MATRIX_SHAPE))
                masks.append(rects_to_mask(parse_region_field(record["region"])))
                subjects.append(str(record["people_name"]))
                actions.append(int(record["action"]))
                positions.append(int(record["sleep_pos"]))
                numbers.append(int(record["frame"]))
            self._frames = np.stack(frames)
            self._masks = np.stack(masks)
            self._subjects = np.asarray(subjects)
            self._actions = np.asarray(actions, dtype=np.int64)
            self._sleep_positions = np.asarray(positions, dtype=np.int64)
            self._frame_numbers = np.asarray(numbers, dtype=np.int64)

    def catalog(self) -> dict[str, Any]:
        """Subject -> action -> frame count overview for the frontend."""

        self._ensure_loaded()
        catalog: dict[str, Any] = {}
        for subject in sorted(np.unique(self._subjects).tolist()):
            selector = self._subjects == subject
            actions: dict[str, Any] = {}
            for action in sorted(np.unique(self._actions[selector]).tolist()):
                action_selector = selector & (self._actions == action)
                actions[str(action)] = {
                    "frames": int(action_selector.sum()),
                    "sleep_pos": int(self._sleep_positions[action_selector][0]),
                }
            catalog[subject] = actions
        return catalog

    def sample(self, subject: str, action: int, frame_number: int) -> dict[str, Any]:
        """One annotated frame with its ground-truth mask."""

        self._ensure_loaded()
        selector = (
            (self._subjects == subject)
            & (self._actions == action)
            & (self._frame_numbers == frame_number)
        )
        matches = np.flatnonzero(selector)
        if matches.size == 0:
            raise KeyError(
                f"No annotated sample for subject={subject!r}, action={action}, "
                f"frame={frame_number}."
            )
        index = int(matches[0])
        return {
            "subject": subject,
            "action": action,
            "frame": frame_number,
            "sleep_pos": int(self._sleep_positions[index]),
            "pressure_matrix": self._frames[index].tolist(),
            "ground_truth_mask": self._masks[index].astype(int).tolist(),
        }
