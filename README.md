# beaverhacks2026

A dynamic graphics display application with image upload API endpoints.

## Project Structure

- **AIBackend/** - Python AI/backend service
- **ts-frontend/** - Original TypeScript frontend
- **ui-v1/** - React/TypeScript UI with webcam and image display features

## Quick Start - UI-V1 Frontend

### Prerequisites

- Node.js installed
- A webcam (for live video feed)
- Python with `requests` library (optional, for sending images)

### Installation

```bash
cd ui-v1
npm install
```

### Running the Application

You need to run **two servers** in separate terminals:

**Terminal 1 - Start Backend API Server:**
```bash
cd ui-v1
npm run server
```
- Runs on http://localhost:3001
- Provides API endpoints for image uploads

**Terminal 2 - Start Frontend Dev Server:**
```bash
cd ui-v1
npm run dev
```
- Runs on http://localhost:5173
- Open in your browser and allow webcam permissions

**OR use the quick launcher (Windows):**
```bash
cd ui-v1
start-servers.bat
```

### Features

- **Live Webcam Display** - Real-time video feed from your camera
- **Dynamic Image Boxes** - Two image display slots (example1.png, example2.png)
- **API Endpoints** - Receive images from external sources (Python Flask, etc.)
- **Auto-Refresh** - Frontend automatically updates when new images are uploaded

### API Usage

**Send an image from Python:**
```bash
cd ui-v1
pip install requests
python send_image_example.py path/to/image.png example1
```

**Update images via HTTP:**
```python
import requests

# Upload to general uploads
with open('image.png', 'rb') as f:
    requests.post('http://localhost:3001/api/upload-image', files={'image': f})

# Update display slot
with open('image.png', 'rb') as f:
    requests.post('http://localhost:3001/api/update-image/example1', files={'image': f})
```

### Available API Endpoints

- `POST /api/upload-image` - Upload single image
- `POST /api/update-image/example1` - Update Image 1
- `POST /api/update-image/example2` - Update Image 2
- `GET /api/images` - List all uploaded images
- `GET /api/health` - Health check

### Documentation

- [ui-v1/PROJECT_README.md](ui-v1/PROJECT_README.md) - Detailed project documentation
- [ui-v1/API_DOCUMENTATION.md](ui-v1/API_DOCUMENTATION.md) - Complete API reference
- [ui-v1/TESTING.md](ui-v1/TESTING.md) - Testing guide with examples

# 