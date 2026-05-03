"""Flask API layer for prompt pipeline execution.

This module keeps the frontend-compatible routes (`/analyze`, `/voice-to-text`)
and exposes explicit prompt-stage routes (`/prompts/*`) that execute the plan:
1) voice transcription, 2) main text instruction, 3) diagram generation,
4) text-to-speech, 5) task-state update.
"""

import base64
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from .AIBackend import GeminiSequenceBackend
except ImportError:
    from AIBackend import GeminiSequenceBackend

try:
    from .ApiScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_bytes,
        transcribe_audio_file,
    )
except ImportError:
    from ApiScripts.voiceToText import (
        DEFAULT_TRANSCRIPTION_PROMPT,
        SUPPORTED_AUDIO_SUFFIXES,
        VOICE_TO_TEXT_MODEL,
        transcribe_audio_bytes,
        transcribe_audio_file,
    )

try:
    from .ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL
except ImportError:
    from ApiScripts.GeminiEndpoint.config import DEFAULT_VOICE_NAME, TEXT_MODEL, VISION_MODEL, VOICE_MODEL

try:
    from .ApiScripts.docTools import prime_machine_doc_caches
except ImportError:
    from ApiScripts.docTools import prime_machine_doc_caches

try:
    from . import sessionStore
except ImportError:
    import sessionStore

try:
    from .ApiScripts.docTools import list_machine_folders as _list_machine_folders
except ImportError:
    from ApiScripts.docTools import list_machine_folders as _list_machine_folders

try:
    from .ApiScripts import toolPrimer as _tool_primer
except ImportError:
    from ApiScripts import toolPrimer as _tool_primer


app = Flask(__name__)
CORS(app)

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_PUBLIC_DIR = REPO_ROOT / "frontend" / "public"

SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PROMPT_UPLOAD_FIELD_NAMES = ("images", "image", "files", "file")


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


def _split_image_sources(image_paths: list[Path], temp_dir: Path) -> tuple[list[Path], list[Path]]:
    temp_root = temp_dir.resolve()
    schematic_paths: list[Path] = []
    user_uploaded_paths: list[Path] = []

    for image_path in image_paths:
        resolved_path = image_path.resolve()
        if resolved_path.is_relative_to(temp_root):
            user_uploaded_paths.append(resolved_path)
        else:
            schematic_paths.append(resolved_path)

    return schematic_paths, user_uploaded_paths


def _attach_binary_payload(value: object) -> object:
    if isinstance(value, dict):
        serialized = {key: _attach_binary_payload(nested_value) for key, nested_value in value.items()}

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
        return [_attach_binary_payload(item) for item in value]

    return value


def _json_error_response(exc: Exception):
    traceback.print_exc()
    status_code = 400 if isinstance(exc, (FileNotFoundError, ValueError)) else 500
    return jsonify({"error": str(exc)}), status_code


