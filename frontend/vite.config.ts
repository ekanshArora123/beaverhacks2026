import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Default Vite binds 127.0.0.1 only — phones scanning the QR (LAN IP) never connect.
    host: true,
    port: 5173,
  },
})
