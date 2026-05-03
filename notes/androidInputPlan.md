# Android Phone Input Mode — Options Plan

## Context
Today the frontend ([frontend/src/App.tsx](frontend/src/App.tsx)) supports two input modes:
- **Audio** — laptop mic via `MediaRecorder`, sent to `/analyze` as a file.
- **Text** — typed into a textarea, sent as the `text_source_2` form field.

Goal: add a third mode where the *input* (audio + photos + optional text) comes from a phone instead of the laptop. A technician carrying a phone can speak into it and snap photos with the better rear camera while the laptop screen shows results, schematic, and the AI's diagram.

What "input" includes:
- Voice (currently `audio` field on `/analyze`)
- Photos (currently `files` field on `/analyze`)
- Optional text (currently `text_source_2`)

The output side (text + diagram + TTS) stays on the laptop — we do **not** need to redesign the result UI for the phone.

---

## Option 1 — Open the existing frontend on the phone (PWA-style)
Just point a phone browser at `http://<laptop-ip>:5173`. The app already uses `getUserMedia`, `MediaRecorder`, and a `<video>`/`<canvas>` capture pipeline that all work on Android Chrome.

**Pros**
- Zero new code to ship a working v0. Probably ~1 hour of CSS to make the layout usable on a phone.
- Same code path on backend, so `/analyze` contract is unchanged.
- Android Chrome lets `getUserMedia` pick the rear camera with `{ video: { facingMode: { exact: 'environment' } } }` — better than the webcam.

**Cons**
- Phone replaces the laptop instead of pairing with it. The AI's response + diagram render on the phone too, which fights the "laptop = display, phone = input" idea.
- HTTPS is required for `getUserMedia` on most Android browsers when not on `localhost`. Need a self-signed cert + `chrome://flags` workaround, an `ngrok` tunnel, or run Vite with `--host` and accept the cert warning.
- No way to drive the laptop's loop from the phone without pairing logic.

**Best when:** we want the simplest possible demo and are OK with the phone being the *only* screen.

---

## Option 2 — Phone-as-input, laptop-as-display (paired session over backend)  ★ recommended
Add a lightweight `/mobile` route in the frontend that is a phone-only capture page (camera button, mic button, send). The laptop stays on the existing UI and shows results. A short session code (or QR) ties the two together so the phone's captures land in the laptop's loop.

**Architecture**
- Backend gains a session table keyed by a 4–6 char code.
  - `POST /session/new` → returns `{ code }`. Laptop calls this on load and shows the code (or a QR encoding `http://<laptop-ip>:5173/mobile?code=ABC123`).
  - `POST /session/<code>/input` → phone uploads images + audio + text, same multipart shape as `/analyze` accepts today. Backend stores the latest payload in memory.
  - `GET /session/<code>/pending` (long-poll or SSE) → laptop reads pending payloads and triggers the existing `sendToBackend` flow with them in place of webcam captures.
- Phone page reuses the existing capture logic in [App.tsx](frontend/src/App.tsx) — pull `captureImage`, `toggleRecording`, and the audio/file form-data assembly out into a hook and import it from a `MobileCapturePage` component.

**Pros**
- Matches the actual ergonomics: technician walks around the machine with the phone, glances at the laptop for the diagram + spoken instructions.
- Backend's `/analyze` contract stays the same; only a thin pairing layer is added.
- Works without the phone and laptop sharing a Wi-Fi network if the backend is reachable from both (e.g., via an ngrok tunnel for the phone leg).
- QR-code pairing makes the demo feel polished without much work.

**Cons**
- ~1 day of work: pairing endpoints, QR rendering on the laptop, separate phone layout, refactoring capture into a shared hook.
- Need to decide on transport for laptop ← backend updates: SSE is probably simplest for a hackathon (no socket library), long-polling works too.
- Still needs HTTPS or a tunnel for camera/mic on the phone.

**Best when:** we want the full "phone = input device" story with the laptop as the focal display. This is what most users probably picture when they hear "use the Android phone instead."

---

## Option 3 — Phone as a WebRTC peer to the laptop browser
Phone opens a join page, scans QR, and establishes a WebRTC data + media channel directly to the laptop's browser. The laptop pulls camera frames + mic audio off the peer and feeds them into the existing `sendToBackend` path.

**Pros**
- Lowest latency — no round-trip through Flask for the media stream.
- The laptop never has to touch its own webcam; phone is a true replacement input device.
- Cool demo factor.

**Cons**
- Need a signaling channel (could be Flask + a tiny `/signal/<code>` POST/GET, or a WS dependency).
- WebRTC connection setup is fiddly across networks (NAT/STUN). On a hackathon Wi-Fi this *usually* works but can fail in ways that are hard to debug live.
- Overkill if we don't actually need <1s latency — current flow already takes seconds for Gemini to respond.

**Best when:** we specifically want a live phone-camera *preview* on the laptop, not just snapped photos + recorded clips.

---

