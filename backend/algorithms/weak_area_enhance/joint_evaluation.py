"""Joint-annotation utilities for evaluating weak-pressure enhancement.

The annotations are used only for offline evaluation and visualisation.  The
real-time :func:`enhance_pressure` API deliberately remains pressure-only.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

import numpy as np


JOINT_NAMES = (
    "head",
    "neck",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)

# Connections follow the 14-point order documented with the dataset.
SKELETON_EDGES = (
    (0, 1),
    (1, 2),
    (1, 3),
    (2, 4),
    (4, 6),
    (3, 5),
    (5, 7),
    (2, 8),
    (3, 9),
    (8, 9),
    (8, 10),
    (10, 12),
    (9, 11),
    (11, 13),
)
LEG_EDGES = ((8, 10), (10, 12), (9, 11), (11, 13))
TORSO_EDGES = ((1, 2), (1, 3), (2, 8), (3, 9), (8, 9))

Point = tuple[float, float]


@dataclass(frozen=True)
class JointAnnotatedFrame:
    """One pressure frame and its optional 14 joint coordinates."""

    folder: str
    action: int
    frame: int
    occurrence: int
    pressure: np.ndarray
    keypoints: tuple[Point | None, ...]


def _normalise_keypoints(
    keypoints: Sequence[Sequence[float] | None],
    state: Sequence[int] | None,
    rows: int,
    cols: int,
) -> tuple[Point | None, ...]:
    if len(keypoints) != len(JOINT_NAMES):
        raise ValueError(f"expected {len(JOINT_NAMES)} keypoints, got {len(keypoints)}")
    if state is not None and len(state) != len(JOINT_NAMES):
        raise ValueError(f"expected {len(JOINT_NAMES)} state values, got {len(state)}")

    result: list[Point | None] = []
    for index, point in enumerate(keypoints):
        if point is None or (state is not None and int(state[index]) == 1):
            result.append(None)
            continue
        if len(point) != 2:
            raise ValueError(f"keypoint {index} must contain x and y")
        # A few annotations lie exactly on x=24/y=44, the outer plotting
        # boundary of a 24x44 frame.  Clamp them to the nearest sensor cell.
        x = float(np.clip(float(point[0]), 0.0, cols - 1.0))
        y = float(np.clip(float(point[1]), 0.0, rows - 1.0))
        result.append((x, y))
    return tuple(result)


def load_joint_record(
    path: str | Path,
    folder: str,
    action: int,
    frame: int,
    occurrence: int = 0,
    rows: int = 44,
    cols: int = 24,
) -> JointAnnotatedFrame:
    """Load one annotated JSON record.

    Most ``folder/action/frame`` keys occur twice because the supplied dataset
    includes an augmented counterpart.  ``occurrence`` selects which matching
    record to use, starting at zero.
    """

    if occurrence < 0:
        raise ValueError("occurrence cannot be negative")
    with Path(path).open("r", encoding="utf-8-sig") as stream:
        records = json.load(stream)

    matched = 0
    for record in records:
        if (
            str(record.get("folder", "")).casefold() != folder.casefold()
            or int(record.get("action", -1)) != action
            or int(record.get("frame", -1)) != frame
        ):
            continue
        if matched != occurrence:
            matched += 1
            continue

        raw_data = record.get("data")
        if isinstance(raw_data, str):
            values = np.fromstring(raw_data, sep=",", dtype=np.float32)
        else:
            values = np.asarray(raw_data, dtype=np.float32).reshape(-1)
        expected = rows * cols
        if values.size != expected:
            raise ValueError(
                f"record contains {values.size} pressure values; expected {expected}"
            )
        keypoints = _normalise_keypoints(
            record.get("kpts", ()), record.get("state"), rows, cols
        )
        return JointAnnotatedFrame(
            folder=str(record["folder"]),
            action=action,
            frame=frame,
            occurrence=occurrence,
            pressure=values.reshape(rows, cols),
            keypoints=keypoints,
        )

    raise LookupError(
        f"no joint record for folder={folder!r}, action={action}, "
        f"frame={frame}, occurrence={occurrence}"
    )


def _segment_mask(
    shape: tuple[int, int],
    start: Point,
    end: Point,
    radius: float,
) -> np.ndarray:
    """Return cells within ``radius`` of a line segment."""

    yy, xx = np.indices(shape, dtype=np.float64)
    ax, ay = start
    bx, by = end
    dx = bx - ax
    dy = by - ay
    denominator = dx * dx + dy * dy
    if denominator <= np.finfo(np.float64).eps:
        distance_sq = (xx - ax) ** 2 + (yy - ay) ** 2
    else:
        projection = np.clip(((xx - ax) * dx + (yy - ay) * dy) / denominator, 0, 1)
        nearest_x = ax + projection * dx
        nearest_y = ay + projection * dy
        distance_sq = (xx - nearest_x) ** 2 + (yy - nearest_y) ** 2
    return distance_sq <= radius * radius


def skeleton_mask(
    shape: tuple[int, int],
    keypoints: Sequence[Point | None],
    limb_radius: float = 2.5,
    torso_radius: float = 4.0,
) -> np.ndarray:
    """Build a conservative anatomical corridor around the labelled body."""

    if len(keypoints) != len(JOINT_NAMES):
        raise ValueError(f"expected {len(JOINT_NAMES)} keypoints")
    mask = np.zeros(shape, dtype=bool)
    for edge in SKELETON_EDGES:
        start = keypoints[edge[0]]
        end = keypoints[edge[1]]
        if start is None or end is None:
            continue
        radius = torso_radius if edge in TORSO_EDGES else limb_radius
        mask |= _segment_mask(shape, start, end, radius)
    return mask


def _edges_mask(
    shape: tuple[int, int],
    keypoints: Sequence[Point | None],
    edges: Sequence[tuple[int, int]],
    radius: float,
) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    for first, second in edges:
        if keypoints[first] is not None and keypoints[second] is not None:
            result |= _segment_mask(
                shape, keypoints[first], keypoints[second], radius  # type: ignore[arg-type]
            )
    return result


def joint_guided_metrics(
    original: np.ndarray,
    enhanced: np.ndarray,
    keypoints: Sequence[Point | None],
) -> dict[str, float]:
    """Measure enhancement placement and leg continuity using annotations."""

    before = np.asarray(original, dtype=np.float64)
    after = np.asarray(enhanced, dtype=np.float64)
    if before.shape != after.shape or before.ndim != 2:
        raise ValueError("original and enhanced must be same-shaped 2D matrices")

    anatomy = skeleton_mask(before.shape, keypoints)
    legs = _edges_mask(before.shape, keypoints, LEG_EDGES, radius=1.25)
    torso = _edges_mask(before.shape, keypoints, TORSO_EDGES, radius=3.0)
    added = np.maximum(after - before, 0.0)
    total_added = float(added.sum())
    outside_added = float(added[~anatomy].sum())

    positive = before[before > 0]
    scale = float(np.percentile(positive, 99.5)) if positive.size else 1.0
    visible_threshold = 0.04 * max(scale, 1e-6)
    weak = (before >= 0.015 * scale) & (before <= 0.35 * scale)

    def gain(mask: np.ndarray) -> float:
        selected = mask & weak
        if not selected.any():
            return 1.0
        before_mean = float(before[selected].mean())
        after_mean = float(after[selected].mean())
        return after_mean / max(before_mean, 1e-6)

    def continuity(values: np.ndarray) -> float:
        return float(np.mean(values[legs] >= visible_threshold)) if legs.any() else 0.0

    return {
        "anatomy_added_ratio": (
            float(added[anatomy].sum()) / total_added if total_added > 0 else 1.0
        ),
        "outside_added_ratio": outside_added / total_added if total_added > 0 else 0.0,
        "torso_weak_gain_ratio": gain(torso),
        "leg_weak_gain_ratio": gain(legs),
        "leg_continuity_before": continuity(before),
        "leg_continuity_after": continuity(after),
    }
