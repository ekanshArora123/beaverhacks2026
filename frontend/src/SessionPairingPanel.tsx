import { useEffect, useMemo, useState } from 'react'
import { QRCodeCanvas } from 'qrcode.react'
import { fetchNgrokAgentHttpsOrigin } from './api/ngrokAgentTunnels'
import { fetchHostInfo } from './api/session'
import { getPairingOriginOverride } from './env/pairing'

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

function hostnameLooksLikePrivateLanIPv4(hostname: string): boolean {
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) {
    return false
  }
  const parts = hostname.split('.').map((p) => Number(p))
  const [a, b] = parts
  if (a === undefined || Number.isNaN(a)) {
    return false
  }
  if (b === undefined || Number.isNaN(b)) {
    return false
  }
  if (a === 10) {
    return true
  }
  if (a === 192 && b === 168) {
    return true
  }
  if (a === 172 && b >= 16 && b <= 31) {
    return true
  }
  return false
}

function originUsesPrivateLanIp(origin: string): boolean {
  try {
    const { hostname } = new URL(origin)
    return hostnameLooksLikePrivateLanIPv4(hostname)
  } catch {
    return false
  }
}

function SessionPairingPanel({ state, code, errorMessage, lastPayloadAt }: SessionPairingPanelProps) {
  const laptopHostname = typeof window !== 'undefined' ? window.location.hostname : ''
  const laptopUsesLoopback = isLocalhostHostname(laptopHostname)
  const envTunnelOrigin = useMemo(() => getPairingOriginOverride(), [])
  const [agentTunnelOrigin, setAgentTunnelOrigin] = useState<string | null>(null)
  const pairingTunnelOrigin = envTunnelOrigin ?? agentTunnelOrigin

  const [resolvedOrigin, setResolvedOrigin] = useState<ResolvedPhoneOrigin>(() => ({
    origin: typeof window !== 'undefined' ? window.location.origin : '',
    warning: null,
    suggestedAddresses: [],
  }))

  const [lanProbeDone, setLanProbeDone] = useState(() => !laptopUsesLoopback || !!envTunnelOrigin)
  const [qrLanHost, setQrLanHost] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    const resolve = async () => {
      if (envTunnelOrigin) {
        setAgentTunnelOrigin(null)
        setResolvedOrigin({
          origin: envTunnelOrigin,
          warning: null,
          suggestedAddresses: [],
        })
        setQrLanHost(null)
        setLanProbeDone(true)
        return
      }

      if (!laptopUsesLoopback) {
        setAgentTunnelOrigin(null)
        setResolvedOrigin({
          origin: window.location.origin,
          warning: null,
          suggestedAddresses: [],
        })
        setQrLanHost(null)
        setLanProbeDone(true)
        return
      }

      setLanProbeDone(false)

      if (import.meta.env.DEV) {
        const tunnelFromAgent = await fetchNgrokAgentHttpsOrigin()
        if (cancelled) {
          return
        }
        if (tunnelFromAgent) {
          setAgentTunnelOrigin(tunnelFromAgent)
          setResolvedOrigin({
            origin: tunnelFromAgent,
            warning: null,
            suggestedAddresses: [],
          })
          setQrLanHost(null)
          setLanProbeDone(true)
          return
        }
        setAgentTunnelOrigin(null)
      }

      try {
        const info = await fetchHostInfo()
        if (cancelled) {
          return
        }

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
              'No LAN IPv4 found while on localhost — phones cannot reach that. Open this app at the Network URL Vite prints (your PC LAN IP on port 5173), or use ngrok.',
            suggestedAddresses: [],
          })
          setQrLanHost(null)
        }
      } catch {
        if (cancelled) {
          return
        }
        setResolvedOrigin({
          origin: window.location.origin,
          warning:
            'Could not reach /host-info (Flask on port 5000). Start the backend, then refresh — we need it to choose an IP for the QR.',
          suggestedAddresses: [],
        })
        setQrLanHost(null)
      } finally {
        if (!cancelled) {
          setLanProbeDone(true)
        }
      }
    }

    void resolve()
    return () => {
      cancelled = true
    }
  }, [laptopUsesLoopback, envTunnelOrigin])

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
  const mobileOrigin = pairingTunnelOrigin ?? buildOriginFromHostname(hostnameForQr)
  const mobileUrl = `${mobileOrigin}/mobile?code=${encodeURIComponent(code)}`
  const qrWouldUseLoopback =
    !pairingTunnelOrigin && lanProbeDone && isLocalhostHostname(hostnameForQr)
  const qrLooksLikeBlockedCampusLan =
    lanProbeDone && !pairingTunnelOrigin && !qrWouldUseLoopback && originUsesPrivateLanIp(mobileOrigin)

  return (
    <div className="pairing-panel">
      <div className="pairing-header">
        <span className="pairing-label">Phone session</span>
        <span className="pairing-code">{code}</span>
      </div>

      {pairingTunnelOrigin && (
        <div className="pairing-status pairing-status-connected">
          QR uses an <strong>HTTPS tunnel</strong> (works on eduroam — phone talks to the internet, not your laptop LAN). Keep{' '}
          <code className="pairing-code-inline">ngrok http 5173</code> running.{' '}
          {envTunnelOrigin ? (
            <>Origin from <code className="pairing-code-inline">VITE_PAIRING_ORIGIN</code>.</>
          ) : (
            <>Auto-detected from the ngrok agent on this PC (localhost:4040). Set <code className="pairing-code-inline">VITE_PAIRING_ORIGIN</code> to override.</>
          )}{' '}
          On <strong>ngrok free</strong>, the phone may show a warning first — tap <strong>Visit Site</strong>.
        </div>
      )}

      {qrLooksLikeBlockedCampusLan && (
        <div className="pairing-warning">
          <strong>Eduroam / many campus networks</strong> block your phone from opening a private LAN IP like this QR
          (client isolation). Use a tunnel so the QR starts with <code className="pairing-code-inline">https://</code> and a
          public hostname — run <code className="pairing-code-inline">.\start-dev-ngrok.ps1</code>, wait for the QR to update, then scan again.
        </div>
      )}

      {!lanProbeDone ? (
        <div className="pairing-status pairing-status-waiting">
          Resolving pairing URL for this QR (ngrok agent on this PC, then LAN via /host-info)...
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
        <strong>Eduroam / phone pairing:</strong> run <code className="pairing-code-inline">.\start-dev-ngrok.ps1</code> so ngrok is up; the pairing QR
        should show an <code className="pairing-code-inline">https://</code> link (auto-read from ngrok, or set{' '}
        <code className="pairing-code-inline">VITE_PAIRING_ORIGIN</code> in <code className="pairing-code-inline">frontend/.env.local</code> — see{' '}
        <code className="pairing-code-inline">frontend/.env.example</code>). LAN-only QR codes usually fail on campus Wi-Fi. On the phone, tap{' '}
        <strong>Visit Site</strong> if ngrok shows a warning, then turn on camera when asked.
      </p>
    </div>
  )
}

export default SessionPairingPanel
