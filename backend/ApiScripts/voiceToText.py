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
			f"Unsupported audio type for {resolved_path.name}. Use wav, mp3, aiff, aac, ogg, flac, or m4a."
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
