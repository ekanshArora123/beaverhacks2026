import { useEffect, useRef, useState } from 'react'
import './App.css'
import SessionPairingPanel, { type PairingState } from './SessionPairingPanel'
import { createSession, pollSessionPending, type PhonePayload } from './api/session'

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
  first_prompt_response_text?: string
}

interface RecorderFormat {
  mimeType: string
  extension: string
}

interface PhonePayloadInputs {
  imageDataUrls: string[]
  audioBlob: Blob | null
  audioMime: string | null
  audioExtension: string | null
  text: string | null
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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)
  const loopTranscriptsRef = useRef<string[]>([])
  const sendToBackendRef = useRef<(override?: PhonePayloadInputs) => Promise<void>>(async () => {})

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

  const [usePhoneInput, setUsePhoneInput] = useState(false)
  const [pairingState, setPairingState] = useState<PairingState>('idle')
  const [sessionCode, setSessionCode] = useState<string | null>(null)
  const [pairingError, setPairingError] = useState<string | null>(null)
  const [lastPayloadAt, setLastPayloadAt] = useState<number | null>(null)

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

  const togglePhoneInputMode = () => {
    setUsePhoneInput((previous) => !previous)
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

  const sendToBackend = async (phoneInputs?: PhonePayloadInputs) => {
    const isPhonePayload = !!phoneInputs
    const rollingLoopContext = buildRollingLoopContext()

    const allUserImageDataUrls = isPhonePayload
      ? phoneInputs!.imageDataUrls
      : buildPendingImageDataUrls()
    const selectedUserImages = isPhonePayload
      ? allUserImageDataUrls
      : selectUserImagesForRequest(allUserImageDataUrls, rollingLoopContext)

    const manualUserText = isPhonePayload
      ? (phoneInputs!.text || '').trim()
      : manualTextInput.trim()
    const hasManualText = isPhonePayload
      ? manualUserText.length > 0
      : useTextInput && manualUserText.length > 0

    const phoneAudioBlob = isPhonePayload ? phoneInputs!.audioBlob : null
    const hasPhoneAudio = isPhonePayload && !!phoneAudioBlob

    if (selectedUserImages.length === 0 && !hasManualText && !hasPhoneAudio) {
      if (!isPhonePayload) {
        alert('Please capture at least one image first')
      } else {
        console.warn('Phone payload arrived empty — skipping send')
      }
      return
    }

    if (!isPhonePayload && useTextInput && !hasManualText) {
      alert('Please enter text before sending, or switch back to audio mode.')
      return
    }

    if (!isPhonePayload && isRecording && mediaRecorderRef.current?.state === 'recording') {
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
        availableUserImageCount: allUserImageDataUrls.length,
        fallbackLimit: USER_IMAGE_FALLBACK_LIMIT,
        schematicCount: SCHEMATIC_IMAGE_PATHS.length,
        diagramSource,
        inputMode: isPhonePayload ? 'phone' : (useTextInput ? 'text' : 'audio'),
      })

      formData.append('diagram_source', diagramSource)

      let audioBlob: Blob | null = null
      let audioExtension = 'webm'
      if (isPhonePayload) {
        audioBlob = phoneAudioBlob
        audioExtension = phoneInputs!.audioExtension || 'webm'
      } else {
        const hasLocalAudio = audioChunksRef.current.length > 0 && recorderFormatRef.current
        if (!hasManualText && hasLocalAudio && recorderFormatRef.current) {
          audioBlob = new Blob(audioChunksRef.current, { type: recorderFormatRef.current.mimeType })
          audioExtension = recorderFormatRef.current.extension
        }
      }

      const wantsAudio = !hasManualText && !!audioBlob

      if (!wantsAudio && !hasManualText) {
        formData.append('prompt', DEFAULT_ANALYZE_PROMPT)
      }

      if (hasManualText) {
        formData.append('text_source_2', manualUserText)
      }

      if (rollingLoopContext) {
        formData.append('text_source_1', rollingLoopContext)
      }

      if (wantsAudio && audioBlob) {
        formData.append('audio', audioBlob, `recording.${audioExtension}`)

        const approximateDurationSeconds = (audioBlob.size * 8) / (128 * 1024)

        console.log('=== AUDIO CLIP INFO ===')
        console.log('Source:', isPhonePayload ? 'phone' : 'laptop')
        console.log('Full audio clip size:', audioBlob.size, 'bytes', `(${(audioBlob.size / 1024).toFixed(2)} KB)`)
        console.log('Audio format:', audioBlob.type)
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

      if (!isPhonePayload) {
        setCapturedImages([])
        audioChunksRef.current = []
        setHasAudioRecording(false)
        if (useTextInput) {
          setManualTextInput('')
        }
      }
    } catch (error) {
      console.error('Error sending to backend:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      if (!isPhonePayload) {
        alert(`Error: ${errorMessage}\n\nMake sure:\n1. Flask server is running (python backend/start_server.py)\n2. You have set GEMINI_API_KEY`)
      }
    } finally {
      setIsSending(false)
    }
  }

  // Keep ref to latest sendToBackend so the phone-mode poll loop can call it without re-subscribing.
  useEffect(() => {
    sendToBackendRef.current = sendToBackend
  })

  // Phone-mode lifecycle: create session, long-poll for phone payloads, dispatch them.
  useEffect(() => {
    if (!usePhoneInput) {
      setPairingState('idle')
      setSessionCode(null)
      setPairingError(null)
      setLastPayloadAt(null)
      return
    }

    let cancelled = false
    const abortController = new AbortController()

    const handlePhonePayload = async (payload: PhonePayload) => {
      setLastPayloadAt(Date.now())
      setPairingState('connected')

      let audioBlob: Blob | null = null
      if (payload.audio_data_url) {
        try {
          const audioResponse = await fetch(payload.audio_data_url)
          audioBlob = await audioResponse.blob()
        } catch (error) {
          console.error('Failed to decode phone audio:', error)
        }
      }

      const phoneInputs: PhonePayloadInputs = {
        imageDataUrls: payload.image_data_urls,
        audioBlob,
        audioMime: payload.audio_mime,
        audioExtension: payload.audio_extension,
        text: payload.text_source_2,
      }

      try {
        await sendToBackendRef.current(phoneInputs)
      } catch (error) {
        console.error('Phone payload send failed:', error)
      }
    }

    const start = async () => {
      setPairingState('creating')
      setPairingError(null)
      try {
        const code = await createSession()
        if (cancelled) return
        setSessionCode(code)
        setPairingState('waiting')

        while (!cancelled) {
          try {
            const payload = await pollSessionPending(code, abortController.signal, 25)
            if (cancelled) break
            if (payload) {
              await handlePhonePayload(payload)
            }
          } catch (error) {
            if (cancelled) break
            if ((error as DOMException).name === 'AbortError') break
            console.error('Phone poll error:', error)
            await new Promise((resolve) => setTimeout(resolve, 1500))
          }
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to create session:', error)
          setPairingError(error instanceof Error ? error.message : 'Unknown error')
          setPairingState('error')
        }
      }
    }

    void start()

    return () => {
      cancelled = true
      abortController.abort()
    }
  }, [usePhoneInput])

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

        {/* Right column: Webcam (or phone pairing panel when phone mode is active) */}
        <div className="webcam-column">
          <div className="input-mode-bar">
            <button
              className={`input-mode-button ${usePhoneInput ? 'input-mode-active' : ''}`}
              onClick={togglePhoneInputMode}
              title={usePhoneInput ? 'Stop using phone as input' : 'Use Android phone as input device'}
            >
              {usePhoneInput ? '📱 Phone On' : '📱 Use Phone'}
            </button>
          </div>

          {usePhoneInput ? (
            <SessionPairingPanel
              state={pairingState}
              code={sessionCode}
              errorMessage={pairingError}
              lastPayloadAt={lastPayloadAt}
            />
          ) : (
            <>
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
            </>
          )}
        </div>
      </div>

      {/* Thumbnail preview section (laptop capture mode only) */}
      {!usePhoneInput && capturedImages.length > 0 && (
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

      {usePhoneInput && isSending && (
        <div className="phone-sending-banner">Processing phone input...</div>
      )}

      {/* Hidden canvas for image capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  )
}

export default App
