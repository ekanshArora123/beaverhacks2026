import os
import time
from pathlib import Path

from google import genai
from google.genai import types

try:
	from keys import GEMINI_KEY
except ImportError:
	GEMINI_KEY = None

try:
	from prompt import PROMPT1
except ImportError:
	PROMPT1 = "Describe this image."


DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_PROMPT = PROMPT1
SUPPORTED_IMAGE_SUFFIXES = {
	".jpg",
	".jpeg",
	".png",
	".webp",
	".gif",
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


def send_image_prompt(
	client: genai.Client,
	image_path: Path,
	prompt: str,
	model: str = DEFAULT_MODEL,
) -> str:
	if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
		raise ValueError("Unsupported image type. Use jpg, jpeg, png, webp, or gif.")

	uploaded_file = client.files.upload(file=image_path)
	ready_file = wait_for_upload(client, uploaded_file)

	response = client.models.generate_content(
		model=model,
		contents=[prompt, ready_file],
	)
	return response.text or "No text response returned."


def prompt_for_image_path() -> Path | None:
	while True:
		raw_value = input("Image path (or 'q' to quit): ").strip().strip('"')
		if raw_value.lower() in {"q", "quit", "exit"}:
			return None

		image_path = Path(raw_value)
		if not image_path.exists() or not image_path.is_file():
			print("File not found. Try again.")
			continue

		if image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
			print("Unsupported image type. Use jpg, jpeg, png, webp, or gif.")
			continue

		return image_path


def main() -> None:
	client = create_client()
	print("Gemini backend ready. Submit an image path, or enter q to exit.")
	print(f"Default prompt: {DEFAULT_PROMPT}")

	while True:
		image_path = prompt_for_image_path()
		if image_path is None:
			print("Exiting backend loop.")
			return

		prompt = input("Prompt for Gemini (press Enter to use default): ").strip()
		if not prompt:
			prompt = DEFAULT_PROMPT

		try:
			result = send_image_prompt(client, image_path, prompt)
			print("\nGemini response:\n")
			print(result)
			print()
		except Exception as error:
			print(f"Request failed: {error}")


if __name__ == "__main__":
	main()
