const BACKEND_PORT = '5000'

/** Backend origin for /analyze, /session/*, /host-info, etc. */
export function getProgramApiBaseUrl(): string {
  const configured = (import.meta.env.VITE_PROGRAM_API_URL as string | undefined)?.trim()
  if (configured) {
    return configured.replace(/\/+$/, '')
  }

  // Dev: same origin — Vite proxies to Flask (see vite.config.ts). Avoid hard-coding https; default dev is HTTP.
  if (import.meta.env.DEV) {
    if (typeof window !== 'undefined' && window.location?.origin) {
      return window.location.origin
    }
    return 'http://127.0.0.1:5173'
  }

  if (typeof window !== 'undefined' && window.location?.hostname) {
    const { protocol, hostname } = window.location
    return `${protocol}//${hostname}:${BACKEND_PORT}`
  }

  return `http://127.0.0.1:${BACKEND_PORT}`
}
