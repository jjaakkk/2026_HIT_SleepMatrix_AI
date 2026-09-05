"""压力数据读取、标签映射、数据发现和完整性检查。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_CANDIDATES = (
    PROJECT_ROOT / "dataset" / "睡姿 区域划分data" / "睡姿数据",
    PROJECT_ROOT
    / "dataset"
    / "睡姿 区域划分data"
    / "睡姿 区域划分data"
    / "睡姿数据",
    PROJECT_ROOT / "睡姿 区域划分data" / "睡姿 区域划分data" / "睡姿数据",
)
DEFAULT_DATA_DIR = next(
    (candidate for candidate in DATA_DIR_CANDIDATES if candidate.is_dir()),
    DATA_DIR_CANDIDATES[0],
)

FRAME_ROWS = 44
FRAME_COLS = 24
LABEL_NAMES = ("仰卧", "俯卧", "左侧卧", "右侧卧")
ACTION_PATTERN = re.compile(r"_(\d+)\.txt$", re.IGNORECASE)


@dataclass(frozen=True)
class FrameRecord:
    """一帧静态压力数据的索引信息。"""

    path: str
    subject: str
    action: int
    label: int
    frame_index: int

    def to_dict(self) -> dict:
        return asdict(self)


def action_to_label(action: int) -> int:
    """把动作编号 1-21 映射为四类睡姿标签。"""

    if 1 <= action <= 6:
        return 0
    if 7 <= action <= 9:
        return 1
    if 10 <= action <= 15:
        return 2
    if 16 <= action <= 21:
        return 3
    raise ValueError(f"动作编号必须位于 1-21，收到：{action}")


def action_from_filename(path: str | Path) -> int | None:
    """从类似 dgs_10.txt 的文件名中解析动作编号。"""

    match = ACTION_PATTERN.search(Path(path).name)
    if match is None:
        return None
    action = int(match.group(1))
    return action if 1 <= action <= 21 else None


def read_pressure_frames(path: str | Path) -> np.ndarray:
    """读取静态压力文件，返回形状为 (N, 44, 24) 的 float32 数组。

    数据集镜像拼接处有时缺少空行，因此不能只按空行分帧。本函数忽略
    空行后严格按照每 44 个非空行切分，并校验每行恰好有 24 个数。
    """

    source = Path(path)
    rows: list[list[float]] = []

    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = source.read_text(encoding="gb18030")

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != FRAME_COLS:
            raise ValueError(
                f"{source} 第 {line_number} 行应有 {FRAME_COLS} 列，"
                f"实际为 {len(parts)} 列"
            )
        try:
            row = [float(value) for value in parts]
        except ValueError as exc:
            raise ValueError(f"{source} 第 {line_number} 行含非数值内容") from exc
        rows.append(row)

    if not rows:
        raise ValueError(f"静态压力文件为空：{source}")
    if len(rows) % FRAME_ROWS != 0:
        raise ValueError(
            f"{source} 有 {len(rows)} 个非空数据行，不能按每帧 "
            f"{FRAME_ROWS} 行完整切分"
        )

    frames = np.asarray(rows, dtype=np.float32).reshape(-1, FRAME_ROWS, FRAME_COLS)
    if not np.isfinite(frames).all():
        raise ValueError(f"{source} 含 NaN 或无穷大")
    return frames


def list_subjects(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[str]:
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"找不到睡姿数据目录：{root}")
    return sorted(
        (path.name for path in root.iterdir() if path.is_dir()),
        key=str.casefold,
    )


def list_static_files(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    subjects: Iterable[str] | None = None,
) -> list[Path]:
    """列出动作编号 1-21 的静态文件，自动排除动态和空载文件。"""

    root = Path(data_dir)
    selected = set(subjects) if subjects is not None else None
    files: list[Path] = []
    for subject_dir in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if not subject_dir.is_dir():
            continue
        if selected is not None and subject_dir.name not in selected:
            continue
        for path in sorted(subject_dir.glob("*.txt"), key=lambda p: p.name.casefold()):
            if action_from_filename(path) is not None:
                files.append(path)
    return files


def discover_frame_records(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    subjects: Iterable[str] | None = None,
) -> list[FrameRecord]:
    """扫描静态文件并为每一帧建立索引。"""

    records: list[FrameRecord] = []
    for path in list_static_files(data_dir, subjects):
        action = action_from_filename(path)
        assert action is not None
        frames = read_pressure_frames(path)
        label = action_to_label(action)
        for frame_index in range(len(frames)):
            records.append(
                FrameRecord(
                    path=str(path.resolve()),
                    subject=path.parent.name,
                    action=action,
                    label=label,
                    frame_index=frame_index,
                )
            )
    return records


def validate_dataset(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    verify_mirrors: bool = True,
) -> dict:
    """完整校验本项目所用静态睡姿数据并返回统计摘要。"""

    root = Path(data_dir)
    subjects = list_subjects(root)
    files = list_static_files(root)
    file_map: dict[tuple[str, int], np.ndarray] = {}
    class_frames = np.zeros(len(LABEL_NAMES), dtype=np.int64)
    class_files = np.zeros(len(LABEL_NAMES), dtype=np.int64)
    action_frame_counts: dict[str, list[int]] = {str(i): [] for i in range(1, 22)}
    missing_actions: dict[str, list[int]] = {}

    for path in files:
        action = action_from_filename(path)
        assert action is not None
        frames = read_pressure_frames(path)
        key = (path.parent.name, action)
        if key in file_map:
            raise ValueError(f"同一用户存在重复动作文件：{key}")
        file_map[key] = frames
        label = action_to_label(action)
        class_frames[label] += len(frames)
        class_files[label] += 1
        action_frame_counts[str(action)].append(len(frames))

    for subject in subjects:
        available = {action for name, action in file_map if name == subject}
        missing = sorted(set(range(1, 22)) - available)
        if missing:
            missing_actions[subject] = missing

    mirror_summary = {
        "checked": False,
        "same_file_passed": 0,
        "same_file_total": 0,
        "side_pair_passed": 0,
        "side_pair_total": 0,
        "failures": [],
    }
    if verify_mirrors:
        mirror_summary["checked"] = True
        failures: list[str] = []
        for (subject, action), frames in file_map.items():
            if action > 9:
                continue
            mirror_summary["same_file_total"] += 1
            half = len(frames) // 2
            passed = (
                len(frames) % 2 == 0
                and half > 0
                and np.array_equal(frames[half:], np.flip(frames[:half], axis=2))
            )
            mirror_summary["same_file_passed"] += int(passed)
            if not passed:
                failures.append(f"{subject}:动作{action}")

        for subject in subjects:
            for left_action in range(10, 16):
                right_action = left_action + 6
                left = file_map.get((subject, left_action))
                right = file_map.get((subject, right_action))
                if left is None or right is None:
                    continue
                mirror_summary["side_pair_total"] += 1
                left_half, right_half = len(left) // 2, len(right) // 2
                passed = (
                    len(left) % 2 == 0
                    and len(right) % 2 == 0
                    and left_half == right_half
                    and left_half > 0
                    and np.array_equal(left[left_half:], np.flip(right[:right_half], axis=2))
                    and np.array_equal(right[right_half:], np.flip(left[:left_half], axis=2))
                )
                mirror_summary["side_pair_passed"] += int(passed)
                if not passed:
                    failures.append(f"{subject}:动作{left_action}<->{right_action}")
        mirror_summary["failures"] = failures

    dynamic_files = list(root.rglob("*动态*.txt"))
    empty_files = list(root.rglob("*空载*.txt"))
    summary = {
        "data_dir": str(root.resolve()),
        "subject_count": len(subjects),
        "subjects": subjects,
        "static_file_count": len(files),
        "dynamic_file_count": len(dynamic_files),
        "empty_file_count": len(empty_files),
        "total_static_frames": int(class_frames.sum()),
        "class_names": list(LABEL_NAMES),
        "files_by_class": {
            name: int(class_files[index]) for index, name in enumerate(LABEL_NAMES)
        },
        "frames_by_class": {
            name: int(class_frames[index]) for index, name in enumerate(LABEL_NAMES)
        },
        "action_frame_counts": {
            action: sorted(set(counts)) for action, counts in action_frame_counts.items()
        },
        "missing_actions": missing_actions,
        "mirror_check": mirror_summary,
    }
    return summary


def save_json(data: dict, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def unique_files(records: Sequence[FrameRecord]) -> list[Path]:
    return sorted({Path(record.path) for record in records}, key=lambda path: str(path).casefold())
