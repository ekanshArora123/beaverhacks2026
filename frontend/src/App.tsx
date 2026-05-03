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
  audio_base64?: string
  audio_mime_type?: string
  user_input_text?: string
  model?: string
  error?: string
}

interface RecorderFormat {
  mimeType: string
  extension: string
}

type DiagramSource = 'user' | 'schematic'

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
const DEFAULT_SCHEMATIC_IMAGE_PATH = ''
const configuredSchematicPaths = ((import.meta.env.VITE_SCHEMATIC_IMAGE_PATHS as string | undefined) || '')
  .split(',')
  .map((path) => path.trim())
  .filter(Boolean)
const SCHEMATIC_IMAGE_PATHS = configuredSchematicPaths.length > 0
  ? configuredSchematicPaths
  : DEFAULT_SCHEMATIC_IMAGE_PATH === '' ? [] : [DEFAULT_SCHEMATIC_IMAGE_PATH]

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
  const audioRef = useRef<HTMLAudioElement | null>(null)
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
  const [useTextInput, setUseTextInput] = useState(false)
  const [manualTextInput, setManualTextInput] = useState('')
  const [diagramSource, setDiagramSource] = useState<DiagramSource>('user')

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

  const toggleTextInputMode = () => {
    const nextUseTextInput = !useTextInput
    setUseTextInput(nextUseTextInput)

    if (nextUseTextInput) {
      if (isRecording && mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop()
      }
      setIsRecording(false)
      audioChunksRef.current = []
      setHasAudioRecording(false)
    }
  }

  const hasSchematicSources = SCHEMATIC_IMAGE_PATHS.length > 0

  const toggleDiagramSource = () => {
    if (!hasSchematicSources) {
      return
    }

    setDiagramSource((previousSource) => previousSource === 'user' ? 'schematic' : 'user')
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

  const buildPendingImageDataUrls = () => {
    return capturedImages.map((image) => image.dataUrl)
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

  const sendToBackend = async () => {
    const rollingLoopContext = buildRollingLoopContext()
    const pendingImageDataUrls = buildPendingImageDataUrls()
    const selectedUserImages = selectUserImagesForRequest(pendingImageDataUrls, rollingLoopContext)
    const manualUserText = manualTextInput.trim()
    const hasManualText = useTextInput && manualUserText.length > 0


    if (selectedUserImages.length === 0) {
      alert('Please capture at least one image first')
      return
    }

    if (useTextInput && !hasManualText) {
      alert('Please enter text before sending, or switch back to audio mode.')
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
      const formData = new FormData()

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
        diagramSource,
        inputMode: useTextInput ? 'text' : 'audio',

      })

      formData.append('diagram_source', diagramSource)

      const hasAudioClip = audioChunksRef.current.length > 0 && recorderFormatRef.current

      if (!hasAudioClip && !hasManualText) {
        formData.append('prompt', DEFAULT_ANALYZE_PROMPT)
      }

      if (hasManualText) {
        formData.append('text_source_2', manualUserText)
      }

      const rollingLoopContext = buildRollingLoopContext()
      if (rollingLoopContext) {
        formData.append('text_source_1', rollingLoopContext)
      }

      // Append accumulated audio if available
      if (!hasManualText && hasAudioClip && recorderFormatRef.current) {
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

      // Play returned TTS audio if available, otherwise fall back to browser speech synthesis
      window.speechSynthesis.cancel()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
      if (result?.audio_base64) {
        const audioSrc = `data:${result.audio_mime_type || 'audio/wav'};base64,${result.audio_base64}`
        const audio = new Audio(audioSrc)
        audioRef.current = audio
        void audio.play()
      } else {
        const utterance = new SpeechSynthesisUtterance(responseText)
        window.speechSynthesis.speak(utterance)
      }

      setCapturedImages([])
      audioChunksRef.current = []
      setHasAudioRecording(false)
      if (useTextInput) {
        setManualTextInput('')
      }
    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python backend/start_server.py)\n2. You have set GEMINI_API_KEY`)
    } finally {
      setIsSending(false)
    }
  }

  const hasManualText = manualTextInput.trim().length > 0
  const isSendDisabled = isSending || (useTextInput && !hasManualText)

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
                    title={useTextInput ? 'Text mode is active' : (isRecording ? 'Stop Recording' : 'Start Recording')}
                    disabled={useTextInput}
                  >
                    {isRecording ? '⏹ Stop' : '🎤 Record'}
                  </button>
                  <button
                    className={`input-mode-button ${useTextInput ? 'input-mode-active' : ''}`}
                    onClick={toggleTextInputMode}
                    title={useTextInput ? 'Use audio instead' : 'Use text instead of audio'}
                  >
                    {useTextInput ? '⌨ Text On' : '⌨ Use Text'}
                  </button>
                  <button
                    className={`diagram-source-button ${diagramSource === 'user' ? 'diagram-source-user' : 'diagram-source-schematic'}`}
                    onClick={toggleDiagramSource}
                    title={hasSchematicSources
                      ? 'Switch edited-image source (user photo vs schematic)'
                      : 'No schematic source configured. Set VITE_SCHEMATIC_IMAGE_PATHS to enable switching.'}
                    disabled={!hasSchematicSources}
                  >
                    {diagramSource === 'user' ? '🖼 Edit: User' : '📐 Edit: Schematic'}
                  </button>
                </div>
              </>
            )}
          </div>
          <p className="diagram-source-hint">
            Edited image source: <strong>{diagramSource === 'user' ? 'User photo' : 'Schematic image'}</strong>
          </p>
          {useTextInput && (
            <div className="text-input-panel">
              <label htmlFor="manual-input" className="text-input-label">Technician text input</label>
              <textarea
                id="manual-input"
                className="manual-input"
                value={manualTextInput}
                onChange={(event) => setManualTextInput(event.target.value)}
                placeholder="Type what the technician would normally say out loud..."
                rows={3}
              />
              <p className="text-input-hint">Text mode sends this message instead of recorded audio.</p>
            </div>
          )}
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
            disabled={isSendDisabled}
          >
            {isSending
              ? 'Sending...'
              : `Send ${capturedImages.length} image${capturedImages.length > 1 ? 's' : ''}${useTextInput ? (hasManualText ? ' + text' : '') : (hasAudioRecording ? ' + audio' : '')}`}
          </button>
        </div>
      )}

      {/* Hidden canvas for image capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  )
}

export default App
