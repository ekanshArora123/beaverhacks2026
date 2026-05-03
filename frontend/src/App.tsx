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
  model?: string
  error?: string
}

interface VoiceToTextResponse {
  text?: string
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
  const audioContextRef = useRef<AudioContext | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)
  
  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [returnedImages, setReturnedImages] = useState<string[]>([])
  const [isSending, setIsSending] = useState(false)

  const [isRecording, setIsRecording] = useState(false)
  const [transcription, setTranscription] = useState<string>("")

  useEffect(() => {
    // Request webcam and microphone access
    const enableMediaCapture = async () => {
      let animationFrameId = 0
      let audioContext: AudioContext | null = null

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true
        })

        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }

        const recorderFormat = resolveRecorderFormat()
        recorderFormatRef.current = recorderFormat
        const mediaRecorder = new MediaRecorder(stream, {
          mimeType: recorderFormat.mimeType,
        })
        mediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
          if (event.data.size > 0) {
            audioChunksRef.current.push(event.data)
          }
        }

        mediaRecorder.onstop = async () => {
          const activeRecorderFormat = recorderFormatRef.current
          if (!activeRecorderFormat) {
            return
          }
          const audioBlob = new Blob(audioChunksRef.current, { type: activeRecorderFormat.mimeType })
          audioChunksRef.current = [] // reset
          await sendAudioToBackend(audioBlob, activeRecorderFormat)
        }

        // --- Automated Voice Activity Detection (VAD) ---
        const localAudioContext = new AudioContext()
        audioContext = localAudioContext
        audioContextRef.current = localAudioContext
        const analyser = localAudioContext.createAnalyser()
        const microphone = localAudioContext.createMediaStreamSource(stream)

        analyser.smoothingTimeConstant = 0.8
        analyser.fftSize = 1024
        microphone.connect(analyser)

        let isSpeaking = false
        let silenceTimer: ReturnType<typeof setTimeout> | null = null
        const array = new Uint8Array(analyser.frequencyBinCount)

        const checkAudioLevel = () => {
          analyser.getByteFrequencyData(array)

          let maxVolume = 0
          for (let i = 0; i < array.length; i++) {
            if (array[i] > maxVolume) {
              maxVolume = array[i]
            }
          }

          // VOLUME THRESHOLD: Volume ranges from 0 to 255.
          const THRESHOLD = 10

          if (maxVolume > THRESHOLD) {
            // User is speaking
            if (!isSpeaking) {
              isSpeaking = true
              if (mediaRecorder.state === "inactive") {
                // Ensure audio context is running (browsers suspend it if no user interaction occurred)
                if (localAudioContext.state === 'suspended') {
                  void localAudioContext.resume()
                }
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

          // Debug log - open DevTools (F12) to see this!
          // If this says 0 continuously, your browser is using the wrong microphone 
          // or the audio engine is still suspended.
          if (maxVolume > 0 || localAudioContext.state === 'suspended') {
            console.log('Max Volume:', maxVolume, '| Context State:', localAudioContext.state)
          }

          // Loop forever
          animationFrameId = requestAnimationFrame(checkAudioLevel)
        }

        // Start the listening loop
        checkAudioLevel()
        // ------------------------------------------------
      } catch (error) {
        console.error('Error accessing webcam/microphone:', error)
        setWebcamError('Unable to access webcam/microphone. Please grant permissions.')
      }

      return () => {
        if (animationFrameId) {
          cancelAnimationFrame(animationFrameId)
        }
        if (audioContext) {
          void audioContext.close()
        }
        if (audioContextRef.current === audioContext) {
          audioContextRef.current = null
        }
      }
    }

    let cleanupInternal: (() => void) | undefined
    void enableMediaCapture().then((cleanupFn) => {
      cleanupInternal = cleanupFn
    })

    // Cleanup: stop video and audio streams when component unmounts
    return () => {
      if (cleanupInternal) {
        cleanupInternal()
      }

      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream
        stream.getTracks().forEach(track => track.stop())
      }

      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
    }
  }, [])

  const getAnalysisPrompt = () => {
    const normalizedTranscription = transcription.trim()
    if (!normalizedTranscription || normalizedTranscription === 'Listening...' || normalizedTranscription === 'Thinking...') {
      return DEFAULT_ANALYZE_PROMPT
    }
    return normalizedTranscription
  }

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
      formData.append('prompt', getAnalysisPrompt())
      
      // Call backend
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

      alert(`Analysis: ${result?.text || 'No response'}`)

      setCapturedImages([])
    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python backend/start_server.py)\n2. You have set GEMINI_API_KEY`)
    } finally {
      setIsSending(false)
    }
  }

  const sendAudioToBackend = async (audioBlob: Blob, recorderFormat: RecorderFormat) => {
    const formData = new FormData()
    formData.append('file', audioBlob, `recording.${recorderFormat.extension}`)

    try {
      const voiceToTextUrl = buildApiUrl('/voice-to-text')
      console.log('Sending audio to backend for transcription...', voiceToTextUrl)
      const response = await fetch(voiceToTextUrl, {
        method: 'POST',
        body: formData,
      })

      const data = await parseJsonResponse<VoiceToTextResponse>(response)
      if (response.ok) {
        const transcriptText = (data?.user_input_text || data?.text || '').trim()
        console.log('Transcription:', transcriptText)
        setTranscription(transcriptText || 'No speech detected from the latest recording.')
      } else {
        const backendError = data?.error || 'Unknown transcription error'
        console.error('Transcription Error:', backendError)
        setTranscription(`Transcription failed: ${backendError}`)
      }
    } catch (error) {
      console.error('Failed to connect to backend:', error)
      setTranscription('Transcription failed: unable to connect to backend.')
    }
  }

  return (
    <div
      className="app"
      onClick={() => {
        if (audioContextRef.current?.state === 'suspended') {
          void audioContextRef.current.resume()
          console.log('AudioContext resumed by user interaction!')
        }
      }}
    >
      
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
