# Voice Input (Speech-to-Text)

Audio captured from the technician's microphone is transcribed to text using Gemini, then fed into the main prompt pipeline as the technician's question or message.

## Overview

The system supports two transcription modes:
- **In-memory bytes** — Audio data is sent directly as raw bytes (no temp files)
- **File-based** — An audio file path is uploaded to the Gemini file API

The in-memory mode is the primary path used by the frontend.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/voiceToText.py` | Core transcription functions |
| `backend/programAPI.py` | `/voice-to-text` endpoint + `_read_text_source_2()` helper |
| `frontend/src/App.tsx` | Audio recording and submission from laptop |
| `frontend/src/hooks/useCaptureSession.ts` | Reusable mic capture hook (used by mobile page) |

## Supported Audio Formats

File extensions: `.wav`, `.mp3`, `.aiff`, `.aac`, `.ogg`, `.webm`, `.flac`, `.m4a`

MIME types: `audio/wav`, `audio/mp3`, `audio/mpeg`, `audio/aiff`, `audio/aac`, `audio/ogg`, `audio/webm`, `audio/flac`, `audio/mp4`, `audio/m4a` (with codec variants)

## Execution Flow

### From `/analyze`

1. The frontend records audio using `MediaRecorder` and submits it as a file in `FormData` under the `audio` field.
2. `programAPI._read_text_source_2()` detects the audio upload.
3. Calls `voiceToText.transcribe_audio_bytes()` with the raw bytes and MIME type.
4. Gemini transcribes the audio and returns the text.
5. The transcribed text becomes `text_source_2` for the main prompt.

### Standalone `/voice-to-text`

The endpoint accepts either:
- A file upload (`file` or `audio` field in multipart form)
- An `audio_path` pointing to a file on the server

Returns `{ "text": "transcribed text", "model": "..." }`.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `VOICE_TO_TEXT_MODEL` | `gemini-3-flash-preview` | Gemini model used for transcription |
| `DEFAULT_TRANSCRIPTION_PROMPT` | `"Generate an accurate transcript of the speech. Return only the spoken text."` | System prompt for transcription |

Both are overridable per-request via `model` and `prompt` (or `transcription_prompt`) payload fields.

## Frontend Audio Recording

The frontend negotiates the best available recording format at init time, trying in order:
1. `audio/ogg;codecs=opus`
2. `audio/ogg`
3. `audio/mp4`
4. `audio/aac`
5. `audio/webm;codecs=opus`
6. `audio/webm`

Recording is started/stopped manually via a button toggle. The recording state is visually indicated on the webcam panel.
