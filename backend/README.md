# Backend — Flask API + Gemini Prompt Pipeline

The backend is a Python Flask server that orchestrates a multi-stage Gemini AI pipeline for real-time technician assistance. It handles image analysis, voice transcription, diagram generation, text-to-speech, task state persistence, and phone session management.

## File Structure

```
backend/
├── programAPI.py              # Flask routes and request handling
├── AIBackend.py               # GeminiSequenceBackend — orchestrates all prompt stages
├── sessionStore.py            # In-memory session store for phone pairing
├── start_server.py            # Server entry point
├── test_text_to_voice.py      # Standalone TTS test script
│
├── ApiScripts/                # Core AI prompt modules
│   ├── mainPrompt.py          # Prompt 1 — technician instruction text generation
│   ├── diagramPrompt.py       # Prompt 2 — annotated diagram image generation
│   ├── textToVoice.py         # Prompt 3 — text-to-speech via Gemini
│   ├── updatePrompt.py        # Prompt 4 — task state persistence
│   ├── voiceToText.py         # Audio transcription (speech-to-text)
│   ├── docTools.py            # Agentic document retrieval tools for Gemini
│   ├── pdf_to_md.py           # PDF-to-Markdown conversion utility
│   └── GeminiEndpoint/        # Gemini API configuration
│       ├── config.py          # Model name constants and defaults
│       └── geminiAPI.py       # Reference Gemini API call (template)
│
├── generated_audio/           # TTS output files (auto-created)
├── generated_diagrams/        # Diagram output files (auto-created)
├── registry/                  # Tool-context registry (placeholder)
│
└── tests/                     # Unit tests
    ├── test_program_api_analyze.py
    ├── test_prompt_api.py
    ├── test_prompt_context_growth.py
    ├── test_session_routes.py
    └── test_session_store.py
```

## Execution Flow

### Server Startup

1. `start_server.py` reads `BACKEND_HOST`, `BACKEND_PORT`, and `BACKEND_DEBUG` from environment variables.
2. Calls `run_server()` in `programAPI.py`.
3. On startup, `run_server()` creates a `GeminiSequenceBackend` and calls `prime_machine_doc_caches()` to warm the local document text cache and create Gemini explicit caches for large machine documentation.
4. Flask starts on `0.0.0.0:5000` with CORS enabled and threaded mode on.

### API Key Resolution

The API key is resolved in this priority order:
1. `GEMINI_API_KEY` environment variable
2. `GEMINI_KEY` constant from `keys.py` at the project root

### Request Handling (`programAPI.py`)

`programAPI.py` is the main Flask application. It defines all routes and contains helper functions for:
- Parsing JSON and multipart form payloads (`_get_json_payload`, `_read_request_value`, etc.)
- Resolving image and audio file paths (`_resolve_workspace_file`, `_collect_image_paths`)
- Saving uploaded files to temp directories (`_save_uploaded_files`)
- Splitting images into schematic vs user-uploaded categories (`_split_image_sources`)
- Converting file paths to base64 for JSON responses (`_attach_binary_payload`)
- Detecting LAN IPv4 addresses for phone pairing QR codes (`_detect_lan_ipv4_addresses`)

### Prompt Pipeline (`AIBackend.py`)

`GeminiSequenceBackend` is a dataclass that composes four mixin classes:

| Mixin | File | Prompt | Purpose |
|-------|------|--------|---------|
| `MainPromptMixin` | `diagramPrompt.py` | 1 | Generate technician instruction text |
| `DiagramPromptMixin` | `diagramPrompt.py` | 2 | Generate annotated diagram image |
| `TTSMixin` | `textToVoice.py` | 3 | Convert instruction text to speech |
| `StateUpdateMixin` | `updatePrompt.py` | 4 | Persist task status to disk |

The backend maintains state fields (current images, text sources, task name, selected model) that flow between prompt stages.

### `/analyze` Endpoint Flow

This is the primary endpoint called by the frontend:

1. **Parse inputs** — text sources, model overrides, images (file paths + uploads), audio
2. **Transcribe audio** — If audio is present, use `voiceToText.transcribe_audio_bytes()` to convert to text via Gemini
3. **Run Prompt 1** — Send images + context to Gemini for technician guidance text
4. **Run Prompt 2** — Send first response + images to Gemini vision model to generate an annotated diagram image (skipped if no images provided)
5. **Serialize response** — Encode diagram and audio files as base64, return JSON

### Document Retrieval (`docTools.py`)

Three tool functions are registered with Gemini's automatic function calling:
- `list_machine_folders()` — List available machine doc directories
- `list_documents(machine_name)` — List files in a machine's folder
- `read_document(machine_name, filename)` — Read text content from a doc

At startup, markdown docs are pre-cached in memory, and large docs are uploaded to Gemini's explicit cache for faster retrieval.

### Session Management (`sessionStore.py`)

An in-memory pairing store allows a phone to send captured images/audio to the laptop:
- Sessions are identified by 6-character codes (e.g., `ABC123`)
- Payloads are queued and long-polled by the laptop
- Sessions expire after 1 hour of inactivity
- Thread-safe via `threading.Lock`

## Running

```bash
# From the project root
python backend/start_server.py

# Or with environment overrides
BACKEND_PORT=8080 python backend/start_server.py
```

## Testing

```bash
cd backend
python -m pytest tests/ -v
```
