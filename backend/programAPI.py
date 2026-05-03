import base64
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS
from google import genai
from google.genai import types

try:
    from .AIBackend import GeminiSequenceBackend
except ImportError:
    from AIBackend import GeminiSequenceBackend

try:
    from .ApiScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_file,
    )
except ImportError:
    from ApiScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_file,
    )

try:
    from .ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL
except ImportError:
    from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL


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

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_PUBLIC_DIR = REPO_ROOT / "frontend" / "public"

ANALYZE_TEXT_MODEL = TEXT_MODEL
ANALYZE_MEDIA_MODEL = VISION_MODEL
GENERATE_MODEL = VISION_MODEL

SUPPORTED_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp3",
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
}
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PROMPT_UPLOAD_FIELD_NAMES = ("images", "image", "files")


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
    if not api_key:
        raise RuntimeError("Set the GEMINI_API_KEY environment variable.")
    return genai.Client(api_key=api_key)


def create_sequence_backend() -> GeminiSequenceBackend:
    return GeminiSequenceBackend()


def _get_json_payload() -> dict[str, object]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _read_request_value(payload: dict[str, object], field_name: str, default: object = None) -> object:
    if field_name in payload:
        return payload[field_name]

    if field_name in request.form:
        return request.form.get(field_name, default)

    return default


def _read_request_list(payload: dict[str, object], field_name: str) -> list[str]:
    if field_name in payload:
        raw_value = payload[field_name]
        if raw_value is None:
            return []
        if isinstance(raw_value, (list, tuple)):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        if isinstance(raw_value, str):
            stripped_value = raw_value.strip()
            if not stripped_value:
                return []
            if stripped_value.startswith("["):
                try:
                    parsed_value = json.loads(stripped_value)
                except json.JSONDecodeError:
                    return [stripped_value]
                if isinstance(parsed_value, list):
                    return [str(item).strip() for item in parsed_value if str(item).strip()]
            return [stripped_value]
        return [str(raw_value).strip()]

    form_values = request.form.getlist(field_name)
    return [value.strip() for value in form_values if value and value.strip()]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None

    normalized_value = str(value).strip()
    return normalized_value or None


def _required_str(value: object, field_name: str) -> str:
    normalized_value = _optional_str(value)
    if not normalized_value:
        raise ValueError(f"{field_name} is required")
    return normalized_value


def _coerce_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_prompt_model_overrides(payload: dict[str, object]) -> dict[str, str | None]:
    # Allow a single "model" value to act as a shared text/vision override.
    shared_model = _optional_str(_read_request_value(payload, "model"))
    text_model = _optional_str(_read_request_value(payload, "text_model")) or shared_model
    vision_model = _optional_str(_read_request_value(payload, "vision_model")) or shared_model
    voice_model = _optional_str(_read_request_value(payload, "voice_model"))
    voice_name = _optional_str(_read_request_value(payload, "voice_name"))
    return {
        "text_model": text_model,
        "vision_model": vision_model,
        "voice_model": voice_model,
        "voice_name": voice_name,
    }


def _apply_prompt_backend_overrides(
    backend: GeminiSequenceBackend,
    model_overrides: dict[str, str | None],
) -> None:
    text_model = model_overrides.get("text_model")
    if text_model:
        backend.text_model = text_model

    vision_model = model_overrides.get("vision_model")
    if vision_model:
        backend.vision_model = vision_model

    voice_model = model_overrides.get("voice_model")
    if voice_model:
        backend.voice_model = voice_model

    voice_name = model_overrides.get("voice_name")
    if voice_name:
        backend.voice_name = voice_name


