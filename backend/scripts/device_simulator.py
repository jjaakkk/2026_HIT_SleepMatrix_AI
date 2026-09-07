"""设备模拟器：把数据集帧按真实节奏逐帧推送到后端设备输入接口。

模拟一台真实床垫设备：读取数据集 txt 文件，按指定帧率逐帧
POST /api/stream/ingest，前端「实时推理」模式即可看到实时推理效果。
停止推送后，前端约 2 秒内回到「等待设备输入」静止状态。

用法（在项目根目录）：
    python backend/scripts/device_simulator.py --files dgs_1 dgs_10 dgs_16 dgs_7 --fps 2.5 --loop

详细说明见本目录 README.md。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.algorithms.posture_cnn.data_io import DEFAULT_DATA_DIR, read_pressure_frames

BASE = "http://127.0.0.1:5000"


def ingest(frame: list[list[float]], source: str, seq: int) -> None:
    payload = json.dumps(
        {"pressure_matrix": frame, "source": source, "frame_index": seq}
    ).encode("utf-8")
    request = urllib.request.Request(
        BASE + "/api/stream/ingest",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def main() -> None:
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--files",
        nargs="+",
        default=["dgs_1", "dgs_10", "dgs_16", "dgs_7"],
        help="数据集文件名（<subject>_<action>，可省略 .txt）",
    )
    parser.add_argument("--fps", type=float, default=2.5, help="推送帧率")
    parser.add_argument("--limit", type=int, default=30, help="每文件帧数上限")
    parser.add_argument("--loop", action="store_true", help="序列循环推送")
    parser.add_argument("--source", default="dataset-simulator", help="设备来源标识")
    parser.add_argument("--base", default=BASE, help="后端地址")
    args = parser.parse_args()
    BASE = args.base

    sequences: list[tuple[str, list[list[float]]]] = []
    for name in args.files:
        base = Path(name).stem
        subject, _, action_text = base.rpartition("_")
        source_file = DEFAULT_DATA_DIR / subject / f"{base}.txt"
        if not source_file.is_file():
            raise SystemExit(f"找不到数据集文件：{source_file}")
        frames = read_pressure_frames(source_file)[: args.limit]
        sequences.append((base, [f.tolist() for f in frames]))

    total = sum(len(frames) for _, frames in sequences)
    interval = 1.0 / args.fps
    print(f"设备模拟器：{len(sequences)} 个文件 / {total} 帧 @ {args.fps} fps → {BASE}")
    print("Ctrl+C 停止推送")

    seq = 0
    try:
        while True:
            for name, frames in sequences:
                for frame in frames:
                    ingest(frame, args.source, seq)
                    seq += 1
                    if seq % 10 == 0:
                        print(f"已推送 {seq} 帧（当前 {name}）")
                    time.sleep(interval)
            if not args.loop:
                break
    except KeyboardInterrupt:
        print(f"\n已停止，共推送 {seq} 帧")


if __name__ == "__main__":
    main()
