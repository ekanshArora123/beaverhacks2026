# Prompt Pipeline

The core AI functionality is organized as a four-stage prompt pipeline. Each stage performs a specific task by calling the Gemini API, and stages can be run individually or as a sequence.

## Overview

| Stage | Name | Model | Input | Output |
|-------|------|-------|-------|--------|
| Prompt 1 | Technician Instruction | Text/Vision | Images + context + user message | Spoken-style guidance text |
| Prompt 2 | Diagram Generation | Vision | Prompt 1 response + images | Annotated diagram image |
| Prompt 3 | Text-to-Speech | TTS | Prompt 1 text response | Audio file (WAV) |
| Prompt 4 | Task State Update | — | Task name + status text | Persisted status file |

## Architecture

The pipeline is implemented using Python mixins composed into a single `GeminiSequenceBackend` dataclass:

```
GeminiSequenceBackend
  ├── MainPromptMixin      → run_first_prompt()
  ├── DiagramPromptMixin   → run_second_prompt()
  ├── TTSMixin             → run_third_prompt()
  └── StateUpdateMixin     → run_fourth_prompt()
```

The backend also exposes `run_four_prompts()` which runs all stages sequentially.

## Relevant Files

| File | Role |
|------|------|
| `backend/AIBackend.py` | `GeminiSequenceBackend` dataclass composing all mixins |
| `backend/ApiScripts/diagramPrompt.py` | `DiagramPromptMixin` and `MainPromptMixin` (prompt 1 and 2) |
| `backend/ApiScripts/mainPrompt.py` | Standalone prompt builder and orchestrator (legacy) |
| `backend/ApiScripts/textToVoice.py` | `TTSMixin` (prompt 3) |
| `backend/ApiScripts/updatePrompt.py` | `StateUpdateMixin` (prompt 4) |
| `backend/ApiScripts/GeminiEndpoint/config.py` | Default model name constants |
| `backend/programAPI.py` | HTTP route handlers for `/prompts/1` through `/prompts/4` and `/prompts/run-all` |

## Execution Flow

### Via `/analyze` (Frontend Flow)

1. Frontend submits images + audio/text to `POST /analyze`
2. `programAPI.py` parses inputs and creates a `GeminiSequenceBackend`
3. Audio is transcribed to text (if present)
4. `run_first_prompt()` generates guidance text
5. `run_second_prompt()` generates an annotated diagram (if images available)
6. Results are serialized with base64-encoded binaries and returned as JSON

### Via Individual Endpoints

Each prompt stage is also available as a standalone endpoint:
- `POST /prompts/1` — Run prompt 1 only
- `POST /prompts/2` — Run prompt 2 (requires `first_prompt_response`)
- `POST /prompts/3` — Run prompt 3 (requires `instruction_text`)
- `POST /prompts/4` — Run prompt 4 (requires `task_name` + `updated_status`)
- `POST /prompts/run-all` — Run all 4 sequentially

## Model Configuration

Default models are defined in `backend/ApiScripts/GeminiEndpoint/config.py`:

| Constant | Default Value | Usage |
|----------|--------------|-------|
| `TEXT_MODEL` | `gemini-3.1-pro-preview` | Text-only prompts |
| `VISION_MODEL` | `gemini-3-pro-image-preview` | Image analysis and diagram generation |
| `VOICE_MODEL` | `gemini-2.5-flash-preview-tts` | Text-to-speech |
| `DEFAULT_VOICE_NAME` | `charon` | TTS voice persona |

Models can be overridden per-request via `text_model`, `vision_model`, `voice_model`, and `voice_name` payload fields.
