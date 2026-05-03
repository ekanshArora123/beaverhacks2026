# API Documentation

## Overview

This project includes a Node.js/Express server that provides API endpoints for receiving images from external sources (like a Python Flask server).

## Getting Started

### 1. Start the Backend Server

```bash
npm run server
```

The API server will run on `http://localhost:3001`

### 2. Start the Frontend (in a separate terminal)

```bash
npm run dev
```

The React app will run on `http://localhost:5173`

---

## API Endpoints

### Health Check

**GET** `/api/health`

Check if the server is running.

**Response:**
```json
{
  "status": "ok",
  "message": "Server is running"
}
```

---

### Upload Single Image

**POST** `/api/upload-image`

Upload a single image file. The image will be saved in `public/uploads/` directory.

**Request:**
- Content-Type: `multipart/form-data`
- Field name: `image`
- File types: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Max size: 10MB

**Response:**
```json
{
  "success": true,
  "message": "Image uploaded successfully",
  "filename": "1714608234567-myimage.png",
  "url": "/uploads/1714608234567-myimage.png",
  "size": 245678
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:3001/api/upload-image \
  -F "image=@/path/to/image.png"
```

---

### Upload Multiple Images

**POST** `/api/upload-images`

Upload multiple images at once (up to 10 images).

**Request:**
- Content-Type: `multipart/form-data`
- Field name: `images` (multiple files)
- File types: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Max size: 10MB per file

**Response:**
```json
{
  "success": true,
  "message": "3 images uploaded successfully",
  "files": [
    {
      "filename": "1714608234567-image1.png",
      "url": "/uploads/1714608234567-image1.png",
      "size": 245678
    },
    {
      "filename": "1714608234568-image2.png",
      "url": "/uploads/1714608234568-image2.png",
      "size": 189234
    }
  ]
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:3001/api/upload-images \
  -F "images=@/path/to/image1.png" \
  -F "images=@/path/to/image2.png"
```

---

### Update Example Image Slot

**POST** `/api/update-image/:slot`

Update one of the main display images (example1 or example2).

**Parameters:**
- `slot`: Either `example1` or `example2`

**Request:**
- Content-Type: `multipart/form-data`
- Field name: `image`
- File types: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`
- Max size: 10MB

**Response:**
```json
{
  "success": true,
  "message": "example1.png updated successfully",
  "filename": "example1.png",
  "url": "/example1.png"
}
```

**cURL Examples:**
```bash
# Update Image 1
curl -X POST http://localhost:3001/api/update-image/example1 \
  -F "image=@/path/to/newimage.png"

# Update Image 2
curl -X POST http://localhost:3001/api/update-image/example2 \
  -F "image=@/path/to/newimage.png"
```

---

### List Uploaded Images

**GET** `/api/images`

Get a list of all uploaded images in the uploads directory.

**Response:**
```json
{
  "count": 5,
  "images": [
    {
      "filename": "1714608234567-image1.png",
      "url": "/uploads/1714608234567-image1.png"
    },
    {
      "filename": "1714608234568-image2.png",
      "url": "/uploads/1714608234568-image2.png"
    }
  ]
}
```

---

## Python/Flask Integration

### Using the Example Script

A Python example script is included: `send_image_example.py`

**Install dependencies:**
```bash
pip install requests
```

**Usage:**
```bash
# Upload to general uploads
python send_image_example.py path/to/image.png

# Update Image 1
python send_image_example.py path/to/image.png example1

# Update Image 2
python send_image_example.py path/to/image.png example2
```

### Flask Code Example

```python
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/send-to-ui', methods=['POST'])
def send_to_ui():
    # Get image from Flask request
    if 'image' not in request.files:
        return jsonify({'error': 'No image'}), 400
    
    image_file = request.files['image']
    
    # Forward to frontend API
    files = {'image': image_file}
    response = requests.post(
        'http://localhost:3001/api/upload-image',
        files=files
    )
    
    return jsonify(response.json())

if __name__ == '__main__':
    app.run(port=5000)
```

---

## Error Responses

All endpoints return appropriate HTTP status codes:

- `200 OK` - Success
- `400 Bad Request` - Missing or invalid parameters
- `500 Internal Server Error` - Server error

**Error Response Format:**
```json
{
  "error": "Error message description"
}
```

---

## File Storage

- **Uploaded images:** Saved to `public/uploads/` with timestamp-prefixed filenames
- **Example images:** Saved directly as `public/example1.png` and `public/example2.png`
- **Auto-creation:** The uploads directory is created automatically if it doesn't exist

---

## Notes

- The frontend automatically refreshes to show new images every 3-5 seconds
- CORS is enabled for all origins (configure in `server/index.js` for production)
- Images are validated to ensure they are actual image files
- Maximum file size is 10MB per image
