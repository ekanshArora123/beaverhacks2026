# Phone Pairing (Mobile Input Mode)

The phone pairing system allows a technician (or helper) to use a phone's camera and microphone as input devices, relaying captured data to the laptop dashboard for AI analysis.

## Overview

1. The laptop creates a session and displays a QR code.
2. The phone scans the QR code to open the mobile capture page.
3. The phone captures photos, records audio, or types text, then sends it to the backend.
4. The laptop long-polls the backend and receives the phone's payload.
5. The laptop processes the payload through the normal `/analyze` pipeline.

## Relevant Files

### Backend
| File | Role |
|------|------|
| `backend/sessionStore.py` | In-memory session store (create, push, pop, expire) |
| `backend/programAPI.py` | `/session/new`, `/session/<code>/input`, `/session/<code>/pending`, `/host-info` |

### Frontend
| File | Role |
|------|------|
| `frontend/src/App.tsx` | Phone mode toggle, session lifecycle, payload dispatch |
| `frontend/src/SessionPairingPanel.tsx` | QR code display, origin resolution, pairing status |
| `frontend/src/MobileCapturePage.tsx` | Phone camera/mic UI with capture and send |
| `frontend/src/hooks/useCaptureSession.ts` | Camera/mic negotiation for mobile |
| `frontend/src/api/session.ts` | Session API client functions |
| `frontend/src/api/ngrokAgentTunnels.ts` | Auto-detect ngrok tunnel URL |
| `frontend/src/env/pairing.ts` | Read `VITE_PAIRING_ORIGIN` env var |
| `frontend/src/utils/mediaDeviceErrors.ts` | Human-readable error messages for camera failures |

## Session Lifecycle

### Creating a Session
1. User clicks "📱 Use Phone" on the laptop dashboard.
2. Frontend calls `POST /session/new` → backend generates a 6-character code (e.g., `ABC123`).
3. The `SessionPairingPanel` resolves the phone-accessible URL and renders a QR code.

### Phone Input
1. Phone scans the QR code → opens `/mobile?code=ABC123`.
2. `MobileCapturePage` requests camera + mic access via `useCaptureSession`.
3. User captures photos, records audio, and/or types text.
4. Clicking "Send to laptop" calls `POST /session/<code>/input` with images/audio/text as `FormData`.
5. The backend converts uploads to base64 data URLs and pushes them into the session queue.

### Laptop Receives Payload
1. The laptop long-polls `GET /session/<code>/pending?timeout=25`.
2. When a payload arrives, the poll returns immediately with the data.
3. The laptop decodes the data URLs and passes them to `sendToBackend()` as if they were local captures.

## Session Store Details

- **Codes**: 6 characters from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (ambiguous chars omitted)
- **TTL**: 1 hour of inactivity
- **Concurrency**: Thread-safe with `threading.Lock`
- **Storage**: Single-process in-memory (not for multi-worker deployments)
- **Queue**: Unbounded `queue.Queue` per session

## QR Code URL Resolution

The `SessionPairingPanel` resolves the phone-accessible URL in this order:

1. `VITE_PAIRING_ORIGIN` env var (explicit tunnel URL)
2. Auto-detected ngrok HTTPS tunnel (via `localhost:4040` agent API)
3. LAN IP from `/host-info` (Flask enumerates local IPv4 addresses)
4. Current browser origin (fallback)

If only `localhost` is available, a warning is displayed since phones can't reach `localhost` on the laptop.

## Campus Wi-Fi / Eduroam

Many campus networks block device-to-device LAN traffic. The system supports ngrok tunnels as a workaround — see the [Networking & Tunnels](networking.md) doc.
