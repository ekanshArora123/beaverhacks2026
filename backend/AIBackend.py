import os
from dataclasses import dataclass, field
from pathlib import Path

from google import genai

try:
	from ..keys import GEMINI_KEY
except ImportError:
	try:
		from keys import GEMINI_KEY
	except ImportError:
		GEMINI_KEY = None

try:
	from .config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL
except ImportError:
	from config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL

try:
	from .promptScripts.mainPrompt import MainPromptMixin
except ImportError:
 	from AIBackend.promptScripts.mainPrompt import MainPromptMixin

try:
	from .promptScripts.fourthPrompt import StateUpdateMixin, TASK_STATES_DIR
except ImportError:
	from AIBackend.promptScripts.fourthPrompt import StateUpdateMixin, TASK_STATES_DIR

try:
	from .tts import TTSMixin
except ImportError:
	from tts import TTSMixin


def load_api_key() -> str:
	api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
	if not api_key:
		raise RuntimeError(
			"Set GEMINI_API_KEY or define GEMINI_KEY in AIBackend/keys.py before running the backend."
		)
	return api_key


@dataclass
class GeminiSequenceBackend(MainPromptMixin, StateUpdateMixin, TTSMixin):
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


def main() -> None:
	print("GeminiSequenceBackend ready.")
	print("Example call 1:")
	print(
		"backend.generate(['image1.png'], prompt_number=1, text_source_1='source a', text_source_2='source b', task_name='task1', mode='text')"
	)
	print("Example call 2:")
	print("backend.generate_for_task(task_name='task1', prompt_number=2, mode='text')")


if __name__ == "__main__":
	main()
