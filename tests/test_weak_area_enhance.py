from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

import numpy as np

from backend.algorithms.weak_area_enhance.compare import (
    load_pressure_frames,
    prepare_display_matrices,
)
from backend.algorithms.weak_area_enhance.enhance import enhance_pressure
from backend.algorithms.weak_area_enhance.joint_evaluation import (
    joint_guided_metrics,
    load_joint_record,
    skeleton_mask,
)


class EnhancePressureTests(unittest.TestCase):
    def test_empty_frame_stays_empty(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        result = enhance_pressure(frame)
        self.assertEqual(result.shape, frame.shape)
        self.assertEqual(result.dtype, np.float32)
        self.assertEqual(np.count_nonzero(result), 0)

    def test_weak_body_signal_is_amplified(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[10:34, 9:15] = 25.0
        frame[14:25, 10:14] = 180.0
        result = enhance_pressure(frame)
        self.assertGreater(float(result[30, 11]), float(frame[30, 11]))
        self.assertGreaterEqual(float(result[18, 11]), float(frame[18, 11]))
        self.assertEqual(result.shape, frame.shape)

    def test_isolated_background_noise_is_not_amplified(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[12:30, 9:15] = 150.0
        frame[2, 2] = 3.0
        result = enhance_pressure(frame)
        self.assertEqual(float(result[2, 2]), float(frame[2, 2]))

    def test_sparse_noise_near_body_is_not_amplified(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[12:30, 9:15] = 150.0
        frame[10, 7] = 3.0
        result = enhance_pressure(frame)
        self.assertEqual(float(result[10, 7]), float(frame[10, 7]))

    def test_weak_cluster_disconnected_from_seed_is_not_amplified(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[12:30, 9:15] = 150.0
        frame[9:11, 6:8] = 3.0
        result = enhance_pressure(frame)
        np.testing.assert_array_equal(result[9:11, 6:8], frame[9:11, 6:8])

    def test_enhancement_does_not_create_detached_visible_island(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[12:30, 9:15] = 150.0
        frame[9:11, 7:9] = 5.0
        result = enhance_pressure(frame)
        self.assertLess(float(result[9:11, 7:9].max()), 6.0)

    def test_small_internal_gap_is_connected(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[10:21, 10:14] = 80.0
        frame[22:34, 10:14] = 35.0
        result = enhance_pressure(frame)
        self.assertGreater(float(result[21, 11]), 0.0)

    def test_loader_skips_dynamic_label_rows(self) -> None:
        row = ",".join(str(value) for value in range(24))
        content = "\n".join([row] * 44 + ["1"] + [row] * 44)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynamic.txt"
            path.write_text(content, encoding="utf-8")
            frames = load_pressure_frames(path)
        self.assertEqual(frames.shape, (2, 44, 24))

    def test_display_filter_removes_same_background_noise_from_both(self) -> None:
        original = np.zeros((44, 24), dtype=np.float32)
        original[10:34, 9:15] = 100.0
        original[2, 2] = 2.0
        enhanced = original.copy()
        enhanced[20:24, 9:15] = 120.0
        original_display, enhanced_display = prepare_display_matrices(
            original, enhanced
        )
        self.assertEqual(float(original_display[2, 2]), 0.0)
        self.assertEqual(float(enhanced_display[2, 2]), 0.0)
        self.assertEqual(float(original_display[15, 11]), 100.0)

    def test_joint_json_loader_selects_duplicate_occurrence(self) -> None:
        values = ",".join(["0"] * (44 * 24))
        keypoints = [[12, 5]] * 14
        records = [
            {
                "folder": "SAI",
                "action": 1,
                "frame": 0,
                "data": values,
                "kpts": keypoints,
                "state": [0] * 14,
            },
            {
                "folder": "SAI",
                "action": 1,
                "frame": 0,
                "data": values,
                "kpts": [[24, 44]] * 14,
                "state": [0] * 14,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "joints.json"
            path.write_text(json.dumps(records), encoding="utf-8")
            loaded = load_joint_record(path, "sai", 1, 0, occurrence=1)
        self.assertEqual(loaded.pressure.shape, (44, 24))
        self.assertEqual(loaded.keypoints[0], (23.0, 43.0))

    def test_skeleton_mask_contains_labelled_leg_segment(self) -> None:
        keypoints = [None] * 14
        keypoints[8] = (8.0, 20.0)
        keypoints[10] = (8.0, 30.0)
        mask = skeleton_mask((44, 24), tuple(keypoints), limb_radius=1.0)
        self.assertTrue(mask[25, 8])
        self.assertFalse(mask[25, 15])

    def test_joint_metrics_detect_outside_added_intensity(self) -> None:
        original = np.zeros((44, 24), dtype=np.float32)
        enhanced = original.copy()
        keypoints = [None] * 14
        keypoints[8] = (8.0, 20.0)
        keypoints[10] = (8.0, 30.0)
        enhanced[25, 8] = 10.0
        enhanced[2, 20] = 10.0
        metrics = joint_guided_metrics(original, enhanced, tuple(keypoints))
        self.assertAlmostEqual(metrics["outside_added_ratio"], 0.5)
        self.assertAlmostEqual(metrics["anatomy_added_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
