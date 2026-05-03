"""Prompt 1 context growth test.

Runs prompt 1 in k loops, adding one image on each loop and feeding prior
responses back into text context so terminal output shows growth over time.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_prompt_api import (  # noqa: E402
    PromptHarness,
    _assert_non_empty_response,
    _load_api_key,
    _seed_task,
    _write_png,
)


def _parse_positive_int(raw_value: str, *, field_name: str) -> int:
    try:
        parsed_value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc

    if parsed_value <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return parsed_value


def _load_k_loops(default_value: int = 3) -> int:
    env_value = os.environ.get("PROMPT_CONTEXT_LOOP_K", "").strip()
    if env_value:
        return _parse_positive_int(env_value, field_name="PROMPT_CONTEXT_LOOP_K")

    if len(sys.argv) > 1 and sys.argv[1].strip():
        return _parse_positive_int(sys.argv[1].strip(), field_name="k")

    return default_value


def test_prompt_1_context_growth_k_loops(settings: SimpleNamespace, *, k_loops: int) -> dict[str, object]:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _seed_task(root, "task1", "X part broken")

        harness = PromptHarness(
            task_states_dir=root,
            output_dir=root / "generated_audio",
            use_real_client=settings.real,
        )

        loop_image_paths: list[Path] = []
        rolling_context = "Initial technician context."
        loop_outputs: list[dict[str, object]] = []

        for loop_index in range(1, k_loops + 1):
            loop_image_path = root / f"loop_image_{loop_index}.png"
            _write_png(loop_image_path)
            loop_image_paths.append(loop_image_path)

            result = harness.run_first_prompt(
                image_paths=loop_image_paths,
                text_source_1=rolling_context,
                text_source_2=f"Loop {loop_index} user input",
                task_name="task1",
            )

            response_text = _assert_non_empty_response(result, real_mode=settings.real)
            used_image_paths = [str(item) for item in (result.get("image_paths") or [])]

            if len(used_image_paths) != loop_index:
                raise AssertionError(
                    f"Expected {loop_index} image(s) in loop {loop_index}, got {len(used_image_paths)}."
                )

            selected_model = str(result.get("selected_model") or "")
            if settings.real and selected_model.startswith("fake-"):
                raise AssertionError("Expected a real Gemini model, but fake model was returned.")

            context_char_count_before = len(rolling_context)
            rolling_context = (
                f"{rolling_context}\n"
                f"Loop {loop_index} output:\n{response_text}"
            )
            context_char_count_after = len(rolling_context)

            loop_record: dict[str, object] = {
                "loop": loop_index,
                "image_count": len(used_image_paths),
                "context_char_count_before": context_char_count_before,
                "context_char_count_after": context_char_count_after,
                "selected_model": selected_model,
                "response_text": response_text,
            }
            loop_outputs.append(loop_record)

            print(
                "[LOOP] prompt1.context_growth "
                f"loop={loop_index} images={len(used_image_paths)} "
                f"context_before={context_char_count_before} context_after={context_char_count_after}"
            )
            print(json.dumps(loop_record, indent=2, sort_keys=True))

        return {
            "k_loops": k_loops,
            "final_image_count": len(loop_image_paths),
            "final_context_char_count": len(rolling_context),
            "loop_outputs": loop_outputs,
        }


def main() -> int:
    k_loops = _load_k_loops(default_value=3)
    settings = SimpleNamespace(real=True, include_voice=False)

    try:
        _load_api_key()
    except Exception as exc:
        print(f"[FAIL] real-mode setup: {type(exc).__name__}: {exc}")
        return 1

    print("[MODE] REAL GEMINI")
    print(f"[RUN] prompt selection: prompt1.context_growth_k_loops")
    print(f"[RUN] k loops: {k_loops}")

    try:
        details = test_prompt_1_context_growth_k_loops(settings, k_loops=k_loops)
    except Exception as exc:
        print(f"[FAIL] prompt1.context_growth_k_loops: {type(exc).__name__}: {exc}")
        return 1

    print("[OUTPUT] prompt1.context_growth_k_loops")
    print(json.dumps(details, indent=2, sort_keys=True))
    print(f"[PASS] prompt1.context_growth_k_loops: loops={k_loops}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())