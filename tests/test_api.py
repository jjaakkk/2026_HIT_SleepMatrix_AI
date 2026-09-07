"""HTTP API tests that do not require a trained model."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

from backend import config
from backend.algorithms.body_partition import api as bp_api
from backend.algorithms.posture_cnn.model import build_model
from backend.api_utils import LazyModelLoader
from backend.app import create_app
from backend.data_utils.contracts import MATRIX_SHAPE
from backend.data_utils.predictions import PosturePrediction


def _synthetic_cnn_checkpoint(
    path: Path,
    class_names: list[str] | None = None,
) -> Path:
    """Save a minimal but loadable CNN checkpoint."""

    names = list(class_names) if class_names is not None else [
        "仰卧", "俯卧", "左侧卧", "右侧卧",
    ]
    torch.save(
        {
            "model_state": build_model(num_classes=len(names)).state_dict(),
            "class_names": names,
            "normalization": {"mean": 0.0, "std": 1.0},
            "dropout": 0.3,
        },
        path,
    )
    return path


class _FakeSvmClassifier:
    """Stub returning a fixed contract-shaped prediction."""

    def predict(self, matrix: np.ndarray) -> PosturePrediction:
        return PosturePrediction(
            label_id=2,
            label="left_lateral",
            label_zh="左侧卧",
            confidence=0.7,
            probabilities={
                "supine": 0.1,
                "prone": 0.1,
                "left_lateral": 0.7,
                "right_lateral": 0.1,
            },
        )


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_health_reports_missing_optional_model(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertFalse(response.json["posture_svm"]["model_available"])

    def test_posture_contract_is_available_to_frontend(self) -> None:
        response = self.client.get("/api/contracts/posture")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["contract_version"], "1.1")
        self.assertEqual(response.json["pressure_matrix"]["rows"], 44)
        self.assertEqual(response.json["pressure_matrix"]["columns"], 24)

    def test_prediction_validates_shape_before_loading_model(self) -> None:
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": [[0.0]]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")


class BodyPartitionApiTests(unittest.TestCase):
    """Body-partition endpoints with missing resources or invalid requests."""

    def setUp(self) -> None:
        missing = config.PROJECT_ROOT / "does-not-exist"
        patchers = [
            mock.patch.object(bp_api, "MODEL_PATH", missing / "model.pth"),
            mock.patch.object(bp_api, "DATASET_PATH", missing / "data.json"),
            mock.patch.object(bp_api, "METRICS_PATH", missing / "metrics.json"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_health_reports_resource_state(self) -> None:
        response = self.client.get("/api/body-partition/health")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["model_available"])
        self.assertFalse(response.json["dataset_available"])

    def test_metrics_missing_returns_404(self) -> None:
        response = self.client.get("/api/body-partition/metrics")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json["error"], "metrics_unavailable")

    def test_catalog_missing_dataset_returns_503(self) -> None:
        response = self.client.get("/api/body-partition/catalog")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "dataset_unavailable")

    def test_sample_requires_subject_and_action(self) -> None:
        response = self.client.get("/api/body-partition/sample")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_predict_validates_matrix_shape(self) -> None:
        response = self.client.post(
            "/api/body-partition/predict",
            json={"pressure_matrix": [[0.0]]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_predict_missing_model_returns_503(self) -> None:
        frame = np.zeros(MATRIX_SHAPE, dtype=float).tolist()
        response = self.client.post(
            "/api/body-partition/predict",
            json={"pressure_matrix": frame},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "model_unavailable")


@unittest.skipUnless(
    bp_api.MODEL_PATH.is_file(),
    "trained body-partition model not available",
)
class BodyPartitionModelApiTests(unittest.TestCase):
    """Positive-path tests using the committed production model artifact."""

    def setUp(self) -> None:
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_predict_returns_five_regions_and_mask(self) -> None:
        rng = np.random.default_rng(0)
        frame = np.zeros(MATRIX_SHAPE)
        frame[10:30, 6:18] = rng.uniform(50, 200, size=(20, 12))
        response = self.client.post(
            "/api/body-partition/predict",
            json={"pressure_matrix": frame.tolist()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["mask"]), MATRIX_SHAPE[0])
        self.assertEqual(len(response.json["mask"][0]), MATRIX_SHAPE[1])
        self.assertEqual(len(response.json["regions"]), 5)

    def test_metrics_endpoint_serves_training_report(self) -> None:
        if not bp_api.METRICS_PATH.is_file():
            self.skipTest("training metrics not available")
        response = self.client.get("/api/body-partition/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json["metrics"]["pixel_accuracy"], 0.95)


class UnifiedHealthApiTests(unittest.TestCase):
    """Aggregated health endpoint."""

    def setUp(self) -> None:
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_health_reports_all_modules(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json
        # Legacy top-level key stays for the existing frontend.
        self.assertFalse(payload["posture_svm"]["model_available"])
        models = payload["models"]
        for name in ("posture_svm", "posture_cnn", "body_partition", "weak_area_enhance"):
            self.assertIn(name, models)
        self.assertTrue(models["weak_area_enhance"]["available"])
        self.assertIn("model_available", models["posture_cnn"])
        self.assertIn("dataset_available", models["body_partition"])


class PostureModelSelectionApiTests(unittest.TestCase):
    """Model selection on /api/posture/predict without usable artifacts."""

    def setUp(self) -> None:
        self.client = create_app(
            "model-does-not-exist.joblib",
            posture_cnn_model_path="missing-cnn.pt",
        ).test_client()

    def test_cnn_model_missing_returns_503(self) -> None:
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "cnn"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "model_unavailable")

    def test_unknown_model_returns_400(self) -> None:
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "svm2"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_ensemble_without_any_model_returns_503(self) -> None:
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "ensemble"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "model_unavailable")


class PostureModelStubApiTests(unittest.TestCase):
    """Model-selection paths with a stubbed SVM / synthetic CNN checkpoint."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.cnn_path = _synthetic_cnn_checkpoint(
            Path(self.tmpdir.name) / "best_model.pt"
        )
        self.app = create_app(
            "model-does-not-exist.joblib",
            posture_cnn_model_path=self.cnn_path,
            posture_cnn_device="cpu",
        )
        self.client = self.app.test_client()

    def _install_svm_stub(self) -> None:
        self.app.extensions["posture_svm_classifier"] = LazyModelLoader(
            Path("unused.joblib"), lambda path: _FakeSvmClassifier()
        )

    def test_cnn_prediction_uses_contract_shape(self) -> None:
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "cnn"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["model"], "cnn")
        self.assertIn(payload["label_id"], range(4))
        self.assertIn("supine", payload["probabilities"])
        self.assertIn("label_zh", payload)

    def test_default_model_is_svm_with_stub(self) -> None:
        self._install_svm_stub()
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist()},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["model"], "svm")
        self.assertEqual(response.json["label"], "left_lateral")

    def test_ensemble_uses_both_models(self) -> None:
        self._install_svm_stub()
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "ensemble"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["model"], "ensemble")
        self.assertIn(payload["label_id"], range(4))
        self.assertAlmostEqual(sum(payload["probabilities"].values()), 1.0, places=5)

    def test_ensemble_falls_back_to_svm_when_cnn_missing(self) -> None:
        self.app.extensions["posture_cnn_classifier"] = LazyModelLoader(
            Path("missing-cnn.pt"),
            lambda path: (_ for _ in ()).throw(FileNotFoundError(path)),
        )
        self._install_svm_stub()
        response = self.client.post(
            "/api/posture/predict",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(), "model": "ensemble"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["model"], "svm")


