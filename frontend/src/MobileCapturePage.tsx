import { useEffect, useState } from 'react'
import { postSessionInput } from './api/session'
import { useCaptureSession } from './hooks/useCaptureSession'
import './MobileCapturePage.css'

type SendStatus = 'idle' | 'sending' | 'success' | 'error'

function extensionForPhoneAudio(blob: Blob, recorderExtension: string | undefined): string {
  if (recorderExtension) {
    return recorderExtension
  }
  const mime = (blob.type || '').toLowerCase()
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mpeg') || mime.includes('mp3')) return 'mp3'
  if (mime.includes('mp4') || mime.includes('aac') || mime.includes('m4a')) return 'm4a'
  return 'webm'
}

function readCodeFromQuery(): string {
  const params = new URLSearchParams(window.location.search)
  return (params.get('code') || '').trim().toUpperCase()
}

function MobileCapturePage() {
  const [code, setCode] = useState<string>(readCodeFromQuery())
  const [codeInput, setCodeInput] = useState<string>('')
  const [sendStatus, setSendStatus] = useState<SendStatus>('idle')
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [textInput, setTextInput] = useState<string>('')

  const capture = useCaptureSession({
    facingMode: 'environment',
    enabled: code.length > 0,
  })

  useEffect(() => {
    if (code) {
      const newUrl = `${window.location.pathname}?code=${encodeURIComponent(code)}`
      window.history.replaceState(null, '', newUrl)
    }
  }, [code])

  const handleConnect = (event: React.FormEvent) => {
    event.preventDefault()
    const normalized = codeInput.trim().toUpperCase()
    if (normalized) {
      setCode(normalized)
    }
  }

  const handleSend = async () => {
    if (!code) return

    if (capture.isRecording) {
      capture.toggleRecording()
      await new Promise((resolve) => setTimeout(resolve, 200))
    }

    const trimmedText = textInput.trim()
    const audioBlob = capture.getAudioBlob()

    if (capture.capturedImages.length === 0 && !audioBlob && !trimmedText) {
      setSendStatus('error')
      setStatusMessage('Capture at least one photo, record audio, or type a message before sending.')
      return
    }

    setSendStatus('sending')
    setStatusMessage('Sending to laptop...')

    try {
      const formData = new FormData()

      for (const [index, image] of capture.capturedImages.entries()) {
        const response = await fetch(image.dataUrl)
        const imageBlob = await response.blob()
        formData.append('files', imageBlob, `phone_capture_${index + 1}.png`)
      }

      if (audioBlob) {
        const ext = extensionForPhoneAudio(audioBlob, capture.recorderFormat?.extension)
        formData.append('audio', audioBlob, `phone_recording.${ext}`)
      }

      if (trimmedText) {
        formData.append('text_source_2', trimmedText)
      }

      const result = await postSessionInput(code, formData)

      setSendStatus('success')
      setStatusMessage(
        `Sent: ${result.image_count} image${result.image_count === 1 ? '' : 's'}` +
        `${result.has_audio ? ' + audio' : ''}${result.has_text ? ' + text' : ''}`,
      )
      capture.setCapturedImages([])
      capture.resetAudio()
      setTextInput('')
    } catch (error) {
      console.error('Send failed:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error'
      setSendStatus('error')
      setStatusMessage(`Send failed: ${errorMessage}`)
    }
  }

  const mediaBlocked = !!capture.webcamError
  const controlsDisabled = !capture.isMediaReady || mediaBlocked
  const micDisabled = controlsDisabled || !capture.microphoneAvailable

  if (!code) {
    return (
      <div className="mobile-app">
        <div className="mobile-pair-card">
          <h1>Pair with laptop</h1>
          <p>Open the laptop app, enable Phone Mode, and scan the QR code with your camera. If you typed the URL manually, enter the session code below.</p>
          <form onSubmit={handleConnect} className="mobile-pair-form">
            <input
              type="text"
              value={codeInput}
              onChange={(event) => setCodeInput(event.target.value)}
              placeholder="ABC123"
              maxLength={8}
              className="mobile-code-input"
              autoCapitalize="characters"
              autoCorrect="off"
            />
            <button type="submit" className="mobile-primary-button">Connect</button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="mobile-app">
      <header className="mobile-header">
        <span className="mobile-session-label">Session</span>
        <span className="mobile-session-code">{code}</span>
      </header>

      {capture.insecureContextWarning && (
        <p className="mobile-insecure-banner">
          Camera is blocked on insecure HTTP. Use <strong>npm run dev:https</strong> or an ngrok HTTPS URL, then reopen this page.
        </p>
      )}

      <div className="mobile-video-wrap">
        {mediaBlocked ? (
          <div className="mobile-error-panel">
            <div className="mobile-error">{capture.webcamError}</div>
            <button
              type="button"
              className="mobile-retry-media"
              disabled={capture.isRequestingMedia}
              onClick={() => void capture.requestMedia()}
            >
              {capture.isRequestingMedia ? 'Trying…' : 'Retry camera & mic'}
            </button>
          </div>
        ) : !capture.isMediaReady ? (
          <div className="mobile-media-primer">
            <p className="mobile-media-primer-text">
              Chrome on Android usually requires you to tap a button before it will ask for camera and microphone access
              — automatic requests when the page opens are blocked.
            </p>
            <button
              type="button"
              className="mobile-primary-button mobile-media-open"
              disabled={capture.isRequestingMedia}
              onClick={() => void capture.requestMedia()}
            >
              {capture.isRequestingMedia ? 'Opening camera…' : 'Turn on camera & microphone'}
            </button>
          </div>
        ) : (
          <video
            ref={capture.videoRef}
            autoPlay
            playsInline
            muted
            className="mobile-video"
          />
        )}
        {capture.isRecording && <div className="mobile-recording-overlay" />}
      </div>

      {capture.isMediaReady && capture.micOnlyBlockedHint && (
        <p className="mobile-mic-hint">
          Microphone not available (often with dev HTTPS on Android). Camera and photos still work; use text for notes, or try an ngrok HTTPS link for full audio.
        </p>
      )}

      <div className="mobile-controls">
        <button
          className="mobile-shutter"
          onClick={capture.captureImage}
          disabled={controlsDisabled}
          type="button"
        >
          <span className="mobile-control-label">Photo</span>
        </button>
        <button
          className={`mobile-mic ${capture.isRecording ? 'mobile-mic-recording' : ''} ${capture.hasAudioRecording ? 'mobile-mic-ready' : ''} ${micDisabled && capture.isMediaReady ? 'mobile-mic-disabled' : ''}`}
          onClick={capture.toggleRecording}
          disabled={micDisabled}
          title={!capture.microphoneAvailable && capture.isMediaReady ? 'Microphone not granted on this connection' : undefined}
          type="button"
        >
          <span className="mobile-control-label">{capture.isRecording ? 'Stop' : 'Audio'}</span>
        </button>
        <button
          className="mobile-send mobile-send-island"
          onClick={() => void handleSend()}
          disabled={sendStatus === 'sending'}
          type="button"
        >
          <span className="mobile-control-label">{sendStatus === 'sending' ? 'Sending...' : 'Send'}</span>
        </button>
      </div>

      <div className="mobile-thumb-strip">
        {capture.capturedImages.length === 0 ? (
          <span className="mobile-thumb-empty">No photos yet</span>
        ) : (
          capture.capturedImages.map((image) => (
            <div key={image.id} className="mobile-thumb">
              <img src={image.dataUrl} alt="Captured" />
              <button
                className="mobile-thumb-remove"
                onClick={() => capture.removeCapturedImage(image.id)}
                aria-label="Remove photo"
              >Remove</button>
            </div>
          ))
        )}
      </div>

      <textarea
        className="mobile-text-input"
        value={textInput}
        onChange={(event) => setTextInput(event.target.value)}
        placeholder="Type a message..."
        rows={3}
      />

      {capture.hasAudioRecording && !capture.isRecording && (
        <div className="mobile-audio-ready">
          <span>🎙 Audio captured</span>
          <button type="button" onClick={capture.discardAudio} aria-label="Discard audio">Discard</button>
        </div>
      )}

      {statusMessage && (
        <div className={`mobile-status mobile-status-${sendStatus}`}>{statusMessage}</div>
      )}

      <canvas ref={capture.canvasRef} style={{ display: 'none' }} />
    </div>
  )
}

export default MobileCapturePage
