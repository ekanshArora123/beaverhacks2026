# AI Technician Assistant

An AI-powered field-service technician support tool built for BeaverHacks 2026. The system provides real-time guidance to machinery technicians through a multimodal interface combining image analysis, voice interaction, annotated diagrams, and local documentation retrieval — all powered by Google Gemini.

## Overview

A technician working on a machine captures photos (from a laptop webcam or paired phone), optionally records audio or types a question, and submits the input. The backend runs a multi-stage Gemini prompt pipeline that:

1. **Analyzes** the images and question to produce spoken-style repair guidance.
2. **Generates** an annotated diagram overlaying arrows and labels on the photo showing the next action.
3. **Converts** the text response to speech audio (text-to-speech via Gemini).
4. **Persists** task state so context carries across sessions.

The frontend also reads the response aloud using the browser's `SpeechSynthesis` API for immediate hands-free feedback.

## Use Cases

- **Machinery troubleshooting** — A technician photographs a control panel and asks "Why is this relay clicking?" The AI cross-references schematics, past session context, and the photo to provide step-by-step guidance.
- **Hands-free operation** — Voice input/output allows technicians to interact without touching the screen.
- **Remote phone pairing** — A second person (or the technician's phone) can capture photos and audio that are relayed to the laptop dashboard for analysis.
- **Documentation lookup** — Machine-specific PDFs and manuals stored locally are automatically surfaced by the AI through agentic function calling.
- **Session continuity** — Task state is persisted so the AI remembers what has already been tried across multiple interactions.

## Project Structure

```
beaverhacks2026/
├── backend/                  # Python Flask API + Gemini prompt pipeline
│   ├── ApiScripts/           # Core AI prompt modules
│   ├── generated_audio/      # TTS output files
│   ├── generated_diagrams/   # Annotated diagram output files
│   ├── registry/             # Tool-context registry (placeholder)
│   └── tests/                # Backend unit tests
├── frontend/                 # React + TypeScript Vite application
│   └── src/                  # Components, hooks, API clients
├── machine_docs/             # Local machine documentation (PDFs, images, markdown)
├── taskStates/               # Persisted task state directories
├── scripts/                  # Firewall and network diagnostic scripts
├── notes/                    # Internal planning documents
├── sample output images/     # Example Gemini-generated output
├── start-dev.ps1             # One-command dev launcher (backend + frontend)
├── start-dev-ngrok.ps1       # Dev launcher with ngrok tunnel support
├── keys.env                  # API key file (not committed)
└── requirements.txt          # Python dependencies
```

## Prerequisites

- **Python 3.11+** (with pip)
- **Node.js 18+** (with npm)
- **Google Gemini API key** — obtain from [Google AI Studio](https://aistudio.google.com/)

## Setup

### 1. Clone the Repository

```bash
git clone <repo-url>
cd beaverhacks2026
```

### 2. Python Environment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

### 3. Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. API Key

Create a `keys.env` file in the project root:

```
GEMINI_API_KEY=your_api_key_here
```

Or set the environment variable:

```bash
$env:GEMINI_API_KEY = "your_api_key_here"   # PowerShell
export GEMINI_API_KEY="your_api_key_here"    # bash
```

## Running the Application

### One-Command Launch (Recommended)

The included PowerShell script starts both the backend and frontend together:

```powershell
.\start-dev.ps1
```

This will:
- Start the Flask backend on port **5000**
- Start the Vite dev server on port **5173**
- Open the browser to `http://localhost:5173`
- Read the API key from `keys.env` if not in the environment

**Options:**

| Flag | Description |
|------|-------------|
| `-SeparateWindows` | Open backend and frontend in separate terminal windows |
| `-NoBrowser` | Don't auto-open the browser |
| `-DevHttps` | Enable HTTPS for phone camera pairing on LAN |
| `-DryRun` | Print commands without executing |

### With ngrok (Phone Pairing on Campus Wi-Fi)

```powershell
.\start-dev-ngrok.ps1
```

This launches an ngrok HTTPS tunnel so a phone on eduroam or similar networks can reach the dev server.

### Manual Launch

**Backend** (terminal 1):
```bash
cd backend
python start_server.py
```
Server starts on `http://0.0.0.0:5000`.

**Frontend** (terminal 2):
```bash
cd frontend
npm run dev
```
Vite dev server starts on `http://localhost:5173`, with proxy rules forwarding API calls to Flask on port 5000.

## Environment Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `GEMINI_API_KEY` | Backend | Google Gemini API key |
| `BACKEND_HOST` | Backend | Flask bind address (default `0.0.0.0`) |
| `BACKEND_PORT` | Backend | Flask port (default `5000`) |
| `BACKEND_DEBUG` | Backend | Enable Flask debug mode |
| `VITE_PROGRAM_API_URL` | Frontend | Override backend API URL |
| `VITE_PAIRING_ORIGIN` | Frontend | HTTPS tunnel URL for phone pairing QR codes |
| `VITE_SCHEMATIC_IMAGE_PATHS` | Frontend | Comma-separated schematic image paths |
| `VITE_DEV_HTTPS` | Frontend | Enable HTTPS dev server |
| `VITE_DISABLE_HMR` | Frontend | Disable hot module replacement (default `true`) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/analyze` | POST | Full analysis pipeline (prompt 1 + diagram) |
| `/voice-to-text` | POST | Standalone audio transcription |
| `/prompts/1` | POST | Technician instruction (text) |
| `/prompts/2` | POST | Annotated diagram generation |
| `/prompts/3` | POST | Text-to-speech conversion |
| `/prompts/4` | POST | Task state update |
| `/prompts/run-all` | POST | Execute all 4 prompts sequentially |
| `/host-info` | GET | LAN IP addresses for phone pairing |
| `/session/new` | POST | Create a phone pairing session |
| `/session/<code>/input` | POST | Upload phone-captured input |
| `/session/<code>/pending` | GET | Long-poll for phone payloads |

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

## Documentation

See the [`documentation/`](documentation/) folder for detailed feature docs:

- [Prompt Pipeline](documentation/prompt-pipeline.md) — The 4-stage Gemini prompt sequence
- [Voice Input (Speech-to-Text)](documentation/voice-input.md) — Audio transcription
- [Text-to-Speech Output](documentation/text-to-speech.md) — Voice response generation
- [Diagram Generation](documentation/diagram-generation.md) — Annotated image overlays
- [Task State Management](documentation/task-state.md) — Session persistence
- [Phone Pairing](documentation/phone-pairing.md) — Mobile device input mode
- [Document Retrieval](documentation/document-retrieval.md) — Agentic local doc search
- [PDF to Markdown](documentation/pdf-to-markdown.md) — Documentation conversion
- [Networking & Tunnels](documentation/networking.md) — LAN, ngrok, HTTPS setup
- [Frontend App](documentation/frontend-app.md) — Laptop dashboard UI

## License

Built for BeaverHacks 2026.