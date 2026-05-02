# UI-V1 - Dynamic Graphics Display

A React TypeScript application that displays three dynamic graphics boxes.

## Features

- **Image Display Box 1**: Shows example1.png
- **Image Display Box 2**: Shows example2.png  
- **Live Webcam Feed**: Displays real-time video from your webcam

## Quick Start

1. Install dependencies (if not already done):
   ```bash
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open your browser to: http://localhost:5173/

## Camera Permissions

When you first load the application, your browser will ask for permission to access your webcam. Click "Allow" to enable the live video feed.

## Replacing Placeholder Images

The current example images are SVG placeholders. To use your own images:

1. Replace `public/example1.png` with your actual PNG image
2. Replace `public/example2.png` with your actual PNG image

The images will automatically update when you refresh the page.

## Technology Stack

- React 18
- TypeScript
- Vite 8
- CSS3 with Grid Layout

## Browser Compatibility

The webcam feature requires getUserMedia API support. Works in:
- Chrome/Edge (modern versions)
- Firefox (modern versions)
- Safari (modern versions)

Make sure you're using HTTPS in production for webcam access to work.
