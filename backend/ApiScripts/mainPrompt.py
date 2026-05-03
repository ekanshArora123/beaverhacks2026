"""
Main Prompt — Technician Assistance

Takes schematic images, user images, user message (transcribed voice),
machine info, and previous experience context.
Builds a prompt for Gemini and sends it via sendAPI.
Output is spoken-style text guidance for the technician.
"""

try:
    from GeminiEndpoint import sendAPI
except ImportError:
    sendAPI = None

import os
import time
from pathlib import Path
from typing import Sequence

from google import genai
from google.genai import types


class MainPromptMixin:
    def run_first_prompt(
        self,
        image_paths: Sequence[str | Path],
        text_source_1: str = "",
        text_source_2: str = "",
        task_name: str | int | None = None,
        mode: str = "text",
        prompt_text: str | None = None,
        text_model: str | None = None,
        vision_model: str | None = None,
        voice_model: str | None = None,
    ) -> dict[str, str | int | list[str] | None]:
        # Prompt 1 is the technician instruction stage.
        return self.generate(
            image_paths=image_paths,
            prompt_number=1,
            text_source_1=text_source_1,
            text_source_2=text_source_2,
            mode=mode,
            prompt_text=prompt_text,
            task_name=task_name,
            text_model=text_model,
            vision_model=vision_model,
            voice_model=voice_model,
        )

# ── Stand-in path constants (update to match your environment) ────────────────
SCHEMATIC_IMAGE_DIR = r"C:\path\to\schematic\images"
USER_IMAGE_DIR = r"C:\path\to\user\images"

# ── Gemini client setup ──────────────────────────────────────────────────────
try:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from keys import GEMINI_KEY
except ImportError:
    print("KEY NOT FOUND")
    GEMINI_KEY = None


def _get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY") or GEMINI_KEY
    print("GEMINI_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY env var or define GEMINI_KEY in keys.py")
    return genai.Client(api_key=api_key)


# ── File upload helpers ──────────────────────────────────────────────────────

def _upload_file(client: genai.Client, file_path: str, display_name: str) -> types.File:
    """Upload a single file via the Gemini file API with a descriptive name."""
    uploaded = client.files.upload(
        file=Path(file_path),
        config={"display_name": display_name},
    )
    while getattr(uploaded, "state", None) == types.FileState.PROCESSING:
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
    if getattr(uploaded, "state", None) == types.FileState.FAILED:
        raise RuntimeError(f"Gemini failed to process file: {display_name}")
    return uploaded


def _assign_names(paths: list[str], prefix: str) -> list[tuple[str, str]]:
    """Generate (path, display_name) pairs. Single items get no suffix."""
    if len(paths) == 1:
        return [(paths[0], prefix)]
    return [(p, f"{prefix}_{i + 1}") for i, p in enumerate(paths)]


def prepare_files(
    client: genai.Client,
    schematic_paths: list[str],
    user_image_paths: list[str],
) -> tuple[list[types.File], list[str], list[str]]:
    """Upload all images and return (file_objects, schematic_names, user_image_names)."""
    file_objects: list[types.File] = []
    schematic_names: list[str] = []
    user_image_names: list[str] = []

    for path, name in _assign_names(schematic_paths, "machine_schematic"):
        file_objects.append(_upload_file(client, path, name))
        schematic_names.append(name)

    for path, name in _assign_names(user_image_paths, "technician_photo"):
        file_objects.append(_upload_file(client, path, name))
        user_image_names.append(name)

    return file_objects, schematic_names, user_image_names


# ── Prompt builder ───────────────────────────────────────────────────────────

