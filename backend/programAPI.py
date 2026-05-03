"""
programAPI  –  Flask REST endpoints consumed by the frontend.

Endpoints
---------
POST /analyze
    Accepts an image file, an audio blob, and a machine_info text field.
    Transcribes the audio in-memory, runs the main prompt pipeline, and
    returns the AI's text response.  Nothing is saved to disk.

POST /voice-to-text
    Standalone transcription endpoint used by the frontend's live voice
    activity display.
"""

import os
import tempfile
import traceback

from flask import Flask, jsonify, request
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Imports from sibling / child packages
# ---------------------------------------------------------------------------
try:
    from .ApiScripts.mainPrompt import run_main_prompt
except ImportError:
    from ApiScripts.mainPrompt import run_main_prompt

try:
    from .ApiScripts.voiceToText import transcribe_audio_bytes
    from .ApiScripts.mainPrompt import _get_client
except ImportError:
    from ApiScripts.voiceToText import transcribe_audio_bytes
    from ApiScripts.mainPrompt import _get_client

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# POST /analyze
# ---------------------------------------------------------------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Expected multipart/form-data fields
    ------------------------------------
    file          – image file (required)
    audio         – audio blob from the microphone (optional)
    machine_info  – short text describing the machine (optional, falls back
                    to ``prompt`` for backward-compat with the old frontend)
    prompt        – legacy field; used as machine_info if machine_info is
                    absent
    """
    # --- image (required) ---------------------------------------------------
    image_file = request.files.get("file")
    if not image_file:
        return jsonify({"error": "No image file provided"}), 400

    # --- audio (optional — raw blob, kept entirely in memory) ---------------
    audio_file = request.files.get("audio")
    audio_bytes: bytes | None = None
    audio_mime_type: str = "audio/webm"

    if audio_file:
        audio_bytes = audio_file.read()
        audio_mime_type = audio_file.content_type or audio_file.mimetype or "audio/webm"

    # --- text fields --------------------------------------------------------
    machine_info = (request.form.get("machine_info") or "").strip()
    prompt_text = (request.form.get("prompt") or "").strip()

    # If the caller didn't send a dedicated machine_info field, fall back to
    # the legacy ``prompt`` field so the old frontend still works.
    if not machine_info and prompt_text:
        machine_info = prompt_text

    # --- image bytes: save to a temp file because the Gemini file-upload
    #     API (used by prepare_files in mainPrompt) needs a file path for
    #     images.  Audio is handled in-memory via Part.from_bytes. ----------
    image_path: str | None = None
    try:
        image_ext = os.path.splitext(image_file.filename or "capture.png")[1] or ".png"
        fd, image_path = tempfile.mkstemp(suffix=image_ext)
        try:
            image_file.save(image_path)
        finally:
            os.close(fd)

        # --- call the main prompt pipeline ----------------------------------
        response_text = run_main_prompt(
            audio_bytes=audio_bytes,
            audio_mime_type=audio_mime_type,
            user_image_paths=[image_path],
            machine_info=machine_info,
        )

        return jsonify({"text": response_text})

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500

    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# POST /voice-to-text
# ---------------------------------------------------------------------------
@app.route("/voice-to-text", methods=["POST"])
def voice_to_text():
    """
    Standalone transcription used by the frontend's live voice-activity UI.
    Audio is kept entirely in memory — nothing is written to disk.

    Expected multipart/form-data fields
    ------------------------------------
    file  – audio blob (required)
    """
    audio_file = request.files.get("file")
    if not audio_file:
        return jsonify({"error": "No audio file provided"}), 400

    try:
        audio_bytes = audio_file.read()
        mime_type = audio_file.content_type or audio_file.mimetype or "audio/webm"

        client = _get_client()
        transcript = transcribe_audio_bytes(client, audio_bytes, mime_type)
        return jsonify({"text": transcript, "user_input_text": transcript})

    except Exception as exc:
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Server entry-point (called by start_server.py)
# ---------------------------------------------------------------------------
def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    app.run(host=host, port=port, debug=debug)
