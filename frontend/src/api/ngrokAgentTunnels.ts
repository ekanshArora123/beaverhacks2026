/**
 * Ngrok exposes local agent REST on 127.0.0.1:4040. The browser cannot call that directly (different port → CORS),
 * so dev uses a Vite-only proxy — see vite.config.ts `__vite_dev/ngrok-agent`.
 */
const DEV_TUNNELS_PATH = '/__vite_dev/ngrok-agent/tunnels'

interface NgrokTunnelsJson {
  tunnels?: Array<{ public_url?: string; proto?: string }>
}

/** Returns https:// forwarding origin from a running ngrok agent, or null. */
export async function fetchNgrokAgentHttpsOrigin(): Promise<string | null> {
  if (!import.meta.env.DEV) {
    return null
  }
  try {
    const response = await fetch(DEV_TUNNELS_PATH, { cache: 'no-store' })
    if (!response.ok) {
      return null
    }
    const json = (await response.json()) as NgrokTunnelsJson
    const tunnels = json.tunnels ?? []
    const withUrl = tunnels.filter((t) => !!(t.public_url && /^https?:/i.test(t.public_url.trim())))
    const httpsFirst = [...withUrl].sort((a, b) => {
      const ap = (a.public_url || '').startsWith('https') ? 0 : 1
      const bp = (b.public_url || '').startsWith('https') ? 0 : 1
      return ap - bp
    })
    const pick = httpsFirst[0]
    if (!pick?.public_url) {
      return null
    }
    const parsed = new URL(pick.public_url.trim())
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null
    }
    return `${parsed.protocol}//${parsed.host}`
  } catch {
    return null
  }
}
