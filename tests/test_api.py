"""HTTP API tests that do not require a trained model."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from backend import config
from backend.app import create_app
from backend.data_utils.contracts import MATRIX_SHAPE


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
            mock.patch.object(config, "BODY_PARTITION_MODEL_PATH", missing / "model.pth"),
            mock.patch.object(config, "BODY_PARTITION_DATASET_PATH", missing / "data.json"),
            mock.patch.object(config, "BODY_PARTITION_METRICS_PATH", missing / "metrics.json"),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = create_app("model-does-not-exist.joblib").test_client()

    def test_health_reports_body_partition_block(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        block = response.json["body_partition"]
        self.assertFalse(block["model_available"])
        self.assertFalse(block["dataset_available"])

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
    config.BODY_PARTITION_MODEL_PATH.is_file(),
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
        if not config.BODY_PARTITION_METRICS_PATH.is_file():
            self.skipTest("training metrics not available")
        response = self.client.get("/api/body-partition/metrics")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json["metrics"]["pixel_accuracy"], 0.95)


if __name__ == "__main__":
    unittest.main()
