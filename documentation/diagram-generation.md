# Diagram Generation

Prompt 2 generates an annotated diagram image by overlaying arrows, labels, and callouts on the technician's photo or a schematic, visually showing the next action to take.

## Overview

After Prompt 1 produces text guidance, Prompt 2 sends that text along with the original images to a Gemini vision model configured to return an image. The model edits the input photo by adding directional arrows, short labels, and diagram-style overlays so the technician can immediately see what to do.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/diagramPrompt.py` | `DiagramPromptMixin` — diagram prompt construction and response handling |
| `backend/AIBackend.py` | Composes `DiagramPromptMixin` into `GeminiSequenceBackend` |
| `backend/programAPI.py` | `/prompts/2` endpoint, `/analyze` integration, diagram source routing |
| `backend/ApiScripts/GeminiEndpoint/config.py` | `VISION_MODEL` default |
| `frontend/src/App.tsx` | Displays returned diagram and diagram source toggle |

## Execution Flow

1. `run_second_prompt()` receives the Prompt 1 response text, images, and context.
2. Builds a diagram-specific prompt payload including:
   - The main instruction text from Prompt 1
   - Task name and status
   - Additional context and user input text
   - Instructions for which image to use as the editing base
3. Calls Gemini vision model with `response_modalities=["IMAGE", "TEXT"]`.
4. Extracts the image bytes from the response's inline data parts.
5. Saves the diagram to `backend/generated_diagrams/` with a timestamped filename.
6. Returns the diagram path, MIME type, and any accompanying text.

## Diagram Source Selection

The system supports three diagram source modes, controlling which image the AI edits:

| Mode | Behavior |
|------|----------|
| `user` (default) | Edit the technician-provided photo |
| `schematic` | Edit the schematic/reference image |
| `all` / `auto` / `mixed` | Prefer technician photo, fall back to schematic |

The frontend provides a toggle button to switch between `user` and `schematic` modes. The selection is sent as `diagram_source` in the request payload.

## Image Splitting

When both schematic paths and uploaded photos are present, `programAPI._split_image_sources()` separates them:
- **Uploaded files** (saved to temp dir) → user photos
- **Pre-existing files** (from `image_paths`) → schematics

This split determines which images are sent to the diagram prompt.

## Output

Diagram files are written to `backend/generated_diagrams/`. Files are named `{task_name}_prompt_2_{timestamp}.{ext}` (typically `.png`). The image is base64-encoded and returned in the API response as `image` with `image_mime`.

## Skipping Diagram Generation

When no images are provided (text-only or audio-only submissions), the diagram step is skipped entirely to avoid errors from the vision model.
