# beaverhacks2026

A dynamic graphics display application with image upload API endpoints.

## Project Structure

- **AIBackend/** - Python AI/backend service
- **ts-frontend/** - Original TypeScript frontend
- **frontend/** - React/TypeScript UI with webcam and image display features

## Quick Start - Frontend

### Prerequisites

- Node.js installed
- A webcam (for live video feed)
- Python with `requests` library (optional, for sending images)

### Installation

```bash
cd frontend
npm install
```

### Running the Application

You need to run **two servers** in separate terminals:

**Terminal 1 - Start Backend API Server:**
```bash
cd frontend
npm run server
```
- Runs on http://localhost:3001
- Provides API endpoints for image uploads

**Terminal 2 - Start Frontend Dev Server:**
```bash
cd frontend
npm run dev
```
- Runs on http://localhost:5173
- Open in your browser and allow webcam permissions

**OR use the quick launcher (Windows):**
```bash
cd frontend
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
cd frontend
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

- [frontend/PROJECT_README.md](frontend/PROJECT_README.md) - Detailed project documentation
- [frontend/API_DOCUMENTATION.md](frontend/API_DOCUMENTATION.md) - Complete API reference
- [frontend/TESTING.md](frontend/TESTING.md) - Testing guide with examples

# 