class WeakEnhanceApiTests(unittest.TestCase):
    """Weak-pressure enhancement endpoints (no model required)."""

    def setUp(self) -> None:
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_enhance_returns_same_shape_matrix(self) -> None:
        frame = np.zeros(MATRIX_SHAPE).tolist()
        response = self.client.post("/api/weak-enhance", json={"pressure_matrix": frame})
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(len(payload["enhanced_matrix"]), MATRIX_SHAPE[0])
        self.assertEqual(len(payload["enhanced_matrix"][0]), MATRIX_SHAPE[1])
        self.assertAlmostEqual(payload["config_used"]["gamma"], 0.55, places=6)

    def test_enhance_rejects_bad_shape(self) -> None:
        response = self.client.post(
            "/api/weak-enhance", json={"pressure_matrix": [[0.0]]}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_enhance_rejects_invalid_config_value(self) -> None:
        response = self.client.post(
            "/api/weak-enhance",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "config": {"gamma": 2.0},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_enhance_rejects_unknown_config_key(self) -> None:
        response = self.client.post(
            "/api/weak-enhance",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "config": {"nope": 1},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_enhance_accepts_valid_override(self) -> None:
        response = self.client.post(
            "/api/weak-enhance",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "config": {"gamma": 0.6},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.json["config_used"]["gamma"], 0.6, places=6)

    def test_default_config_endpoint(self) -> None:
        response = self.client.get("/api/weak-enhance/config")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gamma", response.json)
        self.assertIn("strength", response.json)


class AnalyzeApiTests(unittest.TestCase):
    """Aggregated /api/frame/analyze endpoint with graceful degradation."""

    def setUp(self) -> None:
        missing = config.PROJECT_ROOT / "does-not-exist"
        patchers = [
            mock.patch.object(bp_api, "MODEL_PATH", missing / "model.pth"),
            mock.patch.object(bp_api, "DATASET_PATH", missing / "data.json"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = create_app(
            "model-does-not-exist.joblib",
            posture_cnn_model_path=missing / "cnn.pt",
        )
        self.client = self.app.test_client()

    def test_analyze_reports_module_errors_but_runs_enhance(self) -> None:
        response = self.client.post(
            "/api/frame/analyze",
            json={"pressure_matrix": np.zeros(MATRIX_SHAPE).tolist()},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["posture"]["error"], "model_unavailable")
        self.assertEqual(payload["partition"]["error"], "model_unavailable")
        self.assertIn("enhanced_matrix", payload["enhanced"])

    def test_analyze_features_subset(self) -> None:
        response = self.client.post(
            "/api/frame/analyze",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "features": ["enhance"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("posture", response.json)
        self.assertNotIn("partition", response.json)
        self.assertIn("enhanced", response.json)

    def test_analyze_rejects_unknown_feature(self) -> None:
        response = self.client.post(
            "/api/frame/analyze",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "features": ["magic"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "invalid_request")

    def test_analyze_posture_uses_stubbed_svm(self) -> None:
        self.app.extensions["posture_svm_classifier"] = LazyModelLoader(
            Path("unused.joblib"), lambda path: _FakeSvmClassifier()
        )
        response = self.client.post(
            "/api/frame/analyze",
            json={
                "pressure_matrix": np.zeros(MATRIX_SHAPE).tolist(),
                "features": ["posture"],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["posture"]["model"], "svm")
        self.assertEqual(
            response.json["posture"]["prediction"]["label"], "left_lateral"
        )


if __name__ == "__main__":
    unittest.main()
