import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import MobileCapturePage from './MobileCapturePage.tsx'

const isMobileRoute = window.location.pathname.replace(/\/+$/, '') === '/mobile'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isMobileRoute ? <MobileCapturePage /> : <App />}
  </StrictMode>,
)