def _read_text_source_2(payload: dict[str, object], backend: GeminiSequenceBackend) -> str:
    explicit_text = _optional_str(_read_request_value(payload, "text_source_2"))
    if explicit_text:
        return explicit_text

    explicit_user_text = _optional_str(_read_request_value(payload, "user_input_text"))
    if explicit_user_text:
        return explicit_user_text

    audio_upload = request.files.get("audio")
    audio_path = _optional_str(_read_request_value(payload, "audio_path"))
    if not audio_upload and not audio_path:
        return ""

    transcript_prompt = (
        _optional_str(_read_request_value(payload, "transcription_prompt")) or DEFAULT_TRANSCRIPTION_PROMPT
    ).strip()
    transcript_model = (
        _optional_str(_read_request_value(payload, "voice_to_text_model")) or VOICE_TO_TEXT_MODEL
    ).strip()
    client = backend.get_client()

    if audio_upload:
        audio_bytes = audio_upload.read()
        mime_type = audio_upload.content_type or audio_upload.mimetype or "audio/webm"
        return transcribe_audio_bytes(
            client,
            audio_bytes,
            mime_type,
            prompt=transcript_prompt,
            model=transcript_model,
        )

    resolved_audio_path = _resolve_workspace_file(audio_path, allowed_suffixes=SUPPORTED_AUDIO_SUFFIXES)
    return transcribe_audio_file(
        client,
        resolved_audio_path,
        prompt=transcript_prompt,
        model=transcript_model,
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/analyze", methods=["POST"])
def analyze():
    """Frontend-compatible analysis endpoint backed by prompts 1 and 2."""
    payload = _get_json_payload()

    text_source_1 = _optional_str(_read_request_value(payload, "text_source_1"))
    machine_info = _optional_str(_read_request_value(payload, "machine_info"))
    legacy_prompt = _optional_str(_read_request_value(payload, "prompt"))
    if not text_source_1:
        text_source_1 = machine_info or legacy_prompt or ""

    # If a tool context is provided and we have cached documentation for it,
    # prepend it so the prompt prefix matches the KV-cached content from /set-tool.
    tool_context = _optional_str(_read_request_value(payload, "tool_context"))
    if tool_context:
        cached_docs = _tool_primer.get_cached_docs(tool_context)
        if cached_docs:
            display = tool_context.replace("_", " ")
            doc_prefix = f"=== {display} DOCUMENTATION ===\n{cached_docs}\n=== END DOCUMENTATION ==="
            text_source_1 = (f"{doc_prefix}\n\n{text_source_1}").strip() if text_source_1 else doc_prefix

    mode = _optional_str(_read_request_value(payload, "mode")) or "text"
    prompt_text = _optional_str(_read_request_value(payload, "prompt_text"))
    task_name = _read_request_value(payload, "task_name")
    diagram_source = (_optional_str(_read_request_value(payload, "diagram_source")) or "user").strip()

    try:
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            text_source_2 = _read_text_source_2(payload, backend)

            all_image_paths = _collect_image_paths(payload, temp_path)
            schematic_image_paths, user_uploaded_paths = _split_image_sources(all_image_paths, temp_path)

            first_result = backend.run_first_prompt(
                image_paths=all_image_paths,
                text_source_1=text_source_1,
                text_source_2=text_source_2,
                task_name=task_name,
                mode=mode,
                prompt_text=prompt_text,
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )

            normalized_diagram_source = diagram_source.strip().lower()
            if normalized_diagram_source in {"schematic", "schematics", "diagram"}:
                diagram_image_paths = schematic_image_paths or all_image_paths
            elif normalized_diagram_source in {"all", "auto", "mixed"}:
                diagram_image_paths = all_image_paths
            else:
                diagram_image_paths = user_uploaded_paths or all_image_paths

            # Skip diagram generation when no images are available — the
            # vision model needs at least one image to produce an annotated
            # diagram.  Text/audio-only submissions still get the first
            # prompt response.
            if diagram_image_paths:
                second_result = backend.run_second_prompt(
                    first_prompt_response=str(first_result.get("response_text") or ""),
                    task_name=task_name,
                    text_source_1=text_source_1,
                    text_source_2=text_source_2,
                    image_paths=diagram_image_paths,
                    mode="text",
                    prompt_text=None,
                    text_model=model_overrides["text_model"],
                    vision_model=model_overrides["vision_model"],
                    voice_model=model_overrides["voice_model"],
                    diagram_source=diagram_source,
                )
            else:
                second_result = {}

        serialized_first = _attach_binary_payload(first_result)
        serialized_second = _attach_binary_payload(second_result)

        response_body: dict[str, object] = {}
        if isinstance(serialized_second, dict):
            response_body.update(serialized_second)

        if isinstance(serialized_first, dict):
            response_body["first_prompt_response_text"] = serialized_first.get("response_text") or ""
            response_body["first_prompt_selected_model"] = serialized_first.get("selected_model")

        response_body["text"] = str(response_body.get("response_text") or "")
        response_body["model"] = (
            response_body.get("selected_model")
            or response_body.get("vision_model")
            or response_body.get("text_model")
        )
        response_body["user_input_text"] = text_source_2

        diagram_image_base64 = response_body.get("diagram_image_base64")
        if isinstance(diagram_image_base64, str) and diagram_image_base64:
            response_body["image"] = diagram_image_base64
            response_body["image_mime"] = response_body.get("diagram_mime_type") or "image/png"

        return jsonify(response_body)
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/voice-to-text", methods=["POST"])
def voice_to_text():
    payload = _get_json_payload()
    audio_upload = request.files.get("file") or request.files.get("audio")
    audio_path = _optional_str(_read_request_value(payload, "audio_path"))
    if not audio_upload and not audio_path:
        return jsonify({"error": "audio file or audio_path is required"}), 400

    prompt = (_optional_str(_read_request_value(payload, "prompt")) or DEFAULT_TRANSCRIPTION_PROMPT).strip()
    model = (_optional_str(_read_request_value(payload, "model")) or VOICE_TO_TEXT_MODEL).strip()

    try:
        backend = create_sequence_backend()
        client = backend.get_client()

        if audio_upload:
            audio_bytes = audio_upload.read()
            mime_type = audio_upload.content_type or audio_upload.mimetype or "audio/webm"
            transcript = transcribe_audio_bytes(
                client,
                audio_bytes,
                mime_type,
                prompt=prompt,
                model=model,
            )
        else:
            resolved_audio_path = _resolve_workspace_file(audio_path, allowed_suffixes=SUPPORTED_AUDIO_SUFFIXES)
            transcript = transcribe_audio_file(
                client,
                resolved_audio_path,
                prompt=prompt,
                model=model,
            )

        return jsonify({"text": transcript, "user_input_text": transcript, "model": model})
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/1", methods=["POST"])
def run_prompt_one():
    payload = _get_json_payload()

    try:
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            text_source_2 = _read_text_source_2(payload, backend)
            result = backend.run_first_prompt(
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=text_source_2,
                task_name=_read_request_value(payload, "task_name"),
                mode=_optional_str(_read_request_value(payload, "mode")) or "text",
                prompt_text=_optional_str(_read_request_value(payload, "prompt_text")),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )

        serialized = _attach_binary_payload(result)
        if isinstance(serialized, dict):
            serialized["text"] = serialized.get("response_text") or ""
        return jsonify(serialized)
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/2", methods=["POST"])
def run_prompt_two():
    payload = _get_json_payload()

    try:
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            text_source_2 = _read_text_source_2(payload, backend)
            result = backend.run_second_prompt(
                first_prompt_response=_required_str(
                    _read_request_value(payload, "first_prompt_response"), "first_prompt_response"
                ),
                task_name=_read_request_value(payload, "task_name"),
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=text_source_2,
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                mode=_optional_str(_read_request_value(payload, "mode")) or "text",
                prompt_text=_optional_str(_read_request_value(payload, "prompt_text")),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
                diagram_source=_optional_str(_read_request_value(payload, "diagram_source")),
            )

        serialized = _attach_binary_payload(result)
        if isinstance(serialized, dict):
            serialized["text"] = serialized.get("response_text") or ""
        return jsonify(serialized)
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/3", methods=["POST"])
def run_prompt_three():
    payload = _get_json_payload()

    try:
        backend = create_sequence_backend()
        model_overrides = _read_prompt_model_overrides(payload)
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
        return jsonify(_attach_binary_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/4", methods=["POST"])
def run_prompt_four():
    payload = _get_json_payload()

    try:
        backend = create_sequence_backend()
        result = backend.run_fourth_prompt(
            task_name=_required_str(_read_request_value(payload, "task_name"), "task_name"),
            updated_status=_required_str(_read_request_value(payload, "updated_status"), "updated_status"),
        )
        return jsonify(_attach_binary_payload(result))
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/prompts/run-all", methods=["POST"])
def run_all_prompts():
    payload = _get_json_payload()

    try:
        task_name = _required_str(_read_request_value(payload, "task_name"), "task_name")
        model_overrides = _read_prompt_model_overrides(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = create_sequence_backend()
            _apply_prompt_backend_overrides(backend, model_overrides)
            text_source_2 = _read_text_source_2(payload, backend)
            result = backend.run_four_prompts(
                image_paths=_collect_image_paths(payload, Path(temp_dir)),
                task_name=task_name,
                text_source_1=_optional_str(_read_request_value(payload, "text_source_1")) or "",
                text_source_2=text_source_2,
                updated_status=_optional_str(_read_request_value(payload, "updated_status")),
                voice_output=_coerce_bool(_read_request_value(payload, "voice_output"), default=True),
                text_model=model_overrides["text_model"],
                vision_model=model_overrides["vision_model"],
                voice_model=model_overrides["voice_model"],
            )

        serialized = _attach_binary_payload(result)
        if isinstance(serialized, dict):
            first_prompt = serialized.get("first_prompt")
            if isinstance(first_prompt, dict):
                serialized["text"] = first_prompt.get("response_text") or ""
        return jsonify(serialized)
    except Exception as exc:
        return _json_error_response(exc)


def _looks_like_ipv4(addr: str) -> bool:
    parts = addr.strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _windows_powershell_ipv4_addresses() -> list[str]:
    """List IPv4 addresses via PowerShell (Windows often exposes Hyper-V / Docker IPs via UDP heuristic alone)."""
    if sys.platform != "win32":
        return []
    script = (
        "Get-NetIPAddress -AddressFamily IPv4 "
        "| Where-Object { $_.IPAddress -notlike '127.*' } "
        "| Select-Object -ExpandProperty IPAddress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    out: list[str] = []
    for line in (proc.stdout or "").splitlines():
        candidate = line.strip()
        if _looks_like_ipv4(candidate):
            out.append(candidate)
    return out


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _lan_ipv4_rank(ip: str) -> tuple[int, str]:
    """Prefer typical home Wi‑Fi ranges; deprioritize APIPA, Docker bridge, unknown carriers."""
    parts = ip.split(".")
    if len(parts) != 4:
        return (1000, ip)
    try:
        a, b, _, _ = (int(x) for x in parts)
    except ValueError:
        return (1000, ip)
    if a == 127:
        return (999, ip)
    if a == 169 and b == 254:
        return (400, ip)
    if a == 172 and b == 17:
        return (350, ip)
    if a == 192 and b == 168:
        return (0, ip)
    if a == 10:
        return (20, ip)
    if a == 172 and 16 <= b <= 31:
        return (80, ip)
    return (200, ip)


def _drop_apipa_if_alternatives_exist(addresses: list[str]) -> list[str]:
    """Omit 169.254.x.x link-local IPs when we also have routable addresses (less confusing in QR lists)."""
    without_apipa = [a for a in addresses if not a.startswith("169.254.")]
    return without_apipa if without_apipa else addresses


def _detect_lan_ipv4_addresses() -> list[str]:
    """Best-effort enumeration of non-loopback IPv4 addresses for phone pairing QR URLs."""
    addresses: list[str] = []

    try:
        outbound_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            outbound_socket.connect(("8.8.8.8", 80))
            primary_address = outbound_socket.getsockname()[0]
        finally:
            outbound_socket.close()
        if primary_address and _looks_like_ipv4(primary_address) and not primary_address.startswith("127."):
            addresses.append(primary_address)
    except OSError:
        pass

    addresses.extend(_windows_powershell_ipv4_addresses())

    try:
        host_name = socket.gethostname()
        for info in socket.getaddrinfo(host_name, None, socket.AF_INET):
            candidate = info[4][0]
            if candidate.startswith("127.") or not _looks_like_ipv4(candidate):
                continue
            addresses.append(candidate)
    except (OSError, socket.gaierror):
        pass

    addresses = _dedupe_preserve_order(addresses)
    addresses.sort(key=_lan_ipv4_rank)
    return _drop_apipa_if_alternatives_exist(addresses)


@app.route("/host-info", methods=["GET"])
def host_info():
    return jsonify({"lan_addresses": _detect_lan_ipv4_addresses()})


@app.route("/session/new", methods=["POST"])
def session_new():
    code = sessionStore.create_session()
    return jsonify({"code": code})


def _normalize_session_code(code: str) -> str:
    return (code or "").strip().upper()


@app.route("/machine-folders", methods=["GET"])
def machine_folders():
    """Return the list of machine documentation folder names."""
    try:
        return jsonify({"folders": _list_machine_folders()})
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/set-tool", methods=["POST"])
def set_tool():
    """Prime Gemini's KV cache with documentation for a specific tool.

    Called immediately when a tool QR code is scanned.  Returns at once
    while extraction + priming run in a background thread.
    """
    print("[set-tool] Request received")
    body = request.get_json(silent=True, force=True) or {}
    tool_name = _optional_str(
        body.get("tool") or request.form.get("tool") or request.args.get("tool")
    )
    print(f"[set-tool] tool_name={tool_name!r}  body={body}")
    if not tool_name:
        return jsonify({"error": "tool parameter is required"}), 400

    # Validate: tool must exist as a machine_docs subfolder
    available = _list_machine_folders()
    print(f"[set-tool] available folders: {available}")
    if tool_name not in available:
        return jsonify({"error": f"Unknown tool: {tool_name!r}", "available": available}), 404

    try:
        backend = create_sequence_backend()
        client = backend.get_client()
        _tool_primer.start_prime_background(tool_name, client, backend.text_model)
    except Exception as exc:
        # Non-fatal — priming is best-effort
        print(f"[set-tool] Failed to start prime for {tool_name!r}: {exc}")

    display_name = tool_name.replace("_", " ")
    print(f"[set-tool] Priming started for {tool_name!r}")
    return jsonify({"status": "priming", "tool": tool_name, "display_name": display_name})


@app.route("/session/<code>/input", methods=["POST"])
def session_input(code: str):
    code = _normalize_session_code(code)
    if not sessionStore.session_exists(code):
        return jsonify({"error": "Unknown or expired session code"}), 404

    try:
        image_data_urls: list[str] = []
        for uploaded_file in _iter_uploaded_files(PROMPT_UPLOAD_FIELD_NAMES):
            suffix = Path(uploaded_file.filename).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_SUFFIXES:
                allowed_text = ", ".join(sorted(item.lstrip(".") for item in SUPPORTED_IMAGE_SUFFIXES))
                return jsonify({"error": f"Unsupported image type for {uploaded_file.filename}. Use {allowed_text}."}), 400
            mime_type = uploaded_file.content_type or uploaded_file.mimetype or f"image/{suffix.lstrip('.') or 'png'}"
            image_data_urls.append(sessionStore.encode_data_url(uploaded_file.read(), mime_type))

        audio_data_url: str | None = None
        audio_mime: str | None = None
        audio_extension: str | None = None
        audio_upload = request.files.get("audio")
        if audio_upload and getattr(audio_upload, "filename", ""):
            audio_mime = audio_upload.content_type or audio_upload.mimetype or "audio/webm"
            audio_extension = Path(audio_upload.filename).suffix.lstrip(".") or "webm"
            audio_data_url = sessionStore.encode_data_url(audio_upload.read(), audio_mime)

        text_value = _optional_str(request.form.get("text_source_2") or request.form.get("text"))
        diagram_source = _optional_str(request.form.get("diagram_source"))
        tool_context = _optional_str(request.form.get("tool_context"))

        if not image_data_urls and not audio_data_url and not text_value:
            return jsonify({"error": "Phone payload must include at least one image, audio, or text"}), 400

        payload: dict[str, object] = {
            "image_data_urls": image_data_urls,
            "audio_data_url": audio_data_url,
            "audio_mime": audio_mime,
            "audio_extension": audio_extension,
            "text_source_2": text_value,
            "diagram_source": diagram_source,
            "tool_context": tool_context,
            "received_at": time.time(),
        }

        delivered = sessionStore.push_payload(code, payload)
        if not delivered:
            return jsonify({"error": "Unknown or expired session code"}), 404

        return jsonify({"status": "ok", "image_count": len(image_data_urls), "has_audio": bool(audio_data_url), "has_text": bool(text_value)})
    except Exception as exc:
        return _json_error_response(exc)


@app.route("/session/<code>/pending", methods=["GET"])
def session_pending(code: str):
    code = _normalize_session_code(code)
    if not sessionStore.session_exists(code):
        return jsonify({"error": "Unknown or expired session code"}), 404

    try:
        timeout_seconds = float(request.args.get("timeout", "25"))
    except ValueError:
        timeout_seconds = 25.0
    timeout_seconds = max(1.0, min(timeout_seconds, 55.0))

    payload = sessionStore.pop_payload(code, timeout_seconds)
    if payload is None:
        return ("", 204)
    return jsonify(payload)


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    try:
        backend = create_sequence_backend()
        cache_summary = prime_machine_doc_caches(backend.get_client(), backend.text_model or TEXT_MODEL)
        print(f"[startup] machine-doc cache summary: {cache_summary}")
    except Exception as exc:
        print(f"[startup] machine-doc cache init failed: {exc}")
    app.run(host=host, port=port, debug=debug, threaded=True)
