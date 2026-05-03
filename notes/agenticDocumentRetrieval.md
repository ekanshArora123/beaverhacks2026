# Agentic Document Retrieval System — Planning Document

> **Status:** ✅ Implemented.

---

## 1. Goal

Give Gemini the ability to **autonomously search and retrieve machine-specific documentation** (schematics, PDFs, manuals) stored in local folders on the server. When a technician asks about a specific machine, Gemini browses the local doc folder, picks the relevant documents, extracts their text, and incorporates it into its response — all within a single `generate_content()` call using automatic function calling.

---

## 2. How It Works

### Automatic Function Calling

- Three Python functions are passed as `tools=[...]` to `GenerateContentConfig`
- The SDK handles the entire agentic loop internally:
  1. Gemini decides it needs to call a function
  2. SDK executes the Python function locally
  3. SDK sends the result back to Gemini
  4. Gemini either calls another function or produces a final answer
- **One `generate_content()` call from your code — SDK manages all round-trips**

### PDF Handling

PDFs are **always extracted to text strings server-side**:
1. Gemini calls `read_document("Prusa_MK4S", "manual.pdf")`
2. Your Python function opens the PDF from disk, extracts text with PyMuPDF
3. Returns the text as a plain string to Gemini
4. Gemini reads the string — it never touches the actual PDF file

For large PDFs (>50 pages), the function returns a preview of the first ~10,000 characters + page count.

### Documentation Folder Structure

```
machine_docs/                   ← project root
├── Prusa_MK4S/
│   ├── extruder_maintenance.pdf
│   └── belt_tensioning_guide.pdf
└── Haas_VF2/
    └── alarm_codes_reference.pdf
```

---

## 3. Decisions

| Question | Decision |
|----------|----------|
| Function calling style | **Automatic** — SDK handles the loop |
| Tools | **3 custom functions** (list_machine_folders, list_documents, read_document) |
| Image analysis from docs | **No** — name reference only |
| PDF handling | **Text extraction** via PyMuPDF, returned as string |
| Large PDFs | **Preview + page count** for >50 page docs |
| Doc folder location | **`machine_docs/` at project root** |
| Which prompts get tools | **Prompt 1 only** |
| Google Search | **Not now** — easy to add later (one line) |

---

## 4. Limitations

- **Doc images**: Gemini knows image filenames but cannot visually see them via tools
- **Large PDFs**: Truncated to preview for >50 page documents
- **Latency**: Each tool call adds ~1-3 seconds (typical flow = 3 calls ≈ 3-9 seconds)
- **Token budget**: Extracted PDF text consumes tokens (~1 token per 4 characters)

---

## 5. Future: Google Search

When ready, one line addition to `get_doc_tools()` in `docTools.py`:

```python
types.Tool(google_search=types.GoogleSearch())
```

No architectural changes needed — same automatic function calling mechanism handles it.
