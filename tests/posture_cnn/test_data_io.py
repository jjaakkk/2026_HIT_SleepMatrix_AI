from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.algorithms.posture_cnn.data_io import (
    action_from_filename,
    action_to_label,
    read_pressure_frames,
)


class DataIoTests(unittest.TestCase):
    def test_action_mapping(self):
        expected = {
            1: 0,
            6: 0,
            7: 1,
            9: 1,
            10: 2,
            15: 2,
            16: 3,
            21: 3,
        }
        for action, label in expected.items():
            self.assertEqual(action_to_label(action), label)
        with self.assertRaises(ValueError):
            action_to_label(22)

    def test_filename_parser_excludes_non_static_files(self):
        self.assertEqual(action_from_filename("wc0604_21.txt"), 21)
        self.assertIsNone(action_from_filename("dgs_动态一.txt"))
        self.assertIsNone(action_from_filename("dgs_空载.txt"))

    def test_reader_handles_missing_separator_between_frames(self):
        first = np.arange(44 * 24).reshape(44, 24)
        second = first + 1000
        # 故意不在两帧之间加入空行，复现数据集镜像拼接处的实际情况。
        text = "\n".join(
            ",".join(map(str, row)) for row in np.concatenate([first, second])
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "person_1.txt"
            path.write_text(text, encoding="utf-8")
            frames = read_pressure_frames(path)
        self.assertEqual(frames.shape, (2, 44, 24))
        np.testing.assert_array_equal(frames[0], first)
        np.testing.assert_array_equal(frames[1], second)

    def test_reader_rejects_wrong_column_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "person_1.txt"
            path.write_text("1,2,3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "24"):
                read_pressure_frames(path)


if __name__ == "__main__":
    unittest.main()
