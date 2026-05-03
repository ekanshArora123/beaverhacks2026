# beaverhacks2026

A dynamic graphics display application with AI image analysis capabilities.

## Project Structure

- **AIBackend/** - Python AI backend with Gemini API integration
- **ts-frontend/** - Original TypeScript frontend
- **frontend/** - React/TypeScript UI with webcam and audio capture
- **programAPI.py** - Flask API server for AI processing

## Quick Start

### Prerequisites

- Node.js installed
- Python 3.x with pip
- A webcam and microphone
- Gemini API key

### 1. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Key

Set your Gemini API key:
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your-api-key-here"

# Linux/Mac
export GEMINI_API_KEY="your-api-key-here"
```

Or create `AIBackend/keys.py`:
```python
GEMINI_KEY = "your-api-key-here"
```

### 4. Start the Servers

**Terminal 1 - Start Flask Backend:**
```bash
python programAPI.py
```
- Runs on http://localhost:5000
- Provides `/analyze` and `/generate` endpoints

**Terminal 2 - Start Frontend:**
```bash
cd frontend
npm run dev
```
- Runs on http://localhost:5173
- Open in your browser and allow webcam/microphone permissions

## Features

- **Live Webcam Display** - Real-time video feed with audio capture
- **Dynamic Image Boxes** - Two image display slots
- **AI Analysis** - Send images to Gemini for analysis
- **Image Generation** - Generate images from text prompts

## API Endpoints (Flask Backend)

### Analyze Media
```bash
POST http://localhost:5000/analyze
Content-Type: multipart/form-data
Fields: file (optional), prompt (required)
```

### Generate Content
```bash
POST http://localhost:5000/generate
Content-Type: application/json
Body: { "prompt": "your prompt here" }
```

### Health Check
```bash
GET http://localhost:5000/health
```

## Documentation

- [frontend/PROJECT_README.md](frontend/PROJECT_README.md) - Frontend documentation
- [AIBackend/](AIBackend/) - AI backend implementation

# 