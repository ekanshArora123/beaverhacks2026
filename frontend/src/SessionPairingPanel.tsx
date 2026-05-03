import { QRCodeCanvas } from 'qrcode.react'

export type PairingState = 'idle' | 'creating' | 'waiting' | 'connected' | 'error'

interface SessionPairingPanelProps {
  state: PairingState
  code: string | null
  errorMessage: string | null
  lastPayloadAt: number | null
}

function buildMobileUrl(code: string): string {
  const origin = window.location.origin
  return `${origin}/mobile?code=${encodeURIComponent(code)}`
}

function SessionPairingPanel({ state, code, errorMessage, lastPayloadAt }: SessionPairingPanelProps) {
  if (state === 'idle') {
    return null
  }

  if (state === 'creating') {
    return (
      <div className="pairing-panel">
        <div className="pairing-status pairing-status-waiting">Creating session...</div>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="pairing-panel">
        <div className="pairing-status pairing-status-error">
          {errorMessage || 'Failed to create session'}
        </div>
      </div>
    )
  }

  if (!code) {
    return null
  }

  const mobileUrl = buildMobileUrl(code)

  return (
    <div className="pairing-panel">
      <div className="pairing-header">
        <span className="pairing-label">Phone session</span>
        <span className="pairing-code">{code}</span>
      </div>

      <div className="pairing-qr-wrap">
        <QRCodeCanvas value={mobileUrl} size={180} includeMargin={true} level="M" />
      </div>

      <p className="pairing-url">{mobileUrl}</p>

      <div className={`pairing-status pairing-status-${state}`}>
        {state === 'connected'
          ? `Connected — last input ${lastPayloadAt ? `${Math.max(0, Math.round((Date.now() - lastPayloadAt) / 1000))}s ago` : 'received'}`
          : 'Waiting for phone to send input...'}
      </div>

      <p className="pairing-hint">
        Scan the QR with your phone, or open the URL above. Same Wi-Fi network required (or use ngrok).
        Camera/mic on Android Chrome needs HTTPS unless you're on localhost.
      </p>
    </div>
  )
}

export default SessionPairingPanel
