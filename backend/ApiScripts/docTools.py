"""Agentic document retrieval tools for Gemini automatic function calling.

Provides three Python functions that Gemini can call autonomously to browse
and read machine-specific documentation stored in ``machine_docs/`` at the
project root.  Each function has typed parameters and Google-style docstrings
so the ``google-genai`` SDK can auto-generate the tool schema.

Usage::

    from ApiScripts.docTools import get_doc_tools

    response = client.models.generate_content(
        model=model_name,
        contents=[...],
        config=types.GenerateContentConfig(tools=get_doc_tools()),
    )
"""

import os
import re
from pathlib import Path

from google.genai import types

# ── Resolve the machine_docs root once at import time ────────────────────────
# machine_docs/ lives at the project root (same level as taskStates/, etc.)
_MACHINE_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "machine_docs"

# Supported file categories
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".log", ".json", ".xml", ".yaml", ".yml"}
_PDF_SUFFIXES = {".pdf"}
# Toggle to prefer .md companions over .pdf files.
PREFER_MARKDOWN_DOCS = True
# Enable Gemini explicit caching for machine docs at startup.
ENABLE_MACHINE_DOC_GEMINI_CACHE = True
# Only cache large markdown files (in characters).
MACHINE_DOC_CACHE_MIN_CHARS = 8_000
# TTL for Gemini explicit cache entries.
MACHINE_DOC_CACHE_TTL = "2h"

# Large-PDF threshold (pages). Above this we return a summary instead of full text.
_LARGE_PDF_PAGE_THRESHOLD = 50
# Max characters to return for a large PDF preview
_LARGE_PDF_PREVIEW_CHARS = 10_000

# Runtime caches (warm at startup)
_DOC_TEXT_CACHE: dict[str, str] = {}
_MACHINE_DOC_GEMINI_CACHE_NAMES: dict[str, str] = {}


def _safe_resolve(machine_name: str, filename: str | None = None) -> Path:
    """Resolve a path inside machine_docs, rejecting traversal attempts."""
    if ".." in machine_name or "/" in machine_name or "\\" in machine_name:
        raise ValueError(f"Invalid machine name: {machine_name!r}")
    base = _MACHINE_DOCS_DIR / machine_name
    if filename is not None:
        if ".." in filename or "/" in filename or "\\" in filename:
            raise ValueError(f"Invalid filename: {filename!r}")
        return base / filename
    return base


def _doc_cache_key(machine_name: str, filename: str) -> str:
    return f"{machine_name.lower()}/{filename.lower()}"


def _machine_name_variants(machine_name: str) -> set[str]:
    variants = {machine_name.lower()}
    normalized = machine_name.replace("_", " ").replace("-", " ").lower()
    variants.add(normalized)
    variants.add(re.sub(r"\s+", "", normalized))
    return variants


def _classify_file(suffix: str) -> str:
    """Return a human-readable type string for a file extension."""
    suffix = suffix.lower()
    if suffix in _PDF_SUFFIXES:
        return "pdf"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    return "other"


# ─── Tool 1 ─────────────────────────────────────────────────────────────────

def list_machine_folders() -> list[str]:
    """List all available machine documentation folders.

    Scans the machine_docs directory for subdirectories. Each subdirectory
    name represents a machine for which documentation is available.

    Returns:
        A list of machine folder names, for example
        ["Prusa_MK4S", "Haas_VF2", "Kuka_KR16"].
        Returns an empty list if no documentation folders exist.
    """
    print(f"[docTools] list_machine_folders() called")
    if not _MACHINE_DOCS_DIR.exists():
        print(f"[docTools]   machine_docs dir not found: {_MACHINE_DOCS_DIR}")
        return []

    folders = sorted(
        entry.name
        for entry in _MACHINE_DOCS_DIR.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )
    print(f"[docTools]   found {len(folders)} folder(s): {folders}")
    return folders


# ─── Tool 2 ─────────────────────────────────────────────────────────────────

def list_documents(machine_name: str) -> list[dict]:
    """List all documents available for a specific machine.

    Args:
        machine_name: The exact folder name of the machine, for example
            "Prusa_MK4S". Use list_machine_folders() first to discover
            valid machine names.

    Returns:
        A list of dicts, each containing:
        - "filename": the file name (e.g. "extruder_maintenance.pdf")
        - "type": one of "pdf", "image", "text", or "other"
        - "size_kb": file size in kilobytes (rounded to 1 decimal)

        Returns an empty list if the machine folder does not exist or
        contains no files.
    """
    print(f"[docTools] list_documents({machine_name!r}) called")
    folder = _safe_resolve(machine_name)
    if not folder.exists() or not folder.is_dir():
        print(f"[docTools]   folder not found: {folder}")
        return []

    all_files = [
        entry for entry in sorted(folder.iterdir())
        if entry.is_file() and not entry.name.startswith(".")
    ]
    md_stems = {entry.stem.lower() for entry in all_files if entry.suffix.lower() == ".md"}

    documents = []
    for entry in all_files:
        # Prefer markdown companions over PDFs for now.
        if (
            PREFER_MARKDOWN_DOCS
            and entry.suffix.lower() == ".pdf"
            and entry.stem.lower() in md_stems
        ):
            continue
        doc_info = {
            "filename": entry.name,
            "type": _classify_file(entry.suffix),
            "size_kb": round(entry.stat().st_size / 1024, 1),
        }
        documents.append(doc_info)

    print(f"[docTools]   found {len(documents)} file(s)")
    return documents


