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
const USER_IMAGE_FALLBACK_LIMIT = 3
const USER_IMAGE_CONTEXT_SOFT_COUNT_LIMIT = 8
const USER_IMAGE_CONTEXT_SOFT_BYTES_LIMIT = 15 * 1024 * 1024
const TEXT_CONTEXT_SOFT_CHAR_LIMIT = 4000
const DEFAULT_SCHEMATIC_IMAGE_PATH = 'taskContext/task1/3d_printer.jpg'
const configuredSchematicPaths = ((import.meta.env.VITE_SCHEMATIC_IMAGE_PATHS as string | undefined) || '')
  .split(',')
  .map((path) => path.trim())
  .filter(Boolean)
const SCHEMATIC_IMAGE_PATHS = configuredSchematicPaths.length > 0
  ? configuredSchematicPaths
  : [DEFAULT_SCHEMATIC_IMAGE_PATH]

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

function estimateDataUrlBytes(dataUrl: string): number {
  const encodedPayload = dataUrl.split(',', 2)[1] || ''
  return Math.floor(encodedPayload.length * 0.75)
}

function App() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)
  const loopTranscriptsRef = useRef<string[]>([])

  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [returnedImages, setReturnedImages] = useState<string[]>([])
  const [analysisResult, setAnalysisResult] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)

  const [isRecording, setIsRecording] = useState(false)
  const [transcription, setTranscription] = useState<string>("")
  const [shouldSubmit, setShouldSubmit] = useState(false)
  const [isListeningModeEnabled, setIsListeningModeEnabled] = useState(false)
  
  const listeningModeRef = useRef(isListeningModeEnabled)
  useEffect(() => {
    listeningModeRef.current = isListeningModeEnabled
  }, [isListeningModeEnabled])

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
          videoRef.current.muted = true // Prevent audio feedback from microphone
        }

        const recorderFormat = resolveRecorderFormat()
        recorderFormatRef.current = recorderFormat
        
        // Extract only the audio tracks from the stream to avoid NotSupportedError
        // when using an audio-only MIME type with a stream that contains video.
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
          if (!listeningModeRef.current) {
            audioChunksRef.current = [] // discard audio
            setTranscription("Listening mode paused.")
            return
          }
          setTranscription(`Processing voice...`)
          setShouldSubmit(true)
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
          
          // Prevent feedback loops OR user turning off listening mode
          if (!listeningModeRef.current || window.speechSynthesis.speaking) {
            maxVolume = 0
            
            // If they toggled it off mid-sentence, cancel the recording immediately!
            if (!listeningModeRef.current && isSpeaking) {
              isSpeaking = false
              if (silenceTimer) {
                clearTimeout(silenceTimer)
                silenceTimer = null
              }
              if (mediaRecorder.state === "recording") {
                mediaRecorder.stop()
                setIsRecording(false)
              }
            }
          } else {
            for (let i = 0; i < array.length; i++) {
              if (array[i] > maxVolume) {
                maxVolume = array[i]
              }
            }
          }

          // VOLUME THRESHOLD: Volume ranges from 0 to 255.
          const THRESHOLD = 30

          if (maxVolume > THRESHOLD) {
            // User is speaking
            if (!isSpeaking) {
              isSpeaking = true
              if (mediaRecorder.state === "inactive") {
                // Looping mode sends only the latest clip, not historical audio batches.
                audioChunksRef.current = []
                // Ensure audio context is running (browsers suspend it if no user interaction occurred)
                if (localAudioContext.state === 'suspended') {
                  void localAudioContext.resume()
                }
                mediaRecorder.start()
                setIsRecording(true)
                setTranscription("Recording audio...")
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
                  mediaRecorder.stop() // Stops recording, accumulates chunks
                  setIsRecording(false)
                }
              }, 2000)
            }
          }

          // Debug log - print every 60 frames (~1 second) to diagnose
          if (animationFrameId % 60 === 0) {
            console.log('Max Volume:', maxVolume, '| Context State:', localAudioContext.state, '| TTS Speaking:', window.speechSynthesis.speaking)
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

    let isCancelled = false
    let cleanupInternal: (() => void) | undefined
    
    void enableMediaCapture().then((cleanupFn) => {
      if (isCancelled && cleanupFn) {
        // Component unmounted before we finished setting up! Clean up immediately.
        cleanupFn()
      } else {
        cleanupInternal = cleanupFn
      }
    })

    // Cleanup: stop video and audio streams when component unmounts
    return () => {
      isCancelled = true
      
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

  useEffect(() => {
    if (shouldSubmit) {
      setShouldSubmit(false)

      const runAutoSubmit = async () => {
        let dataUrl = ''
        
        // Auto-capture a fresh image right now!
        if (videoRef.current && canvasRef.current) {
          const video = videoRef.current
          const canvas = canvasRef.current
          const context = canvas.getContext('2d')

          if (context) {
            canvas.width = video.videoWidth
            canvas.height = video.videoHeight
            context.drawImage(video, 0, 0, canvas.width, canvas.height)
            dataUrl = canvas.toDataURL('image/png')
            
            // Show the user what we just automatically captured
            setCapturedImages((previousImages) => [
              ...previousImages,
              { id: Date.now().toString(), dataUrl },
            ])
          }
        }

        if (dataUrl) {
          console.log('📸 Auto-captured photo from webcam! Submitting to backend now...')
          await sendToBackend(dataUrl, true)
        }
      }

      void runAutoSubmit()
    }
  }, [shouldSubmit])

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

  const buildPendingImageDataUrls = (autoDataUrl?: string) => {
    const pendingImages = capturedImages.map((image) => image.dataUrl)
    if (autoDataUrl && pendingImages[pendingImages.length - 1] !== autoDataUrl) {
      pendingImages.push(autoDataUrl)
    }
    return pendingImages
  }

  const selectUserImagesForRequest = (allImageDataUrls: string[], rollingLoopContext: string) => {
    if (allImageDataUrls.length <= USER_IMAGE_FALLBACK_LIMIT) {
      return allImageDataUrls
    }

    const totalImageBytes = allImageDataUrls.reduce((totalBytes, imageDataUrl) => {
      return totalBytes + estimateDataUrlBytes(imageDataUrl)
    }, 0)

    const isNearContextLimit =
      allImageDataUrls.length > USER_IMAGE_CONTEXT_SOFT_COUNT_LIMIT ||
      totalImageBytes > USER_IMAGE_CONTEXT_SOFT_BYTES_LIMIT ||
      rollingLoopContext.length > TEXT_CONTEXT_SOFT_CHAR_LIMIT

    if (isNearContextLimit) {
      return allImageDataUrls.slice(-USER_IMAGE_FALLBACK_LIMIT)
    }

    return allImageDataUrls
  }

  const sendToBackend = async (autoDataUrl?: string, isLoopSubmission = false) => {
    const rollingLoopContext = isLoopSubmission ? buildRollingLoopContext() : ''
    const pendingImageDataUrls = buildPendingImageDataUrls(autoDataUrl)
    const selectedUserImages = selectUserImagesForRequest(pendingImageDataUrls, rollingLoopContext)

    if (selectedUserImages.length === 0) {
      alert('Please capture at least one image first')
      return
    }

    setIsSending(true)

    try {
      const formData = new FormData()

      // Schematic paths are always included and excluded from user image fallback logic.
      SCHEMATIC_IMAGE_PATHS.forEach((schematicPath) => {
        formData.append('image_paths', schematicPath)
      })

      for (const [index, imageDataUrl] of selectedUserImages.entries()) {
        const response = await fetch(imageDataUrl)
        const imageBlob = await response.blob()
        formData.append('files', imageBlob, `capture_${index + 1}.png`)
      }

      console.log('Sending images:', {
        selectedUserImageCount: selectedUserImages.length,
        availableUserImageCount: pendingImageDataUrls.length,
        fallbackLimit: USER_IMAGE_FALLBACK_LIMIT,
        schematicCount: SCHEMATIC_IMAGE_PATHS.length,
      })

      const hasAudioClip = audioChunksRef.current.length > 0 && recorderFormatRef.current

      if (!hasAudioClip) {
        formData.append('prompt', DEFAULT_ANALYZE_PROMPT)
      }

      if (isLoopSubmission) {
        if (rollingLoopContext) {
          formData.append('text_source_1', rollingLoopContext)
        }
      }

      // Append accumulated audio if available
      if (hasAudioClip && recorderFormatRef.current) {
        const audioBlob = new Blob(audioChunksRef.current, { type: recorderFormatRef.current.mimeType })
        formData.append('audio', audioBlob, `recording.${recorderFormatRef.current.extension}`)
        
        // Calculate approximate duration (assuming ~128kbps bitrate for webm/ogg)
        const approximateDurationSeconds = (audioBlob.size * 8) / (128 * 1024)
        
        console.log('=== AUDIO CLIP INFO ===')
        console.log('Full audio clip size:', audioBlob.size, 'bytes', `(${(audioBlob.size / 1024).toFixed(2)} KB)`)
        console.log('Audio format:', audioBlob.type)
        console.log('Number of chunks:', audioChunksRef.current.length)
        console.log('Approximate duration:', approximateDurationSeconds.toFixed(2), 'seconds')
        console.log('=======================')
      }
      
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

      const responseText = result?.text || 'No response'
      setAnalysisResult(responseText)

      const transcribedUserInput = (result?.user_input_text || '').trim()
      if (isLoopSubmission && transcribedUserInput) {
        const previousEntries = loopTranscriptsRef.current
        const latestEntry = previousEntries[previousEntries.length - 1]
        if (transcribedUserInput !== latestEntry) {
          loopTranscriptsRef.current = [
            ...previousEntries,
            transcribedUserInput,
          ].slice(-LOOP_TRANSCRIPT_HISTORY_LIMIT)
        }
        setTranscription(`Heard: ${transcribedUserInput}`)
      }

      // Stop any existing speech and read the new response aloud
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(responseText)
      window.speechSynthesis.speak(utterance)

      if (!isLoopSubmission) {
        setCapturedImages([])
      }
      audioChunksRef.current = [] // Reset accumulated audio
      if (!isLoopSubmission) {
        setTranscription('') // Clear transcription after successful send
      }
    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python backend/start_server.py)\n2. You have set GEMINI_API_KEY`)
    } finally {
      setIsSending(false)
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
        
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '15px' }}>
          <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', userSelect: 'none' }}>
            <input 
              type="checkbox" 
              checked={isListeningModeEnabled} 
              onChange={(e) => setIsListeningModeEnabled(e.target.checked)}
              style={{ width: '20px', height: '20px', marginRight: '10px', cursor: 'pointer' }}
            />
            <span style={{ fontSize: '1.2em', fontWeight: 'bold' }}>Hands-Free Assistant Mode</span>
          </label>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '10px', opacity: isListeningModeEnabled ? 1 : 0.5 }}>
          <div style={{
            width: '15px',
            height: '15px',
            borderRadius: '50%',
            backgroundColor: !isListeningModeEnabled ? '#95a5a6' : (isRecording ? '#e74c3c' : '#2ecc71'),
            marginRight: '10px',
            animation: isRecording ? 'pulse 1s infinite' : 'none'
          }} />
          <strong style={{ fontSize: '1.1em' }}>
            {!isListeningModeEnabled 
              ? "⏸️ Microphone Paused (Toggle mode on to speak)" 
              : (isRecording ? "🎤 Listening to your question..." : "🟢 Microphone Active (Waiting for voice...)")}
          </strong>
        </div>

        {transcription && (
          <div style={{ padding: '15px', backgroundColor: '#2c3e50', color: 'white', borderRadius: '5px', textAlign: 'left' }}>
            <strong>Audio Status:</strong> {transcription}
          </div>
        )}
      </div>

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
            onClick={() => {
              void sendToBackend()
            }}
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
