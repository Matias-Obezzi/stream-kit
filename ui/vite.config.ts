import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// el panel lo sirve streamkit/panel.py desde web/app; en desarrollo, la API va a una copia de prueba
const prueba = process.env.STREAMKIT_PANEL ?? 'http://127.0.0.1:8091'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  build: { outDir: '../web/app', emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: {
    proxy: Object.fromEntries(['/api', '/snap', '/piezas.js', '/emotes.js', '/plataformas.js', '/pantalla'].map(p => [p, prueba])),
  },
})
