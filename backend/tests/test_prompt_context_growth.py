"""Unit test for prompt 1 context growth across repeated loops."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_prompt_api import PromptHarness, _seed_task, _write_png  # noqa: E402


class PromptContextGrowthUnitTests(unittest.TestCase):
    def test_prompt_1_context_growth_k_loops(self) -> None:
        k_loops = 3
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _seed_task(root, "task1", "X part broken")

            harness = PromptHarness(
                task_states_dir=root,
                output_dir=root / "generated_audio",
            )

            loop_image_paths: list[Path] = []
            rolling_context = "Initial technician context."
            previous_context_length = len(rolling_context)

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

                response_text = str(result.get("response_text") or "").strip()
                self.assertTrue(response_text)

                used_image_paths = [str(item) for item in (result.get("image_paths") or [])]
                self.assertEqual(len(used_image_paths), loop_index)
                self.assertEqual(result.get("selected_model"), "fake-vision-model")

                rolling_context = (
                    f"{rolling_context}\n"
                    f"Loop {loop_index} output:\n{response_text}"
                )
                self.assertGreater(len(rolling_context), previous_context_length)
                previous_context_length = len(rolling_context)


if __name__ == "__main__":
    unittest.main()