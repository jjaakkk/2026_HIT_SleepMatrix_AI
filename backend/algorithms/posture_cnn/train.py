"""训练四分类睡姿 CNN；只使用训练用户调参和计算标准化参数。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from .data_io import DEFAULT_DATA_DIR, LABEL_NAMES, PROJECT_ROOT, discover_frame_records
from .dataset import PressureFrameDataset, compute_normalization
from .metrics import classification_metrics
from .model import build_model
from .utils import (
    choose_device,
    load_json,
    plot_training_curves,
    save_history,
    save_json,
    set_seed,
)


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None = None,
    max_batches: int | None = None,
) -> tuple[float, dict]:
    training = optimizer is not None
    model.train(training)
    total_loss = 0.0
    targets: list[int] = []
    predictions: list[int] = []

    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for batch_index, (inputs, labels, _) in enumerate(loader):
            if max_batches is not None and batch_index >= max_batches:
                break
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            if training:
                optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = criterion(logits, labels)
            if training:
                loss.backward()
                optimizer.step()
            total_loss += float(loss.item()) * len(labels)
            targets.extend(labels.detach().cpu().tolist())
            predictions.extend(logits.argmax(dim=1).detach().cpu().tolist())

    if not targets:
        raise RuntimeError("没有读取到任何训练批次")
    metrics = classification_metrics(targets, predictions, len(LABEL_NAMES))
    return total_loss / len(targets), metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练智能床垫睡姿识别 CNN")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--splits", type=Path, default=Path(__file__).with_name("splits.json")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "posture_cnn"
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto", help="auto、cpu、cuda 或 cuda:0")
    parser.add_argument(
        "--max-train-batches",
        type=int,
        default=None,
        help="仅用于冒烟测试，限制每轮训练批次数",
    )
    parser.add_argument(
        "--max-val-batches",
        type=int,
        default=None,
        help="仅用于冒烟测试，限制每轮验证批次数",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    device = choose_device(args.device)
    split = load_json(args.splits)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    train_records = discover_frame_records(args.data_dir, split["train_subjects"])
    validation_records = discover_frame_records(
        args.data_dir, split["validation_subjects"]
    )
    normalization = compute_normalization(train_records)
    train_dataset = PressureFrameDataset(train_records, normalization, augment=True)
    validation_dataset = PressureFrameDataset(
        validation_records, normalization, augment=False
    )
    pin_memory = device.type == "cuda"
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=pin_memory,
        persistent_workers=args.num_workers > 0,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=pin_memory,
        persistent_workers=args.num_workers > 0,
    )

    model = build_model(num_classes=len(LABEL_NAMES), dropout=args.dropout).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=3
    )

    print(f"设备：{device}")
    print(f"训练帧：{len(train_dataset)}，验证帧：{len(validation_dataset)}")
    print(f"标准化参数：mean={normalization['mean']:.6f}, std={normalization['std']:.6f}")

    best_f1 = -1.0
    best_epoch = 0
    epochs_without_improvement = 0
    history: list[dict] = []
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        train_loss, train_metrics = run_epoch(
            model,
            train_loader,
            criterion,
            device,
            optimizer=optimizer,
            max_batches=args.max_train_batches,
        )
        validation_loss, validation_metrics = run_epoch(
            model,
            validation_loader,
            criterion,
            device,
            optimizer=None,
            max_batches=args.max_val_batches,
        )
        validation_f1 = validation_metrics["macro_f1"]
        scheduler.step(validation_f1)
        row = {
            "epoch": epoch,
            "learning_rate": optimizer.param_groups[0]["lr"],
            "train_loss": train_loss,
            "train_accuracy": train_metrics["accuracy"],
            "train_macro_f1": train_metrics["macro_f1"],
            "val_loss": validation_loss,
            "val_accuracy": validation_metrics["accuracy"],
            "val_macro_f1": validation_f1,
        }
        history.append(row)
        print(
            f"Epoch {epoch:03d} | train loss {train_loss:.4f} "
            f"acc {train_metrics['accuracy']:.4f} | val loss {validation_loss:.4f} "
            f"acc {validation_metrics['accuracy']:.4f} F1 {validation_f1:.4f}"
        )

        if validation_f1 > best_f1 + 1e-6:
            best_f1 = validation_f1
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "model_name": "PostureCNN",
                    "dropout": args.dropout,
                    "class_names": list(LABEL_NAMES),
                    "normalization": normalization,
                    "best_epoch": best_epoch,
                    "validation_metrics": validation_metrics,
                    "split_file": str(args.splits.resolve()),
                    "seed": args.seed,
                },
                output_dir / "best_model.pt",
            )
        else:
            epochs_without_improvement += 1

        save_history(history, output_dir / "history.csv")
        plot_training_curves(history, output_dir / "training_curves.png")
        if epochs_without_improvement >= args.patience:
            print(f"验证集连续 {args.patience} 轮未提升，提前停止。")
            break

    summary = {
        "device": str(device),
        "train_frames": len(train_dataset),
        "validation_frames": len(validation_dataset),
        "best_epoch": best_epoch,
        "best_validation_macro_f1": best_f1,
        "elapsed_seconds": time.time() - started,
        "normalization": normalization,
        "arguments": vars(args) | {
            "data_dir": str(args.data_dir),
            "splits": str(args.splits),
            "output_dir": str(args.output_dir),
        },
    }
    save_json(summary, output_dir / "training_summary.json")
    print(f"最佳模型：{(output_dir / 'best_model.pt').resolve()}")


if __name__ == "__main__":
    main()
