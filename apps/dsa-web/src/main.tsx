import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import MoexPage from './pages/MoexPage'
import { ThemeProvider } from './components/theme/ThemeProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      {import.meta.env.VITE_MOEX_DEMO === 'true' ? <MoexPage /> : <App />}
    </ThemeProvider>
  </StrictMode>,
)
