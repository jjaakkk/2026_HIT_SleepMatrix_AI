"""不依赖 sklearn 的分类指标计算。"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

import numpy as np


def confusion_matrix(
    targets: Sequence[int], predictions: Sequence[int], num_classes: int
) -> np.ndarray:
    matrix = np.zeros((num_classes, num_classes), dtype=np.int64)
    for target, prediction in zip(targets, predictions, strict=True):
        matrix[int(target), int(prediction)] += 1
    return matrix


def metrics_from_confusion(matrix: np.ndarray) -> dict:
    matrix = np.asarray(matrix, dtype=np.int64)
    true_positive = np.diag(matrix).astype(np.float64)
    predicted = matrix.sum(axis=0).astype(np.float64)
    actual = matrix.sum(axis=1).astype(np.float64)
    precision = np.divide(
        true_positive,
        predicted,
        out=np.zeros_like(true_positive),
        where=predicted != 0,
    )
    recall = np.divide(
        true_positive,
        actual,
        out=np.zeros_like(true_positive),
        where=actual != 0,
    )
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) != 0,
    )
    total = matrix.sum()
    return {
        "accuracy": float(true_positive.sum() / total) if total else 0.0,
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "per_class_precision": precision.tolist(),
        "per_class_recall": recall.tolist(),
        "per_class_f1": f1.tolist(),
        "support": actual.astype(int).tolist(),
        "confusion_matrix": matrix.tolist(),
    }

def classification_metrics(
    targets: Sequence[int], predictions: Sequence[int], num_classes: int
) -> dict:
    return metrics_from_confusion(confusion_matrix(targets, predictions, num_classes))


def per_subject_accuracy(
    subjects: Iterable[str], targets: Iterable[int], predictions: Iterable[int]
) -> dict[str, dict[str, float | int]]:
    totals: dict[str, int] = defaultdict(int)
    correct: dict[str, int] = defaultdict(int)
    for subject, target, prediction in zip(subjects, targets, predictions, strict=True):
        totals[subject] += 1
        correct[subject] += int(target == prediction)
    return {
        subject: {
            "correct": correct[subject],
            "total": totals[subject],
            "accuracy": correct[subject] / totals[subject],
        }
        for subject in sorted(totals, key=str.casefold)
    }
