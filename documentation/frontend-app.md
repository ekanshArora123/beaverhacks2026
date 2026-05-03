# Frontend App (Laptop Dashboard)

The main laptop interface for capturing images, recording audio, viewing AI responses, and managing phone pairing sessions.

## Relevant Files

| File | Role |
|------|------|
| `frontend/src/App.tsx` | Main dashboard component |
| `frontend/src/App.css` | Dashboard styles |
| `frontend/src/main.tsx` | Entry point and route switch |
| `frontend/src/index.css` | Global base styles |
| `frontend/index.html` | HTML shell |
| `frontend/src/api/programApiBase.ts` | Backend URL resolution |

## Layout

The dashboard has a two-column layout:
- **Left column** — Analysis results: text response and annotated diagram images
- **Right column** — Webcam feed (or phone pairing panel) with capture controls

Below the columns is a thumbnail strip showing captured images and a Send button.

## Features

### Image Capture
Click "📷 Capture" to snapshot the current webcam frame. Multiple images can be captured. Each appears as a removable thumbnail. Images are captured as PNG data URLs via a hidden `<canvas>`.

### Audio Recording
Click "🎤 Record" to start/stop microphone recording. Audio is captured via `MediaRecorder`. A status indicator shows recording state. Recorded audio can be discarded before sending.

### Text Input Mode
Toggle "⌨ Use Text" to switch from audio to manual text entry. A textarea replaces the audio controls. When active, audio recording is disabled and cleared.

### Diagram Source Toggle
Click the diagram source button to switch between "Edit: User" (annotate user's photo) and "Edit: Schematic" (annotate reference schematic). Only available when `VITE_SCHEMATIC_IMAGE_PATHS` is configured.

### Rolling Context
Transcribed user inputs are accumulated across submissions (up to 8 entries). This rolling history is sent as `text_source_1` on each request, giving the AI conversation continuity.

### Phone Mode
Toggle "📱 Use Phone" to replace the webcam panel with a phone pairing session. See [Phone Pairing](phone-pairing.md).

### Speech Output
After receiving a response, the frontend reads the text aloud using `window.speechSynthesis`.

### Context Window Management
When many images accumulate, the system trims to the most recent 3 images if the total count exceeds 8 or total bytes exceed 15 MB.

## Sending to Backend

The Send button packages all inputs as `FormData`:
- Schematic image paths (from env)
- Captured images (as file blobs)
- Audio recording (if present and not in text mode)
- Manual text (if in text mode)
- Rolling context history
- Diagram source preference

Sends `POST /analyze` and displays the response text + diagram image.
