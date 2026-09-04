"""命令行数据完整性检查。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data_io import DEFAULT_DATA_DIR, PROJECT_ROOT, save_json, validate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查智能床垫静态睡姿数据")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "posture_cnn" / "data_summary.json",
    )
    parser.add_argument(
        "--skip-mirror-check",
        action="store_true",
        help="跳过耗时较长的镜像一致性检查",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = validate_dataset(args.data_dir, verify_mirrors=not args.skip_mirror_check)
    save_json(summary, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n数据摘要已保存到：{args.output.resolve()}")


if __name__ == "__main__":
    main()
