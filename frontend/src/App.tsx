import { useEffect, useRef, useState } from 'react'
import './App.css'

interface UploadedImage {
  filename: string;
  url: string;
}

function App() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([])
  const [imageTimestamp, setImageTimestamp] = useState(Date.now())

  useEffect(() => {
    // Request webcam and microphone access
    const enableWebcam = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: true,
          audio: true 
        })
        
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (error) {
        console.error('Error accessing webcam/microphone:', error)
        setWebcamError('Unable to access webcam/microphone. Please grant permissions.')
      }
    }

    enableWebcam()

    // Cleanup: stop video stream when component unmounts
    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream
        stream.getTracks().forEach(track => track.stop())
      }
    }
  }, [])

  // Poll for new uploaded images
  useEffect(() => {
    const fetchImages = async () => {
      try {
        const response = await fetch('/api/images')
        if (response.ok) {
          const data = await response.json()
          setUploadedImages(data.images || [])
        }
      } catch (error) {
        console.error('Error fetching images:', error)
      }
    }

    fetchImages()
    
    // Refresh images every 5 seconds
    const interval = setInterval(fetchImages, 5000)
    
    return () => clearInterval(interval)
  }, [])

  // Refresh example images periodically to show updates
  useEffect(() => {
    const interval = setInterval(() => {
      setImageTimestamp(Date.now())
    }, 3000)
    
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="app">
      <h1>Dynamic Graphics Display</h1>
      
      <div className="display-grid">
        <div className="display-box">
          <h2>Image 1</h2>
          <img 
            src={`/example1.png?t=${imageTimestamp}`} 
            alt="Example 1" 
            className="display-image" 
          />
        </div>

        <div className="display-box">
          <h2>Image 2</h2>
          <img 
            src={`/example2.png?t=${imageTimestamp}`} 
            alt="Example 2" 
            className="display-image" 
          />
        </div>

        <div className="display-box">
          <h2>Live Webcam</h2>
          {webcamError ? (
            <div className="error-message">{webcamError}</div>
          ) : (
            <video 
              ref={videoRef} 
              autoPlay 
              playsInline
              className="display-video"
            />
          )}
        </div>
      </div>

      {uploadedImages.length > 0 && (
        <div className="uploaded-section">
          <h2>Uploaded Images ({uploadedImages.length})</h2>
          <div className="uploaded-grid">
            {uploadedImages.map((image) => (
              <div key={image.filename} className="uploaded-image-box">
                <img 
                  src={image.url} 
                  alt={image.filename} 
                  className="uploaded-image"
                />
                <p className="image-filename">{image.filename}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="api-info">
        <h3>API Endpoints</h3>
        <p>Server running on port 3001</p>
        <ul>
          <li><code>POST /api/upload-image</code> - Upload single image</li>
          <li><code>POST /api/update-image/example1</code> - Update Image 1</li>
          <li><code>POST /api/update-image/example2</code> - Update Image 2</li>
        </ul>
      </div>
    </div>
  )
}

export default App
