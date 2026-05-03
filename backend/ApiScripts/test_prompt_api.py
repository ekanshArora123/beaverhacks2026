"""Smoke-test one callable function for each backend prompt stage.

Always runs real Gemini calls across all prompt stages.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import sys
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
from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe5'\xd4\xa2"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def _load_repo_key() -> str | None:
    keys_path = BACKEND_DIR.parent / "keys.py"
    if not keys_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("workspace_keys", keys_path)
    if spec is None or spec.loader is None:
        return None

    keys_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keys_module)
    return getattr(keys_module, "GEMINI_KEY", None)


def _load_env_file_key() -> str | None:
    env_path = BACKEND_DIR.parent / "keys.env"
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        candidate = line
        if line.startswith("GEMINI_API_KEY="):
            candidate = line.split("=", 1)[1].strip()

        if candidate.startswith('"') and candidate.endswith('"') and len(candidate) >= 2:
            candidate = candidate[1:-1]
        elif candidate.startswith("'") and candidate.endswith("'") and len(candidate) >= 2:
            candidate = candidate[1:-1]

        if candidate:
            return candidate

    return None


def _load_api_key() -> str:
    api_key = _load_env_file_key() or os.environ.get("GEMINI_API_KEY") or _load_repo_key()
    if not api_key:
        raise RuntimeError(
            "Set GEMINI_API_KEY, or add GEMINI_API_KEY to keys.env, or define GEMINI_KEY in keys.py before running --real tests."
        )
    return api_key


def _assert_non_empty_response(result: dict[str, str | int | list[str] | None], *, real_mode: bool) -> str:
    response_text = str(result.get("response_text") or "").strip()
    if not response_text:
        raise AssertionError("Gemini returned an empty response_text.")

    if real_mode and response_text.startswith("fake response from"):
        raise AssertionError("Expected a real Gemini response, but fake response text was returned.")

    return response_text


def _print_stage_output(label: str, details: dict[str, str]) -> None:
    print(f"[OUTPUT] {label}")
    print(json.dumps(details, indent=2, sort_keys=True))


class PromptHarness(MainPromptMixin, DiagramPromptMixin, StateUpdateMixin, TTSMixin):
    def __init__(self, task_states_dir: Path, output_dir: Path, *, use_real_client: bool = False):
        self.text_model = TEXT_MODEL if use_real_client else "fake-text-model"
        self.vision_model = VISION_MODEL if use_real_client else "fake-vision-model"
        self.voice_model = VOICE_MODEL if use_real_client else "fake-voice-model"
        self.voice_name = DEFAULT_VOICE_NAME
        self.output_dir = output_dir
        self.diagram_output_dir = output_dir.parent / "generated_diagrams"
        self.task_states_dir = task_states_dir
        self.client = None if use_real_client else FakeClient()
        self.use_real_client = use_real_client
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
        if self.client is None:
            from google import genai

            self.client = genai.Client(api_key=_load_api_key())
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


def test_prompt_1_run_first_prompt(settings: SimpleNamespace) -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        image_path = root / "diagram.png"
        _write_png(image_path)
        _seed_task(root, "task1", "X part broken")

        harness = PromptHarness(
            task_states_dir=root,
            output_dir=root / "generated_audio",
            use_real_client=settings.real,
        )
        image_paths = [] if settings.real else [image_path]
        result = harness.run_first_prompt(
            image_paths=image_paths,
            text_source_1="source one",
            text_source_2="source two",
            task_name="task1",
        )

        assert result["task_status"] == "X part broken"
        if settings.real:
            response_text = _assert_non_empty_response(result, real_mode=True)
            selected_model = str(result.get("selected_model") or "")
        else:
            assert result["selected_model"] == "fake-vision-model"
            assert result["response_text"] == "fake response from fake-vision-model"
            response_text = str(result["response_text"])
            selected_model = str(result["selected_model"])

        return {
            "selected_model": selected_model,
            "response_text": response_text,
        }


def test_prompt_2_run_second_prompt(settings: SimpleNamespace) -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        image_path = root / "diagram.png"
        _write_png(image_path)
        _seed_task(root, "task1", "current task state")

        harness = PromptHarness(
            task_states_dir=root,
            output_dir=root / "generated_audio",
            use_real_client=settings.real,
        )
        image_paths = [] if settings.real else [image_path]
        result = _call_with_supported_kwargs(
            harness.run_second_prompt,
            first_prompt_response="diagram labels and arrows",
            task_name="task1",
            text_source_1="current task state",
            text_source_2="spoken user input",
            image_paths=image_paths,
            mode="text",
        )

        if not isinstance(result, dict):
            raise AssertionError("run_second_prompt must return a dict.")

        response_text = _assert_non_empty_response(result, real_mode=settings.real)
        selected_model = str(result.get("selected_model") or "")
        if settings.real and selected_model.startswith("fake-"):
            raise AssertionError("Expected a real Gemini model for prompt 2, but fake model was returned.")

        diagram_path_value = result.get("diagram_image_path")
        if not diagram_path_value:
            raise AssertionError("run_second_prompt must include diagram_image_path.")

        diagram_path = Path(str(diagram_path_value))
        if not diagram_path.exists():
            raise AssertionError("run_second_prompt diagram_image_path does not exist on disk.")

        diagram_mime_type = str(result.get("diagram_mime_type") or "")
        if not diagram_mime_type.startswith("image/"):
            raise AssertionError(f"Unexpected diagram MIME type: {diagram_mime_type}")

        return {
            "selected_model": selected_model,
            "response_text": response_text,
            "diagram_image_path": str(diagram_path),
            "diagram_mime_type": diagram_mime_type,
        }


def test_prompt_3_run_third_prompt(settings: SimpleNamespace) -> dict[str, str]:
    if settings.real and not settings.include_voice:
        raise SkipTest("Prompt 3 voice test is skipped in --real mode (--no-voice).")

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        harness = PromptHarness(
            task_states_dir=root / "taskStates",
            output_dir=root / "generated_audio",
            use_real_client=settings.real,
        )
        result = harness.run_third_prompt("Tighten the loose bracket.")
        audio_path = Path(str(result["audio_path"]))

        assert audio_path.exists()
        if settings.real:
            if audio_path.stat().st_size == 0:
                raise AssertionError("Voice output file is empty.")
            audio_mime_type = str(result.get("audio_mime_type") or "")
            if not audio_mime_type.startswith("audio/"):
                raise AssertionError(f"Unexpected audio MIME type: {audio_mime_type}")
        else:
            assert audio_path.read_bytes() == b"RIFFfake-audio"
            assert result["audio_mime_type"] == "audio/wav"

        return {
            "audio_path": str(audio_path),
            "audio_mime_type": str(result["audio_mime_type"]),
        }


def test_prompt_4_run_fourth_prompt(settings: SimpleNamespace) -> dict[str, str]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        harness = PromptHarness(
            task_states_dir=root / "taskStates",
            output_dir=root / "generated_audio",
            use_real_client=settings.real,
        )
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
    if len(sys.argv) > 1:
        print("[INFO] CLI flags are removed; running all prompts in real mode.")

    settings = SimpleNamespace(real=True, include_voice=True)

    try:
        _load_api_key()
    except Exception as exc:
        print(f"[FAIL] real-mode setup: {type(exc).__name__}: {exc}")
        return 1

    selected_prompts = list(TESTS.keys())
    print("[MODE] REAL GEMINI")
    print(f"[RUN] prompt selection: {', '.join(selected_prompts)}")
    print("[RUN] include prompt 3 voice: yes")

    failures = 0

    for prompt_key in selected_prompts:
        label, test_func = TESTS[prompt_key]
        try:
            details = test_func(settings)
        except SkipTest as exc:
            print(f"[SKIP] {label}: {exc}")
            continue
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
            continue

        _print_stage_output(label, details)
        print(f"[PASS] {label}: {json.dumps(details, sort_keys=True)}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())