## Option 4 — Phone as IP webcam / DroidCam
Run a third-party app on the phone (DroidCam, Iriun, Camo) that exposes the phone's camera/mic as a virtual webcam on the laptop. The existing frontend just picks that virtual device.

**Pros**
- Literally zero code changes in this repo.
- Best phone camera quality with no engineering effort.

**Cons**
- External dependency / app install at demo time. Judges may not love "and now install this third-party app."
- Doesn't give the technician any control surface on the phone (no per-shot capture button, no record-on-phone affordance) — the laptop is still driving everything.
- USB or same-Wi-Fi requirement varies by app.

**Best when:** we just want better camera quality and are not trying to show off "phone-driven" workflow.

---

## Option 5 — Telegram / Discord / SMS bot as the input channel
Backend exposes a webhook that listens for messages in a chat. Photo + voice note + text from the chat get fed into the `/analyze` pipeline. Laptop stays on the current UI and shows the response.

**Pros**
- Familiar, no app to install — every Android phone already has Telegram or similar.
- Voice notes and photos in chat apps already produce well-formed media files.
- Reads as a clever product demo ("text the assistant a photo of the broken nozzle").

**Cons**
- Bot setup, webhook tunneling (ngrok again), bot token in the keys file.
- Auth/identity story is fuzzy (anyone with the bot handle can poke it).
- Telegram-specific media formats (OGG voice notes) need to flow into `voiceToText.py` — should already be fine since we already accept `audio/ogg`, but worth verifying.

**Best when:** we want a memorable demo angle and don't mind depending on a third-party platform.

---

## Option 6 — Native Android app
Skip — not a hackathon-scale undertaking. Mentioned only for completeness.

---

## Recommendation
Go with **Option 2 (paired session)** as the primary "Android input mode." It's the option that actually delivers the workflow the project description implies (phone in hand at the machine, laptop showing the diagram), keeps the backend contract clean, and is a bounded ~1-day build.

Fallback if time runs short: ship **Option 1** (phone just opens the existing UI, with one CSS pass for mobile + a `facingMode: environment` tweak). It buys 80% of the value for ~1 hour of work, and Option 2 can be layered on top later without throwing the Option 1 work away.

Avoid Option 3 unless we have a specific reason to need live preview — it adds debugging surface area on demo day. Option 4 is a fine "plan C" for camera-quality only. Option 5 is a fun stretch goal if the core demo is already solid.

---

## Concrete next steps if we pick Option 2

1. **Refactor capture in [App.tsx](frontend/src/App.tsx)** — extract the webcam + recorder + capture-image logic into a `useCaptureSession` hook so a phone-only page can reuse it.
2. **Add a `/mobile` route** in the frontend (need to add `react-router-dom` or just a manual path-based switch in [main.tsx](frontend/src/main.tsx)) that renders a stripped-down portrait-layout page: big camera button, big mic button, "send" → POSTs to `/session/<code>/input`.
3. **Backend pairing endpoints** in [backend/programAPI.py](backend/programAPI.py):
   - `POST /session/new` returns a code.
   - `POST /session/<code>/input` accepts the same multipart fields as `/analyze` and stashes them in a per-code in-memory queue.
   - `GET /session/<code>/pending` (SSE or long-poll) for the laptop to consume.
4. **Laptop UI** shows the session code + a QR (use `qrcode.react`) when no phone is paired. When pending input arrives, pipe it into the existing `sendToBackend` instead of using webcam state.
5. **Tunneling** — document running `ngrok http 5000` (or `5173`) for live demos so the phone can reach the laptop over cellular without same-network setup.

Open questions to resolve before building:
- Do we want the laptop's webcam to remain a fallback input, or is "phone mode" a hard switch that disables the laptop's mic/camera capture?
- Per-session persistence (does the queue need to survive a page reload) or pure in-memory?
- HTTPS strategy for the phone leg — ngrok is easiest; a self-signed cert is the no-internet option.

---

## Files to add and change for Option 2

### Backend

**Change** [backend/programAPI.py](backend/programAPI.py)
- Add three Flask routes:
  - `POST /session/new` → mints a 4–6 char code, returns `{ code }`.
  - `POST /session/<code>/input` → multipart endpoint accepting the same fields `/analyze` already accepts (`files`, `audio`, `text_source_2`, `image_paths`, `diagram_source`, etc.). Stashes the payload (saving uploaded files into a per-session temp dir, since Flask's `FileStorage` streams won't survive the request).
  - `GET /session/<code>/pending` → either long-poll (block up to ~25s waiting for input, then return `204`) or Server-Sent Events streaming `data: {...}\n\n` events. SSE is the smaller diff; Flask supports it via a `Response(generator, mimetype="text/event-stream")`.
- Reuse the existing helpers (`_iter_uploaded_files`, `_save_uploaded_files`, `_split_image_sources`) — the goal is for the session input shape to match what `/analyze` already understands so we don't fork the parsing path.