# ─── Tool 3 ─────────────────────────────────────────────────────────────────

def read_document(machine_name: str, filename: str) -> str:
    """Read the text content of a document from the machine documentation folder.

    Supports PDFs and text files. For PDFs, extracts the text content using
    PyMuPDF. For large PDFs (over 50 pages), returns the page count and a
    preview of the first portion of text so you can decide which parts are
    relevant. For text files (.txt, .md, .csv, etc.), returns the raw content.
    For image files, returns metadata only (filename, dimensions, format)
    since images cannot be visually analyzed through this tool.

    Args:
        machine_name: The exact folder name of the machine, for example
            "Prusa_MK4S". Use list_machine_folders() first to discover
            valid machine names.
        filename: The document filename within that machine's folder,
            for example "extruder_maintenance.pdf". Use list_documents()
            first to discover available files.

    Returns:
        The extracted text content of the document as a string, or a
        metadata description for image files. Returns an error message
        string if the file cannot be read.
    """
    print(f"[docTools] read_document({machine_name!r}, {filename!r}) called")
    file_path = _safe_resolve(machine_name, filename)

    if not file_path.exists() or not file_path.is_file():
        msg = f"File not found: {machine_name}/{filename}"
        print(f"[docTools]   {msg}")
        return f"Error: {msg}"

    if PREFER_MARKDOWN_DOCS and file_path.suffix.lower() == ".pdf":
        md_candidate = file_path.with_suffix(".md")
        if md_candidate.exists() and md_candidate.is_file():
            print(f"[docTools]   using markdown companion: {md_candidate.name}")
            file_path = md_candidate

    cache_key = _doc_cache_key(machine_name, file_path.name)
    if cache_key in _DOC_TEXT_CACHE:
        print(f"[docTools]   serving from local cache: {file_path.name}")
        return _DOC_TEXT_CACHE[cache_key]

    suffix = file_path.suffix.lower()
    file_type = _classify_file(suffix)

    # ── PDF extraction ───────────────────────────────────────────────────
    if file_type == "pdf":
        return _read_pdf(file_path)

    # ── Plain text ───────────────────────────────────────────────────────
    if file_type == "text":
        content = _read_text_file(file_path)
        _DOC_TEXT_CACHE[cache_key] = content
        return content

    # ── Image metadata ───────────────────────────────────────────────────
    if file_type == "image":
        return _read_image_metadata(file_path)

    # ── Unsupported ──────────────────────────────────────────────────────
    return f"Unsupported file type: {file_path.name} ({suffix}). Only PDFs, text files, and images are supported."


# ─── Internal helpers ────────────────────────────────────────────────────────

def _read_pdf(file_path: Path) -> str:
    """Extract text from a PDF using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return (
            "Error: PyMuPDF is not installed. "
            "Run 'pip install PyMuPDF' to enable PDF text extraction."
        )

    try:
        doc = fitz.open(file_path)
        page_count = len(doc)
        print(f"[docTools]   PDF has {page_count} page(s)")

        # Extract all text
        all_text_parts: list[str] = []
        for page_num in range(page_count):
            page = doc[page_num]
            page_text = page.get_text().strip()
            if page_text:
                all_text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")
        doc.close()

        if not all_text_parts:
            return (
                f"PDF '{file_path.name}' has {page_count} page(s) but no "
                f"extractable text. It may be a scanned/image-only PDF."
            )

        full_text = "\n\n".join(all_text_parts)

        # For large PDFs, return a preview with guidance
        if page_count > _LARGE_PDF_PAGE_THRESHOLD:
            preview = full_text[:_LARGE_PDF_PREVIEW_CHARS]
            return (
                f"PDF '{file_path.name}' — {page_count} pages (large document).\n"
                f"Showing first ~{_LARGE_PDF_PREVIEW_CHARS} characters:\n\n"
                f"{preview}\n\n"
                f"[Document truncated. The full document has {len(full_text)} characters "
                f"across {page_count} pages.]"
            )

        print(f"[docTools]   extracted {len(full_text)} chars of text")
        return full_text

    except Exception as exc:
        return f"Error reading PDF '{file_path.name}': {exc}"


def _read_text_file(file_path: Path) -> str:
    """Read a plain text file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        print(f"[docTools]   read {len(content)} chars from text file")
        return content
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="latin-1")
            print(f"[docTools]   read {len(content)} chars from text file (latin-1 fallback)")
            return content
        except Exception as exc:
            return f"Error reading text file '{file_path.name}': {exc}"
    except Exception as exc:
        return f"Error reading text file '{file_path.name}': {exc}"


