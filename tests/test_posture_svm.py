"""Dataset-independent tests for the posture SVM module."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
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
from backend.algorithms.posture_svm.train_svm import split_by_subject
from backend.data_utils.data_loader import PostureDataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_SCRIPT = PROJECT_ROOT / "backend" / "algorithms" / "posture_svm" / "train_svm.py"
INFERENCE_SCRIPT = (
    PROJECT_ROOT / "backend" / "algorithms" / "posture_svm" / "inference.py"
)


def _build_test_model(path: Path) -> np.ndarray:
    frames = np.zeros((8, 44, 24), dtype=np.float32)
    labels = np.repeat(np.arange(4), 2)
    for index, label in enumerate(labels):
        frames[index, 4 + label * 8 : 10 + label * 8, 5:19] = 10.0
    config = FeatureConfig()
    pipeline = Pipeline(
        [("scale", StandardScaler()), ("svm", SVC(probability=True, random_state=42))]
    ).fit(extract_feature_matrix(frames, config), labels)
    joblib.dump(
        {
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
            "label_id_to_name_zh": {
                0: "仰卧",
                1: "俯卧",
                2: "左侧卧",
                3: "右侧卧",
            },
            "pipeline": pipeline,
        },
        path,
    )
    return frames


class FeatureTests(unittest.TestCase):
    def test_features_are_finite_and_have_stable_dimensions(self) -> None:
        frame = np.zeros((44, 24), dtype=np.float32)
        frame[8:36, 6:18] = 10.0
        single = extract_frame_features(frame)
        batch = extract_feature_matrix(np.stack([frame, frame]))
        self.assertEqual(single.shape, (997,))
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
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.joblib"
            frames = _build_test_model(path)
            result = PostureSVMClassifier(path).predict(frames[0])
        self.assertIn(result.label_id, range(4))
        self.assertAlmostEqual(sum(result.probabilities.values()), 1.0, places=6)

    def test_direct_training_cli_runs_on_documented_text_format(self) -> None:
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
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TRAIN_SCRIPT),
                    "--dataset-dir",
                    str(dataset_dir),
                    "--model-path",
                    str(model_path),
                    "--jitter-copies",
                    "0",
                    "--n-jobs",
                    "1",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(model_path.is_file())
            self.assertTrue(model_path.with_suffix(".metrics.json").is_file())
            metrics = json.loads(model_path.with_suffix(".metrics.json").read_text("utf-8"))
            prediction = PostureSVMClassifier(model_path).predict(frame)
            self.assertEqual(len(metrics["train_subjects"]), 4)
            self.assertEqual(len(metrics["test_subjects"]), 2)
            self.assertIn(prediction.label_id, range(4))


class InferenceCliTests(unittest.TestCase):
    def test_direct_inference_cli_supports_single_and_all_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.joblib"
            frames = _build_test_model(model_path)
            input_path = root / "subject_1.txt"
            input_path.write_text(
                "\n\n".join(
                    "\n".join(",".join(str(value) for value in row) for row in frame)
                    for frame in frames[:2]
                ),
                encoding="utf-8",
            )

            single = subprocess.run(
                [
                    sys.executable,
                    str(INFERENCE_SCRIPT),
                    "--input-file",
                    str(input_path),
                    "--model-path",
                    str(model_path),
                    "--frame-index",
                    "1",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            batch = subprocess.run(
                [
                    sys.executable,
                    str(INFERENCE_SCRIPT),
                    "--input-file",
                    str(input_path),
                    "--model-path",
                    str(model_path),
                    "--all-frames",
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(single.returncode, 0, single.stderr)
        self.assertEqual(batch.returncode, 0, batch.stderr)
        single_payload = json.loads(single.stdout)
        batch_payload = json.loads(batch.stdout)
        self.assertEqual(single_payload["frame_index"], 1)
        self.assertEqual(batch_payload["frame_count"], 2)
        self.assertEqual(len(batch_payload["predictions"]), 2)


if __name__ == "__main__":
    unittest.main()
