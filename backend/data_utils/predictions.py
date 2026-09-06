"""Shared posture-prediction payload structures for all algorithms.

Both posture models (SVM and CNN) return the same :class:`PosturePrediction`
shape, so the HTTP layer and the frontend consume one stable contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .contracts import LABEL_ID_TO_NAME, LABEL_ID_TO_NAME_ZH, LABEL_NAME_TO_ID


@dataclass(frozen=True)
class PosturePrediction:
    """Language-neutral posture classification result for one frame."""

    label_id: int
    label: str
    label_zh: str
    confidence: float
    probabilities: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def merged_prediction(
    probability_maps: list[dict[str, float]],
) -> PosturePrediction:
    """Average one probability map per model and pick the best posture.

    Maps must use contract label keys (English names, e.g. ``supine``).
    Raises :class:`ValueError` when the list is empty, the maps share no
    keys, or a winning key is not defined by the posture contract.
    """

    if not probability_maps:
        raise ValueError("At least one probability map is required.")
    shared_keys = set(probability_maps[0])
    for probabilities in probability_maps[1:]:
        shared_keys &= set(probabilities)
    if not shared_keys:
        raise ValueError("Probability maps share no label keys.")
    for probabilities in probability_maps:
        for key in shared_keys:
            value = probabilities.get(key)
            if value is None:
                raise ValueError(f"Probability map is missing label {key!r}.")

    merged = {
        key: sum(float(probabilities[key]) for probabilities in probability_maps)
        / len(probability_maps)
        for key in sorted(shared_keys, key=lambda key: LABEL_NAME_TO_ID.get(key, 10**9))
    }
    best_label = max(merged, key=merged.get)
    label_id = LABEL_NAME_TO_ID.get(best_label)
    if label_id is None:
        raise ValueError(f"Predicted label {best_label!r} is not in the posture contract.")
    return PosturePrediction(
        label_id=label_id,
        label=LABEL_ID_TO_NAME[label_id],
        label_zh=LABEL_ID_TO_NAME_ZH[label_id],
        confidence=float(merged[best_label]),
        probabilities={key: float(value) for key, value in merged.items()},
    )
