"""HTTP API tests that do not require a trained model."""

from __future__ import annotations

import unittest

from backend.app import create_app


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


if __name__ == "__main__":
    unittest.main()
