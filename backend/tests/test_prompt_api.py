"""Unit tests for prompt-stage mixins with a fake Gemini client.

These tests are deterministic and do not require network/API access.
"""

from __future__ import annotations

import struct
import sys
import unittest
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ApiScripts.mainPrompt import MainPromptMixin
from ApiScripts.diagramPrompt import DiagramPromptMixin
from ApiScripts.textToVoice import TTSMixin
from ApiScripts.updatePrompt import StateUpdateMixin
from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME


def _build_png_bytes(width: int = 64, height: int = 64) -> bytes:
    # Generate a simple opaque RGB gradient PNG using only stdlib modules.
    def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        return struct.pack("!I", len(payload)) + chunk_type + payload + struct.pack("!I", crc)

    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive integers")

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_payload = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)

    rows: list[bytes] = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            red = int(255 * x / max(width - 1, 1))
            green = int(255 * y / max(height - 1, 1))
            blue = 96
            row.extend((red, green, blue))
        rows.append(b"\x00" + bytes(row))

    idat_payload = zlib.compress(b"".join(rows), level=9)
    return (
        signature
        + _chunk(b"IHDR", ihdr_payload)
        + _chunk(b"IDAT", idat_payload)
        + _chunk(b"IEND", b"")
    )


PNG_BYTES = _build_png_bytes()


class FakeFiles:
    def upload(self, *, file):
        return SimpleNamespace(name=f"upload::{Path(file).name}", state="ACTIVE")

    def get(self, *, name):
        return SimpleNamespace(name=name, state="ACTIVE")


class FakeModels:
    def generate_content(self, *, model, contents, config=None):
        response_modalities = [
            str(modality).upper() for modality in (getattr(config, "response_modalities", None) or [])
        ]
        if "AUDIO" in response_modalities:
            inline_data = SimpleNamespace(data=b"RIFFfake-audio", mime_type="audio/wav")
            return SimpleNamespace(
                text=None,
                parts=[SimpleNamespace(text=None, inline_data=inline_data)],
            )

        if "IMAGE" in response_modalities:
            inline_data = SimpleNamespace(data=PNG_BYTES, mime_type="image/png")
            response_text = f"fake diagram from {model}"
            return SimpleNamespace(
                text=response_text,
                parts=[
                    SimpleNamespace(text=response_text, inline_data=None),
                    SimpleNamespace(text=None, inline_data=inline_data),
                ],
            )

        response_text = f"fake response from {model}"
        return SimpleNamespace(
            text=response_text,
            parts=[SimpleNamespace(text=response_text, inline_data=None)],
        )


class FakeClient:
    def __init__(self):
        self.files = FakeFiles()
        self.models = FakeModels()


class PromptHarness(MainPromptMixin, DiagramPromptMixin, StateUpdateMixin, TTSMixin):
    def __init__(self, task_states_dir: Path, output_dir: Path):
        self.text_model = "fake-text-model"
        self.vision_model = "fake-vision-model"
        self.voice_model = "fake-voice-model"
        self.voice_name = DEFAULT_VOICE_NAME
        self.output_dir = output_dir
        self.diagram_output_dir = output_dir.parent / "generated_diagrams"
        self.task_states_dir = task_states_dir
        self.client = FakeClient()
        self.image_paths = []
        self.task_image_paths = []
        self.prompt_number = None
        self.prompt_text = ""
        self.text_source_1 = ""
        self.text_source_2 = ""
        self.task_name = None
        self.task_status = ""
        self.selected_model = ""

    def get_client(self):
        return self.client


def _write_png(image_path: Path) -> None:
    image_path.write_bytes(PNG_BYTES)


def _seed_task(task_states_dir: Path, task_name: str, status: str) -> None:
    task_dir = task_states_dir / task_name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "text1.txt").write_text(f"{status}\n", encoding="utf-8")


class PromptHarnessUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.harness = PromptHarness(
            task_states_dir=self.root,
            output_dir=self.root / "generated_audio",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_first_prompt_uses_vision_model_with_images(self) -> None:
        image_path = self.root / "diagram.png"
        _write_png(image_path)
        _seed_task(self.root, "task1", "X part broken")

        result = self.harness.run_first_prompt(
            image_paths=[image_path],
            text_source_1="source one",
            text_source_2="source two",
            task_name="task1",
        )

        self.assertEqual(result["task_status"], "X part broken")
        self.assertEqual(result["selected_model"], "fake-vision-model")
        self.assertEqual(result["response_text"], "fake response from fake-vision-model")
        self.assertEqual(len(result["image_paths"]), 1)

    def test_run_second_prompt_returns_generated_diagram(self) -> None:
        image_path = self.root / "photo.png"
        _write_png(image_path)
        _seed_task(self.root, "task1", "current task state")

        result = self.harness.run_second_prompt(
            first_prompt_response="Add a label and arrow",
            task_name="task1",
            text_source_1="current task state",
            text_source_2="spoken user input",
            image_paths=[image_path],
            mode="text",
            diagram_source="user",
        )

        diagram_path = Path(str(result["diagram_image_path"]))
        self.assertTrue(diagram_path.exists())
        self.assertEqual(result["selected_model"], "fake-vision-model")
        self.assertEqual(result["diagram_source"], "user")
        self.assertEqual(result["diagram_mime_type"], "image/png")

    def test_run_second_prompt_normalizes_diagram_source_alias(self) -> None:
        image_path = self.root / "photo.png"
        _write_png(image_path)

        result = self.harness.run_second_prompt(
            first_prompt_response="Mark the component",
            image_paths=[image_path],
            diagram_source="schematics",
        )

        self.assertEqual(result["diagram_source"], "schematic")

    def test_diagram_prompt_payload_includes_overlay_requirements(self) -> None:
        self.harness.prompt_text = "Make a guidance image"
        self.harness.text_source_1 = "Context"
        self.harness.text_source_2 = "User update"
        self.harness.task_name = "task1"
        self.harness.task_status = "X part broken"
        self.harness.image_paths = [self.root / "placeholder.png"]
        self.harness.diagram_source = "user"

        payload = self.harness._build_diagram_prompt_payload("Tighten screw A")

        self.assertIn("Primary image-editing target: the technician-provided photo", payload)
        self.assertIn("Overlay requirements", payload)
        self.assertIn("arrows", payload)
        self.assertIn("labels", payload)

    def test_run_third_prompt_writes_audio_file(self) -> None:
        result = self.harness.run_third_prompt("Tighten the loose bracket.")
        audio_path = Path(str(result["audio_path"]))

        self.assertTrue(audio_path.exists())
        self.assertEqual(audio_path.read_bytes(), b"RIFFfake-audio")
        self.assertEqual(result["audio_mime_type"], "audio/wav")

    def test_run_fourth_prompt_writes_task_status_file(self) -> None:
        result = self.harness.run_fourth_prompt("task4", "Replace the bent pin")
        status_path = self.root / "task4" / "text1.txt"

        self.assertTrue(status_path.exists())
        self.assertEqual(status_path.read_text(encoding="utf-8").strip(), "Replace the bent pin")
        self.assertEqual(result["task_status"], "Replace the bent pin")


if __name__ == "__main__":
    unittest.main()