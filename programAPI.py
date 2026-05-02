import base64
import os
import sys
import tempfile
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).parent / "AIBackend"))
try:
    from keys import GEMINI_KEY
except ImportError:
    GEMINI_KEY = None

app = Flask(__name__)
CORS(app)

ANALYZE_MODEL = "gemini-2.0-flash"
GENERATE_MODEL = "gemini-2.0-flash-preview-image-generation"

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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
