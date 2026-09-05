"""以用户为单位生成可复现的训练、验证和最终测试划分。"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .data_io import DEFAULT_DATA_DIR, list_subjects, save_json


def build_subject_split(
    subjects: list[str],
    seed: int = 42,
    test_ratio: float = 0.30,
    validation_ratio_within_development: float = 0.20,
) -> dict:
    if len(subjects) < 3:
        raise ValueError("至少需要3名用户才能划分训练、验证和测试集")
    if not 0 < test_ratio < 1:
        raise ValueError("test_ratio 必须位于 0 和 1 之间")
    if not 0 < validation_ratio_within_development < 1:
        raise ValueError("validation_ratio_within_development 必须位于 0 和 1 之间")

    shuffled = sorted(subjects, key=str.casefold)
    random.Random(seed).shuffle(shuffled)
    test_count = max(1, round(len(shuffled) * test_ratio))
    development = shuffled[:-test_count]
    test = shuffled[-test_count:]
    validation_count = max(1, round(len(development) * validation_ratio_within_development))
    validation = development[-validation_count:]
    train = development[:-validation_count]

    return {
        "seed": seed,
        "strategy": "subject_independent_holdout",
        "test_ratio": test_ratio,
        "validation_ratio_within_development": validation_ratio_within_development,
        "all_subjects": sorted(subjects, key=str.casefold),
        "development_subjects": sorted(development, key=str.casefold),
        "train_subjects": sorted(train, key=str.casefold),
        "validation_subjects": sorted(validation, key=str.casefold),
        "test_subjects": sorted(test, key=str.casefold),
        "counts": {
            "all": len(subjects),
            "development": len(development),
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按用户生成训练/验证/测试划分")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("splits.json")
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-ratio", type=float, default=0.30)
    parser.add_argument("--validation-ratio", type=float, default=0.20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    split = build_subject_split(
        list_subjects(args.data_dir),
        seed=args.seed,
        test_ratio=args.test_ratio,
        validation_ratio_within_development=args.validation_ratio,
    )
    save_json(split, args.output)
    print(json.dumps(split, ensure_ascii=False, indent=2))
    print(f"\n用户划分已保存到：{args.output.resolve()}")


if __name__ == "__main__":
    main()
