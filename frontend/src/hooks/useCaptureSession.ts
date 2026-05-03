import { useCallback, useEffect, useRef, useState } from 'react'
import { describeMobileCameraMicFailure } from '../utils/mediaDeviceErrors'

export interface CapturedImage {
  id: string
  dataUrl: string
}

export interface RecorderFormat {
  mimeType: string
  extension: string
}

const RECORDER_FORMAT_CANDIDATES: RecorderFormat[] = [
  { mimeType: 'audio/ogg;codecs=opus', extension: 'ogg' },
  { mimeType: 'audio/ogg', extension: 'ogg' },
  { mimeType: 'audio/mp4', extension: 'm4a' },
  { mimeType: 'audio/aac', extension: 'aac' },
  { mimeType: 'audio/webm;codecs=opus', extension: 'webm' },
  { mimeType: 'audio/webm', extension: 'webm' },
]

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

function extensionFromMime(mime: string): string {
  const m = mime.toLowerCase()
  if (m.includes('ogg')) return 'ogg'
  if (m.includes('mpeg') || m.includes('mp3')) return 'mp3'
  if (m.includes('mp4') || m.includes('aac') || m.includes('m4a')) return 'm4a'
  return 'webm'
}

/** Try several constraints: combined audio+mic breaks on some phones; insecure HTTPS can block mic alone. */
async function negotiateCaptureStream(params: {
  facingMode: 'user' | 'environment'
}): Promise<{ stream: MediaStream }> {
  const { facingMode } = params
  const rear = facingMode === 'environment'

  type Attempt = { description: string; constraints: MediaStreamConstraints }

  const attempts: Attempt[] = [
    {
      description: 'rear + mic',
      constraints: rear
        ? { video: { facingMode: { ideal: 'environment' } }, audio: true }
        : { video: true, audio: true },
    },
    {
      description: 'any camera + mic',
      constraints: { video: true, audio: true },
    },
    {
      description: 'rear video only',
      constraints: rear
        ? { video: { facingMode: { ideal: 'environment' } }, audio: false }
        : { video: true, audio: false },
    },
    {
      description: 'any video only',
      constraints: { video: true, audio: false },
    },
  ]

  let lastError: unknown
  const md = navigator.mediaDevices
  if (!md?.getUserMedia) {
    throw new Error('getUserMedia is not supported on this page')
  }

  for (const attempt of attempts) {
    try {
      const stream = await md.getUserMedia(attempt.constraints)
      return { stream }
    } catch (error) {
      lastError = error
      console.warn(`useCaptureSession: attempt "${attempt.description}" failed`, error)
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError))
}

export interface UseCaptureSessionOptions {
  facingMode?: 'user' | 'environment'
  enabled?: boolean
}

export interface UseCaptureSessionResult {
  videoRef: React.RefObject<HTMLVideoElement | null>
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  webcamError: string | null
  insecureContextWarning: boolean
  isMediaReady: boolean
  microphoneAvailable: boolean
  micOnlyBlockedHint: boolean
  isRequestingMedia: boolean
  requestMedia: () => Promise<void>
  capturedImages: CapturedImage[]
  setCapturedImages: React.Dispatch<React.SetStateAction<CapturedImage[]>>
  isRecording: boolean
  hasAudioRecording: boolean
  recorderFormat: RecorderFormat | null
  captureImage: () => void
  removeCapturedImage: (id: string) => void
  toggleRecording: () => void
  discardAudio: () => void
  getAudioBlob: () => Blob | null
  resetAudio: () => void
}

