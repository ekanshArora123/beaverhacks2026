/**
 * Optional HTTPS base URL for phone pairing (ngrok, Cloudflare Tunnel, etc.).
 * Set in frontend/.env.local:  VITE_PAIRING_ORIGIN=https://xxxx.ngrok-free.app
 */
export function getPairingOriginOverride(): string | null {
  const raw = (import.meta.env.VITE_PAIRING_ORIGIN as string | undefined)?.trim()
  if (!raw) {
    return null
  }

  try {
    const normalized = raw.includes('://') ? raw : `https://${raw}`
    const parsed = new URL(normalized)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null
    }
    return `${parsed.protocol}//${parsed.host}`
  } catch {
    return null
  }
}
