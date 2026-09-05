"""Command-line comparison tool for weak-pressure enhancement."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .enhance import EnhancementConfig, enhance_pressure


def _component_count(mask: np.ndarray) -> int:
    """Count 8-connected components without an image-processing dependency."""

    pending = mask.astype(bool, copy=True)
    count = 0
    height, width = pending.shape
    for start_row in range(height):
        for start_col in range(width):
            if not pending[start_row, start_col]:
                continue
            count += 1
            pending[start_row, start_col] = False
            stack = [(start_row, start_col)]
            while stack:
                row, col = stack.pop()
                for next_row in range(max(0, row - 1), min(height, row + 2)):
                    for next_col in range(max(0, col - 1), min(width, col + 2)):
                        if pending[next_row, next_col]:
                            pending[next_row, next_col] = False
                            stack.append((next_row, next_col))
    return count


def _retain_large_components(mask: np.ndarray, minimum_size: int) -> np.ndarray:
    """Remove tiny display-only islands using 8-connectivity."""

    pending = mask.astype(bool, copy=True)
    retained = np.zeros_like(pending)
    height, width = pending.shape
    for start_row in range(height):
        for start_col in range(width):
            if not pending[start_row, start_col]:
                continue
            pending[start_row, start_col] = False
            component = [(start_row, start_col)]
            stack = [(start_row, start_col)]
            while stack:
                row, col = stack.pop()
                for next_row in range(max(0, row - 1), min(height, row + 2)):
                    for next_col in range(max(0, col - 1), min(width, col + 2)):
                        if pending[next_row, next_col]:
                            pending[next_row, next_col] = False
                            component.append((next_row, next_col))
                            stack.append((next_row, next_col))
            if len(component) >= minimum_size:
                rows, cols = zip(*component)
                retained[rows, cols] = True
    return retained


def prepare_display_matrices(
    original: np.ndarray,
    enhanced: np.ndarray,
    floor_ratio: float = 0.07,
    minimum_component_size: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the same reproducible background cleanup to both display panels.

    This function changes only the plotted copies, never the pressure matrices
    returned by the enhancement algorithm.
    """

    if not 0.0 <= floor_ratio < 1.0:
        raise ValueError("display floor ratio must be between 0 and 1")
    if minimum_component_size < 1:
        raise ValueError("minimum component size must be positive")
    positive = original[original > 0]
    scale = float(np.percentile(positive, 99.5)) if positive.size else 1.0
    floor = floor_ratio * max(scale, 1e-6)
    visible = (original >= floor) | (enhanced >= floor)
    retained = _retain_large_components(visible, minimum_component_size)
    original_display = np.where(retained & (original >= floor), original, 0.0)
    enhanced_display = np.where(retained & (enhanced >= floor), enhanced, 0.0)
    return original_display, enhanced_display


def load_pressure_frames(
    path: str | Path,
    rows: int = 44,
    cols: int = 24,
) -> np.ndarray:
    """Read all complete pressure frames from a dataset TXT file.

    Ordinary files contain comma-separated sensor rows.  Dynamic files also
    contain one-value 0/1/2 label rows; any non-``cols`` row is ignored.
    """

    numeric_rows: list[list[float]] = []
    with Path(path).open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != cols:
                # The dataset documentation explicitly permits label rows in
                # dynamic recordings.  Other short rows are ignored as well.
                continue
            try:
                numeric_rows.append([float(value) for value in parts])
            except ValueError as exc:
                raise ValueError(f"invalid number on line {line_number}: {path}") from exc

    complete_rows = len(numeric_rows) - len(numeric_rows) % rows
    if complete_rows == 0:
        raise ValueError(f"no complete {rows}x{cols} frame found in {path}")
    array = np.asarray(numeric_rows[:complete_rows], dtype=np.float32)
    return array.reshape(-1, rows, cols)


def enhancement_metrics(original: np.ndarray, enhanced: np.ndarray) -> dict[str, float]:
    """Compute simple, reproducible before/after display metrics."""

    positive = original[original > 0]
    scale = float(np.percentile(positive, 99.5)) if positive.size else 1.0
    normalized = np.clip(original / max(scale, 1e-6), 0.0, 1.0)
    weak_mask = (normalized >= 0.015) & (normalized <= 0.35)
    weak_before = float(original[weak_mask].mean()) if weak_mask.any() else 0.0
    weak_after = float(enhanced[weak_mask].mean()) if weak_mask.any() else 0.0
    threshold = 0.04 * scale
    before_components = _component_count(original >= threshold)
    after_components = _component_count(enhanced >= threshold)
    return {
        "weak_mean_before": weak_before,
        "weak_mean_after": weak_after,
        "weak_gain_ratio": weak_after / max(weak_before, 1e-6),
        "active_cells_before": float(np.count_nonzero(original >= threshold)),
        "active_cells_after": float(np.count_nonzero(enhanced >= threshold)),
        "components_before": float(before_components),
        "components_after": float(after_components),
    }


