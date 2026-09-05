from __future__ import annotations

import importlib.util
import unittest


TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(TORCH_AVAILABLE, "需要安装 PyTorch")
class ModelTests(unittest.TestCase):
    def test_output_shape(self):
        import torch

        from backend.algorithms.posture_cnn.model import build_model

        model = build_model()
        outputs = model(torch.randn(8, 1, 44, 24))
        self.assertEqual(tuple(outputs.shape), (8, 4))


if __name__ == "__main__":
    unittest.main()
