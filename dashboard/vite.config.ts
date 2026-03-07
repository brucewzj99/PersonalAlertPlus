import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const configuredBackendUrl = env.BACKEND_API_URL || 'http://127.0.0.1:8000'

  let backendOrigin = configuredBackendUrl
  try {
    backendOrigin = new URL(configuredBackendUrl).origin
  } catch {
    console.warn(
      `Invalid BACKEND_API_URL: ${configuredBackendUrl}. Falling back to http://127.0.0.1:8000`
    )
    backendOrigin = 'http://127.0.0.1:8000'
  }

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: backendOrigin,
          changeOrigin: true,
          secure: false,
          headers: {
            'ngrok-skip-browser-warning': 'true',
          },
        },
      },
    },
  }
})