export function useCaptureSession(options: UseCaptureSessionOptions = {}): UseCaptureSessionResult {
  const { facingMode = 'user', enabled = true } = options

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const activeStreamRef = useRef<MediaStream | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)

  const insecureContextWarning =
    typeof window !== 'undefined' && !!window.location?.hostname && !window.isSecureContext

  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [isMediaReady, setIsMediaReady] = useState(false)
  const [microphoneAvailable, setMicrophoneAvailable] = useState(false)
  const [micOnlyBlockedHint, setMicOnlyBlockedHint] = useState(false)
  const [isRequestingMedia, setIsRequestingMedia] = useState(false)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [isRecording, setIsRecording] = useState(false)
  const [hasAudioRecording, setHasAudioRecording] = useState(false)
  const [recorderFormat, setRecorderFormat] = useState<RecorderFormat | null>(null)

  const releaseMediaResources = useCallback(() => {
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject = null
    }
    if (activeStreamRef.current) {
      activeStreamRef.current.getTracks().forEach((track) => track.stop())
      activeStreamRef.current = null
    }
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
    mediaRecorderRef.current = null
    recorderFormatRef.current = null
    setRecorderFormat(null)
    setIsMediaReady(false)
    setMicrophoneAvailable(false)
    setMicOnlyBlockedHint(false)
    setIsRecording(false)
    setHasAudioRecording(false)
    audioChunksRef.current = []
  }, [])

  const attachStreamToVideo = useCallback((stream: MediaStream) => {
    const video = videoRef.current
    if (!video) {
      return
    }
    video.srcObject = stream
    video.muted = true
    // Some Android builds need an explicit play() after setting srcObject.
    void video.play().catch(() => {
      // Ignore autoplay race; user gesture already happened in requestMedia().
    })
  }, [])

  useEffect(() => {
    if (!isMediaReady || !activeStreamRef.current) {
      return
    }
    attachStreamToVideo(activeStreamRef.current)
  }, [attachStreamToVideo, isMediaReady])

  useEffect(() => {
    if (!enabled) {
      releaseMediaResources()
      setWebcamError(null)
    }
  }, [enabled, releaseMediaResources])

  useEffect(() => () => releaseMediaResources(), [releaseMediaResources])

  const attachRecorderForStream = useCallback((stream: MediaStream) => {
    const audioTracks = stream.getAudioTracks()
    if (audioTracks.length === 0) {
      mediaRecorderRef.current = null
      recorderFormatRef.current = null
      setRecorderFormat(null)
      setMicrophoneAvailable(false)
      return
    }

    setMicrophoneAvailable(true)

    let chosenFormat = resolveRecorderFormat()
    recorderFormatRef.current = chosenFormat

    const audioStream = new MediaStream(audioTracks)
    let mediaRecorder: MediaRecorder
    try {
      mediaRecorder = new MediaRecorder(audioStream, { mimeType: chosenFormat.mimeType })
    } catch {
      mediaRecorder = new MediaRecorder(audioStream)
      const browserMime = mediaRecorder.mimeType || chosenFormat.mimeType
      const inferred = RECORDER_FORMAT_CANDIDATES.find((candidate) => candidate.mimeType === browserMime)
      chosenFormat = inferred ?? {
        mimeType: browserMime || 'audio/webm',
        extension: extensionFromMime(browserMime || ''),
      }
      recorderFormatRef.current = chosenFormat
    }
    mediaRecorderRef.current = mediaRecorder
    setRecorderFormat(chosenFormat)

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
  }, [])

  const requestMedia = useCallback(async () => {
    if (!enabled) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setWebcamError('Browser does not support camera/microphone access on this page.')
      return
    }

    releaseMediaResources()
    setWebcamError(null)
    setMicOnlyBlockedHint(false)
    setIsRequestingMedia(true)

    try {
      if (typeof window !== 'undefined' && !window.isSecureContext) {
        setWebcamError(
          [
            'This page is not a secure HTTPS context — Chrome blocks camera on mobile HTTP.',
            'Run npm run dev:https (or start-dev.ps1 -DevHttps), accept any certificate warnings, reopen this URL, then tap the button again.',
            'Or expose port 5173 with ngrok / Cloudflare Tunnel and use their https link.',
          ].join('\n'),
        )
        setIsMediaReady(false)
        return
      }

      const { stream } = await negotiateCaptureStream({ facingMode })
      activeStreamRef.current = stream
      attachStreamToVideo(stream)

      const hasMic = stream.getAudioTracks().length > 0
      setMicOnlyBlockedHint(stream.getVideoTracks().length > 0 && !hasMic)
      attachRecorderForStream(stream)
      setIsMediaReady(true)
    } catch (error) {
      console.error('Error accessing webcam/microphone:', error)
      setWebcamError(describeMobileCameraMicFailure(error))
      setIsMediaReady(false)
      setMicOnlyBlockedHint(false)
    } finally {
      setIsRequestingMedia(false)
    }
  }, [attachRecorderForStream, attachStreamToVideo, enabled, facingMode, releaseMediaResources])

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

    setCapturedImages((previous) => [...previous, { id: Date.now().toString(), dataUrl }])
  }

  const removeCapturedImage = (id: string) => {
    setCapturedImages((previous) => previous.filter((image) => image.id !== id))
  }

  const toggleRecording = () => {
    const recorder = mediaRecorderRef.current
    if (!recorder) return

    if (isRecording) {
      if (recorder.state === 'recording') {
        recorder.stop()
      }
      setIsRecording(false)
    } else {
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

  const getAudioBlob = () => {
    const format = recorderFormatRef.current
    if (!format || audioChunksRef.current.length === 0) {
      return null
    }
    return new Blob(audioChunksRef.current, { type: format.mimeType })
  }

  const resetAudio = () => {
    audioChunksRef.current = []
    setHasAudioRecording(false)
  }

  return {
    videoRef,
    canvasRef,
    webcamError,
    insecureContextWarning,
    isMediaReady,
    microphoneAvailable,
    micOnlyBlockedHint,
    isRequestingMedia,
    requestMedia,
    capturedImages,
    setCapturedImages,
    isRecording,
    hasAudioRecording,
    recorderFormat,
    captureImage,
    removeCapturedImage,
    toggleRecording,
    discardAudio,
    getAudioBlob,
    resetAudio,
  }
}
