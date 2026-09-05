"""Region-label parsing, mask conversion and partition metrics.

The annotated dataset marks five body regions (shoulder, back, waist, hip,
thigh) as axis-aligned rectangles on the 44x24 pressure matrix. A sixth calf
rectangle exists for only three participants and is intentionally ignored, as
documented in the dataset manual. This module converts between rectangle
annotations and per-pixel segmentation masks, and implements the metrics used
for both the random 70/30 validation and the held-out-participant evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from backend.data_utils.contracts import MATRIX_SHAPE

NUM_CLASSES = 6  # background + five body regions
BACKGROUND_CLASS = 0
REGION_KEYS = ("shoulder", "back", "waist", "hip", "thigh")
REGION_NAMES_ZH = ("肩部", "背部", "腰部", "臀部", "大腿部")
REGION_CLASS_IDS = tuple(range(1, NUM_CLASSES))
NUM_REGION_FIELDS = 12  # x pairs + y pairs for six documented rectangles


class RegionFormatError(ValueError):
    """Raised when an annotated region string cannot be parsed."""


@dataclass(frozen=True)
class RegionRect:
    """Axis-aligned rectangle [x1, x2) x [y1, y2) for one body region."""

    key: str
    name_zh: str
    class_id: int
    x1: int
    x2: int
    y1: int
    y2: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name_zh": self.name_zh,
            "class_id": self.class_id,
            "x1": self.x1,
            "x2": self.x2,
            "y1": self.y1,
            "y2": self.y2,
        }


def parse_region_field(region: str) -> list[tuple[int, int, int, int] | None]:
    """Parse the documented ``x1 x2 ... x12 y1 ... y12`` region string.

    Returns six ``(x1, x2, y1, y2)`` rectangles in the documented order
    (shoulder, back, waist, hip, thigh, calf). The calf entry is ``None`` for
    participants without calf annotations (``na`` tokens).
    """

    tokens = str(region).split()
    if len(tokens) != 2 * NUM_REGION_FIELDS:
        raise RegionFormatError(
            f"Region field must contain {2 * NUM_REGION_FIELDS} tokens; "
            f"received {len(tokens)}."
        )
    xs = tokens[:NUM_REGION_FIELDS]
    ys = tokens[NUM_REGION_FIELDS:]

    rects: list[tuple[int, int, int, int] | None] = []
    for index in range(0, NUM_REGION_FIELDS, 2):
        pair = xs[index : index + 2] + ys[index : index + 2]
        if any(token == "na" for token in pair):
            if pair.count("na") != len(pair):
                raise RegionFormatError(f"Partially missing rectangle in region: {pair}")
            rects.append(None)
            continue
        x1, x2, y1, y2 = (int(float(token)) for token in pair)
        rows, columns = MATRIX_SHAPE
        if not (0 <= x1 < x2 <= columns and 0 <= y1 < y2 <= rows):
            raise RegionFormatError(
                f"Rectangle {(x1, x2, y1, y2)} lies outside the {rows}x{columns} matrix."
            )
        rects.append((x1, x2, y1, y2))
    return rects


def rects_to_mask(
    rects: Sequence[tuple[int, int, int, int] | None],
    matrix_shape: tuple[int, int] = MATRIX_SHAPE,
) -> np.ndarray:
    """Paint the first five rectangles into a uint8 segmentation mask.

    Class ids follow ``REGION_CLASS_IDS``; pixels outside every rectangle stay
    background. Any calf rectangle is ignored by design.
    """

    if len(rects) < len(REGION_CLASS_IDS):
        raise ValueError(f"Expected at least {len(REGION_CLASS_IDS)} rectangles.")
    mask = np.zeros(matrix_shape, dtype=np.uint8)
    for class_id, rect in zip(REGION_CLASS_IDS, rects):
        if rect is None:
            continue
        x1, x2, y1, y2 = rect
        mask[y1:y2, x1:x2] = class_id
    return mask


def mask_to_rects(mask: np.ndarray) -> list[RegionRect | None]:
    """Recover one bounding rectangle per body region from a predicted mask."""

    array = np.asarray(mask)
    if array.shape != MATRIX_SHAPE:
        raise ValueError(f"mask must have shape {MATRIX_SHAPE}; received {array.shape}.")
    rects: list[RegionRect | None] = []
    for class_id, key, name_zh in zip(REGION_CLASS_IDS, REGION_KEYS, REGION_NAMES_ZH):
        rows, columns = np.where(array == class_id)
        if rows.size == 0:
            rects.append(None)
            continue
        rects.append(
            RegionRect(
                key=key,
                name_zh=name_zh,
                class_id=class_id,
                x1=int(columns.min()),
                x2=int(columns.max()) + 1,
                y1=int(rows.min()),
                y2=int(rows.max()) + 1,
            )
        )
    return rects


def pixel_accuracy(prediction: np.ndarray, target: np.ndarray) -> float:
    """Overall per-pixel accuracy, the headline metric of this task."""

    pred = np.asarray(prediction)
    truth = np.asarray(target)
    if pred.shape != truth.shape:
        raise ValueError("prediction and target must share the same shape.")
    return float((pred == truth).mean())


def per_class_iou(
    prediction: np.ndarray,
    target: np.ndarray,
    num_classes: int = NUM_CLASSES,
) -> list[float | None]:
    """IoU per class; ``None`` when the class is absent from both inputs."""

    pred = np.asarray(prediction)
    truth = np.asarray(target)
    scores: list[float | None] = []
    for class_id in range(num_classes):
        pred_mask = pred == class_id
        true_mask = truth == class_id
        union = np.logical_or(pred_mask, true_mask).sum()
        if union == 0:
            scores.append(None)
            continue
        intersection = np.logical_and(pred_mask, true_mask).sum()
        scores.append(float(intersection / union))
    return scores


def mean_iou(
    prediction: np.ndarray,
    target: np.ndarray,
    num_classes: int = NUM_CLASSES,
) -> float:
    """Mean IoU over the classes present in the batch."""

    scores = [score for score in per_class_iou(prediction, target, num_classes) if score is not None]
    return float(np.mean(scores)) if scores else 1.0


def rect_iou(rect_a: tuple[int, int, int, int], rect_b: tuple[int, int, int, int]) -> float:
    """IoU between two ``(x1, x2, y1, y2)`` rectangles."""

    ax1, ax2, ay1, ay2 = rect_a
    bx1, bx2, by1, by2 = rect_b
    inter_x = max(0, min(ax2, bx2) - max(ax1, bx1))
    inter_y = max(0, min(ay2, by2) - max(ay1, by1))
    intersection = inter_x * inter_y
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - intersection
    return float(intersection / union) if union else 0.0


def region_rect_metrics(
    prediction: np.ndarray,
    target: np.ndarray,
) -> dict[str, float]:
    """Compare rectangles recovered from two masks.

    Reports the mean rectangle IoU and the mean absolute error of the vertical
    band boundaries (in sensor rows), both averaged over the regions present
    in the ground-truth mask.
    """

    pred_rects = mask_to_rects(prediction)
    true_rects = mask_to_rects(target)
    ious: list[float] = []
    boundary_errors: list[float] = []
    for pred_rect, true_rect in zip(pred_rects, true_rects):
        if true_rect is None:
            continue
        if pred_rect is None:
            ious.append(0.0)
            boundary_errors.append(float(MATRIX_SHAPE[0]))
            continue
        ious.append(rect_iou(pred_rect_bounds(pred_rect), pred_rect_bounds(true_rect)))
        boundary_errors.append(
            (abs(pred_rect.y1 - true_rect.y1) + abs(pred_rect.y2 - true_rect.y2)) / 2.0
        )
    return {
        "mean_rect_iou": float(np.mean(ious)) if ious else 0.0,
        "mean_boundary_mae": float(np.mean(boundary_errors)) if boundary_errors else 0.0,
    }


def pred_rect_bounds(rect: RegionRect) -> tuple[int, int, int, int]:
    """Return ``(x1, x2, y1, y2)`` for one :class:`RegionRect`."""

    return rect.x1, rect.x2, rect.y1, rect.y2
