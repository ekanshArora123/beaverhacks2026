# Text-to-Speech Output

Prompt 3 converts the AI's text response into spoken audio using Gemini's TTS capabilities, allowing hands-free delivery of instructions to the technician.

## Overview

After the main prompt generates guidance text (Prompt 1), the text can be converted to audio using the `TTSMixin`. The audio file is saved to disk and returned as base64-encoded data in the API response.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/textToVoice.py` | `TTSMixin` class — Gemini TTS generation |
| `backend/AIBackend.py` | Composes `TTSMixin` into `GeminiSequenceBackend` |
| `backend/programAPI.py` | `/prompts/3` endpoint |
| `backend/ApiScripts/GeminiEndpoint/config.py` | `VOICE_MODEL` and `DEFAULT_VOICE_NAME` defaults |
| `backend/test_text_to_voice.py` | Standalone TTS test script |

## Execution Flow

1. `run_third_prompt(instruction_text)` is called with the guidance text from Prompt 1.
2. Sends the text to Gemini with `response_modalities=["AUDIO"]` and the configured voice name.
3. Extracts audio bytes from the response's inline data parts.
4. Saves the audio file to `backend/generated_audio/` with a timestamped filename (e.g., `prompt_3_1714700000.wav`).
5. Returns the file path and MIME type.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `VOICE_MODEL` | `gemini-2.5-flash-preview-tts` | Gemini model for TTS |
| `DEFAULT_VOICE_NAME` | `charon` | Voice persona name |

Both are overridable per-request via `voice_model` and `voice_name` payload fields.

## Output

Audio files are written to `backend/generated_audio/`. The directory is auto-created if it doesn't exist. Files are named `prompt_{number}_{timestamp}.{ext}` where the extension is inferred from the response MIME type (typically `.wav`).

## Frontend Integration

In addition to the Gemini TTS path, the frontend also uses the browser's built-in `SpeechSynthesis` API to immediately read the text response aloud, providing instant audio feedback without waiting for the Gemini TTS round-trip.
