""" 
Outputs audio from text instruction 
"""

"""Voice-mode helpers for Gemini text-to-speech output."""

import io
import mimetypes
import os
import time
import wave
from pathlib import Path

from google import genai
from google.genai import types


DEBUG = False


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, sampwidth: int = 2) -> bytes:
	"""Wrap raw PCM bytes in a WAV container and return the WAV bytes."""
	buf = io.BytesIO()
	with wave.open(buf, "wb") as wf:
		wf.setnchannels(channels)
		wf.setsampwidth(sampwidth)   # 2 bytes = 16-bit
		wf.setframerate(sample_rate)
		wf.writeframes(pcm_bytes)
	return buf.getvalue()


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
		self._log_response(response)
		print("[TTS] Extracting audio bytes from response...")
		
		audio_bytes, audio_mime_type = self._extract_audio_bytes(response)
		
		print(f"[TTS] ✓ Extracted {len(audio_bytes)} bytes of audio data")
		print(f"[TTS] Creating output directory: {self.output_dir}")
		
		self.output_dir.mkdir(parents=True, exist_ok=True)
		# Gemini TTS returns raw PCM — wrap it in a WAV container so it's playable.
		if "pcm" in audio_mime_type.lower() or "l16" in audio_mime_type.lower():
			audio_bytes = _pcm_to_wav(audio_bytes)
			audio_mime_type = "audio/wav"
		file_extension = mimetypes.guess_extension(audio_mime_type) or ".wav"
		prompt_label = self.prompt_number if self.prompt_number is not None else "custom"
		output_path = self.output_dir / f"prompt_{prompt_label}_{int(time.time())}{file_extension}"
		
		print(f"[TTS] Writing audio to file: {output_path}")
		output_path.write_bytes(audio_bytes)
		print(f"[TTS] ✓ Audio file saved successfully")
		
		return output_path, audio_mime_type

	@staticmethod
	def _log_response(response: types.GenerateContentResponse) -> None:
		"""Print all response metadata to the terminal, skipping raw audio bytes."""
		print("[TTS] --- Response metadata ---")

		# Top-level scalar fields
		for attr in ("model_version", "response_id"):
			val = getattr(response, attr, None)
			if val is not None:
				print(f"[TTS]   {attr}: {val}")

		# Usage metadata
		usage = getattr(response, "usage_metadata", None)
		if usage is not None:
			print(f"[TTS]   usage_metadata:")
			for field in ("prompt_token_count", "candidates_token_count", "total_token_count"):
				v = getattr(usage, field, None)
				if v is not None:
					print(f"[TTS]     {field}: {v}")

		# Candidates
		candidates = getattr(response, "candidates", None) or []
		print(f"[TTS]   candidates: {len(candidates)}")
		for ci, candidate in enumerate(candidates):
			print(f"[TTS]   candidate[{ci}]:")
			for attr in ("index", "finish_reason", "finish_message", "avg_logprobs"):
				val = getattr(candidate, attr, None)
				if val is not None:
					print(f"[TTS]     {attr}: {val}")
			content = getattr(candidate, "content", None)
			if content:
				role = getattr(content, "role", None)
				if role:
					print(f"[TTS]     content.role: {role}")
				parts = getattr(content, "parts", None) or []
				print(f"[TTS]     content.parts: {len(parts)}")
				for pi, part in enumerate(parts):
					inline = getattr(part, "inline_data", None)
					if inline and inline.data:
						print(f"[TTS]       part[{pi}]: inline_data mime_type={inline.mime_type} "
						      f"size={len(inline.data)} bytes (audio omitted)")
					else:
						text_val = getattr(part, "text", None)
						if text_val is not None:
							print(f"[TTS]       part[{pi}]: text={text_val!r}")
						else:
							print(f"[TTS]       part[{pi}]: {part}")

		print("[TTS] --- End response metadata ---")

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


# --------------------------------------------------------------------------- #
# Standalone runner (used by the test script and debug mode)
# --------------------------------------------------------------------------- #

class TTSRunner(TTSMixin):
	"""Self-contained TTS runner that does not depend on GeminiSequenceBackend.

	Parameters
	----------
	debug:
		When True the API key is loaded from *keys.env* (found by walking up the
		directory tree) rather than from the GEMINI_API_KEY environment variable.
	voice_model:
		Gemini model to use for TTS (defaults to config.VOICE_MODEL).
	voice_name:
		Built-in voice name to pass as speech_config (defaults to config.DEFAULT_VOICE_NAME).
	output_dir:
		Directory where generated audio files are written.
	"""

	def __init__(
		self,
		debug: bool = False,
		voice_model: str | None = None,
		voice_name: str | None = None,
		output_dir: Path | None = None,
	) -> None:
		# Import config lazily so the module stays importable without the full
		# backend package on the path.
		try:
			from GeminiEndpoint.config import DEFAULT_VOICE_NAME, VOICE_MODEL
		except ImportError:
			try:
				from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, VOICE_MODEL
			except ImportError:
				VOICE_MODEL = "gemini-2.5-flash-preview-tts"
				DEFAULT_VOICE_NAME = "charon"

		self.debug = debug
		self.voice_model = voice_model or VOICE_MODEL
		self.voice_name = voice_name or DEFAULT_VOICE_NAME
		self.output_dir = output_dir or (Path(__file__).resolve().parent.parent / "generated_audio")
		self.prompt_number = None
		self._client: genai.Client | None = None

		if debug:
			print("[TTS/debug] Debug mode ON — loading API key from keys.env")
			key = ""
			if key:
				print("[TTS/debug] ✓ API key loaded from keys.env")
				os.environ.setdefault("GEMINI_API_KEY", key)
			else:
				print("[TTS/debug] ✗ keys.env not found or GEMINI_API_KEY missing — "
				      "falling back to environment variable")

	def get_client(self) -> genai.Client:
		if self._client is None:
			api_key = os.environ.get("GEMINI_API_KEY")
			if not api_key:
				raise RuntimeError(
					"GEMINI_API_KEY is not set. Use debug=True to load it from keys.env, "
					"or set the environment variable before running."
				)
			self._client = genai.Client(api_key=api_key)
		return self._client
