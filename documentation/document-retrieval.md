# Document Retrieval (Agentic)

The system uses Gemini's automatic function calling to let the AI autonomously browse and read machine-specific documentation stored locally, enriching its responses with real technical manuals and schematics.

## Overview

Machine documentation (PDFs, markdown, text files, images) is stored in `machine_docs/` at the project root, organized by machine name. Three tool functions are registered with Gemini so the model can discover and read relevant documents during prompt generation.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/docTools.py` | Tool functions + caching logic |
| `backend/ApiScripts/pdf_to_md.py` | PDF-to-Markdown conversion (for pre-processing) |
| `backend/ApiScripts/diagramPrompt.py` | Passes `get_doc_tools()` to Gemini config |
| `backend/programAPI.py` | Calls `prime_machine_doc_caches()` at startup |
| `machine_docs/` | Root folder for machine documentation |

## Documentation Structure

```
machine_docs/
├── Dremel_3000/
│   ├── user_manual.md
│   ├── user_manual.pdf
│   └── exploded_view.png
├── Lenovo_Thinkpad_T450/
│   └── hardware_maintenance.md
└── Lulzbot_Taz_Workhorse/
    └── ...
```

## Tool Functions

Three Python functions are exposed to Gemini as callable tools:

### `list_machine_folders()`
Lists all subdirectories in `machine_docs/`. Returns folder names like `["Dremel_3000", "Lenovo_Thinkpad_T450"]`.

### `list_documents(machine_name)`
Lists files in a specific machine's folder with metadata (filename, type, size in KB). When `PREFER_MARKDOWN_DOCS` is enabled, PDFs with a matching `.md` companion are hidden.

### `read_document(machine_name, filename)`
Reads the text content of a document:
- **Text/Markdown files** — Returns raw content
- **PDFs** — Extracts text using PyMuPDF; large PDFs (>50 pages) return a preview
- **Images** — Returns metadata only (dimensions, format) since images can't be read as text through this tool
- PDF requests are automatically redirected to `.md` companions when available

## Caching

### Local Text Cache
At startup, `prime_machine_doc_caches()` reads all markdown files into `_DOC_TEXT_CACHE` (an in-memory dict). Subsequent `read_document()` calls serve from cache.

### Gemini Explicit Cache
For large documents (≥8,000 characters), the system creates Gemini explicit cache entries at startup. These are stored under a TTL of 2 hours and associated with the model. When a request mentions a machine name in its context, the cached content name is looked up and passed to `GenerateContentConfig.cached_content`.

Machine name matching uses fuzzy variants (underscores → spaces, case-insensitive, whitespace-stripped).

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `PREFER_MARKDOWN_DOCS` | `True` | Use `.md` companion instead of `.pdf` when both exist |
| `ENABLE_MACHINE_DOC_GEMINI_CACHE` | `True` | Create Gemini explicit caches at startup |
| `MACHINE_DOC_CACHE_MIN_CHARS` | `8000` | Minimum characters for Gemini caching |
| `MACHINE_DOC_CACHE_TTL` | `"2h"` | TTL for Gemini cache entries |

## Prompt Integration

The document tools are included in every Prompt 1 call via:
```python
config=types.GenerateContentConfig(
    tools=get_doc_tools(),
    cached_content=cached_content_name,
)
```

The prompt payload includes instructions telling the model to use `list_machine_folders` → `list_documents` → `read_document` when the technician mentions a specific machine.