def _resolve_workspace_file(raw_path: str, *, allowed_suffixes: set[str] | None = None) -> Path:
    normalized_text = raw_path.strip()
    if not normalized_text:
        raise ValueError("path cannot be empty")
    if normalized_text.startswith(("http://", "https://")):
        raise ValueError("Remote URLs are not supported. Send uploaded files or workspace paths instead.")

    stripped_text = normalized_text.lstrip("/\\")
    raw_candidate = Path(normalized_text).expanduser()
    candidate_paths: list[Path] = []

    if raw_candidate.is_absolute():
        candidate_paths.append(raw_candidate)
    else:
        candidate_paths.extend(
            [
                REPO_ROOT / normalized_text,
                REPO_ROOT / stripped_text,
                BACKEND_DIR / normalized_text,
                BACKEND_DIR / stripped_text,
                FRONTEND_PUBLIC_DIR / stripped_text,
            ]
        )

    seen_paths: set[str] = set()
    for candidate_path in candidate_paths:
        resolved_path = candidate_path.resolve()
        resolved_key = str(resolved_path).lower()
        if resolved_key in seen_paths:
            continue
        seen_paths.add(resolved_key)

        if resolved_path.exists() and resolved_path.is_file():
            if allowed_suffixes and resolved_path.suffix.lower() not in allowed_suffixes:
                allowed_text = ", ".join(sorted(suffix.lstrip(".") for suffix in allowed_suffixes))
                raise ValueError(f"Unsupported file type for {resolved_path.name}. Use {allowed_text}.")
            return resolved_path

    raise FileNotFoundError(f"File not found for path: {normalized_text}")


def _iter_uploaded_files(field_names: tuple[str, ...]) -> list[Any]:
    uploaded_files: list[Any] = []
    for field_name in field_names:
        uploaded_files.extend(
            file for file in request.files.getlist(field_name) if file and getattr(file, "filename", "")
        )
    return uploaded_files


def _save_uploaded_files(temp_dir: Path, *, allowed_suffixes: set[str], field_names: tuple[str, ...]) -> list[Path]:
    saved_paths: list[Path] = []
    for index, uploaded_file in enumerate(_iter_uploaded_files(field_names), start=1):
        suffix = Path(uploaded_file.filename).suffix.lower()
        if suffix not in allowed_suffixes:
            allowed_text = ", ".join(sorted(item.lstrip(".") for item in allowed_suffixes))
            raise ValueError(f"Unsupported file type for {uploaded_file.filename}. Use {allowed_text}.")

        destination = temp_dir / f"upload_{index}{suffix}"
        uploaded_file.save(destination)
        saved_paths.append(destination)

    return saved_paths


def _collect_image_paths(payload: dict[str, object], temp_dir: Path) -> list[Path]:
    raw_image_paths = _read_request_list(payload, "image_paths")
    single_image_path = _optional_str(_read_request_value(payload, "image_path"))
    if single_image_path:
        raw_image_paths.append(single_image_path)

    resolved_paths = [
        _resolve_workspace_file(raw_path, allowed_suffixes=SUPPORTED_IMAGE_SUFFIXES)
        for raw_path in raw_image_paths
    ]
    uploaded_paths = _save_uploaded_files(
        temp_dir,
        allowed_suffixes=SUPPORTED_IMAGE_SUFFIXES,
        field_names=PROMPT_UPLOAD_FIELD_NAMES,
    )
    return [*resolved_paths, *uploaded_paths]


def _attach_audio_payload(value: object) -> object:
    if isinstance(value, dict):
        serialized = {key: _attach_audio_payload(nested_value) for key, nested_value in value.items()}
        audio_path = serialized.get("audio_path")
        if isinstance(audio_path, str) and audio_path:
            resolved_audio_path = Path(audio_path)
            if resolved_audio_path.exists() and resolved_audio_path.is_file():
                serialized["audio_base64"] = base64.b64encode(resolved_audio_path.read_bytes()).decode("ascii")

        diagram_image_path = serialized.get("diagram_image_path")
        if isinstance(diagram_image_path, str) and diagram_image_path:
            resolved_diagram_path = Path(diagram_image_path)
            if resolved_diagram_path.exists() and resolved_diagram_path.is_file():
                serialized["diagram_image_base64"] = base64.b64encode(
                    resolved_diagram_path.read_bytes()
                ).decode("ascii")
        return serialized

    if isinstance(value, list):
        return [_attach_audio_payload(item) for item in value]

    return value


