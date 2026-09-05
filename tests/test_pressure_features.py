"""Tests for shared pressure preprocessing and feature primitives."""

from __future__ import annotations

import unittest

import numpy as np

from backend.data_utils.pressure_processing import (
    prepare_pressure_frame,
    validate_pressure_frame,
)
from backend.features.pressure import (
    block_mean,
    calculate_pressure_statistics,
    normalized_projections,
    occupancy_projections,
)


class PressureProcessingTests(unittest.TestCase):
    def test_prepare_clips_negative_offsets_and_normalizes_positive_pressure(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[0, 0] = -2.0
        frame[1, 1] = 2.0
        frame[2, 2] = 4.0

        prepared = prepare_pressure_frame(frame, pressure_percentile=100.0)

        self.assertEqual(prepared.normalization_scale, 4.0)
        self.assertEqual(prepared.pressure[0, 0], 0.0)
        self.assertEqual(prepared.normalized[1, 1], 0.5)
        self.assertEqual(prepared.normalized[2, 2], 1.0)

    def test_validate_rejects_invalid_shape_and_non_finite_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_pressure_frame(np.zeros((1, 1), dtype=np.float32))
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[0, 0] = np.nan
        with self.assertRaises(ValueError):
            validate_pressure_frame(frame)


class PressureFeaturePrimitiveTests(unittest.TestCase):
    def setUp(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[4:12, 6:18] = 5.0
        self.prepared = prepare_pressure_frame(frame)

    def test_block_and_projection_features_have_interpretable_shapes(self) -> None:
        coarse = block_mean(self.prepared.normalized, (4, 2))
        rows, columns = normalized_projections(self.prepared.normalized)
        occupied, row_occupancy, column_occupancy = occupancy_projections(
            self.prepared.normalized,
            threshold_ratio=0.05,
        )

        self.assertEqual(coarse.shape, (11, 12))
        self.assertEqual(rows.shape, (44,))
        self.assertEqual(columns.shape, (24,))
        self.assertAlmostEqual(float(rows.sum()), 1.0)
        self.assertAlmostEqual(float(columns.sum()), 1.0)
        self.assertEqual(row_occupancy.shape, (44,))
        self.assertEqual(column_occupancy.shape, (24,))
        self.assertEqual(occupied.dtype, np.bool_)

    def test_global_statistics_are_named_and_have_stable_vector_order(self) -> None:
        occupied, _, _ = occupancy_projections(self.prepared.normalized)
        statistics = calculate_pressure_statistics(
            self.prepared.pressure,
            self.prepared.normalized,
            occupied,
        )
        default_statistics = calculate_pressure_statistics(
            self.prepared.pressure,
            self.prepared.normalized,
        )

        self.assertEqual(statistics.to_array().shape, (9,))
        self.assertEqual(statistics.contact_ratio, default_statistics.contact_ratio)
        self.assertEqual(
            list(statistics.to_dict()),
            [
                "log_total_pressure",
                "log_max_pressure",
                "log_positive_mean_pressure",
                "contact_ratio",
                "centroid_x",
                "centroid_y",
                "spread_x",
                "spread_y",
                "mirror_difference",
            ],
        )
        self.assertTrue(np.isfinite(statistics.to_array()).all())


if __name__ == "__main__":
    unittest.main()
