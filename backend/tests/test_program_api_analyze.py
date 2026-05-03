"""Unit tests for /analyze and /prompts/2 API behavior."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import programAPI
from test_prompt_api import PNG_BYTES


class FakeSequenceBackend:
    DIAGRAM_B64 = "ZmFrZS1hbm5vdGF0ZWQtaW1hZ2U="

    def __init__(self):
        self.text_model = "fake-text-model"
        self.vision_model = "fake-vision-model"
        self.voice_model = "fake-voice-model"
        self.voice_name = "charon"
        self.run_first_calls: list[dict[str, object]] = []
        self.run_second_calls: list[dict[str, object]] = []

    def run_first_prompt(self, **kwargs):
        self.run_first_calls.append(kwargs)
        return {
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "voice_model": self.voice_model,
            "selected_model": self.vision_model,
            "response_text": "Inspect the highlighted connector first.",
            "task_status": None,
            "image_paths": [str(path) for path in kwargs.get("image_paths", [])],
        }

    def run_second_prompt(self, **kwargs):
        self.run_second_calls.append(kwargs)
        return {
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "voice_model": self.voice_model,
            "selected_model": self.vision_model,
            "response_text": "Annotated the image with arrow and label for connector A.",
            "diagram_mime_type": "image/png",
            "diagram_image_base64": self.DIAGRAM_B64,
            "diagram_source": kwargs.get("diagram_source"),
            "image_paths": [str(path) for path in kwargs.get("image_paths", [])],
        }


class AnalyzeEndpointUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        programAPI.app.testing = True
        self.client = programAPI.app.test_client()

    def _post_analyze(
        self,
        backend: FakeSequenceBackend,
        *,
        diagram_source: str,
        schematic_path: Path | None = None,
    ):
        data: dict[str, object] = {
            "text_source_2": "Tighten the top-left bolt.",
            "diagram_source": diagram_source,
            "files": (io.BytesIO(PNG_BYTES), "capture.png"),
        }
        if schematic_path is not None:
            data["image_paths"] = str(schematic_path)

        with patch.object(programAPI, "create_sequence_backend", return_value=backend):
            return self.client.post(
                "/analyze",
                data=data,
                content_type="multipart/form-data",
            )

    def test_analyze_runs_prompt_1_then_prompt_2_and_returns_annotated_image(self) -> None:
        backend = FakeSequenceBackend()
        response = self._post_analyze(backend, diagram_source="user")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        assert payload is not None

        self.assertEqual(payload.get("text"), "Annotated the image with arrow and label for connector A.")
        self.assertEqual(payload.get("image"), FakeSequenceBackend.DIAGRAM_B64)
        self.assertEqual(payload.get("image_mime"), "image/png")
        self.assertEqual(payload.get("user_input_text"), "Tighten the top-left bolt.")

        self.assertEqual(len(backend.run_first_calls), 1)
        self.assertEqual(len(backend.run_second_calls), 1)

        second_call = backend.run_second_calls[0]
        self.assertEqual(second_call.get("diagram_source"), "user")
        second_paths = second_call.get("image_paths")
        self.assertIsInstance(second_paths, list)
        assert isinstance(second_paths, list)
        self.assertEqual(len(second_paths), 1)
        self.assertTrue(Path(str(second_paths[0])).name.startswith("upload_"))

    def test_analyze_uses_schematic_image_when_diagram_source_is_schematic(self) -> None:
        backend = FakeSequenceBackend()
        with TemporaryDirectory() as temp_dir:
            schematic_path = Path(temp_dir) / "schematic.png"
            schematic_path.write_bytes(PNG_BYTES)

            response = self._post_analyze(
                backend,
                diagram_source="schematic",
                schematic_path=schematic_path,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(backend.run_first_calls), 1)
        self.assertEqual(len(backend.run_second_calls), 1)

        first_call = backend.run_first_calls[0]
        first_paths = first_call.get("image_paths")
        self.assertIsInstance(first_paths, list)
        assert isinstance(first_paths, list)
        self.assertEqual(len(first_paths), 2)

        second_call = backend.run_second_calls[0]
        self.assertEqual(second_call.get("diagram_source"), "schematic")
        second_paths = second_call.get("image_paths")
        self.assertIsInstance(second_paths, list)
        assert isinstance(second_paths, list)
        self.assertEqual(len(second_paths), 1)
        self.assertEqual(Path(str(second_paths[0])).resolve(), schematic_path.resolve())

    def test_prompts_2_endpoint_passes_through_diagram_source(self) -> None:
        backend = FakeSequenceBackend()
        data = {
            "first_prompt_response": "Point to connector A",
            "text_source_2": "Do this now",
            "diagram_source": "schematic",
            "files": (io.BytesIO(PNG_BYTES), "capture.png"),
        }

        with patch.object(programAPI, "create_sequence_backend", return_value=backend):
            response = self.client.post(
                "/prompts/2",
                data=data,
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(backend.run_second_calls), 1)
        self.assertEqual(backend.run_second_calls[0].get("diagram_source"), "schematic")


if __name__ == "__main__":
    unittest.main()
