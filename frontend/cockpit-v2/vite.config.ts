import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Cockpit v2: the Figma Make export, trimmed to the two plugins it actually
// needs. Built once (`pnpm build`) into the FastAPI static tree and served at
// /v2/ by `open_composer.cockpit.app`; no node runtime on the server.
export default defineConfig({
  base: '/v2/',
  build: {
    outDir: path.resolve(__dirname, '../../open_composer/cockpit/static/v2'),
    emptyOutDir: true,
    sourcemap: false,
    minify: true,
    target: 'es2020',
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Dev only: the JSON API and the agent SSE stream come from the cockpit.
    proxy: {
      '/api': 'http://127.0.0.1:8770',
      '/agents': 'http://127.0.0.1:8770',
    },
  },
})
