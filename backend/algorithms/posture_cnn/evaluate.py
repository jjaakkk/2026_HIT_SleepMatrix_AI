"""在锁定的30%新用户测试集上进行一次最终评估。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from .data_io import DEFAULT_DATA_DIR, LABEL_NAMES, PROJECT_ROOT, discover_frame_records
from .dataset import PressureFrameDataset
from .metrics import classification_metrics, per_subject_accuracy
from .model import build_model
from .utils import (
    choose_device,
    load_checkpoint,
    load_json,
    plot_confusion_matrix,
    save_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估睡姿识别模型")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--splits", type=Path, default=Path(__file__).with_name("splits.json")
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "posture_cnn" / "best_model.pt",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "posture_cnn"
    )
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = choose_device(args.device)
    split = load_json(args.splits)
    checkpoint = load_checkpoint(args.checkpoint, device)
    class_names = checkpoint.get("class_names", list(LABEL_NAMES))
    model = build_model(
        num_classes=len(class_names), dropout=float(checkpoint.get("dropout", 0.3))
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    records = discover_frame_records(args.data_dir, split["test_subjects"])
    dataset = PressureFrameDataset(records, checkpoint["normalization"], augment=False)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
        persistent_workers=args.num_workers > 0,
    )

    targets: list[int] = []
    predictions: list[int] = []
    probabilities: list[list[float]] = []
    subjects: list[str] = []
    rows: list[dict] = []

    with torch.inference_mode():
        for inputs, labels, metadata in loader:
            logits = model(inputs.to(device, non_blocking=True))
            batch_probabilities = torch.softmax(logits, dim=1).cpu()
            batch_predictions = batch_probabilities.argmax(dim=1)
            for index in range(len(labels)):
                target = int(labels[index])
                prediction = int(batch_predictions[index])
                subject = metadata["subject"][index]
                probability_values = batch_probabilities[index].tolist()
                targets.append(target)
                predictions.append(prediction)
                probabilities.append(probability_values)
                subjects.append(subject)
                rows.append(
                    {
                        "subject": subject,
                        "action": int(metadata["action"][index]),
                        "frame_index": int(metadata["frame_index"][index]),
                        "path": metadata["path"][index],
                        "target": class_names[target],
                        "prediction": class_names[prediction],
                        "correct": int(target == prediction),
                        **{
                            f"probability_{name}": probability_values[class_index]
                            for class_index, name in enumerate(class_names)
                        },
                    }
                )

    metrics = classification_metrics(targets, predictions, len(class_names))
    metrics["class_names"] = class_names
    metrics["test_subjects"] = split["test_subjects"]
    metrics["test_frame_count"] = len(dataset)
    metrics["per_subject"] = per_subject_accuracy(subjects, targets, predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_json(metrics, args.output_dir / "test_metrics.json")
    plot_confusion_matrix(
        metrics["confusion_matrix"],
        class_names,
        args.output_dir / "confusion_matrix.png",
    )
    with (args.output_dir / "test_predictions.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"测试用户：{', '.join(split['test_subjects'])}")
    print(f"Accuracy:        {metrics['accuracy']:.4f}")
    print(f"Macro Precision: {metrics['macro_precision']:.4f}")
    print(f"Macro Recall:    {metrics['macro_recall']:.4f}")
    print(f"Macro F1:        {metrics['macro_f1']:.4f}")
    print(f"结果已保存到：{args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