def _json_error_response(exc: Exception):
    status_code = 400 if isinstance(exc, (FileNotFoundError, ValueError)) else 500
    return jsonify({"error": str(exc)}), status_code


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
    print("--- [ENDPOINT HIT]: GET /health ---")
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
    print("--- [ENDPOINT HIT]: POST /analyze ---")
    payload = _get_json_payload()
    prompt = _optional_str(_read_request_value(payload, "prompt")) or "Describe this media."
    requested_model = _optional_str(_read_request_value(payload, "model"))
    file = request.files.get("file")

    try:
        client = get_client()
        selected_model = requested_model or ANALYZE_TEXT_MODEL

        if file and file.filename:
            suffix = Path(file.filename).suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                return jsonify({"error": f"Unsupported file type: {suffix}"}), 400

            selected_model = requested_model or ANALYZE_MEDIA_MODEL

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                file.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                uploaded = client.files.upload(file=tmp_path)
                ready = wait_for_upload(client, uploaded)
                response = client.models.generate_content(
                    model=selected_model,
                    contents=[ready, prompt],
                )
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            response = client.models.generate_content(
                model=selected_model,
                contents=[prompt],
            )

        return jsonify({"text": response.text or "", "model": selected_model})

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
          "text":       "...",
          "image":      "<base64>",
          "image_mime": "image/png"
        }
    """
    print("--- [ENDPOINT HIT]: POST /generate ---")
    payload = _get_json_payload()
    prompt = _optional_str(_read_request_value(payload, "prompt")) or ""
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    selected_model = _optional_str(_read_request_value(payload, "model")) or GENERATE_MODEL

    try:
        client = get_client()
        response = client.models.generate_content(
            model=selected_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        result: dict[str, str | None] = {"text": "", "image": None, "image_mime": None}
        for part in response.parts or []:
            if part.text:
                result["text"] += part.text
            elif part.inline_data and part.inline_data.data:
                result["image"] = base64.b64encode(part.inline_data.data).decode()
                result["image_mime"] = part.inline_data.mime_type

        result["model"] = selected_model

        return jsonify(result)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/voice-to-text", methods=["POST"])
def voice_to_text():
    """
    Transcribe uploaded audio into plain text for later use as prompt 2 user input.

    Request (multipart/form-data or JSON):
        file       - audio file
        audio_path - existing workspace audio path
        prompt     - optional transcription instruction
        model      - optional Gemini model override
    """
    print("--- [ENDPOINT HIT]: POST /voice-to-text ---")
    payload = _get_json_payload()
    file = request.files.get("file")
    audio_path = _optional_str(_read_request_value(payload, "audio_path"))
    if (not file or not file.filename) and not audio_path:
        return jsonify({"error": "audio file or audio_path is required"}), 400

    prompt = (_optional_str(_read_request_value(payload, "prompt")) or DEFAULT_TRANSCRIPTION_PROMPT).strip()
    model = (_optional_str(_read_request_value(payload, "model")) or VOICE_TO_TEXT_MODEL).strip()

    try:
        if file and file.filename:
            suffix = Path(file.filename).suffix.lower()
            if suffix not in SUPPORTED_AUDIO_SUFFIXES:
                return jsonify({"error": f"Unsupported audio type: {suffix}"}), 400

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
        else:
            resolved_audio_path = _resolve_workspace_file(audio_path, allowed_suffixes=SUPPORTED_AUDIO_SUFFIXES)
            transcript_text = transcribe_audio_file(
                client=get_client(),
                audio_path=resolved_audio_path,
                prompt=prompt,
                model=model,
            )

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
        return _json_error_response(exc)


@app.route("/prompts/1", methods=["POST"])
def run_prompt_one():
    print("--- [ENDPOINT HIT]: POST /prompts/1 ---")
    payload = _get_json_payload()

    try:
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            result = backend.run_first_prompt(
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=_optional_str(_read_request_value(payload, "text_source_2")) or "",
                task_name=_read_request_value(payload, "task_name"),
                mode=_optional_str(_read_request_value(payload, "mode")) or "text",
                prompt_text=_optional_str(_read_request_value(payload, "prompt_text")),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )
        return jsonify(_attach_audio_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/2", methods=["POST"])
def run_prompt_two():
    print("--- [ENDPOINT HIT]: POST /prompts/2 ---")
    payload = _get_json_payload()

    try:
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            result = backend.run_second_prompt(
                first_prompt_response=_required_str(
                    _read_request_value(payload, "first_prompt_response"), "first_prompt_response"
                ),
                task_name=_read_request_value(payload, "task_name"),
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=_optional_str(_read_request_value(payload, "text_source_2")) or "",
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                mode=_optional_str(_read_request_value(payload, "mode")) or "text",
                prompt_text=_optional_str(_read_request_value(payload, "prompt_text")),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )
        return jsonify(_attach_audio_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/3", methods=["POST"])
def run_prompt_three():
    print("--- [ENDPOINT HIT]: POST /prompts/3 ---")
    payload = _get_json_payload()

    try:
        backend = create_sequence_backend()
        model_overrides = _read_prompt_model_overrides(payload)
        # Prompt 3 only synthesizes audio, so we apply voice-level overrides directly.
        _apply_prompt_backend_overrides(backend, model_overrides)
        if not model_overrides.get("voice_model") and _optional_str(_read_request_value(payload, "model")):
            backend.voice_model = _required_str(_read_request_value(payload, "model"), "model")
        if not model_overrides.get("voice_name"):
            backend.voice_name = DEFAULT_VOICE_NAME
        if not backend.voice_model:
            backend.voice_model = VOICE_MODEL
        result = backend.run_third_prompt(
            _required_str(_read_request_value(payload, "instruction_text"), "instruction_text")
        )
        return jsonify(_attach_audio_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/4", methods=["POST"])
def run_prompt_four():
    print("--- [ENDPOINT HIT]: POST /prompts/4 ---")
    payload = _get_json_payload()

    try:
        backend = create_sequence_backend()
        result = backend.run_fourth_prompt(
            task_name=_required_str(_read_request_value(payload, "task_name"), "task_name"),
            updated_status=_required_str(_read_request_value(payload, "updated_status"), "updated_status"),
        )
        return jsonify(_attach_audio_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/run-all", methods=["POST"])
def run_all_prompts():
    print("--- [ENDPOINT HIT]: POST /prompts/run-all ---")
    payload = _get_json_payload()

    try:
        task_name = _required_str(_read_request_value(payload, "task_name"), "task_name")
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            result = backend.run_four_prompts(
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                task_name=task_name,
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=_optional_str(_read_request_value(payload, "text_source_2")) or "",
                updated_status=_optional_str(_read_request_value(payload, "updated_status")),
                voice_output=_coerce_bool(_read_request_value(payload, "voice_output"), default=True),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )
        return jsonify(_attach_audio_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


def run_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Start the backend HTTP server and wait for frontend API calls."""
    print(f"Backend API listening on http://{host}:{port}")
    print(
        "Routes: GET /health, POST /analyze, POST /generate, POST /voice-to-text, "
        "POST /prompts/1, POST /prompts/2, POST /prompts/3, POST /prompts/4, POST /prompts/run-all"
    )
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    default_host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    default_port = int(os.environ.get("BACKEND_PORT", "5000"))
    default_debug = os.environ.get("BACKEND_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
    run_server(host=default_host, port=default_port, debug=default_debug)
