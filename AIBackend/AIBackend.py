import os
import time
from pathlib import Path

from google import genai
from google.genai import types

try:
	from keys import GEMINI_KEY
except ImportError:
	GEMINI_KEY = None


DEFAULT_MODEL = "gemini-2.0-flash"
SUPPORTED_SUFFIXES = {
	".jpg",
	".jpeg",
	".png",
	".webp",
	".gif",
	".mp4",
	".mov",
	".avi",
	".mkv",
	".webm",
}


def load_api_key() -> str:
	api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
	if not api_key:
		raise RuntimeError(
			"Set GEMINI_API_KEY or define GEMINI_KEY in AIBackend/keys.py before running the backend."
		)
	return api_key


def create_client() -> genai.Client:
	return genai.Client(api_key=load_api_key())


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
	current_file = uploaded_file
	while getattr(current_file, "state", None) == types.FileState.PROCESSING:
		print("Waiting for Gemini to finish processing the file...")
		time.sleep(2)
		current_file = client.files.get(name=uploaded_file.name)

	if getattr(current_file, "state", None) == types.FileState.FAILED:
		raise RuntimeError(f"Gemini failed to process {current_file.display_name or uploaded_file.name}.")

	return current_file


def send_media_prompt(
	client: genai.Client,
	media_path: Path,
	prompt: str,
	model: str = DEFAULT_MODEL,
) -> str:
	uploaded_file = client.files.upload(file=media_path)
	ready_file = wait_for_upload(client, uploaded_file)

	response = client.models.generate_content(
		model=model,
		contents=[ready_file, prompt],
	)
	return response.text or "No text response returned."


def prompt_for_media_path() -> Path | None:
	raw_value = input("Image or video path (or 'q' to quit): ").strip().strip('"')
	if raw_value.lower() in {"q", "quit", "exit"}:
		return None

	media_path = Path(raw_value)
	if not media_path.exists() or not media_path.is_file():
		print("File not found. Try again.")
		return prompt_for_media_path()

	if media_path.suffix.lower() not in SUPPORTED_SUFFIXES:
		print("Unsupported file type. Use a common image or video file.")
		return prompt_for_media_path()

	return media_path


def main() -> None:
	client = create_client()
	print("Gemini backend ready. Submit an image or video path, or enter q to exit.")

	while True:
		media_path = prompt_for_media_path()
		if media_path is None:
			print("Exiting backend loop.")
			return

		prompt = input("Prompt for Gemini: ").strip()
		if not prompt:
			prompt = "Describe this media."

		try:
			result = send_media_prompt(client, media_path, prompt)
			print("\nGemini response:\n")
			print(result)
			print()
		except Exception as error:
			print(f"Request failed: {error}")


if __name__ == "__main__":
	main()
