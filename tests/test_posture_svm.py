"""Dataset-independent tests for the posture SVM module."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from backend.algorithms.posture_svm.features import (
    FeatureConfig,
    extract_feature_matrix,
    extract_frame_features,
)
from backend.algorithms.posture_svm.inference import PostureSVMClassifier
from backend.algorithms.posture_svm.train_svm import split_by_subject, train_and_evaluate
from backend.data_utils.data_loader import PostureDataset


class FeatureTests(unittest.TestCase):
    def test_features_are_finite_and_have_stable_dimensions(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[8:36, 6:18] = 10.0
        single = extract_frame_features(frame)
        batch = extract_feature_matrix(np.stack([frame, frame]))
        self.assertEqual(batch.shape, (2, single.size))
        self.assertTrue(np.isfinite(batch).all())

class SplitAndArtifactTests(unittest.TestCase):
    def test_subject_split_has_no_participant_leakage(self) -> None:
        subjects = np.repeat([f"subject-{index}" for index in range(10)], 4)
        labels = np.tile(np.arange(4), 10)
        dataset = PostureDataset(
            frames=np.zeros((40, 44, 24), dtype=np.float32),
            labels=labels,
            subjects=subjects,
            actions=np.tile(np.asarray([1, 7, 10, 16]), 10),
            frame_numbers=np.zeros(40, dtype=np.int64),
            source_files=np.asarray(["test.txt"] * 40),
        )
        train_indices, test_indices = split_by_subject(dataset, random_state=7)
        train_subjects = set(subjects[train_indices])
        test_subjects = set(subjects[test_indices])
        self.assertFalse(train_subjects & test_subjects)
        self.assertEqual(len(test_subjects), 3)

    def test_model_artifact_round_trip_supports_inference(self) -> None:
        frames = np.zeros((8, 44, 24), dtype=np.float32)
        labels = np.repeat(np.arange(4), 2)
        for index, label in enumerate(labels):
            frames[index, 4 + label * 8 : 10 + label * 8, 5:19] = 10.0
        config = FeatureConfig()
        features = extract_feature_matrix(frames, config)
        pipeline = Pipeline(
            [("scale", StandardScaler()), ("svm", SVC(probability=True, random_state=42))]
        ).fit(features, labels)
        artifact = {
            "format": "sleepmatrix-posture-svm",
            "version": 1,
            "contract_version": "1.1",
            "matrix_shape": (44, 24),
            "feature_config": config.to_dict(),
            "label_id_to_name": {
                0: "supine",
                1: "prone",
                2: "left_lateral",
                3: "right_lateral",
            },
            "label_id_to_name_zh": {0: "仰卧", 1: "俯卧", 2: "左侧卧", 3: "右侧卧"},
            "pipeline": pipeline,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.joblib"
            joblib.dump(artifact, path)
            result = PostureSVMClassifier(path).predict(frames[0])
        self.assertIn(result.label_id, range(4))
        self.assertAlmostEqual(sum(result.probabilities.values()), 1.0, places=6)

    def test_training_pipeline_runs_on_documented_text_format(self) -> None:
        action_by_label = [1, 7, 10, 16]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_dir = root / "dataset"
            dataset_dir.mkdir()
            for subject_index in range(6):
                for label, action in enumerate(action_by_label):
                    frame = np.zeros((44, 24), dtype=np.float32)
                    row_start = 2 + label * 9
                    frame[row_start : row_start + 7, 4:20] = 10.0 + subject_index
                    lines = [",".join(str(value) for value in row) for row in frame]
                    (dataset_dir / f"subject-{subject_index}_{action}.txt").write_text(
                        "\n".join(lines), encoding="utf-8"
                    )

            model_path = root / "posture_svm.joblib"
            metrics = train_and_evaluate(
                dataset_dir=dataset_dir,
                model_path=model_path,
                jitter_copies=0,
                n_jobs=1,
            )
            prediction = PostureSVMClassifier(model_path).predict(frame)

            self.assertTrue(model_path.is_file())
            self.assertTrue(model_path.with_suffix(".metrics.json").is_file())
            self.assertEqual(len(metrics["train_subjects"]), 4)
            self.assertEqual(len(metrics["test_subjects"]), 2)
            self.assertIn(prediction.label_id, range(4))


if __name__ == "__main__":
    unittest.main()
