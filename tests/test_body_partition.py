"""Tests for the body-partition region parsing, masks and metrics."""

from __future__ import annotations

import unittest

import numpy as np

from backend.algorithms.body_partition.partition import (
    NUM_CLASSES,
    REGION_KEYS,
    RegionFormatError,
    mask_to_rects,
    mean_iou,
    parse_region_field,
    pixel_accuracy,
    rect_iou,
    rects_to_mask,
    region_rect_metrics,
)
from backend.algorithms.body_partition.preprocess import normalize_frames
from backend.data_utils.contracts import MATRIX_SHAPE
from train.body_partition.augment import augment_frames_and_masks


class RegionParsingTests(unittest.TestCase):
    def test_parse_full_region_field(self) -> None:
        rects = parse_region_field("6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")
        self.assertEqual(len(rects), 6)
        self.assertEqual(rects[0], (6, 18, 3, 8))
        self.assertEqual(rects[4], (5, 20, 27, 36))
        self.assertEqual(rects[5], (6, 20, 36, 44))

    def test_parse_region_with_missing_calf(self) -> None:
        rects = parse_region_field(
            "4 16 4 16 5 17 6 19 6 18 na na 5 9 9 14 14 19 19 28 28 36 na na"
        )
        self.assertEqual(rects[0], (4, 16, 5, 9))
        self.assertIsNone(rects[5])

    def test_parse_rejects_bad_token_count(self) -> None:
        with self.assertRaises(RegionFormatError):
            parse_region_field("1 2 3")

    def test_parse_rejects_out_of_bounds(self) -> None:
        with self.assertRaises(RegionFormatError):
            parse_region_field("0 99 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")


class MaskConversionTests(unittest.TestCase):
    def test_rects_to_mask_paints_five_regions(self) -> None:
        rects = parse_region_field("6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")
        mask = rects_to_mask(rects)
        self.assertEqual(mask.shape, MATRIX_SHAPE)
        self.assertEqual(int((mask == 1).sum()), (8 - 3) * (18 - 6))
        self.assertEqual(int((mask == 5).sum()), (36 - 27) * (20 - 5))
        self.assertEqual(int((mask > 0).sum()), 60 + 60 + 60 + 135 + 135)
        # calf rectangle is ignored by design
        self.assertTrue((mask[36:44, :] == 0).all())

    def test_mask_to_rects_roundtrip(self) -> None:
        source = parse_region_field("6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")
        mask = rects_to_mask(source)
        recovered = mask_to_rects(mask)
        for expected, actual in zip(source[:5], recovered):
            self.assertIsNotNone(actual)
            self.assertEqual((actual.x1, actual.x2, actual.y1, actual.y2), expected)


class MetricTests(unittest.TestCase):
    def test_pixel_accuracy(self) -> None:
        target = np.zeros((4, 4), dtype=np.uint8)
        prediction = target.copy()
        prediction[0, 0] = 1
        self.assertAlmostEqual(pixel_accuracy(prediction, target), 15 / 16)

    def test_rect_iou(self) -> None:
        self.assertEqual(rect_iou((0, 4, 0, 4), (0, 4, 0, 4)), 1.0)
        self.assertEqual(rect_iou((0, 2, 0, 4), (2, 4, 0, 4)), 0.0)
        self.assertAlmostEqual(rect_iou((0, 4, 0, 4), (0, 4, 2, 6)), 8 / 24)

    def test_mean_iou_perfect(self) -> None:
        mask = rects_to_mask(
            parse_region_field("6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")
        )
        self.assertEqual(mean_iou(mask, mask), 1.0)

    def test_region_rect_metrics_keys(self) -> None:
        mask = rects_to_mask(
            parse_region_field("6 18 6 18 6 18 5 20 5 20 6 20 3 8 8 13 13 18 18 27 27 36 36 44")
        )
        metrics = region_rect_metrics(mask, mask)
        self.assertAlmostEqual(metrics["mean_rect_iou"], 1.0)
        self.assertAlmostEqual(metrics["mean_boundary_mae"], 0.0)


class PreprocessTests(unittest.TestCase):
    def test_normalize_scales_to_unit_range(self) -> None:
        frame = np.zeros(MATRIX_SHAPE, dtype=np.float32)
        frame[10:20, 5:15] = 250.0
        normalized = normalize_frames(frame)
        self.assertLessEqual(float(normalized.max()), 1.0)
        self.assertGreater(float(normalized.max()), 0.9)
        self.assertEqual(float(normalized.min()), 0.0)

    def test_normalize_handles_empty_frame(self) -> None:
        normalized = normalize_frames(np.zeros(MATRIX_SHAPE, dtype=np.float32))
        self.assertEqual(float(normalized.max()), 0.0)


class AugmentationTests(unittest.TestCase):
    def test_augmentation_keeps_shapes_and_mask_classes(self) -> None:
        frames = np.random.default_rng(0).random((8, *MATRIX_SHAPE), dtype=np.float32) * 100
        masks = np.random.default_rng(1).integers(0, NUM_CLASSES, size=(8, *MATRIX_SHAPE)).astype(np.uint8)
        new_frames, new_masks = augment_frames_and_masks(frames, masks, copies=2, random_state=7)
        self.assertEqual(new_frames.shape, (24, *MATRIX_SHAPE))
        self.assertEqual(new_masks.shape, (24, *MATRIX_SHAPE))
        self.assertTrue(set(np.unique(new_masks)).issubset(set(range(NUM_CLASSES))))
        self.assertTrue((new_frames >= 0).all())

    def test_augmentation_is_deterministic(self) -> None:
        frames = np.ones((2, *MATRIX_SHAPE), dtype=np.float32)
        masks = np.ones((2, *MATRIX_SHAPE), dtype=np.uint8)
        first = augment_frames_and_masks(frames, masks, copies=1, random_state=3)
        second = augment_frames_and_masks(frames, masks, copies=1, random_state=3)
        self.assertTrue(np.array_equal(first[0], second[0]))
        self.assertTrue(np.array_equal(first[1], second[1]))


if __name__ == "__main__":
    unittest.main()
