"""Load and validate the language-neutral pressure/posture contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PROJECT_ROOT / "shared" / "contracts" / "posture.json"


class ContractError(ValueError):
    """Raised when a shared data contract is missing or inconsistent."""


def _read_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Shared posture contract was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Shared posture contract is not valid JSON: {path}") from exc
    if not isinstance(document, dict):
        raise ContractError("Shared posture contract root must be a JSON object.")
    return document


def _positive_integer(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ContractError(f"Contract field {field} must be a positive integer.")
    return value


def _build_contract_values(document: dict[str, Any]) -> dict[str, Any]:
    contract_version = document.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version:
        raise ContractError("Contract field contract_version must be a non-empty string.")
    try:
        matrix = document["pressure_matrix"]
        posture_records = document["postures"]
        mirror_pairs = document["mirrored_action_pairs"]
    except KeyError as exc:
        raise ContractError(f"Shared posture contract is missing field {exc.args[0]!r}.") from exc

    if not isinstance(matrix, dict):
        raise ContractError("Contract field pressure_matrix must be an object.")
    matrix_shape = (
        _positive_integer(matrix.get("rows"), "pressure_matrix.rows"),
        _positive_integer(matrix.get("columns"), "pressure_matrix.columns"),
    )
    if matrix.get("index_order") != "row_column":
        raise ContractError("Only matrix[row][column] ordering is currently supported.")
    if not isinstance(posture_records, list) or not posture_records:
        raise ContractError("Contract field postures must be a non-empty array.")

    label_id_to_name: dict[int, str] = {}
    label_id_to_name_zh: dict[int, str] = {}
    action_to_label: dict[int, int] = {}
    mirrored_label: dict[int, int] = {}
    for record in posture_records:
        if not isinstance(record, dict):
            raise ContractError("Every posture entry must be an object.")
        label_id = record.get("id")
        name = record.get("key")
        name_zh = record.get("name_zh")
        actions = record.get("actions")
        mirrored_label_id = record.get("mirrored_label_id")
        if not isinstance(label_id, int) or isinstance(label_id, bool) or label_id < 0:
            raise ContractError("Every posture ID must be a non-negative integer.")
        if label_id in label_id_to_name:
            raise ContractError(f"Duplicate posture ID in contract: {label_id}")
        if not isinstance(name, str) or not name or not isinstance(name_zh, str) or not name_zh:
            raise ContractError(f"Posture {label_id} must have non-empty names.")
        if not isinstance(actions, list) or not actions:
            raise ContractError(f"Posture {label_id} must contain action IDs.")
        if not isinstance(mirrored_label_id, int) or isinstance(mirrored_label_id, bool):
            raise ContractError(f"Posture {label_id} has an invalid mirrored label ID.")

        label_id_to_name[label_id] = name
        label_id_to_name_zh[label_id] = name_zh
        mirrored_label[label_id] = mirrored_label_id
        for action in actions:
            if not isinstance(action, int) or isinstance(action, bool) or action < 0:
                raise ContractError(f"Posture {label_id} contains an invalid action ID.")
            if action in action_to_label:
                raise ContractError(f"Action {action} is assigned to multiple postures.")
            action_to_label[action] = label_id

    label_ids = set(label_id_to_name)
    if set(mirrored_label.values()) != label_ids:
        raise ContractError("Mirrored posture IDs must reference the defined posture IDs.")
    for label_id, mirror_id in mirrored_label.items():
        if mirrored_label.get(mirror_id) != label_id:
            raise ContractError("Mirrored posture mapping must be symmetric.")

    mirrored_action = {action: action for action in action_to_label}
    if not isinstance(mirror_pairs, list):
        raise ContractError("Contract field mirrored_action_pairs must be an array.")
    for pair in mirror_pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ContractError("Every mirrored action pair must contain two action IDs.")
        left, right = pair
        if left not in action_to_label or right not in action_to_label:
            raise ContractError("Mirrored action pair references an undefined action ID.")
        mirrored_action[left] = right
        mirrored_action[right] = left

    for action, mirror_action in mirrored_action.items():
        source_label = action_to_label[action]
        target_label = action_to_label[mirror_action]
        if target_label != mirrored_label[source_label]:
            raise ContractError(
                f"Mirrored action {action}->{mirror_action} conflicts with posture mapping."
            )

    return {
        "contract_version": contract_version,
        "matrix_shape": matrix_shape,
        "label_id_to_name": label_id_to_name,
        "label_id_to_name_zh": label_id_to_name_zh,
        "action_to_label": action_to_label,
        "mirrored_label": mirrored_label,
        "mirrored_action": mirrored_action,
    }


CONTRACT = _read_contract()
_VALUES = _build_contract_values(CONTRACT)
CONTRACT_VERSION: str = _VALUES["contract_version"]
MATRIX_SHAPE: tuple[int, int] = _VALUES["matrix_shape"]
LABEL_ID_TO_NAME: dict[int, str] = _VALUES["label_id_to_name"]
LABEL_ID_TO_NAME_ZH: dict[int, str] = _VALUES["label_id_to_name_zh"]
LABEL_NAME_TO_ID = {name: label_id for label_id, name in LABEL_ID_TO_NAME.items()}
ACTION_TO_LABEL: dict[int, int] = _VALUES["action_to_label"]
MIRRORED_LABEL: dict[int, int] = _VALUES["mirrored_label"]
MIRRORED_ACTION: dict[int, int] = _VALUES["mirrored_action"]


def action_to_label(action: int) -> int:
    """Return the static-posture label ID for an action from the contract."""

    try:
        return ACTION_TO_LABEL[action]
    except KeyError as exc:
        raise ValueError(
            f"Action {action} is not a static posture action "
            f"(expected one of {sorted(ACTION_TO_LABEL)})."
        ) from exc
