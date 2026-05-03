import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const disableHmr =
  process.env.VITE_DISABLE_HMR === '1' || process.env.VITE_DISABLE_HMR === 'true'

const devHttps =
  process.env.VITE_DEV_HTTPS === '1' || process.env.VITE_DEV_HTTPS === 'true'

const backendTarget = process.env.VITE_DEV_BACKEND_TARGET || 'http://127.0.0.1:5000'

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
    ...(disableHmr ? { hmr: false } : {}),
    proxy: {
      '/analyze': flaskProxy(),
      '/health': flaskProxy(),
      '/host-info': flaskProxy(),
      '/voice-to-text': flaskProxy(),
      '/session': flaskProxy(),
      '/prompts': flaskProxy(),
    },
  },
}))
