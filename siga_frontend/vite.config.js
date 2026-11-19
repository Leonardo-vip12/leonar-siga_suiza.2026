import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: ['html5-qrcode']
  },
  server: {
    watch: {
      usePolling: true,
    },
    host: true, // needed for docker
  },
  // Configurar proxy solo si no hay variables de Railway
  // En producción (Vercel + Railway), usamos las env vars directamente
  define: {
    'process.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL || `https://${process.env.RAILWAY_PUBLIC_DOMAIN || 'localhost'}:8000`),
    'process.env.VITE_WS_URL': JSON.stringify(process.env.VITE_WS_URL || `wss://${process.env.RAILWAY_PUBLIC_DOMAIN || 'localhost'}:8000/ws`),
  },
})
