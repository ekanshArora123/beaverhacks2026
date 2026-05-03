"""Voice-to-text helpers for backend audio transcription."""

from pathlib import Path

from google import genai
from google.genai import types


VOICE_TO_TEXT_MODEL = "gemini-3-flash-preview"
DEFAULT_TRANSCRIPTION_PROMPT = "Generate an accurate transcript of the speech. Return only the spoken text."
SUPPORTED_AUDIO_SUFFIXES = {
	".wav",
	".mp3",
	".aiff",
	".aac",
	".ogg",
	".webm",
	".flac",
	".m4a",
}


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
	current_file = uploaded_file
	while getattr(current_file, "state", None) == types.FileState.PROCESSING:
		current_file = client.files.get(name=uploaded_file.name)

	if getattr(current_file, "state", None) == types.FileState.FAILED:
		raise RuntimeError("Gemini failed to process the uploaded audio file.")

	return current_file


def validate_audio_path(audio_path: str | Path) -> Path:
	resolved_path = Path(audio_path).expanduser().resolve()
	if not resolved_path.exists() or not resolved_path.is_file():
		raise FileNotFoundError(f"Audio file not found: {resolved_path}")

	if resolved_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
		raise ValueError(
			f"Unsupported audio type for {resolved_path.name}. Use wav, mp3, aiff, aac, ogg, webm, flac, or m4a."
		)

	return resolved_path


def transcribe_audio_file(
	client: genai.Client,
	audio_path: str | Path,
	prompt: str | None = None,
	model: str = VOICE_TO_TEXT_MODEL,
) -> str:
	resolved_path = validate_audio_path(audio_path)
	uploaded_file = client.files.upload(file=resolved_path)
	ready_file = wait_for_upload(client, uploaded_file)

	transcript_prompt = (prompt or DEFAULT_TRANSCRIPTION_PROMPT).strip()
	response = client.models.generate_content(
		model=model,
		contents=[transcript_prompt, ready_file],
	)

	transcript_text = (response.text or "").strip()
	if not transcript_text:
		raise RuntimeError("Gemini returned an empty transcript.")

	return transcript_text


# Accepted MIME types for in-memory audio transcription
SUPPORTED_AUDIO_MIMES = {
	"audio/wav", "audio/x-wav",
	"audio/mp3", "audio/mpeg",
	"audio/aiff", "audio/x-aiff",
	"audio/aac",
	"audio/ogg", "audio/ogg;codecs=opus",
	"audio/webm", "audio/webm;codecs=opus",
	"audio/flac", "audio/x-flac",
	"audio/mp4", "audio/m4a",
}


def transcribe_audio_bytes(
	client: genai.Client,
	audio_bytes: bytes,
	mime_type: str,
	prompt: str | None = None,
	model: str = VOICE_TO_TEXT_MODEL,
) -> str:
	"""Transcribe raw audio bytes without writing anything to disk.

	Uses Gemini's inline ``Part.from_bytes`` so the audio travels
	entirely in-memory from the Flask request to the API call.

	Parameters
	----------
	client : genai.Client
		An authenticated Gemini client.
	audio_bytes : bytes
		Raw audio data.
	mime_type : str
		MIME type of the audio (e.g. ``"audio/webm"``).
	prompt : str | None
		Custom transcription instruction.  Falls back to the default.
	model : str
		Gemini model to use for transcription.

	Returns
	-------
	str
		The transcribed text.
	"""
	# Strip codec parameters for validation (e.g. "audio/ogg;codecs=opus" → "audio/ogg")
	base_mime = mime_type.split(";")[0].strip().lower()
	if base_mime not in {m.split(";")[0] for m in SUPPORTED_AUDIO_MIMES}:
		raise ValueError(
			f"Unsupported audio MIME type: {mime_type!r}. "
			f"Accepted types: {', '.join(sorted(SUPPORTED_AUDIO_MIMES))}"
		)

	audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
	transcript_prompt = (prompt or DEFAULT_TRANSCRIPTION_PROMPT).strip()

	response = client.models.generate_content(
		model=model,
		contents=[transcript_prompt, audio_part],
	)

	transcript_text = (response.text or "").strip()
	if not transcript_text:
		raise RuntimeError("Gemini returned an empty transcript.")

	return transcript_text
