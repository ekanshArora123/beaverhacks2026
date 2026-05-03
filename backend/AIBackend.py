import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path

from google import genai

def _load_repo_key() -> str | None:
	keys_path = Path(__file__).resolve().parent.parent / "keys.py"
	if not keys_path.exists():
		return None

	spec = importlib.util.spec_from_file_location("workspace_keys", keys_path)
	if spec is None or spec.loader is None:
		return None

	keys_module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(keys_module)
	return getattr(keys_module, "GEMINI_KEY", None)


GEMINI_KEY = _load_repo_key()

try:
	from .ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL
except ImportError:
	from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL

try:
	from .ApiScripts.diagramPrompt import MainPromptMixin
except ImportError:
	from ApiScripts.diagramPrompt import MainPromptMixin

try:
	from .ApiScripts.mainPrompt import SecondPromptMixin
except ImportError:
	from ApiScripts.mainPrompt import SecondPromptMixin

try:
	from .ApiScripts.updatePrompt import StateUpdateMixin, TASK_STATES_DIR
except ImportError:
	from ApiScripts.updatePrompt import StateUpdateMixin, TASK_STATES_DIR

try:
	from .ApiScripts.textToVoice import TTSMixin
except ImportError:
	from ApiScripts.textToVoice import TTSMixin


def load_api_key() -> str:
	api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
	if not api_key:
		raise RuntimeError(
			"Set GEMINI_API_KEY or define GEMINI_KEY in AIBackend/keys.py before running the backend."
		)
	return api_key


@dataclass
class GeminiSequenceBackend(MainPromptMixin, SecondPromptMixin, StateUpdateMixin, TTSMixin):
	text_model: str = TEXT_MODEL
	vision_model: str = VISION_MODEL
	voice_model: str = VOICE_MODEL
	voice_name: str = DEFAULT_VOICE_NAME
	output_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "generated_audio")
	task_states_dir: Path = field(default_factory=lambda: TASK_STATES_DIR)
	client: genai.Client | None = field(default=None, init=False, repr=False)
	image_paths: list[Path] = field(default_factory=list, init=False)
	task_image_paths: list[Path] = field(default_factory=list, init=False)
	prompt_number: int | None = field(default=None, init=False)
	prompt_text: str = field(default="", init=False)
	text_source_1: str = field(default="", init=False)
	text_source_2: str = field(default="", init=False)
	task_name: str | None = field(default=None, init=False)
	task_status: str = field(default="", init=False)
	selected_model: str = field(default="", init=False)

	def get_client(self) -> genai.Client:
		if self.client is None:
			self.client = genai.Client(api_key=load_api_key())
		return self.client

	def run_four_prompts(
		self,
		image_paths: list[str | Path],
		task_name: str | int,
		text_source_1: str = "",
		text_source_2: str = "",
		updated_status: str | None = None,
		voice_output: bool = True,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> dict[str, object]:
		first_result = self.run_first_prompt(
			image_paths=image_paths,
			text_source_1=text_source_1,
			text_source_2=text_source_2,
			task_name=task_name,
			mode="text",
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)

		second_result = self.run_second_prompt(
			first_prompt_response=str(first_result.get("response_text", "")),
			task_name=task_name,
			text_source_1=text_source_1,
			text_source_2=text_source_2,
			image_paths=image_paths,
			mode="text",
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)

		third_result = (
			self.run_third_prompt(str(second_result.get("response_text", ""))) if voice_output else None
		)

		fourth_result = self.run_fourth_prompt(task_name, updated_status) if updated_status else None

		return {
			"first_prompt": first_result,
			"second_prompt": second_result,
			"third_prompt": third_result,
			"fourth_prompt": fourth_result,
		}


def main() -> None:
	print("GeminiSequenceBackend ready.")
	print("Example call 1:")
	print(
		"backend.run_first_prompt(['image1.png'], text_source_1='source a', text_source_2='source b', task_name='task1')"
	)
	print("Example call 2:")
	print("backend.run_second_prompt(first_prompt_response='diagram text', task_name='task1')")
	print("backend.run_third_prompt('instruction text')")
	print("backend.run_fourth_prompt('task1', 'updated status')")
	print("backend.run_four_prompts(['image1.png'], task_name='task1', text_source_1='source a')")


if __name__ == "__main__":
	main()
