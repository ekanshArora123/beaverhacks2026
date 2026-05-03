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

  const [isRecording, setIsRecording] = useState(false)
  const [transcription, setTranscription] = useState<string>("")
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])

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

        const mediaRecorder = new MediaRecorder(stream)
        mediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data)
          }
        }

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
          audioChunksRef.current = [] // reset
          await sendAudioToBackend(audioBlob)
        }

        // --- Automated Voice Activity Detection (VAD) ---
        const audioContext = new AudioContext()
        const analyser = audioContext.createAnalyser()
        const microphone = audioContext.createMediaStreamSource(stream)

        analyser.smoothingTimeConstant = 0.8
        analyser.fftSize = 1024
        microphone.connect(analyser)

        let isSpeaking = false
        let silenceTimer: NodeJS.Timeout | null = null
        const array = new Uint8Array(analyser.frequencyBinCount)

        const checkAudioLevel = () => {
          analyser.getByteFrequencyData(array)

          let values = 0
          for (let i = 0; i < array.length; i++) {
            values += array[i]
          }
          const average = values / array.length

          // VOLUME THRESHOLD: Adjust this between 5-30 depending on how noisy your hackathon room is!
          const THRESHOLD = 10

          if (average > THRESHOLD) {
            // User is speaking
            if (!isSpeaking) {
              isSpeaking = true
              if (mediaRecorder.state === "inactive") {
                mediaRecorder.start()
                setIsRecording(true)
                setTranscription("Listening...")
              }
            }
            // Clear any pending silence timeout because they are still talking
            if (silenceTimer) {
              clearTimeout(silenceTimer)
              silenceTimer = null
            }
          } else {
            // User is silent
            if (isSpeaking && !silenceTimer) {
              // Wait 2 seconds before assuming they finished their sentence
              silenceTimer = setTimeout(() => {
                isSpeaking = false
                if (mediaRecorder.state === "recording") {
                  mediaRecorder.stop() // Triggers mediaRecorder.onstop -> sendAudioToBackend
                  setIsRecording(false)
                  setTranscription("Thinking...")
                }
              }, 2000)
            }
          }

          // Loop forever
          requestAnimationFrame(checkAudioLevel)
        }

        // Start the listening loop
        checkAudioLevel()
        // ------------------------------------------------
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

  const sendAudioToBackend = async (audioBlob: Blob) => {
    const formData = new FormData()
    formData.append("file", audioBlob, "recording.webm")

    try {
      console.log("Sending audio to backend for transcription...")
      const response = await fetch("http://127.0.0.1:5000/voice-to-text", {
        method: "POST",
        body: formData,
      })

      const data = await response.json()
      if (response.ok) {
        console.log("Transcription:", data.text)
        setTranscription(data.text)
      } else {
        console.error("Transcription Error:", data.error)
      }
    } catch (error) {
      console.error("Failed to connect to backend:", error)
    }
  }

  return (
    <div className="app">
      <h1>Dynamic Graphics Display</h1>

      <div className="audio-controls" style={{ marginBottom: '20px', padding: '15px', backgroundColor: '#f8f9fa', borderRadius: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px' }}>
          <div style={{
            width: '15px',
            height: '15px',
            borderRadius: '50%',
            backgroundColor: isRecording ? '#e74c3c' : '#2ecc71',
            marginRight: '10px',
            animation: isRecording ? 'pulse 1s infinite' : 'none'
          }} />
          <strong style={{ fontSize: '1.2em' }}>
            {isRecording ? "🎤 Listening to your question..." : "🟢 Microphone Active (Waiting for voice...)"}
          </strong>
        </div>

        {transcription && (
          <div style={{ padding: '15px', backgroundColor: '#2c3e50', color: 'white', borderRadius: '5px', textAlign: 'left' }}>
            <strong>Status / AI Heard:</strong> {transcription}
          </div>
        )}
      </div>

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
