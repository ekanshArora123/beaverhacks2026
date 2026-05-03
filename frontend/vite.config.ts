import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { defineConfig } from 'vite'

/** Log to the Vite server console when /mobile?tool= is accessed. */
function toolAccessLogger(): Plugin {
  return {
    name: 'tool-access-logger',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const url = req.url ?? ''
        if (url.startsWith('/mobile')) {
          const params = new URLSearchParams(url.includes('?') ? url.slice(url.indexOf('?') + 1) : '')
          const tool = params.get('tool')
          if (tool) {
            const ts = new Date().toISOString()
            server.config.logger.info(
              `\x1b[36m[tool-access]\x1b[0m ${ts}  tool=${tool}  path=${url}`,
              { timestamp: false },
            )
          }
        }
        next()
      })
    },
  }
}

const disableHmr =
  process.env.VITE_DISABLE_HMR === '1' || process.env.VITE_DISABLE_HMR === 'true'

const devHttps =
  process.env.VITE_DEV_HTTPS === '1' || process.env.VITE_DEV_HTTPS === 'true'

const backendTarget = process.env.VITE_DEV_BACKEND_TARGET || 'http://127.0.0.1:5000'

// HTTP dev rejects unknown Host headers. Tunnels terminate TLS and hit Vite over HTTP with a tunnel hostname.
// https://vite.dev/config/server-options.html#server-allowedhosts
const additionalAllowedHosts =
  process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS?.split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean) ?? []

const tunnelAllowedHosts = [
  '.ngrok-free.app',
  '.ngrok-free.dev',
  '.ngrok.app',
  '.ngrok.io',
  '.trycloudflare.com',
  '.loca.lt',
]

function flaskProxy() {
  return {
    target: backendTarget,
    changeOrigin: true,
    timeout: 180_000,
  }
}

// Default dev is HTTP so laptop webcam/mic stay reliable (localhost HTTP is a secure context).
// Use VITE_DEV_HTTPS=true (npm run dev:https) when pairing an Android phone — Chrome blocks camera on http:// LAN.
// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react(), toolAccessLogger(), ...(command === 'serve' && devHttps ? [basicSsl()] : [])],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: [...tunnelAllowedHosts, ...additionalAllowedHosts],
    ...(disableHmr ? { hmr: false } : {}),
    proxy: {
      // Browser cannot call localhost:4040 from the Vite origin (CORS). Used to auto-fill tunnel QR without .env.local.
      '/__vite_dev/ngrok-agent/tunnels': {
        target: 'http://127.0.0.1:4040',
        changeOrigin: true,
        rewrite: () => '/api/tunnels',
      },
      '/analyze': flaskProxy(),
      '/health': flaskProxy(),
      '/host-info': flaskProxy(),
      '/voice-to-text': flaskProxy(),
      '/session': flaskProxy(),
      '/prompts': flaskProxy(),
      '/set-tool': flaskProxy(),
      '/machine-folders': flaskProxy(),
    },
  },
}))
