import { useEffect, useRef, useState } from 'react'
import './App.css'

function App() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [webcamError, setWebcamError] = useState<string | null>(null)

  useEffect(() => {
    // Request webcam access
    const enableWebcam = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: true,
          audio: false 
        })
        
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (error) {
        console.error('Error accessing webcam:', error)
        setWebcamError('Unable to access webcam. Please grant camera permissions.')
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

  return (
    <div className="app">
      <h1>Dynamic Graphics Display</h1>
      
      <div className="display-grid">
        <div className="display-box">
          <h2>Image 1</h2>
          <img src="/example1.png" alt="Example 1" className="display-image" />
        </div>

        <div className="display-box">
          <h2>Image 2</h2>
          <img src="/example2.png" alt="Example 2" className="display-image" />
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
    </div>
  )
}

export default App
