import mimetypes
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence

from google import genai
from google.genai import types

try:
	from .keys import GEMINI_KEY
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
	from . import prompt as prompt_module
except ImportError:
	import prompt as prompt_module


SUPPORTED_IMAGE_SUFFIXES = {
	".jpg",
	".jpeg",
	".png",
	".webp",
	".gif",
}
ResponseMode = Literal["text", "voice"]


def load_api_key() -> str:
	api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
	if not api_key:
		raise RuntimeError(
			"Set GEMINI_API_KEY or define GEMINI_KEY in AIBackend/keys.py before running the backend."
		)
	return api_key


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
	current_file = uploaded_file
	while getattr(current_file, "state", None) == types.FileState.PROCESSING:
		time.sleep(2)
		current_file = client.files.get(name=uploaded_file.name)

	if getattr(current_file, "state", None) == types.FileState.FAILED:
		raise RuntimeError(f"Gemini failed to process {current_file.display_name or uploaded_file.name}.")

	return current_file


@dataclass
class GeminiSequenceBackend:
	text_model: str = TEXT_MODEL
	vision_model: str = VISION_MODEL
	voice_model: str = VOICE_MODEL
	voice_name: str = DEFAULT_VOICE_NAME
	output_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent / "generated_audio")
	client: genai.Client | None = field(default=None, init=False, repr=False)
	image_paths: list[Path] = field(default_factory=list, init=False)
	prompt_number: int | None = field(default=None, init=False)
	prompt_text: str = field(default="", init=False)
	text_source_1: str = field(default="", init=False)
	text_source_2: str = field(default="", init=False)

	def get_client(self) -> genai.Client:
		if self.client is None:
			self.client = genai.Client(api_key=load_api_key())
		return self.client

	def get_prompt(self, prompt_number: int) -> str:
		prompt_name = f"PROMPT{prompt_number}"
		prompt_value = getattr(prompt_module, prompt_name, None)
		if not isinstance(prompt_value, str) or not prompt_value.strip():
			raise ValueError(f"{prompt_name} is not defined in prompt.py.")
		return prompt_value.strip()

	def update_text_source_1(self, new_text_source_1: str) -> dict[str, str | int | list[str] | None]:
		self.text_source_1 = new_text_source_1.strip()
		return self.get_state()

	def get_state(self) -> dict[str, str | int | list[str] | None]:
		return {
			"prompt_number": self.prompt_number,
			"prompt_text": self.prompt_text,
			"image_paths": [str(image_path) for image_path in self.image_paths],
			"text_source_1": self.text_source_1,
			"text_source_2": self.text_source_2,
		}

	def generate(
		self,
		image_paths: Sequence[str | Path],
		prompt_number: int,
		text_source_1: str,
		text_source_2: str,
		mode: ResponseMode = "text",
	) -> dict[str, str | int | list[str] | None]:
		self.image_paths = self._normalize_image_paths(image_paths)
		self.prompt_number = prompt_number
		self.prompt_text = self.get_prompt(prompt_number)
		self.text_source_1 = text_source_1.strip()
		self.text_source_2 = text_source_2.strip()

		response_text = self._generate_text_response()
		result: dict[str, str | int | list[str] | None] = {
			"mode": mode,
			"prompt_number": self.prompt_number,
			"prompt_text": self.prompt_text,
			"image_paths": [str(image_path) for image_path in self.image_paths],
			"text_source_1": self.text_source_1,
			"text_source_2": self.text_source_2,
			"response_text": response_text,
			"audio_path": None,
			"audio_mime_type": None,
		}

		if mode == "voice":
			audio_path, audio_mime_type = self._generate_voice_response(response_text)
			result["audio_path"] = str(audio_path)
			result["audio_mime_type"] = audio_mime_type
		elif mode != "text":
			raise ValueError("mode must be either 'text' or 'voice'.")

		return result

	def _normalize_image_paths(self, image_paths: Sequence[str | Path]) -> list[Path]:
		normalized_paths: list[Path] = []
		for image_path in image_paths:
			resolved_path = Path(image_path).expanduser().resolve()
			if not resolved_path.exists() or not resolved_path.is_file():
				raise FileNotFoundError(f"Image file not found: {resolved_path}")
			if resolved_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
				raise ValueError(
					f"Unsupported image type for {resolved_path.name}. Use jpg, jpeg, png, webp, or gif."
				)
			normalized_paths.append(resolved_path)

		if not normalized_paths:
			raise ValueError("At least one image path is required.")

		return normalized_paths

	def _generate_text_response(self) -> str:
		uploaded_files = self._upload_images()
		response = self.get_client().models.generate_content(
			model=self.vision_model,
			contents=[self._build_prompt_payload(), *uploaded_files],
		)
		response_text = response.text or self._collect_text_from_parts(response)
		if not response_text:
			raise RuntimeError("Gemini returned an empty text response.")
		return response_text

	def _upload_images(self) -> list[types.File]:
		uploaded_files: list[types.File] = []
		for image_path in self.image_paths:
			uploaded_file = self.get_client().files.upload(file=image_path)
			uploaded_files.append(wait_for_upload(self.get_client(), uploaded_file))
		return uploaded_files

	def _build_prompt_payload(self) -> str:
		return (
			f"Prompt:\n{self.prompt_text}\n\n"
			f"Text source 1:\n{self.text_source_1}\n\n"
			f"Text source 2:\n{self.text_source_2}\n\n"
			"Use every provided image together with both text sources in one combined answer."
		)

	def _generate_voice_response(self, response_text: str) -> tuple[Path, str]:
		response = self.get_client().models.generate_content(
			model=self.voice_model,
			contents=response_text,
			config=types.GenerateContentConfig(
				response_modalities=["AUDIO"],
				speech_config=self.voice_name,
			),
		)
		audio_bytes, audio_mime_type = self._extract_audio_bytes(response)
		self.output_dir.mkdir(parents=True, exist_ok=True)
		file_extension = mimetypes.guess_extension(audio_mime_type) or ".wav"
		output_path = self.output_dir / f"prompt_{self.prompt_number}_{int(time.time())}{file_extension}"
		output_path.write_bytes(audio_bytes)
		return output_path, audio_mime_type

	@staticmethod
	def _collect_text_from_parts(response: types.GenerateContentResponse) -> str:
		parts = getattr(response, "parts", None)
		if not parts and getattr(response, "candidates", None):
			parts = response.candidates[0].content.parts

		if not parts:
			return ""

		return "".join(part.text for part in parts if getattr(part, "text", None))

	@staticmethod
	def _extract_audio_bytes(response: types.GenerateContentResponse) -> tuple[bytes, str]:
		parts = getattr(response, "parts", None)
		if not parts and getattr(response, "candidates", None):
			parts = response.candidates[0].content.parts

		for part in parts or []:
			inline_data = getattr(part, "inline_data", None)
			if inline_data and inline_data.data:
				return inline_data.data, inline_data.mime_type or "audio/wav"

		raise RuntimeError("Gemini did not return audio data for voice mode.")


def main() -> None:
	print("GeminiSequenceBackend ready.")
	print("Example call 1:")
	print(
		"backend.generate(['image1.png', 'image2.png'], prompt_number=1, text_source_1='source a', text_source_2='source b', mode='text')"
	)
	print("Example call 2:")
	print("backend.update_text_source_1('updated source text')")


if __name__ == "__main__":
	main()
