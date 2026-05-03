import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

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
  plugins: [react(), ...(command === 'serve' && devHttps ? [basicSsl()] : [])],
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
    },
  },
}))
