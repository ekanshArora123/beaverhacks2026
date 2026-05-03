import { useEffect, useRef, useState } from 'react'

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

export interface UseCaptureSessionOptions {
  facingMode?: 'user' | 'environment'
  enabled?: boolean
}

export interface UseCaptureSessionResult {
  videoRef: React.RefObject<HTMLVideoElement | null>
  canvasRef: React.RefObject<HTMLCanvasElement | null>
  webcamError: string | null
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
  const audioChunksRef = useRef<Blob[]>([])
  const recorderFormatRef = useRef<RecorderFormat | null>(null)

  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([])
  const [isRecording, setIsRecording] = useState(false)
  const [hasAudioRecording, setHasAudioRecording] = useState(false)
  const [recorderFormat, setRecorderFormat] = useState<RecorderFormat | null>(null)

  useEffect(() => {
    if (!enabled) {
      setRecorderFormat(null)
      recorderFormatRef.current = null
      return
    }

    let activeStream: MediaStream | null = null

    const enableMediaCapture = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: facingMode === 'user' ? true : { facingMode: { ideal: 'environment' } },
          audio: true,
        })
        activeStream = stream

        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.muted = true
        }

        let chosenFormat = resolveRecorderFormat()
        recorderFormatRef.current = chosenFormat

        const audioStream = new MediaStream(stream.getAudioTracks())
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
      } catch (error) {
        console.error('Error accessing webcam/microphone:', error)
        setWebcamError('Unable to access webcam/microphone. Please grant permissions.')
      }
    }

    void enableMediaCapture()

    return () => {
      if (activeStream) {
        activeStream.getTracks().forEach((track) => track.stop())
      }
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream
        stream.getTracks().forEach((track) => track.stop())
        videoRef.current.srcObject = null
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
      mediaRecorderRef.current = null
      recorderFormatRef.current = null
      setRecorderFormat(null)
    }
  }, [enabled, facingMode])

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
