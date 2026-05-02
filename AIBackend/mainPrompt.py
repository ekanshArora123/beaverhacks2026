"""Main multimodal generation flow.

Takes schematic, image, context text, and input text for the primary Gemini call.
"""

import time
from pathlib import Path
from typing import Literal, Sequence

from google import genai
from google.genai import types

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


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
	current_file = uploaded_file
	while getattr(current_file, "state", None) == types.FileState.PROCESSING:
		time.sleep(2)
		current_file = client.files.get(name=uploaded_file.name)

	if getattr(current_file, "state", None) == types.FileState.FAILED:
		raise RuntimeError(f"Gemini failed to process {current_file.display_name or uploaded_file.name}.")

	return current_file


class MainPromptMixin:
	def get_prompt(self, prompt_number: int) -> str:
		prompt_name = f"PROMPT{prompt_number}"
		prompt_value = getattr(prompt_module, prompt_name, None)
		if not isinstance(prompt_value, str) or not prompt_value.strip():
			raise ValueError(f"{prompt_name} is not defined in prompt.py.")
		return prompt_value.strip()

	def generate_for_task(
		self,
		task_name: str | int,
		prompt_number: int | None,
		text_source_1: str = "",
		text_source_2: str = "",
		mode: ResponseMode = "text",
		prompt_text: str | None = None,
		image_paths: Sequence[str | Path] | None = None,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> dict[str, str | int | list[str] | None]:
		return self.generate(
			image_paths=image_paths or [],
			prompt_number=prompt_number,
			text_source_1=text_source_1,
			text_source_2=text_source_2,
			mode=mode,
			prompt_text=prompt_text,
			task_name=task_name,
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)

	def generate(
		self,
		image_paths: Sequence[str | Path],
		prompt_number: int | None,
		text_source_1: str,
		text_source_2: str,
		mode: ResponseMode = "text",
		prompt_text: str | None = None,
		task_name: str | int | None = None,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> dict[str, str | int | list[str] | None]:
		self._apply_model_overrides(
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)
		self.prompt_number = prompt_number
		self.prompt_text = self._resolve_prompt(prompt_number, prompt_text)
		self.text_source_1 = text_source_1.strip()
		self.text_source_2 = text_source_2.strip()
		self.task_name = self._normalize_task_name(task_name)
		self.task_status = self._load_task_status(self.task_name) if self.task_name else ""
		self.task_image_paths = self._load_task_image_paths(self.task_name) if self.task_name else []
		all_image_paths = [*image_paths, *self.task_image_paths]
		self.image_paths = self._normalize_image_paths(all_image_paths)

		response_text = self._generate_text_response()
		result: dict[str, str | int | list[str] | None] = {
			"text_model": self.text_model,
			"vision_model": self.vision_model,
			"voice_model": self.voice_model,
			"selected_model": self.selected_model,
			"mode": mode,
			"prompt_number": self.prompt_number,
			"prompt_text": self.prompt_text,
			"image_paths": [str(image_path) for image_path in self.image_paths],
			"task_image_paths": [str(image_path) for image_path in self.task_image_paths],
			"text_source_1": self.text_source_1,
			"text_source_2": self.text_source_2,
			"task_name": self.task_name,
			"task_status": self.task_status or None,
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

	def _apply_model_overrides(
		self,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> None:
		if text_model and text_model.strip():
			self.text_model = text_model.strip()
		if vision_model and vision_model.strip():
			self.vision_model = vision_model.strip()
		if voice_model and voice_model.strip():
			self.voice_model = voice_model.strip()

	def _resolve_prompt(self, prompt_number: int | None, prompt_text: str | None) -> str:
		if prompt_text and prompt_text.strip():
			return prompt_text.strip()
		if prompt_number is None:
			raise ValueError("prompt_number or prompt_text is required.")
		return self.get_prompt(prompt_number)

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

		return normalized_paths

	def _generate_text_response(self) -> str:
		uploaded_files = self._upload_images()
		self.selected_model = self.vision_model if uploaded_files else self.text_model
		response = self.get_client().models.generate_content(
			model=self.selected_model,
			contents=[self._build_prompt_payload(), *uploaded_files],
		)
		response_text = response.text or self._collect_text_from_parts(response)
		if not response_text:
			raise RuntimeError("Gemini returned an empty text response.")
		return response_text

	def _upload_images(self) -> list[types.File]:
		uploaded_files: list[types.File] = []
		client = self.get_client()
		for image_path in self.image_paths:
			uploaded_file = client.files.upload(file=image_path)
			uploaded_files.append(wait_for_upload(client, uploaded_file))
		return uploaded_files

	def _build_prompt_payload(self) -> str:
		sections = [f"Prompt:\n{self.prompt_text}"]
		if self.task_name:
			sections.append(f"Task:\n{self.task_name}")
		if self.task_status:
			sections.append(f"Task status:\n{self.task_status}")
		if self.text_source_1:
			sections.append(f"Text source 1:\n{self.text_source_1}")
		if self.text_source_2:
			sections.append(f"Text source 2:\n{self.text_source_2}")
		if self.image_paths:
			sections.append("Use the provided images, prompt, and task status together in one combined answer.")
		else:
			sections.append("Use the provided prompt and task status together in one combined answer.")
		return "\n\n".join(sections)

	@staticmethod
	def _collect_text_from_parts(response: types.GenerateContentResponse) -> str:
		parts = getattr(response, "parts", None)
		if not parts and getattr(response, "candidates", None):
			parts = response.candidates[0].content.parts

		if not parts:
			return ""

		return "".join(part.text for part in parts if getattr(part, "text", None))
