# Task State Management

Prompt 4 persists task progress to disk so the AI can maintain context across multiple interactions and sessions. Task state includes status text and associated images.

## Overview

Each task is identified by a name (e.g., `task1`, `brake_repair`) and gets a dedicated directory under `taskStates/`. The directory stores a status text file and any associated images. On each new request, the backend loads the task's current status and images to include as context for the AI.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/updatePrompt.py` | `StateUpdateMixin` — read/write task state |
| `backend/AIBackend.py` | Composes `StateUpdateMixin` into `GeminiSequenceBackend` |
| `backend/programAPI.py` | `/prompts/4` endpoint |
| `taskStates/` | Root directory for all task state folders |

## Data Structure

```
taskStates/
├── task1/
│   ├── text1.txt          # Current task status text
│   ├── photo1.png         # (Optional) associated task images
│   └── photo2.jpg
└── task2/
    └── text1.txt
```

## Execution Flow

### Writing State (Prompt 4)

1. `run_fourth_prompt(task_name, updated_status)` is called.
2. The task name is normalized (e.g., `1` → `task1`).
3. The task directory is created if it doesn't exist.
4. The status text is written to `text1.txt` in the task's directory.

### Loading State (Prompts 1 & 2)

When a request includes a `task_name`:
1. `_load_task_status()` reads `text1.txt` from the task directory. If it starts with `STATUS=`, the value after `=` is parsed.
2. `_load_task_image_paths()` scans the task directory for image files (`.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`).
3. The loaded status and images are included as context in the prompt payload.

## Task Name Normalization

| Input | Normalized |
|-------|-----------|
| `1` | `task1` |
| `"task1"` | `task1` |
| `"brake_repair"` | `brake_repair` |
| `None` or `""` | `None` (no task context loaded) |

## API Endpoint

`POST /prompts/4` requires:
- `task_name` (string) — The task identifier
- `updated_status` (string) — New status text to persist