def build_prompt(
    user_message: str,
    machine_info: str,
    previous_context: str,
    schematic_names: list[str],
    user_image_names: list[str],
    tool_context: str = "",
) -> str:
    """Construct the full prompt as a single f-string."""

    # -- sub-sections built before the f-string for readability ----------------
    _effective_machine_info = machine_info.strip() if machine_info else ""
    if not _effective_machine_info and tool_context and tool_context.strip():
        _effective_machine_info = (
            f"TARGET MACHINE: {tool_context.strip()}\n"
            "Use the document retrieval tools to load documentation for this machine "
            "before answering the technician's question."
        )
    machine_section = (
        _effective_machine_info
        if _effective_machine_info
        else "No specific machine information was provided. Use your general technical knowledge, but inform the technician if you need more details about their specific machine."
    )

    context_section = (
        previous_context.strip()
        if previous_context and previous_context.strip()
        else "No previous experience context is available. Treat this as a first interaction."
    )

    if schematic_names:
        schematic_section = (
            "Refer to the attached schematic image(s) by the following name(s):\n"
            + "\n".join(f'  - "{name}"' for name in schematic_names)
        )
    else:
        schematic_section = "No schematic images were provided for this session."

    if user_image_names:
        user_image_section = (
            "The technician has provided the following image(s) showing their current situation. "
            "Examine these carefully to understand what the technician is seeing and describing.\n"
            + "\n".join(f'  - "{name}"' for name in user_image_names)
        )
    else:
        user_image_section = (
            "The technician has not provided any images of their current situation. "
            "Base your response only on their verbal description and the schematics."
        )

    # -- the prompt ------------------------------------------------------------
    prompt = f"""\
You are an expert field-service technician assistant providing real-time support. \
A technician is currently working on a piece of machinery and has contacted you for help. \
Your response will be converted to speech and played directly to the technician through their earpiece, \
so you must speak naturally and conversationally, as if you are a knowledgeable colleague standing right beside them on the job. \
The text will also be used by another model to to label a diagram of the machine.

=== MACHINE INFORMATION ===
The following is the known information about the machine the technician is working on. \
This provided information takes precedence over any prior knowledge you have about this machine or similar machines. \
Use your general knowledge of this machine to supplement details, but never contradict what is explicitly stated here.

{machine_section}

CRITICAL: If you do not have sufficient information about this specific machine, either from the details above \
or from your own training data, to provide a safe and accurate answer, you MUST clearly tell the technician \
that you do not have enough information and advise them to consult the manufacturer documentation, \
the machine manual, or a specialist. Never guess or speculate about safety-critical procedures, \
wiring, pressures, voltages, or chemical processes.

=== PREVIOUS EXPERIENCE CONTEXT ===
The following is a summary of the technician's previous interactions and documented experiences with this machine. \
Use this to avoid repeating steps already taken, build on previous troubleshooting progress, \
and maintain continuity across sessions.

{context_section}

=== MACHINE SCHEMATICS ===
{schematic_section}

Use these schematics to identify components, trace connections such as wiring, piping, or mechanical linkages, \
and give the technician precise spatial directions when guiding them to a part or area on the machine.

=== TECHNICIAN-PROVIDED IMAGES ===
{user_image_section}

=== TECHNICIAN'S MESSAGE ===
The technician has said the following (originally spoken, transcribed to text):

"{user_message}"

=== RESPONSE INSTRUCTIONS ===
Your response will be spoken aloud to the technician as a voice message. Follow these rules strictly:

Write in natural, spoken language. Do not use bullet points, numbered lists, markdown formatting, \
asterisks, dashes, special characters, or any visual-only formatting. Structure your response as \
flowing speech with clear pauses between ideas.

Be concise but thorough. The technician is actively working with their hands and needs clear, \
actionable guidance, not lengthy theory.

When referencing locations on the machine, use the schematics to give precise, unambiguous directions. \
For example say something like "the relay on the upper left of the control panel, the one labeled R3 \
on the schematic" rather than vague references.

If the technician provided images, describe specifically what you observe in them and connect your \
observations to your guidance. Do not ignore the images.

If the technician is documenting something rather than asking for help, acknowledge what they have \
recorded, confirm the details clearly, and note anything that seems unusual or worth flagging.

Prioritize safety above all else. If any recommended action could be dangerous, state the safety \
precaution first before giving the instruction. If you are unsure whether an action is safe, say so.

If you need more information from the technician to help them effectively, ask specific follow-up \
questions. Tell them exactly what to check, measure, or describe.

Do not use abbreviations or acronyms without first saying the full term at least once.

Keep your tone professional, calm, and supportive. The technician may be under stress."""

    return prompt