**Add** `backend/sessionStore.py`
- Tiny module holding `{ code: Queue }` plus `create_session()`, `push_input(code, payload)`, `pop_input(code, timeout)`. Keeping it out of `programAPI.py` keeps that file readable.
- In-memory only (single Flask process). If we ever go multi-worker we need Redis, but for the hackathon a `dict` + `threading.Condition` is enough.

**No change** to [backend/AIBackend.py](backend/AIBackend.py) or anything in `backend/ApiScripts/` — the prompt pipeline does not need to know the input came from a phone.

**No new Python deps** — Flask + flask-cors already cover this. SSE is plain text streaming.

### Frontend

**Change** [frontend/src/main.tsx](frontend/src/main.tsx)
- Add a path switch so `/mobile` mounts a `MobileCapturePage` and `/` keeps mounting `App`. Either install `react-router-dom` or do a one-liner `window.location.pathname === '/mobile' ? <Mobile/> : <App/>` — the manual switch is fine for two routes.

**Change** [frontend/src/App.tsx](frontend/src/App.tsx)
- Extract the camera/recorder lifecycle (the `useEffect` that calls `getUserMedia`, `toggleRecording`, `captureImage`, `discardAudio`, the `recorderFormatRef` setup) into a new `useCaptureSession` hook so `MobileCapturePage` can reuse it.
- On mount, call `POST /session/new`, store the code, render the code + QR somewhere visible.
- Open an SSE connection to `GET /session/<code>/pending`. When a payload arrives, route it into `sendToBackend` *in place of* the current webcam capture state — i.e., `selectedUserImages` come from the phone payload's images, `audio` from the phone payload's audio, `text_source_2` from the phone payload's text. The existing `/analyze` POST and the rolling-loop bookkeeping below it stay untouched.
- Add a "phone mode" toggle that hides the local capture/record/text-input controls when active, so we don't have two competing input sources.

**Add** `frontend/src/hooks/useCaptureSession.ts`
- The extracted capture logic from `App.tsx`. Returns `{ videoRef, isRecording, hasAudioRecording, capturedImages, captureImage, removeCapturedImage, toggleRecording, discardAudio, getAudioBlob }`.
- One detail to preserve: the phone needs `getUserMedia({ video: { facingMode: { ideal: 'environment' } } })` to default to the rear camera. Make `facingMode` a hook option.

**Add** `frontend/src/MobileCapturePage.tsx`
- Reads `?code=ABC123` from the URL (or shows a "paste code" input if missing).
- Uses `useCaptureSession` for camera + mic.
- Big portrait-friendly buttons: shutter, mic toggle, send.
- Send handler builds the same multipart `FormData` `App.tsx` builds today, but POSTs to `/session/<code>/input` instead of `/analyze`.

**Add** `frontend/src/api/session.ts`
- Thin client wrapping `fetch` for `/session/new`, `/session/<code>/input`, plus a helper that opens an `EventSource` to `/session/<code>/pending` and yields parsed payloads. Keeps the network layer out of components.

**Add** `frontend/src/SessionPairingPanel.tsx`
- Component for the laptop UI: shows the code, a QR (use `qrcode.react`), and a "phone connected ✓" indicator (flip when the first SSE event arrives or when a phone calls a `/session/<code>/hello` ping).

**Change** [frontend/src/App.css](frontend/src/App.css) (and add `frontend/src/MobileCapturePage.css`)
- Portrait/touch-target styles for the mobile page; QR styling on the laptop side.

**Change** [frontend/package.json](frontend/package.json)
- Add `qrcode.react` for the QR rendering.
- Optionally add `react-router-dom` if we go that route instead of the manual path switch.

**No change** needed to [frontend/vite.config.ts](frontend/vite.config.ts) for in-network demos — `npm run dev -- --host` exposes the dev server on the LAN. For HTTPS (required by `getUserMedia` on Android Chrome from a non-`localhost` origin), either run through ngrok or add `@vitejs/plugin-basic-ssl` and accept the cert warning on the phone.

### Tooling / docs

**Change** [start-dev.ps1](start-dev.ps1)
- Probably nothing required (Flask already binds `0.0.0.0:5000`). Optional: pass `--host` to the Vite command so the laptop prints the LAN URL on startup.

**Change** [README.md](README.md)
- Document the new `/mobile` route, how to pair via QR, and the ngrok/HTTPS step for the phone.

### Summary

- **New files (5):** `backend/sessionStore.py`, `frontend/src/hooks/useCaptureSession.ts`, `frontend/src/MobileCapturePage.tsx`, `frontend/src/MobileCapturePage.css`, `frontend/src/api/session.ts`, `frontend/src/SessionPairingPanel.tsx` *(6 if we count the pairing panel separately, which we should)*.
- **Edited files (5):** `backend/programAPI.py`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/package.json`.
- **Unchanged:** all of `backend/ApiScripts/`, `backend/AIBackend.py`, `requirements.txt`, the prompt scripts. The phone leg is purely an input-source adapter; the AI pipeline doesn't notice.
