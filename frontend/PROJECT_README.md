# Frontend - Dynamic Graphics Display

A React TypeScript application that displays dynamic graphics boxes with webcam feed and connects to a Python Flask AI backend.

## Features

- **Image Display Box 1**: Shows example1.png
- **Image Display Box 2**: Shows example2.png
- **Live Webcam Feed**: Displays real-time video from your webcam with audio capture
- **AI Backend Integration**: Ready to send captures to Flask backend for analysis

## Quick Start

### Install Dependencies

```bash
cd frontend
npm install
```

### Start the Development Server

```bash
npm run dev
```

The React app will run on http://localhost:5173

### Start the AI Backend (Separate Terminal)

```bash
cd ../
python programAPI.py
```

The Flask backend will run on http://localhost:5000

## Camera Permissions

When you first load the application, your browser will ask for permission to access your webcam and microphone. Click "Allow" to enable the live video and audio capture.

## Technology Stack

- **Frontend:** React 18, TypeScript, Vite 8
- **Backend:** Python Flask with Gemini AI
- **Styling:** CSS3 with Grid Layout
- **APIs:** MediaDevices API (webcam/audio), Fetch API

## Browser Compatibility

The webcam feature requires getUserMedia API support. Works in:
- Chrome/Edge (modern versions)
- Firefox (modern versions)
- Safari (modern versions)

Make sure you're using HTTPS in production for webcam access to work.
