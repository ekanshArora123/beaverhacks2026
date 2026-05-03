"""Prompt generation helpers.

Prompt 1 (mainPrompt): Generate technician instruction text.
Prompt 2 (diagramPrompt): Generate an updated diagram image from prompt 1 output + context.
"""

import mimetypes
import time
from pathlib import Path
from typing import Literal, Sequence

from google import genai
from google.genai import types


SUPPORTED_IMAGE_SUFFIXES = {
	".jpg",
	".jpeg",
	".png",
	".webp",
	".gif",
}
ResponseMode = Literal["text", "voice"]
DEFAULT_PROMPTS = {
	1: (
		"You are an expert field technician assistant. Use the provided context, task status, and images "
		"to produce one clear text instruction for what the technician should do next. Focus on safe, "
		"actionable guidance."
	),
	2: (
		"Create an updated schematic-style diagram image that reflects the main instruction text and the "
		"current task context. Keep the diagram clear, technical, and directly useful for the next action."
	),
}
GENERATED_DIAGRAMS_DIR = Path(__file__).resolve().parent.parent / "generated_diagrams"


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
	current_file = uploaded_file
	while getattr(current_file, "state", None) == types.FileState.PROCESSING:
		time.sleep(2)
		current_file = client.files.get(name=uploaded_file.name)

	if getattr(current_file, "state", None) == types.FileState.FAILED:
		raise RuntimeError(f"Gemini failed to process {current_file.display_name or uploaded_file.name}.")

	return current_file


class DiagramPromptMixin:
	def run_second_prompt(
		self,
		first_prompt_response: str,
		task_name: str | int | None = None,
		text_source_1: str = "",
		text_source_2: str = "",
		image_paths: Sequence[str | Path] | None = None,
		mode: ResponseMode = "text",
		prompt_text: str | None = None,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> dict[str, str | int | list[str] | None]:
		if not first_prompt_response or not first_prompt_response.strip():
			raise ValueError("first_prompt_response is required for prompt 2.")

		self._apply_model_overrides(
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)
		self.prompt_number = 2
		self.prompt_text = self._resolve_prompt(2, prompt_text)
		self.task_name = self._normalize_task_name(task_name)
		self.task_status = self._load_task_status(self.task_name) if self.task_name else ""
		self.task_image_paths = self._load_task_image_paths(self.task_name) if self.task_name else []
		self.text_source_1 = text_source_1.strip()
		self.text_source_2 = text_source_2.strip()
		all_image_paths = [*(image_paths or []), *self.task_image_paths]
		self.image_paths = self._normalize_image_paths(all_image_paths)

		response_text, diagram_image_path, diagram_mime_type = self._generate_diagram_response(first_prompt_response)
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
			"task_name": self.task_name,
			"task_status": self.task_status or None,
			"first_prompt_response": first_prompt_response.strip(),
			"text_source_1": self.text_source_1,
			"text_source_2": self.text_source_2,
			"response_text": response_text,
			"diagram_image_path": str(diagram_image_path),
			"diagram_mime_type": diagram_mime_type,
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

	def get_prompt(self, prompt_number: int) -> str:
		default_prompt = DEFAULT_PROMPTS.get(prompt_number)
		if default_prompt:
			return default_prompt

		raise ValueError(f"PROMPT{prompt_number} is not defined.")

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

	def _generate_diagram_response(self, first_prompt_response: str) -> tuple[str, Path, str]:
		uploaded_files = self._upload_images()
		self.selected_model = self.vision_model
		response = self.get_client().models.generate_content(
			model=self.selected_model,
			contents=[self._build_diagram_prompt_payload(first_prompt_response.strip()), *uploaded_files],
			config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
		)

		response_text = (response.text or self._collect_text_from_parts(response)).strip()
		if not response_text:
			response_text = "Generated an updated diagram image for the technician."

		image_bytes, image_mime_type = self._extract_image_bytes(response)
		diagram_path = self._write_generated_diagram(image_bytes, image_mime_type)
		return response_text, diagram_path, image_mime_type

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
			sections.append(f"Context text:\n{self.text_source_1}")
		if self.text_source_2:
			sections.append(f"User input text:\n{self.text_source_2}")
		if self.image_paths:
			sections.append("Use the provided images with the text context to produce one clear next-step instruction.")
		else:
			sections.append("Use the provided task context to produce one clear next-step instruction.")
		sections.append("Output plain text only.")
		return "\n\n".join(sections)

	def _build_diagram_prompt_payload(self, first_prompt_response: str) -> str:
		sections = [f"Prompt:\n{self.prompt_text}"]
		sections.append(f"Main instruction text:\n{first_prompt_response}")
		if self.task_name:
			sections.append(f"Task:\n{self.task_name}")
		if self.task_status:
			sections.append(f"Task status:\n{self.task_status}")
		if self.text_source_1:
			sections.append(f"Additional context:\n{self.text_source_1}")
		if self.text_source_2:
			sections.append(f"Latest user update:\n{self.text_source_2}")
		if self.image_paths:
			sections.append("Use the provided images as visual references for the updated diagram.")
		sections.append(
			"Return an IMAGE that clearly visualizes the next technician action. Keep labels concise and technical."
		)
		return "\n\n".join(sections)

	def _write_generated_diagram(self, image_bytes: bytes, image_mime_type: str) -> Path:
		configured_output_dir = getattr(self, "diagram_output_dir", GENERATED_DIAGRAMS_DIR)
		output_dir = Path(configured_output_dir)
		output_dir.mkdir(parents=True, exist_ok=True)
		file_extension = mimetypes.guess_extension(image_mime_type or "") or ".png"
		task_label = (self.task_name or "task").replace(" ", "_")
		output_path = output_dir / f"{task_label}_prompt_2_{int(time.time())}{file_extension}"
		output_path.write_bytes(image_bytes)
		return output_path

	@staticmethod
	def _collect_text_from_parts(response: types.GenerateContentResponse) -> str:
		parts = getattr(response, "parts", None)
		if not parts and getattr(response, "candidates", None):
			parts = response.candidates[0].content.parts

		if not parts:
			return ""

		return "".join(part.text for part in parts if getattr(part, "text", None))

	@staticmethod
	def _extract_image_bytes(response: types.GenerateContentResponse) -> tuple[bytes, str]:
		parts = getattr(response, "parts", None)
		if not parts and getattr(response, "candidates", None):
			parts = response.candidates[0].content.parts

		for part in parts or []:
			inline_data = getattr(part, "inline_data", None)
			if inline_data and inline_data.data:
				mime_type = inline_data.mime_type or "image/png"
				if mime_type.startswith("image/"):
					return inline_data.data, mime_type

		raise RuntimeError("Gemini did not return an image for prompt 2.")


class MainPromptMixin(DiagramPromptMixin):
	"""Backward-compatible alias for older imports from this module."""

	def run_first_prompt(
		self,
		image_paths: Sequence[str | Path],
		text_source_1: str = "",
		text_source_2: str = "",
		task_name: str | int | None = None,
		mode: ResponseMode = "text",
		prompt_text: str | None = None,
		text_model: str | None = None,
		vision_model: str | None = None,
		voice_model: str | None = None,
	) -> dict[str, str | int | list[str] | None]:
		return self.generate(
			image_paths=image_paths,
			prompt_number=1,
			text_source_1=text_source_1,
			text_source_2=text_source_2,
			mode=mode,
			prompt_text=prompt_text,
			task_name=task_name,
			text_model=text_model,
			vision_model=vision_model,
			voice_model=voice_model,
		)
