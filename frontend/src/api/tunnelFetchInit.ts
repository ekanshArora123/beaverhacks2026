/** ngrok free tier wraps some responses unless this header is set (helps API calls from tunnel URLs). */

const NGROK_SKIP_HEADER = 'ngrok-skip-browser-warning'

function hostnameLooksLikePublicTunnel(hostname: string): boolean {
  const h = hostname.toLowerCase()
  return (
    h.endsWith('.ngrok-free.app')
    || h.endsWith('.ngrok-free.dev')
    || h.endsWith('.ngrok.app')
    || h.endsWith('.ngrok.io')
    || h.includes('.loca.lt')
    || h.includes('.trycloudflare.com')
  )
}

/** Merge into fetch() RequestInit — no-op unless the page origin is a known tunnel host. */
export function withTunnelFetchInit(init?: RequestInit): RequestInit {
  if (
    typeof window === 'undefined'
    || !hostnameLooksLikePublicTunnel(window.location.hostname)
  ) {
    return init ? { ...init } : {}
  }
  const headers = new Headers(init?.headers ?? undefined)
  headers.set(NGROK_SKIP_HEADER, 'true')
  return { ...init, headers }
}
