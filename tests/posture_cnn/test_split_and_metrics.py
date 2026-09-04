from __future__ import annotations

import unittest

from backend.algorithms.posture_cnn.make_splits import build_subject_split
from backend.algorithms.posture_cnn.metrics import classification_metrics


class SplitTests(unittest.TestCase):
    def test_33_subject_split_is_disjoint_and_reproducible(self):
        subjects = [f"p{i:02d}" for i in range(33)]
        first = build_subject_split(subjects, seed=42)
        second = build_subject_split(subjects, seed=42)
        self.assertEqual(first, second)
        self.assertEqual(first["counts"]["development"], 23)
        self.assertEqual(first["counts"]["test"], 10)
        train = set(first["train_subjects"])
        validation = set(first["validation_subjects"])
        test = set(first["test_subjects"])
        self.assertFalse(train & validation)
        self.assertFalse(train & test)
        self.assertFalse(validation & test)
        self.assertEqual(train | validation | test, set(subjects))


class MetricsTests(unittest.TestCase):
    def test_perfect_metrics(self):
        metrics = classification_metrics([0, 1, 2, 3], [0, 1, 2, 3], 4)
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["macro_f1"], 1.0)

    def test_known_confusion(self):
        metrics = classification_metrics([0, 0, 1, 1], [0, 1, 1, 1], 2)
        self.assertAlmostEqual(metrics["accuracy"], 0.75)
        self.assertEqual(metrics["confusion_matrix"], [[1, 1], [0, 2]])


if __name__ == "__main__":
    unittest.main()
