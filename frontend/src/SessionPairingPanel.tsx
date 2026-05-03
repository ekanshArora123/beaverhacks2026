import { useEffect, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import { fetchHostInfo } from './api/session'

export type PairingState = 'idle' | 'creating' | 'waiting' | 'connected' | 'error'

interface SessionPairingPanelProps {
  state: PairingState
  code: string | null
  errorMessage: string | null
  lastPayloadAt: number | null
}

function isLocalhostHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
}

interface ResolvedPhoneOrigin {
  origin: string
  warning: string | null
  suggestedAddresses: string[]
}

function buildOriginFromHostname(hostname: string): string {
  const { protocol, port } = window.location
  const portSuffix = port ? `:${port}` : ''
  return `${protocol}//${hostname}${portSuffix}`
}

function SessionPairingPanel({ state, code, errorMessage, lastPayloadAt }: SessionPairingPanelProps) {
  const [resolvedOrigin, setResolvedOrigin] = useState<ResolvedPhoneOrigin>(() => {
    if (typeof window === 'undefined') {
      return { origin: '', warning: null, suggestedAddresses: [] }
    }
    return { origin: window.location.origin, warning: null, suggestedAddresses: [] }
  })

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    const currentHostname = window.location.hostname
    if (!isLocalhostHostname(currentHostname)) {
      setResolvedOrigin({ origin: window.location.origin, warning: null, suggestedAddresses: [] })
      return
    }

    let cancelled = false
    const resolve = async () => {
      try {
        const info = await fetchHostInfo()
        if (cancelled) return

        const lanAddresses = info.lan_addresses || []
        if (lanAddresses.length > 0) {
          setResolvedOrigin({
            origin: buildOriginFromHostname(lanAddresses[0]),
            warning: 'Laptop opened the app at localhost — QR rewritten to your LAN IP. If the phone still cannot connect, open the laptop browser at that LAN URL too so the dev server stays consistent.',
            suggestedAddresses: lanAddresses,
          })
        } else {
          setResolvedOrigin({
            origin: window.location.origin,
            warning: 'Could not detect a LAN IP and the laptop is on localhost. The phone will not be able to reach this URL. Run the dev server with `npm run dev -- --host`, then open the laptop page at the LAN URL Vite prints, or expose the app via ngrok.',
            suggestedAddresses: [],
          })
        }
      } catch {
        if (cancelled) return
        setResolvedOrigin({
          origin: window.location.origin,
          warning: 'Could not reach /host-info on the backend. The phone likely cannot resolve a localhost URL — start the laptop browser at your LAN IP instead.',
          suggestedAddresses: [],
        })
      }
    }

    void resolve()
    return () => {
      cancelled = true
    }
  }, [])

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

  const mobileUrl = `${resolvedOrigin.origin}/mobile?code=${encodeURIComponent(code)}`

  return (
    <div className="pairing-panel">
      <div className="pairing-header">
        <span className="pairing-label">Phone session</span>
        <span className="pairing-code">{code}</span>
      </div>

      <div className="pairing-qr-wrap">
        <QRCodeCanvas value={mobileUrl} size={180} marginSize={2} level="M" />
      </div>

      <p className="pairing-url">{mobileUrl}</p>

      <div className={`pairing-status pairing-status-${state}`}>
        {state === 'connected'
          ? `Connected — last input ${lastPayloadAt ? `${Math.max(0, Math.round((Date.now() - lastPayloadAt) / 1000))}s ago` : 'received'}`
          : 'Waiting for phone to send input...'}
      </div>

      {resolvedOrigin.warning && (
        <div className="pairing-warning">
          <strong>Heads up:</strong> {resolvedOrigin.warning}
          {resolvedOrigin.suggestedAddresses.length > 1 && (
            <div className="pairing-warning-extras">
              Other LAN addresses detected: {resolvedOrigin.suggestedAddresses.slice(1).join(', ')}
            </div>
          )}
        </div>
      )}

      <p className="pairing-hint">
        Scan the QR with your phone, or open the URL above. Same Wi-Fi network required (or use ngrok).
        Camera/mic on Android Chrome needs HTTPS unless you're on localhost.
      </p>
    </div>
  )
}

export default SessionPairingPanel
