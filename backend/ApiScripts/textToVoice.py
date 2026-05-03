""" 
Outputs audio from text instruction 
"""

"""Voice-mode helpers for Gemini text-to-speech output."""

import mimetypes
import time
from pathlib import Path

from google.genai import types


class TTSMixin:
	def run_third_prompt(self, instruction_text: str) -> dict[str, str | None]:
		print("[TTS] Starting text-to-voice conversion...")
		print(f"[TTS] Instruction text length: {len(instruction_text)} characters")
		print(f"[TTS] Voice model: {self.voice_model}")
		
		audio_path, audio_mime_type = self._generate_voice_response(instruction_text)
		
		print(f"[TTS] ✓ Conversion complete. Audio saved to: {audio_path}")
		print(f"[TTS] Audio MIME type: {audio_mime_type}")
		
		return {
			"voice_model": self.voice_model,
			"audio_path": str(audio_path),
			"audio_mime_type": audio_mime_type,
			"instruction_text": instruction_text,
		}

	def _generate_voice_response(self, response_text: str) -> tuple[Path, str]:
		print(f"[TTS] Generating voice response with voice: {self.voice_name}")
		print(f"[TTS] Sending request to Gemini API...")
		
		response = self.get_client().models.generate_content(
			model=self.voice_model,
			contents=response_text,
			config=types.GenerateContentConfig(
				response_modalities=["AUDIO"],
				speech_config=self.voice_name,
			),
		)
		
		print("[TTS] ✓ Received response from Gemini API")
		print("[TTS] Extracting audio bytes from response...")
		
		audio_bytes, audio_mime_type = self._extract_audio_bytes(response)
		
		print(f"[TTS] ✓ Extracted {len(audio_bytes)} bytes of audio data")
		print(f"[TTS] Creating output directory: {self.output_dir}")
		
		self.output_dir.mkdir(parents=True, exist_ok=True)
		file_extension = mimetypes.guess_extension(audio_mime_type) or ".wav"
		prompt_label = self.prompt_number if self.prompt_number is not None else "custom"
		output_path = self.output_dir / f"prompt_{prompt_label}_{int(time.time())}{file_extension}"
		
		print(f"[TTS] Writing audio to file: {output_path}")
		output_path.write_bytes(audio_bytes)
		print(f"[TTS] ✓ Audio file saved successfully")
		
		return output_path, audio_mime_type

	@staticmethod
	def _extract_audio_bytes(response: types.GenerateContentResponse) -> tuple[bytes, str]:
		print("[TTS] Parsing response structure...")
		parts = getattr(response, "parts", None)
		
		if not parts and getattr(response, "candidates", None):
			print("[TTS] Using candidates[0].content.parts")
			parts = response.candidates[0].content.parts
		else:
			print(f"[TTS] Found {len(parts) if parts else 0} parts in response")

		for i, part in enumerate(parts or []):
			print(f"[TTS] Checking part {i + 1}...")
			inline_data = getattr(part, "inline_data", None)
			if inline_data and inline_data.data:
				print(f"[TTS] ✓ Found audio data in part {i + 1}")
				return inline_data.data, inline_data.mime_type or "audio/wav"

		print("[TTS] ✗ ERROR: No audio data found in response")
		raise RuntimeError("Gemini did not return audio data for voice mode.")
