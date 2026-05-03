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
  const laptopHostname = typeof window !== 'undefined' ? window.location.hostname : ''
  const laptopUsesLoopback = isLocalhostHostname(laptopHostname)

  const [resolvedOrigin, setResolvedOrigin] = useState<ResolvedPhoneOrigin>(() => ({
    origin: typeof window !== 'undefined' ? window.location.origin : '',
    warning: null,
    suggestedAddresses: [],
  }))

  const [lanProbeDone, setLanProbeDone] = useState(!laptopUsesLoopback)
  const [qrLanHost, setQrLanHost] = useState<string | null>(null)

  useEffect(() => {
    if (!laptopUsesLoopback) {
      setResolvedOrigin({
        origin: window.location.origin,
        warning: null,
        suggestedAddresses: [],
      })
      setQrLanHost(null)
      setLanProbeDone(true)
      return
    }

    let cancelled = false
    setLanProbeDone(false)

    const resolve = async () => {
      try {
        const info = await fetchHostInfo()
        if (cancelled) return

        const lanAddresses = info.lan_addresses || []
        if (lanAddresses.length > 0) {
          setResolvedOrigin({
            origin: buildOriginFromHostname(lanAddresses[0]),
            warning: null,
            suggestedAddresses: lanAddresses,
          })
          setQrLanHost(lanAddresses[0])
        } else {
          setResolvedOrigin({
            origin: window.location.origin,
            warning:
              'No LAN IPv4 found while on localhost — phones cannot reach that. Open this app at the Network URL Vite prints (your PC LAN IP on port 5173), or use a tunnel like ngrok.',
            suggestedAddresses: [],
          })
          setQrLanHost(null)
        }
      } catch {
        if (cancelled) return
        setResolvedOrigin({
          origin: window.location.origin,
          warning:
            'Could not reach /host-info (Flask on port 5000). Start the backend, then refresh — we need it to choose an IP for the QR.',
          suggestedAddresses: [],
        })
        setQrLanHost(null)
      } finally {
        if (!cancelled) setLanProbeDone(true)
      }
    }

    void resolve()
    return () => {
      cancelled = true
    }
  }, [laptopUsesLoopback])

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

  const hostnameForQr = qrLanHost ?? laptopHostname
  const mobileOrigin = buildOriginFromHostname(hostnameForQr)
  const mobileUrl = `${mobileOrigin}/mobile?code=${encodeURIComponent(code)}`
  const qrWouldUseLoopback = lanProbeDone && isLocalhostHostname(hostnameForQr)

  return (
    <div className="pairing-panel">
      <div className="pairing-header">
        <span className="pairing-label">Phone session</span>
        <span className="pairing-code">{code}</span>
      </div>

      {!lanProbeDone ? (
        <div className="pairing-status pairing-status-waiting">
          Looking up a LAN URL for this QR (calling /host-info)…
        </div>
      ) : qrWouldUseLoopback ? (
        <div className="pairing-status pairing-status-error">
          A localhost URL in the QR is not usable on your phone (localhost there means the phone, not this laptop).
          Keep using localhost in the laptop browser if you like; fix pairing by starting Flask on port 5000 and refreshing,
          or open this app directly at the Network address Vite prints (for example http://192.168.x.x:5173).
        </div>
      ) : (
        <>
          {resolvedOrigin.suggestedAddresses.length > 1 && (
            <div className="pairing-ip-row">
              <label htmlFor="pairing-ip-select">Phone should open</label>
              <select
                id="pairing-ip-select"
                className="pairing-ip-select"
                value={qrLanHost ?? resolvedOrigin.suggestedAddresses[0]}
                onChange={(event) => setQrLanHost(event.target.value)}
              >
                {resolvedOrigin.suggestedAddresses.map((ip) => (
                  <option key={ip} value={ip}>
                    {buildOriginFromHostname(ip)}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="pairing-qr-wrap">
            <QRCodeCanvas value={mobileUrl} size={180} marginSize={2} level="M" />
          </div>

          <p className="pairing-url">{mobileUrl}</p>
        </>
      )}

      <div className={`pairing-status pairing-status-${state}`}>
        {state === 'connected'
          ? `Connected — last input ${lastPayloadAt ? `${Math.max(0, Math.round((Date.now() - lastPayloadAt) / 1000))}s ago` : 'received'}`
          : 'Waiting for phone to send input...'}
      </div>

      {resolvedOrigin.warning && (
        <div className="pairing-warning">
          <strong>Note:</strong> {resolvedOrigin.warning}
        </div>
      )}

      <p className="pairing-hint">
        Laptop mode: default dev is HTTP (<code className="pairing-code-inline">npm run dev</code>) so the PC webcam works reliably.
        For Android camera/mic on your LAN IP, run <code className="pairing-code-inline">npm run dev:https</code>, or{' '}
        <code className="pairing-code-inline">.\start-dev.ps1 -DevHttps</code>. Trust the dev certificate on the laptop too if the webcam stops working there.
      </p>
    </div>
  )
}

export default SessionPairingPanel