def save_comparison(
    original: np.ndarray,
    enhanced: np.ndarray,
    output_path: str | Path,
    title: str = "Weak-pressure enhancement",
    display_floor_ratio: float = 0.07,
    minimum_component_size: int = 4,
) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    combined_positive = np.concatenate(
        [original[original > 0], enhanced[enhanced > 0]]
    )
    color_max = (
        float(np.percentile(combined_positive, 99.5))
        if combined_positive.size
        else 1.0
    )
    difference = np.maximum(enhanced - original, 0.0)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        figure, axes = plt.subplots(1, 3, figsize=(12, 5), constrained_layout=True)
        original_image = axes[0].imshow(
            original,
            cmap="turbo",
            interpolation="bilinear",
            vmin=0,
            vmax=color_max,
        )
        axes[0].set_title("Original")
        axes[1].imshow(
            enhanced,
            cmap="turbo",
            interpolation="bilinear",
            vmin=0,
            vmax=color_max,
        )
        axes[1].set_title("Enhanced")
        difference_image = axes[2].imshow(
            difference, cmap="magma", interpolation="nearest", vmin=0
        )
        axes[2].set_title("Added intensity")
        for axis in axes:
            axis.set_xticks([])
            axis.set_yticks([])
        figure.colorbar(original_image, ax=axes[:2], fraction=0.025, pad=0.02)
        figure.colorbar(difference_image, ax=axes[2], fraction=0.05, pad=0.03)
        figure.suptitle(title)
        figure.savefig(output, dpi=180, bbox_inches="tight")
        plt.close(figure)
    except ModuleNotFoundError:
        _save_comparison_with_pillow(
            original,
            enhanced,
            difference,
            output,
            title,
            color_max,
        )


def _colorize(values: np.ndarray, maximum: float) -> np.ndarray:
    """Map values to a compact blue-cyan-yellow-red heat-map palette."""

    normalized = np.clip(values / max(maximum, 1e-6), 0.0, 1.0)
    stops = np.asarray(
        [
            [20, 8, 70],
            [25, 80, 160],
            [20, 180, 180],
            [245, 225, 45],
            [220, 45, 30],
        ],
        dtype=np.float32,
    )
    position = normalized * (len(stops) - 1)
    lower = np.floor(position).astype(int)
    upper = np.minimum(lower + 1, len(stops) - 1)
    weight = (position - lower)[..., None]
    return ((1.0 - weight) * stops[lower] + weight * stops[upper]).astype(np.uint8)


def _save_comparison_with_pillow(
    original: np.ndarray,
    enhanced: np.ndarray,
    difference: np.ndarray,
    output: Path,
    title: str,
    color_max: float,
) -> None:
    from PIL import Image, ImageDraw

    scale = 10
    margin = 24
    title_height = 56
    panel_width = original.shape[1] * scale
    panel_height = original.shape[0] * scale
    canvas = Image.new(
        "RGB",
        (margin * 4 + panel_width * 3, title_height + panel_height + margin),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 10), title, fill="black")
    panels = [
        ("Original", _colorize(original, color_max)),
        ("Enhanced", _colorize(enhanced, color_max)),
        ("Added intensity", _colorize(difference, float(max(difference.max(), 1.0)))),
    ]
    for index, (label_text, rgb) in enumerate(panels):
        left = margin + index * (panel_width + margin)
        image = Image.fromarray(rgb, mode="RGB").resize(
            (panel_width, panel_height), Image.Resampling.NEAREST
        )
        canvas.paste(image, (left, title_height))
        draw.text((left, 32), label_text, fill="black")
    canvas.save(output)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="dataset TXT file")
    parser.add_argument("--frame", type=int, default=0, help="zero-based frame index")
    parser.add_argument("--output", type=Path, default=Path("weak_pressure_comparison.png"))
    parser.add_argument("--gamma", type=float, default=EnhancementConfig.gamma)
    parser.add_argument("--strength", type=float, default=EnhancementConfig.strength)
    parser.add_argument(
        "--display-floor",
        type=float,
        default=0.07,
        help="hide display values below this fraction of the robust frame maximum",
    )
    parser.add_argument(
        "--min-display-component",
        type=int,
        default=4,
        help="hide smaller connected components in comparison figures",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    frames = load_pressure_frames(args.input)
    if not 0 <= args.frame < len(frames):
        raise IndexError(f"frame must be between 0 and {len(frames) - 1}")
    config = EnhancementConfig(gamma=args.gamma, strength=args.strength)
    original = frames[args.frame]
    enhanced = enhance_pressure(original, config)
    save_comparison(
        original,
        enhanced,
        args.output,
        title=f"{args.input.name} - frame {args.frame}",
        display_floor_ratio=args.display_floor,
        minimum_component_size=args.min_display_component,
    )
    for key, value in enhancement_metrics(original, enhanced).items():
        print(f"{key}: {value:.4f}")
    print(f"saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
