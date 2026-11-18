import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

// The shared comparison assets stay external to the React bundle. Their
// content hash changes the immutable-cache URLs whenever either file changes.
const comparisonHash = createHash('sha256')
for (const asset of ['css/paper-comparison.css', 'js/paper-comparison.mjs']) {
  comparisonHash.update(readFileSync(path.resolve(__dirname, '../../open_composer/cockpit/static', asset)))
}
const comparisonVersion = comparisonHash.digest('hex').slice(0, 12)

// React workspace with the shared paper comparison renderer, served by FastAPI.
export default defineConfig({
  base: '/v2/',
  define: {
    __PAPER_COMPARISON_VERSION__: JSON.stringify(comparisonVersion),
  },
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
