import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const quietProxyAbort = (err) => {
  if (['ECONNRESET', 'ECONNABORTED', 'EPIPE'].includes(err?.code)) return;
  console.warn('[vite proxy]', err?.message ?? err);
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@cv': path.resolve(__dirname, '../cv'),
    },
  },
  server: {
    port: 3000,
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('error', quietProxyAbort);
        },
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', quietProxyAbort);
        },
      },
    },
  },
});
