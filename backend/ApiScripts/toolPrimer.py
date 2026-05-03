"""Server-side tool documentation primer for Gemini KV cache warming.

When a QR code for a specific tool is scanned, ``/set-tool`` calls
``start_prime_background()`` which:

1. Extracts all readable docs for the tool using the docTools functions
   (no Gemini call needed — pure local PDF/text extraction).
2. Caches the extracted text in memory (TTL: 1 hour).
3. Sends a single Gemini ``generate_content`` call with the full doc text
   so that Gemini's server-side KV cache is warmed.

When the real ``/analyze`` call later arrives with ``tool_context`` set,
``get_cached_docs()`` returns the doc text and the caller prepends it to the
prompt.  Because the prefix is identical to what was sent during priming,
Gemini can reuse its cached key/value attention entries and respond faster.
"""

import threading
import time
from typing import Optional

try:
    from .docTools import list_documents, read_document
except ImportError:
    from docTools import list_documents, read_document

# ── In-memory doc cache ───────────────────────────────────────────────────────
# tool_name -> {"text": str, "ts": float}
_cache: dict[str, dict] = {}
_lock = threading.Lock()
_CACHE_TTL = 3600  # seconds — 1 hour


# ── Public helpers ────────────────────────────────────────────────────────────

def get_cached_docs(tool_name: str) -> Optional[str]:
    """Return cached doc text for *tool_name*, or ``None`` on cache miss / stale entry."""
    with _lock:
        entry = _cache.get(tool_name)
    if entry is None:
        return None
    if (time.time() - entry["ts"]) >= _CACHE_TTL:
        return None
    text = entry.get("text") or ""
    return text if text else None


def start_prime_background(tool_name: str, client, text_model: str) -> None:
    """Kick off documentation extraction + Gemini priming in a daemon thread.

    Returns immediately — the caller does not need to wait.
    """
    thread = threading.Thread(
        target=_prime_worker,
        args=(tool_name, client, text_model),
        daemon=True,
        name=f"toolPrimer-{tool_name}",
    )
    thread.start()


# ── Internal ──────────────────────────────────────────────────────────────────

def _extract_all_docs(tool_name: str) -> str:
    """Use docTools to extract text from every readable document for *tool_name*.

    This is a local operation — no Gemini API call is made.
    """
    docs = list_documents(tool_name)
    if not docs:
        return ""

    parts: list[str] = []
    for doc in docs:
        if doc.get("type") in ("pdf", "text"):
            content = read_document(tool_name, doc["filename"])
            # Ignore error strings returned by read_document on failure
            if content and not content.startswith("Error:") and not content.startswith("Unsupported"):
                parts.append(f"[{doc['filename']}]\n{content}")

    return "\n\n".join(parts)


def _prime_worker(tool_name: str, client, text_model: str) -> None:
    """Background thread body: extract → cache → prime Gemini."""
    print(f"[toolPrimer] Starting prime for {tool_name!r}")

    doc_text = _extract_all_docs(tool_name)

    with _lock:
        _cache[tool_name] = {"text": doc_text, "ts": time.time()}

    if not doc_text:
        print(f"[toolPrimer] {tool_name!r}: no readable docs found — skipping Gemini prime")
        return

    display_name = tool_name.replace("_", " ")
    prime_contents = (
        f"You will shortly be helping a technician working on the {display_name}. "
        f"Read and familiarise yourself with all of the following documentation:\n\n"
        f"{doc_text}\n\n"
        f"Confirm you have read the documentation in one sentence only."
    )

    try:
        from google.genai import types
        response = client.models.generate_content(
            model=text_model,
            contents=prime_contents,
            config=types.GenerateContentConfig(max_output_tokens=60),
        )
        ack = (response.text or "").strip()
        print(f"[toolPrimer] {tool_name!r}: Gemini primed — {ack[:120]}")
    except Exception as exc:
        print(f"[toolPrimer] {tool_name!r}: Gemini prime failed: {exc}")
