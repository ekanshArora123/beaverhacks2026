# PDF to Markdown Conversion

A CLI utility that converts PDF documents to Markdown using `pymupdf4llm`, pre-processing machine docs for efficient caching and retrieval.

## Relevant Files

| File | Role |
|------|------|
| `backend/ApiScripts/pdf_to_md.py` | CLI conversion script |
| `machine_docs/` | Target directory for converted docs |

## Usage

```bash
# Single PDF
python backend/ApiScripts/pdf_to_md.py --input machine_docs/Dremel_3000/manual.pdf

# All PDFs in a directory (recursive)
python backend/ApiScripts/pdf_to_md.py --input machine_docs --recursive

# Specific pages
python backend/ApiScripts/pdf_to_md.py --input in.pdf --pages 1-5
```

## CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--input` | Yes | Input PDF file or directory |
| `--output` | No | Output path (single file mode only) |
| `--recursive` | No | Include subdirectories |
| `--pages` | No | Page selection (e.g., `1-5`, `1,3,8-12`) |

Output is written next to the source PDF with a `.md` extension by default.
