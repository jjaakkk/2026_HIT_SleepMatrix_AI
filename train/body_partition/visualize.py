"""Render sample partition visualisations for the report.

Produces one PNG per sleep position with ground-truth vs predicted masks and
region rectangles, plus a training-curve figure, under ``docs/body-partition/``.

Run from the repository root after training::

    python -m train.body_partition.visualize
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Rectangle

from backend.algorithms.body_partition.inference import BodyPartitionPredictor
from backend.algorithms.body_partition.partition import REGION_NAMES_ZH, mask_to_rects
from train.body_partition.dataset_prep import DEFAULT_SOURCE, build_base_arrays, load_partition_records

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "docs" / "body-partition"
POSITIONS = {0: "supine 仰卧", 1: "prone 俯卧", 2: "left_lateral 左侧卧", 3: "right_lateral 右侧卧"}
MASK_CMAP = ListedColormap(
    ["#00000000", "#165dff", "#00b42a", "#ff7d00", "#f53f3f", "#722ed1"]
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _draw_rects(ax, mask, color_cycle):
    for rect in mask_to_rects(mask):
        if rect is None:
            continue
        ax.add_patch(
            Rectangle(
                (rect.x1 - 0.5, rect.y1 - 0.5),
                rect.x2 - rect.x1,
                rect.y2 - rect.y1,
                fill=False,
                edgecolor=color_cycle[rect.class_id - 1],
                linewidth=1.6,
            )
        )
        ax.text(
            rect.x1,
            rect.y1 - 0.8,
            rect.name_zh,
            color=color_cycle[rect.class_id - 1],
            fontsize=8,
            fontweight="bold",
        )


def render_position_grids(predictor: BodyPartitionPredictor, arrays, out_dir: Path, seed: int) -> list[str]:
    rng = np.random.default_rng(seed)
    written: list[str] = []
    colors = ["#165dff", "#00b42a", "#ff7d00", "#f53f3f", "#722ed1"]
    for position, title in POSITIONS.items():
        candidates = np.flatnonzero(arrays["sleep_positions"] == position)
        chosen = rng.choice(candidates, size=3, replace=False)
        fig, axes = plt.subplots(3, 3, figsize=(11, 15))
        for row, index in enumerate(chosen):
            frame = arrays["frames"][index]
            gt_mask = arrays["masks"][index]
            prediction = predictor.predict(frame)
            pred_mask = np.asarray(prediction.mask, dtype=np.uint8)
            subject = arrays["subjects"][index]
            action = int(arrays["actions"][index])
            frame_no = int(arrays["frame_numbers"][index])
            acc = float((pred_mask == gt_mask).mean())

            ax = axes[row, 0]
            ax.imshow(frame, cmap="turbo", interpolation="bilinear")
            ax.set_title(f"{subject} 动作{action} 第{frame_no}帧 · 压力热力", fontsize=9)
            _draw_rects(ax, gt_mask, colors)

            ax = axes[row, 1]
            ax.imshow(frame, cmap="turbo", interpolation="bilinear", alpha=0.35)
            ax.imshow(gt_mask, cmap=MASK_CMAP, interpolation="nearest", alpha=0.85, vmin=0, vmax=5)
            ax.set_title("真值区域划分", fontsize=9)

            ax = axes[row, 2]
            ax.imshow(frame, cmap="turbo", interpolation="bilinear", alpha=0.35)
            ax.imshow(pred_mask, cmap=MASK_CMAP, interpolation="nearest", alpha=0.85, vmin=0, vmax=5)
            ax.set_title(f"模型预测 · 像素准确率 {acc:.2%}", fontsize=9)
            _draw_rects(ax, pred_mask, colors)

        for ax in axes.ravel():
            ax.set_xticks([])
            ax.set_yticks([])
        fig.suptitle(f"睡姿：{title}", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.98))
        path = out_dir / f"body_partition_{title.split()[0]}.png"
        fig.savefig(path, dpi=130)
        plt.close(fig)
        written.append(str(path))
    return written


def render_training_curve(report_path: Path, out_dir: Path) -> str | None:
    if not report_path.is_file():
        return None
    document = json.loads(report_path.read_text(encoding="utf-8"))
    history = document.get("history") or []
    if not history:
        return None
    epochs = [row["epoch"] for row in history]
    losses = [row["train_loss"] for row in history]
    accuracies = [row["val_pixel_accuracy"] for row in history]

    fig, ax1 = plt.subplots(figsize=(7.5, 4))
    ax1.plot(epochs, losses, color="#f53f3f", label="训练损失")
    ax1.set_xlabel("epoch")
    ax1.set_ylabel("loss", color="#f53f3f")
    ax2 = ax1.twinx()
    ax2.plot(epochs, [acc * 100 for acc in accuracies], color="#165dff", label="验证像素准确率")
    ax2.set_ylabel("pixel accuracy (%)", color="#165dff")
    ax2.axhline(95, color="#00b42a", linestyle="--", linewidth=1, label="95% 目标线")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], loc="center right", fontsize=9)
    fig.suptitle("身体区域划分训练曲线（70/30 随机划分）")
    fig.tight_layout()
    path = out_dir / "body_partition_training_curve.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    predictor = BodyPartitionPredictor(args.model) if args.model else BodyPartitionPredictor()
    arrays = build_base_arrays(load_partition_records(args.data))

    written = render_position_grids(predictor, arrays, REPORT_DIR, args.seed)
    curve = render_training_curve(
        PROJECT_ROOT / "backend" / "models" / "body_partition.metrics.json", REPORT_DIR
    )
    if curve:
        written.append(curve)
    print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
