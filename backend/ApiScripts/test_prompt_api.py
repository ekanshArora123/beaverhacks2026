"""Smoke-test one callable function for each backend prompt stage."""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from promptScripts.diagramPrompt import MainPromptMixin
from promptScripts.mainPrompt import SecondPromptMixin
from promptScripts.textToVoice import TTSMixin
from promptScripts.updatePrompt import StateUpdateMixin


PNG_BYTES = b"\x89PNG\r\n\x1a\n"


class SkipTest(Exception):
    pass


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

        response_text = f"fake response from {model}"
        return SimpleNamespace(
            text=response_text,
            parts=[SimpleNamespace(text=response_text, inline_data=None)],
        )


class FakeClient:
    def __init__(self):
        self.files = FakeFiles()
        self.models = FakeModels()


class PromptHarness(MainPromptMixin, StateUpdateMixin, TTSMixin):
    def __init__(self, task_states_dir: Path, output_dir: Path):
        self.text_model = "fake-text-model"
        self.vision_model = "fake-vision-model"
        self.voice_model = "fake-voice-model"
        self.voice_name = "charon"
        self.output_dir = output_dir
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


def _call_with_supported_kwargs(func, **kwargs):
    signature = inspect.signature(func)
    supports_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
    )
    if supports_var_kwargs:
        supported_kwargs = kwargs
    else:
        supported_kwargs = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return func(**supported_kwargs)


def test_prompt_1_run_first_prompt() -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        image_path = root / "diagram.png"
        _write_png(image_path)
        _seed_task(root, "task1", "X part broken")

        harness = PromptHarness(task_states_dir=root, output_dir=root / "generated_audio")
        result = harness.run_first_prompt(
            image_paths=[image_path],
            text_source_1="source one",
            text_source_2="source two",
            task_name="task1",
        )

        assert result["selected_model"] == "fake-vision-model"
        assert result["task_status"] == "X part broken"
        assert result["response_text"] == "fake response from fake-vision-model"
        return {
            "selected_model": str(result["selected_model"]),
            "response_text": str(result["response_text"]),
        }


def test_prompt_2_run_second_prompt() -> dict[str, str]:
    second_prompt_module = importlib.import_module("promptScripts.mainPrompt")
    second_prompt_mixin = getattr(second_prompt_module, "SecondPromptMixin", None)
    if second_prompt_mixin is None or not hasattr(second_prompt_mixin, "run_second_prompt"):
        raise SkipTest("promptScripts.mainPrompt does not define SecondPromptMixin.run_second_prompt yet.")

    prompt_two_harness_class = type("PromptTwoHarness", (second_prompt_mixin, PromptHarness), {})

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        image_path = root / "diagram.png"
        _write_png(image_path)
        _seed_task(root, "task1", "current task state")

        harness = prompt_two_harness_class(task_states_dir=root, output_dir=root / "generated_audio")
        result = _call_with_supported_kwargs(
            harness.run_second_prompt,
            first_prompt_response="diagram labels and arrows",
            task_name="task1",
            text_source_1="current task state",
            text_source_2="spoken user input",
            image_paths=[image_path],
            mode="text",
        )

        if not isinstance(result, dict):
            raise AssertionError("run_second_prompt must return a dict.")

        return {
            "result_keys": ", ".join(sorted(str(key) for key in result.keys())) or "<empty>",
        }


def test_prompt_3_run_third_prompt() -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        harness = PromptHarness(task_states_dir=root / "taskStates", output_dir=root / "generated_audio")
        result = harness.run_third_prompt("Tighten the loose bracket.")
        audio_path = Path(str(result["audio_path"]))

        assert audio_path.exists()
        assert audio_path.read_bytes() == b"RIFFfake-audio"
        assert result["audio_mime_type"] == "audio/wav"
        return {
            "audio_path": str(audio_path),
            "audio_mime_type": str(result["audio_mime_type"]),
        }


def test_prompt_4_run_fourth_prompt() -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        harness = PromptHarness(task_states_dir=root / "taskStates", output_dir=root / "generated_audio")
        result = harness.run_fourth_prompt("task4", "Replace the bent pin")
        status_path = root / "taskStates" / "task4" / "text1.txt"

        assert status_path.exists()
        assert status_path.read_text(encoding="utf-8").strip() == "Replace the bent pin"
        assert result["task_status"] == "Replace the bent pin"
        return {
            "status_file": str(status_path),
            "task_status": str(result["task_status"]),
        }


TESTS = {
    "1": ("prompt1.run_first_prompt", test_prompt_1_run_first_prompt),
    "2": ("prompt2.run_second_prompt", test_prompt_2_run_second_prompt),
    "3": ("prompt3.run_third_prompt", test_prompt_3_run_third_prompt),
    "4": ("prompt4.run_fourth_prompt", test_prompt_4_run_fourth_prompt),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one smoke test per prompt stage.")
    parser.add_argument(
        "--prompt",
        choices=["all", *TESTS.keys()],
        default="all",
        help="Run a single prompt test or the full set.",
    )
    args = parser.parse_args()

    selected_prompts = TESTS.keys() if args.prompt == "all" else [args.prompt]
    failures = 0

    for prompt_key in selected_prompts:
        label, test_func = TESTS[prompt_key]
        try:
            details = test_func()
        except SkipTest as exc:
            print(f"[SKIP] {label}: {exc}")
            continue
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
            continue

        print(f"[PASS] {label}: {json.dumps(details, sort_keys=True)}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())