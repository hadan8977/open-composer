import { defineConfig } from 'vite'
import path from 'path'
import fs from 'fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

function dashboardCatalogResolver() {
  const catalogPath = path.resolve(__dirname, '..', 'reports', 'dashboard', 'catalog.json')

  return {
    name: 'dashboard-catalog-resolver',
    resolveId(id) {
      if (id === 'virtual:dashboard-catalog') {
        return '\0virtual:dashboard-catalog'
      }
    },
    load(id) {
      if (id !== '\0virtual:dashboard-catalog') {
        return null
      }

      const emptyCatalog = {
        generated_at: null,
        source_root: path.resolve(__dirname, '..'),
        summary: {
          source_root: path.resolve(__dirname, '..'),
          generated_at: null,
          read_model_version: '1',
          notes: ['Run uv run oc dashboard catalog to build reports/dashboard/catalog.json.'],
        },
        strategies: [],
        versions: [],
        runs: [],
        signals: [],
        reviews: [],
        contexts: [],
        journals: [],
        orders: [],
        paper_positions: [],
        audits: [],
        groups: [],
        data_comparisons: [],
        feature_packets: [],
      }

      const catalog = fs.existsSync(catalogPath)
        ? fs.readFileSync(catalogPath, 'utf-8')
        : JSON.stringify(emptyCatalog)

      return `export const catalogPath = ${JSON.stringify(catalogPath)};\nexport default ${catalog};\n`
    },
    configureServer(server) {
      if (fs.existsSync(catalogPath)) {
        server.watcher.add(catalogPath)
      }
    },
  }
}

export default defineConfig({
  plugins: [
    dashboardCatalogResolver(),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
