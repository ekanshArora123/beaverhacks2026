# Frontend — React + TypeScript Vite Application

The frontend is a React (TypeScript) single-page application built with Vite. It provides a laptop dashboard for capturing images and audio, and a mobile-optimized page for phone-based input via session pairing.

## File Structure

```
frontend/
├── index.html                 # HTML entry point
├── package.json               # Dependencies and npm scripts
├── vite.config.ts             # Vite configuration (proxy rules, HTTPS, HMR)
├── tsconfig.json              # TypeScript project references
├── tsconfig.app.json          # App-specific TS config
├── tsconfig.node.json         # Node-side TS config (Vite config)
├── eslint.config.js           # ESLint configuration
├── .env.example               # Example env vars for phone pairing
│
├── src/
│   ├── main.tsx               # Application entry — route between App and MobileCapturePage
│   │
│   ├── App.tsx                # Laptop dashboard (webcam, audio, analysis display)
│   ├── App.css                # Styles for the laptop dashboard
│   │
│   ├── MobileCapturePage.tsx  # Phone camera input page
│   ├── MobileCapturePage.css  # Styles for the mobile page
│   │
│   ├── SessionPairingPanel.tsx # QR code + session pairing UI component
│   │
│   ├── index.css              # Global CSS reset and base styles
│   │
│   ├── api/                   # Backend communication layer
│   │   ├── programApiBase.ts  # Backend URL resolution
│   │   ├── session.ts         # Session API client (create, input, poll)
│   │   ├── ngrokAgentTunnels.ts # Auto-detect ngrok HTTPS tunnel URL
│   │   └── tunnelFetchInit.ts # Add ngrok bypass headers when on tunnel
│   │
│   ├── hooks/
│   │   └── useCaptureSession.ts # Reusable camera + mic + recording hook
│   │
│   ├── utils/
│   │   └── mediaDeviceErrors.ts # Human-readable camera/mic error messages
│   │
│   ├── env/
│   │   └── pairing.ts         # Read VITE_PAIRING_ORIGIN env var
│   │
│   └── assets/                # Static images and icons
│       ├── hero.png
│       ├── react.svg
│       └── vite.svg
│
├── public/                    # Static files served at root
├── dist/                      # Production build output
└── context/                   # Additional context files
```

## Execution Flow

### Entry Point (`main.tsx`)

The app uses a simple pathname-based router:
- **`/mobile`** → Renders `MobileCapturePage` (phone input interface)
- **Everything else** → Renders `App` (laptop dashboard)

Both are wrapped in React's `StrictMode`.

### Laptop Dashboard (`App.tsx`)

The main application component manages:

1. **Webcam capture** — Requests `getUserMedia` for video + audio on mount. Video is streamed to a `<video>` element. Photos are captured by drawing a frame to a hidden `<canvas>` and converting to a data URL.

2. **Audio recording** — A `MediaRecorder` records audio from the microphone. The user manually starts/stops recording with a button. Supported formats are negotiated at init time (prefers OGG Opus, falls back to WebM).

3. **Text input** — A toggle switches between audio and manual text input modes.

4. **Diagram source selection** — The user can choose whether the AI overlays annotations on the user photo or a schematic image.

5. **Submission to backend** — Collected images, audio, and text are packaged as `FormData` and sent to `/analyze`. The response includes:
   - `first_prompt_response_text` — spoken-style guidance (displayed on screen and read aloud via `SpeechSynthesis`)
   - `image` — base64-encoded annotated diagram (displayed in the results column)

6. **Rolling context** — Transcribed user inputs are accumulated across submissions and sent as `text_source_1` for conversation continuity.

7. **Phone pairing mode** — When toggled, creates a backend session, displays a QR code, and long-polls for payloads sent from the phone.

### Mobile Capture Page (`MobileCapturePage.tsx`)

A mobile-optimized interface used on a paired phone:

1. Reads the session code from the URL query parameter (`?code=ABC123`)
2. Uses `useCaptureSession` hook for camera + mic access (prefers rear camera)
3. Captures photos with a shutter button, records audio with a mic button
4. Sends images/audio/text to the backend via `POST /session/<code>/input`
5. The laptop long-polls `/session/<code>/pending` and processes the payload

### Capture Session Hook (`useCaptureSession.ts`)

A reusable React hook that encapsulates:
- Camera stream negotiation (tries multiple constraint sets for compatibility)
- `MediaRecorder` setup with format detection
- Image capture via canvas
- Audio recording state management
- Proper cleanup of media streams on unmount

### API Layer (`api/`)

- **`programApiBase.ts`** — Resolves the backend URL. In dev mode, uses the Vite origin (proxy forwards to Flask). In production, constructs `protocol://hostname:5000`.
- **`session.ts`** — Session lifecycle: `createSession()`, `postSessionInput()`, `pollSessionPending()`, `fetchHostInfo()`.
- **`ngrokAgentTunnels.ts`** — In dev, attempts to auto-detect the HTTPS tunnel URL from the local ngrok agent API at `localhost:4040`.
- **`tunnelFetchInit.ts`** — Adds the `ngrok-skip-browser-warning` header when running on a known tunnel hostname.

### Vite Configuration (`vite.config.ts`)

Key configuration:
- **Proxy** — All API paths (`/analyze`, `/health`, `/session`, `/prompts`, etc.) are proxied to Flask on port 5000
- **HTTPS** — Enabled via `VITE_DEV_HTTPS=true` (uses `@vitejs/plugin-basic-ssl`)
- **HMR** — Disabled by default for stability with phone connections
- **Allowed hosts** — Ngrok and Cloudflare tunnel domains are pre-allowed

## npm Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start dev server (HTTP, HMR disabled) |
| `npm run dev:https` | Start dev server with self-signed HTTPS |
| `npm run dev:hmr` | Start dev server with HMR enabled |
| `npm run build` | TypeScript check + production build |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview production build |

## Environment Variables

Set in `frontend/.env.local` (copy from `.env.example`):

| Variable | Description |
|----------|-------------|
| `VITE_PAIRING_ORIGIN` | HTTPS tunnel URL for phone QR codes |
| `VITE_PROGRAM_API_URL` | Override backend API base URL |
| `VITE_SCHEMATIC_IMAGE_PATHS` | Comma-separated schematic image paths |
| `VITE_DEV_HTTPS` | Enable HTTPS dev server (`true`/`false`) |
| `VITE_DISABLE_HMR` | Disable hot module replacement (`true`/`false`) |
