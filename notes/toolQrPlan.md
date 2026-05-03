# Plan: Static QR Codes for Tool Context Pre-selection

## Goal

Each machine in `machine_docs/` gets a **static, printable QR code** that
can be stuck on the physical tool. Scanning it (or scanning a laptop-displayed
QR that embeds the same tool hint) automatically pre-selects that machine's
documentation as the AI context - no manual typing or menu navigation required.

---

## URL Structure

Two QR flavours, both optional and backward-compatible:

| QR type | URL encoded | When used |
|---|---|---|
| **Physical/static** | `/mobile?tool=Dremel_3000` | Printed label stuck on the tool |
| **Laptop QR (enhanced)** | `/mobile?code=ABCDEF&tool=Dremel_3000` | Laptop shows when a tool is pre-selected |

The `tool` param is the exact `machine_docs/` subfolder name (e.g. `Dremel_3000`).
Everything that currently works without `tool` continues to work unchanged.

---

## Component Changes

### 1. QR Code Generation Script — `scripts/generate-tool-qr.py` (new file)

- Scans `machine_docs/` for subdirectories (same scan logic as `docTools.list_machine_folders()`)
- For each folder, generates `machine_docs/<Name>/qr_<Name>.png` (and optionally a PDF for printing)
- URL template is configurable via `--base-url` arg (e.g. ngrok HTTPS URL for physical labels, or LAN IP for dev)
- Default URL: `http://localhost:5173/mobile?tool=<name>` (overridden at print time)
- Depends only on `qrcode[pil]` (already a natural dependency; add to `requirements.txt`)

Usage:
```bash
python scripts/generate-tool-qr.py --base-url https://<ngrok>.ngrok-free.app
# → writes machine_docs/Dremel_3000/qr_Dremel_3000.png
```

---

### 2. Backend: New `/machine-folders` Route — `backend/programAPI.py` (small addition)

New read-only endpoint so the frontend can populate the tool selector without
hardcoding machine names:

```
GET /machine-folders
→ { "folders": ["Dremel_3000", ...] }
```

Internally just calls `docTools.list_machine_folders()`.
No auth needed — it returns only folder names, no doc content.

---

### 3. Backend: Thread `tool_context` Through Payload — `backend/programAPI.py` (small addition)

In `session_input()`, after reading `text_source_2` and `diagram_source`, also read:

```python
tool_context = _optional_str(request.form.get("tool_context"))
```

Include it in the queued payload dict:

```python
payload = {
    ...existing fields...,
    "tool_context": tool_context,   # None if not provided
}
```

The laptop already receives the full payload dict from `/session/<code>/pending`.
No further routing changes needed — the existing `/analyze` and prompt routes
already accept arbitrary extra fields from which they read named keys.

---

### 4. AI Pipeline: Tool Context Hint — `backend/ApiScripts/mainPrompt.py` (small addition)

`build_prompt()` already has a `=== MACHINE INFORMATION ===` section fed by
`text_source_1`. Add a secondary hook: if `tool_context` is provided and
`text_source_1` is empty, inject a lightweight machine hint:

```
=== TARGET MACHINE ===
The machine being worked on is: Dremel_3000
Use the document tools to load its documentation before answering.
```

This guides the agentic `docTools` calls (which currently have to discover
the machine themselves) toward the right folder from the first round-trip,
without bypassing the existing agentic flow. If `text_source_1` is already
set, the hint is skipped — no change.

Alternatively (simpler): pass `tool_context` as a named kwarg through
`run_four_prompts()` → `run_first_prompt()` → `build_prompt()`, prepended
to `text_source_1` if that field is blank.

---

### 5. Frontend: `MobileCapturePage.tsx` (small addition)

Read `tool` from query params alongside `code` (same pattern already used
for `code`):

```ts
function readToolFromQuery(): string {
  return new URLSearchParams(window.location.search).get('tool')?.trim() ?? ''
}
```

- If present, display the tool name in the header (replaces or supplements session label)
- Append `tool_context` to every `FormData` POST:
  ```ts
  if (toolContext) formData.append('tool_context', toolContext)
  ```
- If `tool` is in the URL but `code` is not, the phone shows the normal
  "Enter code" screen but with the tool name pre-displayed so the user
  knows which machine they're pairing with.
- `tool` is persisted in the URL via `history.replaceState` (same as `code`
  is today) so it survives page refreshes.

---

### 6. Frontend: `SessionPairingPanel.tsx` (optional enhancement)

Add a tool selector that calls `GET /machine-folders` on mount, populates a
`<select>` showing the discovered machine names, and when one is chosen:

- Appends `&tool=<name>` to the QR URL the laptop displays
- The laptop's QR then carries both session code and tool context in one scan

This is the single-scan optimal flow:  
`[scan physical tool QR] → phone knows tool`  
`[scan laptop QR with tool pre-selected] → phone knows both session + tool in one scan`

---

## Data Flow Diagram

```
Physical label QR (/mobile?tool=Dremel_3000)
        │
        ▼
  Phone opens MobileCapturePage
  - Shows "Dremel 3000" context
  - Prompts for session code (type or scan laptop QR)
        │
   [user enters/scans code]
        │
        ▼
  Phone POSTs /session/ABCDEF/input
  FormData: { files, audio, text_source_2, tool_context: "Dremel_3000" }
        │
        ▼
  Backend queues payload including tool_context
        │
        ▼
  Laptop polls /session/ABCDEF/pending → receives payload
        │
        ▼
  /analyze or prompt route:
    - tool_context="Dremel_3000" → injected into system prompt hint
    - docTools.list_machine_folders() / read_document() guided to Dremel_3000
    - AI generates step-by-step instructions
```

---

## What Does Not Change

- Session code generation and TTL logic in `sessionStore.py` — untouched
- `docTools.py` agentic retrieval — works exactly as before, just better guided
- All existing QR/pairing flow without `tool` — backward compatible
- The `/analyze` route contract — `tool_context` is additive, not required

---

## Implementation Order

1. `scripts/generate-tool-qr.py` — standalone, no backend deps, can be done first
2. `backend/programAPI.py` — add `/machine-folders` route + `tool_context` passthrough
3. `backend/ApiScripts/mainPrompt.py` — inject tool hint into prompt if context is set
4. `frontend/src/MobileCapturePage.tsx` — read `tool` param, send `tool_context`
5. `frontend/src/SessionPairingPanel.tsx` — optional tool selector + enhanced QR URL

Steps 1–3 can be done in parallel. Steps 4–5 are frontend-only and independent
of each other.
