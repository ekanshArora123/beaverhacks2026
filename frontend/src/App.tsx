import { useEffect, useRef, useState } from 'react'
import './App.css'

interface CapturedImage {
  id: string
  dataUrl: string
}

function App() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  
  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [returnedImages, setReturnedImages] = useState<string[]>([])
  const [isRecording, setIsRecording] = useState(false)
  const [isSending, setIsSending] = useState(false)

  useEffect(() => {
    // Request webcam and microphone access
    const enableMediaCapture = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: true,
          audio: true 
        })
        
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }

        // Start audio recording
        try {
          const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true })
          const mediaRecorder = new MediaRecorder(audioStream, {
            mimeType: 'audio/webm'
          })
          
          mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
              audioChunksRef.current.push(event.data)
            }
          }

          mediaRecorder.start(1000) // Collect data every second
          mediaRecorderRef.current = mediaRecorder
          setIsRecording(true)
        } catch (audioError) {
          console.error('Error starting audio recording:', audioError)
        }
      } catch (error) {
        console.error('Error accessing webcam/microphone:', error)
        setWebcamError('Unable to access webcam/microphone. Please grant permissions.')
      }
    }

    enableMediaCapture()

    // Cleanup: stop video and audio streams when component unmounts
    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream
        stream.getTracks().forEach(track => track.stop())
      }
      
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
    }
  }, [])

  const captureImage = () => {
    if (!videoRef.current || !canvasRef.current) return

    const video = videoRef.current
    const canvas = canvasRef.current
    const context = canvas.getContext('2d')

    if (!context) return

    // Set canvas dimensions to match video
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight

    // Draw current video frame to canvas
    context.drawImage(video, 0, 0, canvas.width, canvas.height)

    // Convert canvas to data URL
    const dataUrl = canvas.toDataURL('image/png')

    // Add to captured images
    const newImage: CapturedImage = {
      id: Date.now().toString(),
      dataUrl: dataUrl
    }

    setCapturedImages(prev => [...prev, newImage])
  }

  const removeCapturedImage = (id: string) => {
    setCapturedImages(prev => prev.filter(img => img.id !== id))
  }

  const sendToBackend = async () => {
    if (capturedImages.length === 0) {
      alert('Please capture at least one image first')
      return
    }

    setIsSending(true)

    try {
      // Create audio blob from recorded chunks
      // TODO: Send audio to backend when endpoint supports it
      // const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })

      // Convert first image dataUrl to blob
      const response = await fetch(capturedImages[0].dataUrl)
      const imageBlob = await response.blob()

      console.log('Sending image:', {
        size: imageBlob.size,
        type: imageBlob.type,
        imagesCount: capturedImages.length
      })

      const formData = new FormData()
      formData.append('file', imageBlob, 'capture.png')
      formData.append('prompt', 'Analyze this image and describe what you see.')
      
      // Call backend
      console.log('Calling backend at http://127.0.0.1:5000/analyze')
      const apiResponse = await fetch('http://127.0.0.1:5000/analyze', {
        method: 'POST',
        body: formData
      })

      console.log('Response status:', apiResponse.status)

      if (!apiResponse.ok) {
        const errorData = await apiResponse.json().catch(() => ({ error: 'Unknown error' }))
        console.error('Backend error:', errorData)
        throw new Error(`API error: ${apiResponse.status} - ${errorData.error || 'Unknown error'}`)
      }

      const result = await apiResponse.json()
      console.log('Backend response:', result)
      
      // Handle response
      // Currently /analyze returns { "text": "..." }
      // When backend is updated to return audio/images, handle them here
      
      if (result.audio) {
        // Play audio response
        const audioUrl = `data:audio/webm;base64,${result.audio}`
        const audio = new Audio(audioUrl)
        audio.play()
      }

      if (result.images && Array.isArray(result.images)) {
        // Display returned images
        setReturnedImages(result.images)
      } else if (result.image) {
        // Single image
        const imageUrl = `data:${result.image_mime || 'image/png'};base64,${result.image}`
        setReturnedImages([imageUrl])
      }

      // For now, just log the text response
      console.log('Backend response:', result)
      alert(`Analysis: ${result.text || 'No response'}`)

      // Clear captured images after successful send
      setCapturedImages([])
      audioChunksRef.current = []

    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python programAPI.py)\n2. You have set GEMINI_API_KEY environment variable or in AIBackend/keys.py`)
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="app">
      <h1>AI Media Analyzer</h1>
      
      <div className="main-content">
        {/* Left column: Returned images from backend */}
        <div className="returned-images-column">
          <h2>Analysis Results</h2>
          {returnedImages.length === 0 ? (
            <div className="empty-state">
              <p>Analyzed images will appear here</p>
            </div>
          ) : (
            <div className="returned-images-grid">
              {returnedImages.map((imgUrl, index) => (
                <div key={index} className="returned-image-box">
                  <img src={imgUrl} alt={`Result ${index + 1}`} className="returned-image" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right column: Webcam feed */}
        <div className="webcam-column">
          <h2>Live Webcam {isRecording && <span className="recording-indicator">● REC</span>}</h2>
          <div className="video-container">
            {webcamError ? (
              <div className="error-message">{webcamError}</div>
            ) : (
              <>
                <video 
                  ref={videoRef} 
                  autoPlay 
                  playsInline
                  className="display-video"
                />
                <button 
                  className="capture-button" 
                  onClick={captureImage}
                  title="Capture Image"
                >
                  📷 Capture
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Thumbnail preview section */}
      {capturedImages.length > 0 && (
        <div className="thumbnails-section">
          <div className="thumbnails-container">
            {capturedImages.map((img) => (
              <div key={img.id} className="thumbnail-box">
                <img src={img.dataUrl} alt="Captured" className="thumbnail" />
                <button 
                  className="remove-thumbnail" 
                  onClick={() => removeCapturedImage(img.id)}
                  title="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <button 
            className="send-button" 
            onClick={sendToBackend}
            disabled={isSending}
          >
            {isSending ? 'Sending...' : `Send ${capturedImages.length} image${capturedImages.length > 1 ? 's' : ''}`}
          </button>
        </div>
      )}

      {/* Hidden canvas for image capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  )
}

export default App
