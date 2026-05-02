""" 
Outputs audio from text instruction 
"""

"""Voice-mode helpers for Gemini text-to-speech output."""

import mimetypes
import time
from pathlib import Path

from google.genai import types


class TTSMixin:
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
		prompt_label = self.prompt_number if self.prompt_number is not None else "custom"
		output_path = self.output_dir / f"prompt_{prompt_label}_{int(time.time())}{file_extension}"
		output_path.write_bytes(audio_bytes)
		return output_path, audio_mime_type

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
