import { useEffect, useRef, useState } from 'react'
import './App.css'

interface CapturedImage {
  id: string
  dataUrl: string
}

interface AnalyzeResponse {
  text?: string
  image?: string | null
  image_mime?: string | null
  user_input_text?: string
  model?: string
  error?: string
}

interface RecorderFormat {
  mimeType: string
  extension: string
}

const DEFAULT_ANALYZE_PROMPT = 'Analyze this image and describe what you see.'
const PROGRAM_API_BASE_URL = ((import.meta.env.VITE_PROGRAM_API_URL as string | undefined)?.trim() || 'http://127.0.0.1:5000').replace(/\/+$/, '')

const RECORDER_FORMAT_CANDIDATES: RecorderFormat[] = [
  { mimeType: 'audio/ogg;codecs=opus', extension: 'ogg' },
  { mimeType: 'audio/ogg', extension: 'ogg' },
  { mimeType: 'audio/mp4', extension: 'm4a' },
  { mimeType: 'audio/aac', extension: 'aac' },
  { mimeType: 'audio/webm;codecs=opus', extension: 'webm' },
  { mimeType: 'audio/webm', extension: 'webm' },
]
const LOOP_TRANSCRIPT_HISTORY_LIMIT = 8

function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${PROGRAM_API_BASE_URL}${normalizedPath}`
}

function resolveRecorderFormat(): RecorderFormat {
  if (typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') {
    return { mimeType: 'audio/webm', extension: 'webm' }
  }

  for (const candidate of RECORDER_FORMAT_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate.mimeType)) {
      return candidate
    }
  }

  return { mimeType: 'audio/webm', extension: 'webm' }
}

async function parseJsonResponse<T>(response: Response): Promise<T | null> {
  try {
    return await response.json() as T
  } catch {
    return null
  }
}

function App() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)
  const loopTranscriptsRef = useRef<string[]>([])

  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [returnedImages, setReturnedImages] = useState<string[]>([])
  const [analysisResult, setAnalysisResult] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)

  const [isRecording, setIsRecording] = useState(false)
  const [hasAudioRecording, setHasAudioRecording] = useState(false)

  useEffect(() => {
    const enableMediaCapture = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true
        })

        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.muted = true
        }

        const recorderFormat = resolveRecorderFormat()
        recorderFormatRef.current = recorderFormat

        const audioStream = new MediaStream(stream.getAudioTracks())

        const mediaRecorder = new MediaRecorder(audioStream, {
          mimeType: recorderFormat.mimeType,
        })
        mediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data)
          }
        }

        mediaRecorder.onstop = () => {
          if (audioChunksRef.current.length > 0) {
            setHasAudioRecording(true)
          }
        }
      } catch (error) {
        console.error('Error accessing webcam/microphone:', error)
        setWebcamError('Unable to access webcam/microphone. Please grant permissions.')
      }
    }

    void enableMediaCapture()

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

  const toggleRecording = () => {
    const recorder = mediaRecorderRef.current
    if (!recorder) return

    if (isRecording) {
      // Stop recording
      if (recorder.state === 'recording') {
        recorder.stop()
      }
      setIsRecording(false)
    } else {
      // Start recording — clear previous audio
      audioChunksRef.current = []
      setHasAudioRecording(false)
      if (recorder.state === 'inactive') {
        recorder.start()
      }
      setIsRecording(true)
    }
  }

  const discardAudio = () => {
    audioChunksRef.current = []
    setHasAudioRecording(false)
  }

  const buildRollingLoopContext = () => {
    if (loopTranscriptsRef.current.length === 0) {
      return ''
    }

    const recentTranscripts = loopTranscriptsRef.current.slice(-LOOP_TRANSCRIPT_HISTORY_LIMIT)
    return [
      'Recent technician voice updates (oldest to newest):',
      ...recentTranscripts.map((entry, index) => `${index + 1}. ${entry}`)
    ].join('\n')
  }

  const captureImage = () => {
    if (!videoRef.current || !canvasRef.current) return

    const video = videoRef.current
    const canvas = canvasRef.current
    const context = canvas.getContext('2d')

    if (!context) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    context.drawImage(video, 0, 0, canvas.width, canvas.height)
    const dataUrl = canvas.toDataURL('image/png')

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
    const urlToUse = capturedImages.length > 0 ? capturedImages[capturedImages.length - 1].dataUrl : null

    if (!urlToUse) {
      alert('Please capture at least one image first')
      return
    }

    // If still recording, stop first
    if (isRecording && mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      // Wait briefly for the onstop handler to fire and collect chunks
      await new Promise(resolve => setTimeout(resolve, 200))
    }

    setIsSending(true)

    try {
      const response = await fetch(urlToUse)
      const imageBlob = await response.blob()

      console.log('Sending image:', {
        size: imageBlob.size,
        type: imageBlob.type,
        imagesCount: capturedImages.length
      })

      const formData = new FormData()
      formData.append('file', imageBlob, 'capture.png')
      const hasAudioClip = audioChunksRef.current.length > 0 && recorderFormatRef.current

      if (!hasAudioClip) {
        formData.append('prompt', DEFAULT_ANALYZE_PROMPT)
      }

      const rollingLoopContext = buildRollingLoopContext()
      if (rollingLoopContext) {
        formData.append('text_source_1', rollingLoopContext)
      }

      // Append accumulated audio if available
      if (hasAudioClip && recorderFormatRef.current) {
        const audioBlob = new Blob(audioChunksRef.current, { type: recorderFormatRef.current.mimeType })
        formData.append('audio', audioBlob, `recording.${recorderFormatRef.current.extension}`)

        const approximateDurationSeconds = (audioBlob.size * 8) / (128 * 1024)

        console.log('=== AUDIO CLIP INFO ===')
        console.log('Full audio clip size:', audioBlob.size, 'bytes', `(${(audioBlob.size / 1024).toFixed(2)} KB)`)
        console.log('Audio format:', audioBlob.type)
        console.log('Number of chunks:', audioChunksRef.current.length)
        console.log('Approximate duration:', approximateDurationSeconds.toFixed(2), 'seconds')
        console.log('=======================')
      }

      const analyzeUrl = buildApiUrl('/analyze')
      console.log('Calling backend at', analyzeUrl)
      const apiResponse = await fetch(analyzeUrl, {
        method: 'POST',
        body: formData
      })

      console.log('Response status:', apiResponse.status)

      const result = await parseJsonResponse<AnalyzeResponse>(apiResponse)

      if (!apiResponse.ok) {
        const errorMessage = result?.error || 'Unknown error'
        console.error('Backend error:', result)
        throw new Error(`API error: ${apiResponse.status} - ${errorMessage}`)
      }

      console.log('Backend response:', result)

      if (result?.image) {
        const imageUrl = `data:${result.image_mime || 'image/png'};base64,${result.image}`
        setReturnedImages([imageUrl])
      } else {
        setReturnedImages([])
      }

      const responseText = result?.text || 'No response'
      setAnalysisResult(responseText)

      const transcribedUserInput = (result?.user_input_text || '').trim()
      if (transcribedUserInput) {
        const previousEntries = loopTranscriptsRef.current
        const latestEntry = previousEntries[previousEntries.length - 1]
        if (transcribedUserInput !== latestEntry) {
          loopTranscriptsRef.current = [
            ...previousEntries,
            transcribedUserInput,
          ].slice(-LOOP_TRANSCRIPT_HISTORY_LIMIT)
        }
      }

      // Stop any existing speech and read the new response aloud
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(responseText)
      window.speechSynthesis.speak(utterance)

      setCapturedImages([])
      audioChunksRef.current = []
      setHasAudioRecording(false)
    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python backend/start_server.py)\n2. You have set GEMINI_API_KEY`)
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="app">

      <div className="main-content">
        {/* Left column: Returned images from backend */}
        <div className="returned-images-column">
          <h2>Analysis Results</h2>

          {analysisResult && (
            <div style={{
              padding: '15px',
              backgroundColor: '#34495e',
              color: 'white',
              borderRadius: '8px',
              marginBottom: '20px',
              textAlign: 'left',
              lineHeight: '1.5'
            }}>
              <strong>Response:</strong><br />
              {analysisResult}
            </div>
          )}

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
          <h2>Live Webcam</h2>
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
                {isRecording && <div className="recording-overlay" />}
                <div className="webcam-controls">
                  <button
                    className="capture-button"
                    onClick={captureImage}
                    title="Capture Image"
                  >
                    📷 Capture
                  </button>
                  <button
                    className={`mic-button ${isRecording ? 'mic-recording' : ''} ${hasAudioRecording ? 'mic-has-audio' : ''}`}
                    onClick={toggleRecording}
                    title={isRecording ? 'Stop Recording' : 'Start Recording'}
                  >
                    {isRecording ? '⏹ Stop' : '🎤 Record'}
                  </button>
                </div>
              </>
            )}
          </div>
          {/* Audio status indicator below the webcam */}
          {(isRecording || hasAudioRecording) && (
            <div className={`audio-status ${isRecording ? 'audio-status-recording' : 'audio-status-ready'}`}>
              {isRecording ? (
                <><span className="audio-status-dot recording-dot" /> Recording audio...</>
              ) : (
                <>
                  <span className="audio-status-dot ready-dot" /> Audio recorded — will be sent with images
                  <button className="discard-audio-btn" onClick={discardAudio} title="Discard audio">✕</button>
                </>
              )}
            </div>
          )}
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
            onClick={() => {
              void sendToBackend()
            }}
            disabled={isSending}
          >
            {isSending ? 'Sending...' : `Send ${capturedImages.length} image${capturedImages.length > 1 ? 's' : ''}${hasAudioRecording ? ' + audio' : ''}`}
          </button>
        </div>
      )}

      {/* Hidden canvas for image capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  )
}

export default App