def _read_text_file_uncached(file_path: Path) -> str:
    """Read a plain text file for cache priming."""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1")


def get_cached_content_name_for_text(*context_parts: str) -> str | None:
    """Pick a Gemini cached-content handle based on machine name mention."""
    if not _MACHINE_DOC_GEMINI_CACHE_NAMES:
        return None

    context = " ".join((part or "") for part in context_parts).lower()
    squashed_context = re.sub(r"\s+", "", context)
    for machine_name, cache_name in _MACHINE_DOC_GEMINI_CACHE_NAMES.items():
        for variant in _machine_name_variants(machine_name):
            if variant in context or variant.replace(" ", "") in squashed_context:
                return cache_name
    return None


def prime_machine_doc_caches(client, model: str) -> dict[str, int]:
    """Warm local markdown cache and create Gemini explicit caches per machine."""
    summary = {
        "local_docs_cached": 0,
        "gemini_caches_created": 0,
        "gemini_caches_failed": 0,
    }
    _DOC_TEXT_CACHE.clear()
    _MACHINE_DOC_GEMINI_CACHE_NAMES.clear()

    if not _MACHINE_DOCS_DIR.exists():
        return summary

    machine_chunks: dict[str, list[str]] = {}
    for machine_dir in sorted(entry for entry in _MACHINE_DOCS_DIR.iterdir() if entry.is_dir()):
        chunks: list[str] = []
        for entry in sorted(machine_dir.iterdir()):
            if not entry.is_file():
                continue
            suffix = entry.suffix.lower()
            if suffix == ".md":
                target_path = entry
            elif PREFER_MARKDOWN_DOCS and suffix == ".pdf" and entry.with_suffix(".md").exists():
                target_path = entry.with_suffix(".md")
            else:
                continue

            try:
                content = _read_text_file_uncached(target_path)
            except Exception as exc:
                print(f"[docTools] cache skip {target_path.name}: {exc}")
                continue

            _DOC_TEXT_CACHE[_doc_cache_key(machine_dir.name, target_path.name)] = content
            summary["local_docs_cached"] += 1

            if len(content) >= MACHINE_DOC_CACHE_MIN_CHARS:
                chunks.append(f"### {target_path.name}\n\n{content}")

        if chunks:
            machine_chunks[machine_dir.name] = chunks

    if not ENABLE_MACHINE_DOC_GEMINI_CACHE:
        return summary

    for machine_name, chunks in machine_chunks.items():
        try:
            cached = client.caches.create(
                model=model,
                config=types.CreateCachedContentConfig(
                    display_name=f"machine-docs-{machine_name}",
                    ttl=MACHINE_DOC_CACHE_TTL,
                    system_instruction=(
                        "Cached machine documentation context. Use this as source material "
                        "and use tools for exact file retrieval when needed."
                    ),
                    contents=["\n\n".join(chunks)],
                ),
            )
            cache_name = getattr(cached, "name", None)
            if cache_name:
                _MACHINE_DOC_GEMINI_CACHE_NAMES[machine_name] = cache_name
                summary["gemini_caches_created"] += 1
        except Exception as exc:
            summary["gemini_caches_failed"] += 1
            print(f"[docTools] Gemini cache create failed for {machine_name}: {exc}")

    return summary


def _read_image_metadata(file_path: Path) -> str:
    """Return metadata about an image file (no visual analysis)."""
    size_kb = round(file_path.stat().st_size / 1024, 1)
    suffix = file_path.suffix.lower().lstrip(".")
    info = f"Image file: {file_path.name} ({suffix.upper()}, {size_kb} KB)"

    # Try to get dimensions if PIL is available (optional)
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size
            info += f", {width}x{height} pixels"
    except Exception:
        pass  # PIL not installed or file unreadable — skip dimensions

    print(f"[docTools]   {info}")
    return info + ". Note: images cannot be visually analyzed through this tool."


# ─── Public convenience function ────────────────────────────────────────────

def get_doc_tools() -> list:
    """Return the list of tool functions for use in GenerateContentConfig.

    Usage::

        config = types.GenerateContentConfig(tools=get_doc_tools())
    """
    return [list_machine_folders, list_documents, read_document]
