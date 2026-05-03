
import base64
import importlib.util
import os
import tempfile
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai
from google.genai import types

try:
    from .promptScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_file,
    )
except ImportError:
    from promptScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_file,
    )


def _load_repo_key() -> str | None:
    keys_path = Path(__file__).resolve().parent.parent / "keys.py"
    if not keys_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("workspace_keys", keys_path)
    if spec is None or spec.loader is None:
        return None

    keys_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keys_module)
    return getattr(keys_module, "GEMINI_KEY", None)


GEMINI_KEY = _load_repo_key()

app = Flask(__name__)
CORS(app)

ANALYZE_MODEL = "gemini-2.0-flash"
GENERATE_MODEL = "gemini-3-pro-image-preview"

SUPPORTED_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
}


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
    if not api_key:
        raise RuntimeError("Set the GEMINI_API_KEY environment variable.")
    return genai.Client(api_key=api_key)


def wait_for_upload(client: genai.Client, uploaded_file: types.File) -> types.File:
    current = uploaded_file
    while getattr(current, "state", None) == types.FileState.PROCESSING:
        time.sleep(2)
        current = client.files.get(name=uploaded_file.name)
    if getattr(current, "state", None) == types.FileState.FAILED:
        raise RuntimeError("Gemini failed to process the uploaded file.")
    return current


@app.route("/health", methods=["GET"])
def health():
    """Simple liveness check."""
    return jsonify({"status": "ok"})


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Analyze an image or video with a text prompt and return Gemini's text response.

    Request (multipart/form-data):
        file   - image or video file (optional; omit for text-only prompts)
        prompt - text prompt sent to Gemini

    Response (JSON):
        { "text": "..." }       on success
        { "error": "..." }      on failure
    """
    prompt = request.form.get("prompt") or "Describe this media."
    file = request.files.get("file")

    try:
        client = get_client()

        if file and file.filename:
            suffix = Path(file.filename).suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                return jsonify({"error": f"Unsupported file type: {suffix}"}), 400

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                file.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                uploaded = client.files.upload(file=tmp_path)
                ready = wait_for_upload(client, uploaded)
                response = client.models.generate_content(
                    model=ANALYZE_MODEL,
                    contents=[ready, prompt],
                )
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            response = client.models.generate_content(
                model=ANALYZE_MODEL,
                contents=[prompt],
            )

        return jsonify({"text": response.text or ""})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    """
    Generate text and/or an image from a text prompt.

    Request (JSON):
        { "prompt": "a sunset over mountains" }

    Response (JSON):
        {
          "text":       "...",        # may be empty string
          "image":      "<base64>",   # null if no image was generated
          "image_mime": "image/png"   # null if no image was generated
        }
    """
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        client = get_client()
        response = client.models.generate_content(
            model=GENERATE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        result: dict = {"text": "", "image": None, "image_mime": None}
        for part in response.parts or []:
            if part.text:
                result["text"] += part.text
            elif part.inline_data and part.inline_data.data:
                result["image"] = base64.b64encode(part.inline_data.data).decode()
                result["image_mime"] = part.inline_data.mime_type

        return jsonify(result)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/voice-to-text", methods=["POST"])
def voice_to_text():
    """
    Transcribe uploaded audio into plain text for later use as prompt 2 user input.

    Request (multipart/form-data):
        file   - audio file, required
        prompt - optional transcription instruction
        model  - optional Gemini model override

    Response (JSON):
        {
          "text": "...",
          "user_input_text": "...",
          "model": "..."
        }
    """
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "audio file is required"}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_AUDIO_SUFFIXES:
        return jsonify({"error": f"Unsupported audio type: {suffix}"}), 400

    prompt = (request.form.get("prompt") or DEFAULT_TRANSCRIPTION_PROMPT).strip()
    model = (request.form.get("model") or VOICE_TO_TEXT_MODEL).strip()

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = Path(tmp.name)

        try:
            transcript_text = transcribe_audio_file(
                client=get_client(),
                audio_path=tmp_path,
                prompt=prompt,
                model=model,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        try:
            context_dir = Path(__file__).resolve().parent.parent / "taskContext"
            context_dir.mkdir(parents=True, exist_ok=True)
            output_file = context_dir / "latest_audio_transcription.txt"
            output_file.write_text(transcript_text, encoding="utf-8")
        except Exception as e:
            print(f"Warning: Failed to save transcription to file: {e}")

        return jsonify(
            {
                "text": transcript_text,
                "user_input_text": transcript_text,
                "model": model,
            }
        )

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    """Start the backend HTTP server and wait for frontend API calls."""
    print(f"Backend API listening on http://{host}:{port}")
    print("Routes: GET /health, POST /analyze, POST /generate, POST /voice-to-text")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    default_host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    default_port = int(os.environ.get("BACKEND_PORT", "5000"))
    default_debug = os.environ.get("BACKEND_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    run_server(host=default_host, port=default_port, debug=default_debug)
