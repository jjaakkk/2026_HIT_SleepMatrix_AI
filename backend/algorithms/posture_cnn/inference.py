"""对一个静态压力文件中的指定帧进行预测。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from .data_io import read_pressure_frames
from .dataset import preprocess_single_frame
from .model import build_model
from .utils import choose_device, load_checkpoint


DEFAULT_CHECKPOINT = (
    Path(__file__).resolve().parents[3]
    / "outputs"
    / "posture_cnn"
    / "best_model.pt"
)


def load_trained_model(checkpoint_path: str | Path, device: torch.device):
    checkpoint = load_checkpoint(checkpoint_path, device)
    class_names = checkpoint["class_names"]
    model = build_model(
        num_classes=len(class_names), dropout=float(checkpoint.get("dropout", 0.3))
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model, checkpoint


def predict_frame(model, checkpoint: dict, frame, device: torch.device) -> dict:
    inputs = preprocess_single_frame(frame, checkpoint["normalization"]).to(device)
    with torch.inference_mode():
        probabilities = torch.softmax(model(inputs), dim=1)[0].cpu().tolist()
    class_names = checkpoint["class_names"]
    prediction = max(range(len(probabilities)), key=probabilities.__getitem__)
    return {
        "prediction_index": prediction,
        "prediction": class_names[prediction],
        "confidence": probabilities[prediction],
        "probabilities": dict(zip(class_names, probabilities, strict=True)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预测一个文件中的指定睡姿帧")
    parser.add_argument("file", type=Path)
    parser.add_argument("--frame-index", type=int, default=0)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frames = read_pressure_frames(args.file)
    if not 0 <= args.frame_index < len(frames):
        raise IndexError(
            f"frame-index 应位于 0-{len(frames) - 1}，收到：{args.frame_index}"
        )
    device = choose_device(args.device)
    model, checkpoint = load_trained_model(args.checkpoint, device)
    result = predict_frame(model, checkpoint, frames[args.frame_index], device)
    result.update(
        {
            "file": str(args.file.resolve()),
            "frame_index": args.frame_index,
            "frame_count": len(frames),
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