# ── API call stub ────────────────────────────────────────────────────────────

def send_api(prompt: str, files: list) -> str:
    """
    Stub — sends the prompt and uploaded file objects to the Gemini API.
    TODO: Replace with actual implementation.

    Args:
        prompt: The full prompt string.
        files:  List of Gemini file API file objects.

    Returns:
        The model's text response as a string.
    """
    print(f"[sendAPI stub] Would send prompt ({len(prompt)} chars) + {len(files)} file(s) to Gemini.")
    return "[Stub response — replace sendAPI with actual implementation]"


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_main_prompt(
    audio_bytes: bytes | None = None,
    audio_mime_type: str = "audio/webm",
    schematic_image_paths: list[str] | None = None,
    user_image_paths: list[str] | None = None,
    machine_info: str = "",
    previous_context: str = "",
) -> str:
    """
    Orchestrates the main prompt: transcribes audio, uploads images, builds
    prompt, calls API.

    Parameters
    ----------
    audio_bytes : bytes | None
        Raw audio data from the technician's microphone.  If provided, the
        audio is transcribed to text in-memory via
        ``voiceToText.transcribe_audio_bytes`` (no temp files).
        If *None*, a default message is used.
    audio_mime_type : str
        MIME type of the audio (e.g. ``"audio/webm"``, ``"audio/ogg"``).
    schematic_image_paths : list[str] | None
        Paths to schematic / reference images for the machine.
    user_image_paths : list[str] | None
        Paths to photos the technician captured of the current situation.
    machine_info : str
        Short description of the machine the technician is working on.
    previous_context : str
        Summary text of prior interactions / documented experience.

    Returns
    -------
    str
        The AI's text response (intended to be spoken to the technician).
    """
    try:
        from voiceToText import transcribe_audio_bytes
    except ImportError:
        from .voiceToText import transcribe_audio_bytes

    schematic_image_paths = schematic_image_paths or []
    user_image_paths = user_image_paths or []

    client = _get_client()

    # --- Transcribe audio to text (entirely in-memory) ----------------------
    if audio_bytes:
        user_message = transcribe_audio_bytes(client, audio_bytes, audio_mime_type)
    else:
        user_message = "No voice message was provided. Please analyze the images and machine information."

    file_objects, schematic_names, user_image_names = prepare_files(
        client, schematic_image_paths, user_image_paths
    )

    prompt = build_prompt(
        user_message=user_message,
        machine_info=machine_info,
        previous_context=previous_context,
        schematic_names=schematic_names,
        user_image_names=user_image_names,
    )

    response_text = send_api(prompt, file_objects)
    return response_text


def run_second_prompt(
    audio_bytes: bytes | None = None,
    audio_mime_type: str = "audio/webm",
    schematic_image_paths: list[str] | None = None,
    user_image_paths: list[str] | None = None,
    machine_info: str = "",
    previous_context: str = "",
) -> str:
    """Backward-compatible alias for older scripts."""
    return run_main_prompt(
        audio_bytes=audio_bytes,
        audio_mime_type=audio_mime_type,
        schematic_image_paths=schematic_image_paths,
        user_image_paths=user_image_paths,
        machine_info=machine_info,
        previous_context=previous_context,
    )


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    """Stand-in entry point for testing."""
    test_schematics = [
        os.path.join(SCHEMATIC_IMAGE_DIR, "schematic_page1.png"),
    ]
    test_user_images = [
        os.path.join(USER_IMAGE_DIR, "current_issue.jpg"),
    ]

    response = run_main_prompt(
        audio_bytes=None,  # provide raw audio bytes here for testing
        schematic_image_paths=test_schematics,
        user_image_paths=test_user_images,
        machine_info="Prusa MK4S 3D Printer, Serial: PM4S-2024-00847",
        previous_context="Last session: Technician replaced the extruder gear and recalibrated "
                         "the first layer. Print quality improved but technician noted intermittent "
                         "clicking from the extruder motor during long prints.",
    )

    print("\n" + "=" * 60)
    print("AI RESPONSE TO TECHNICIAN:")
    print("=" * 60)
    print(response)


if __name__ == "__main__":
    main()