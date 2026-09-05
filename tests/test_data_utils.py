"""Tests for shared contracts, dataset parsing and augmentation."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from backend.data_utils.contracts import (
    ACTION_TO_LABEL,
    CONTRACT_PATH,
    CONTRACT_VERSION,
    LABEL_ID_TO_NAME,
    MATRIX_SHAPE,
    action_to_label,
)
from backend.data_utils.data_augmentation import augment_training_frames
from backend.data_utils.data_loader import (
    DatasetFormatError,
    iter_pressure_frames,
    parse_file_identity,
)


class SharedContractTests(unittest.TestCase):
    def test_contract_defines_documented_matrix_and_postures(self) -> None:
        self.assertEqual(MATRIX_SHAPE, (44, 24))
        self.assertEqual(CONTRACT_VERSION, "1.1")
        self.assertEqual(
            LABEL_ID_TO_NAME,
            {0: "supine", 1: "prone", 2: "left_lateral", 3: "right_lateral"},
        )
        self.assertEqual(set(ACTION_TO_LABEL), set(range(1, 22)))
        self.assertTrue(CONTRACT_PATH.is_file())

    def test_json_schema_dimensions_match_posture_contract(self) -> None:
        schema_path = CONTRACT_PATH.with_name("pressure-frame.schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["minItems"], MATRIX_SHAPE[0])
        self.assertEqual(schema["maxItems"], MATRIX_SHAPE[0])
        self.assertEqual(schema["items"]["minItems"], MATRIX_SHAPE[1])
        self.assertEqual(schema["items"]["maxItems"], MATRIX_SHAPE[1])

    def test_action_ranges_map_to_four_postures(self) -> None:
        self.assertEqual([action_to_label(value) for value in (1, 6)], [0, 0])
        self.assertEqual([action_to_label(value) for value in (7, 9)], [1, 1])
        self.assertEqual([action_to_label(value) for value in (10, 15)], [2, 2])
        self.assertEqual([action_to_label(value) for value in (16, 21)], [3, 3])
        with self.assertRaises(ValueError):
            action_to_label(22)


class FilenameAndRawFrameTests(unittest.TestCase):
    def test_filename_parser_supports_documented_suffixes(self) -> None:
        self.assertEqual(parse_file_identity("participant_a_1.txt").subject_id, "participant_a")
        identity = parse_file_identity("张三21.txt")
        self.assertEqual(identity.subject_id, "张三")
        self.assertEqual(identity.action_id, 21)

    def test_frames_can_be_adjacent_without_blank_line(self) -> None:
        row = ",".join(str(value) for value in range(24))
        content = "\n".join([row] * 88)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subject_1.txt"
            path.write_text(content, encoding="utf-8")
            frames = list(iter_pressure_frames(path))
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].shape, MATRIX_SHAPE)

    def test_invalid_column_count_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "subject_1.txt"
            path.write_text("1,2,3\n", encoding="utf-8")
            with self.assertRaises(DatasetFormatError):
                list(iter_pressure_frames(path))


class DataAugmentationTests(unittest.TestCase):
    def test_horizontal_mirror_swaps_lateral_label_and_action(self) -> None:
        frames = np.arange(12, dtype=np.float32).reshape(1, 3, 4)
        augmented = augment_training_frames(
            frames,
            labels=np.asarray([2]),
            subjects=np.asarray(["subject"]),
            actions=np.asarray([10]),
            jitter_copies=0,
            include_horizontal_mirror=True,
        )
        result_frames, result_labels, _, result_actions = augmented
        np.testing.assert_array_equal(result_frames[1], np.fliplr(frames[0]))
        self.assertEqual(result_labels.tolist(), [2, 3])
        self.assertEqual(result_actions.tolist(), [10, 16])


if __name__ == "__main__":
    unittest.main()
