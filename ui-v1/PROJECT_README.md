# UI-V1 - Dynamic Graphics Display

A React TypeScript application that displays three dynamic graphics boxes with API endpoints for receiving images from external sources (like Python Flask servers).

## Features

- **Image Display Box 1**: Shows example1.png (updateable via API)
- **Image Display Box 2**: Shows example2.png (updateable via API)
- **Live Webcam Feed**: Displays real-time video from your webcam
- **API Endpoints**: Accept image uploads from external servers
- **Auto-refresh**: Front-end automatically displays newly uploaded images

## Quick Start

### Start Both Servers

You need to run **two terminals**:

**Terminal 1 - Backend API Server:**
```bash
cd ui-v1
npm run server
```
This starts the API server on http://localhost:3001

**Terminal 2 - Frontend Development Server:**
```bash
cd ui-v1
npm run dev
```
This starts the React app on http://localhost:5173

### First Time Setup

If you haven't installed dependencies yet:
```bash
cd ui-v1
npm install
```

## API Endpoints

The backend server provides endpoints that a Python Flask server (or any HTTP client) can use to send images:

### Upload Single Image
```bash
POST http://localhost:3001/api/upload-image
Content-Type: multipart/form-data
Field: image (file)
```

### Update Display Image
```bash
POST http://localhost:3001/api/update-image/example1
POST http://localhost:3001/api/update-image/example2
Content-Type: multipart/form-data
Field: image (file)
```

### List All Uploaded Images
```bash
GET http://localhost:3001/api/images
```

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for complete API documentation.

## Python Integration

### Using the Example Script

Send an image from Python:
```bash
# First install requests
pip install requests

# Upload an image
python send_image_example.py path/to/image.png

# Or update a specific display slot
python send_image_example.py path/to/image.png example1
```

### Flask Server Example

```python
import requests

# Send image to ui-v1
with open('image.png', 'rb') as f:
    files = {'image': f}
    response = requests.post('http://localhost:3001/api/upload-image', files=files)
    print(response.json())
```

See `send_image_example.py` for a complete Python integration example.

## Camera Permissions

When you first load the application, your browser will ask for permission to access your webcam. Click "Allow" to enable the live video feed.

## Project Structure

```
ui-v1/
├── server/
│   └── index.js          # Express API server
├── src/
│   ├── App.tsx           # React main component
│   └── App.css           # Styles
├── public/
│   ├── example1.png      # Display image 1
│   ├── example2.png      # Display image 2
│   └── uploads/          # Uploaded images directory
├── send_image_example.py # Python integration example
└── API_DOCUMENTATION.md  # Complete API docs
```

## Technology Stack

- **Frontend:** React 18, TypeScript, Vite 8
- **Backend:** Node.js, Express 5, Multer (file uploads)
- **Styling:** CSS3 with Grid Layout
- **APIs:** MediaDevices API (webcam), Fetch API

## Browser Compatibility

The webcam feature requires getUserMedia API support. Works in:
- Chrome/Edge (modern versions)
- Firefox (modern versions)
- Safari (modern versions)

Make sure you're using HTTPS in production for webcam access to work.
